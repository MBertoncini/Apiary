import logging
import uuid
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse

from .models import (
    Apiario, Arnia, ControlloArnia, Regina, Fioritura,
    TrattamentoSanitario, TipoTrattamento, Melario, Smielatura,
    Gruppo, MembroGruppo, InvitoGruppo, DatiMeteo, PrevisioneMeteo,
    Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura,
    Invasettamento, Cliente, Vendita, DettaglioVendita
)

from .serializers import (
    ApiarioSerializer, ArniaSerializer, ControlloArniaDetailSerializer,
    ControlloArniaListSerializer, ReginaSerializer, FiorituraSerializer,
    TrattamentoSanitarioSerializer, TipoTrattamentoSerializer,
    MelarioSerializer, SmielaturaSerializer, GruppoSerializer,
    MembroGruppoSerializer, InvitoGruppoSerializer, UserSerializer,
    PagamentoSerializer, QuotaUtenteSerializer,
    AttrezzaturaSerializer, SpesaAttrezzaturaSerializer,
    ManutenzioneAttrezzaturaSerializer,
    InvasettamentoSerializer, ClienteSerializer, VenditaSerializer,
    DettaglioVenditaSerializer
)

logger = logging.getLogger(__name__)


# --- Helper: queryset apiari accessibili (FIX #10 - DRY) ---
def get_apiari_accessibili(user):
    """
    Restituisce il queryset degli apiari accessibili a un utente:
    - apiari di cui è proprietario
    - apiari condivisi con i gruppi di cui è membro
    """
    apiari_propri = Apiario.objects.filter(proprietario=user)
    gruppi_utente = Gruppo.objects.filter(membri=user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente,
        condiviso_con_gruppo=True
    ).exclude(proprietario=user)
    return (apiari_propri | apiari_condivisi).distinct()


def get_gruppi_utente(user):
    """Restituisce i gruppi di cui l'utente è membro."""
    return Gruppo.objects.filter(membri=user)


# --- Permessi personalizzati ---

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permesso che consente solo al proprietario di un oggetto di modificarlo.
    """
    def has_object_permission(self, request, view, obj):
        # Permessi di lettura sono consentiti a tutti
        if request.method in permissions.SAFE_METHODS:
            return True

        # Controllo se l'oggetto ha un attributo proprietario
        if hasattr(obj, 'proprietario'):
            return obj.proprietario == request.user
        elif hasattr(obj, 'utente'):
            return obj.utente == request.user
        elif hasattr(obj, 'creatore'):
            return obj.creatore == request.user

        return False


class IsOwnerOrGroupRole(permissions.BasePermission):
    """
    FIX #3 - Permesso basato sul ruolo nel gruppo.
    - Il proprietario della risorsa può sempre modificare.
    - I membri del gruppo con ruolo 'admin' o 'editor' possono modificare risorse condivise.
    - I 'viewer' possono solo leggere (SAFE_METHODS).
    - Utenti non proprietari e non in un gruppo non possono modificare.
    """
    def has_object_permission(self, request, view, obj):
        user = request.user

        # Permessi di lettura sono sempre consentiti (il queryset già filtra la visibilità)
        if request.method in permissions.SAFE_METHODS:
            return True

        # Il proprietario/utente/creatore può sempre modificare
        if hasattr(obj, 'proprietario') and obj.proprietario == user:
            return True
        if hasattr(obj, 'utente') and obj.utente == user:
            return True
        if hasattr(obj, 'creatore') and obj.creatore == user:
            return True

        # Per risorse condivise, controlla il ruolo nel gruppo
        # Risorse legate a un apiario (Arnia -> apiario, ControlloArnia -> arnia -> apiario, etc.)
        apiario = None
        gruppo = None

        if hasattr(obj, 'apiario') and obj.apiario:
            apiario = obj.apiario
        elif hasattr(obj, 'arnia') and obj.arnia and hasattr(obj.arnia, 'apiario'):
            apiario = obj.arnia.apiario
        elif hasattr(obj, 'attrezzatura') and obj.attrezzatura:
            # Per manutenzioni di attrezzature condivise
            if obj.attrezzatura.condiviso_con_gruppo and obj.attrezzatura.gruppo:
                gruppo = obj.attrezzatura.gruppo

        if apiario and apiario.condiviso_con_gruppo and apiario.gruppo:
            gruppo = apiario.gruppo

        # Se l'oggetto stesso ha un campo gruppo diretto (Pagamento, SpesaAttrezzatura, etc.)
        if gruppo is None and hasattr(obj, 'gruppo') and obj.gruppo:
            gruppo = obj.gruppo

        if gruppo:
            try:
                membro = MembroGruppo.objects.get(utente=user, gruppo=gruppo)
                return membro.ruolo in ['admin', 'editor']
            except MembroGruppo.DoesNotExist:
                return False

        return False

class ApiarioViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire gli apiari.
    """
    serializer_class = ApiarioSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nome', 'posizione']

    def get_queryset(self):
        """
        Filtra gli apiari in base all'utente autenticato.
        Restituisce gli apiari di cui l'utente è proprietario o
        che sono condivisi con i gruppi di cui l'utente è membro.
        """
        return get_apiari_accessibili(self.request.user)
    
    @action(detail=True, methods=['get'])
    def arnie(self, request, pk=None):
        """
        Restituisce tutte le arnie associate a un apiario.
        """
        apiario = self.get_object()
        arnie = Arnia.objects.filter(apiario=apiario)
        serializer = ArniaSerializer(arnie, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def controlli(self, request, pk=None):
        """
        Restituisce i controlli recenti delle arnie di un apiario.
        """
        apiario = self.get_object()
        # Recupera i controlli degli ultimi 30 giorni (default)
        days = request.query_params.get('days', 30)
        try:
            days = int(days)
        except ValueError:
            days = 30
            
        since_date = timezone.now() - timedelta(days=days)
        
        # Recupera tutte le arnie dell'apiario
        arnie = Arnia.objects.filter(apiario=apiario)
        arnie_ids = [arnia.id for arnia in arnie]
        
        # Recupera i controlli recenti per queste arnie
        controlli = ControlloArnia.objects.filter(
            arnia__in=arnie_ids,
            data__gte=since_date
        ).order_by('-data')
        
        serializer = ControlloArniaListSerializer(controlli, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def meteo(self, request, pk=None):
        """
        Restituisce i dati meteo recenti di un apiario.
        """
        apiario = self.get_object()
        # Ultimi dati meteo (default ultime 24 ore)
        hours = request.query_params.get('hours', 24)
        try:
            hours = int(hours)
        except ValueError:
            hours = 24
            
        since_date = timezone.now() - timedelta(hours=hours)
        
        # Recupera i dati meteo più recenti
        dati_meteo = DatiMeteo.objects.filter(
            apiario=apiario,
            data__gte=since_date
        ).order_by('-data')
        
        # Serializzatore semplice per i dati meteo
        data = [{
            'data': dm.data,
            'temperatura': dm.temperatura,
            'umidita': dm.umidita,
            'pressione': dm.pressione,
            'velocita_vento': dm.velocita_vento,
            'direzione_vento': dm.direzione_vento,
            'descrizione': dm.descrizione,
            'icona': dm.icona,
            'pioggia': dm.pioggia
        } for dm in dati_meteo]
        
        return Response(data)
    
    @action(detail=True, methods=['get'])
    def previsioni(self, request, pk=None):
        """
        Restituisce le previsioni meteo per un apiario.
        """
        apiario = self.get_object()
        
        # Recupera le previsioni future
        previsioni = PrevisioneMeteo.objects.filter(
            apiario=apiario,
            data_riferimento__gte=timezone.now()
        ).order_by('data_riferimento')
        
        # Serializzatore semplice per le previsioni
        data = [{
            'data_previsione': p.data_previsione,
            'data_riferimento': p.data_riferimento,
            'temperatura': p.temperatura,
            'temperatura_min': p.temperatura_min,
            'temperatura_max': p.temperatura_max,
            'umidita': p.umidita,
            'pressione': p.pressione,
            'velocita_vento': p.velocita_vento,
            'direzione_vento': p.direzione_vento,
            'probabilita_pioggia': p.probabilita_pioggia,
            'descrizione': p.descrizione,
            'icona': p.icona
        } for p in previsioni]
        
        return Response(data)

    # Aggiungi alla classe ApiarioViewSet
    @action(detail=True, methods=['put'])
    def condivisione(self, request, pk=None):
        """
        Gestisce la condivisione dell'apiario con un gruppo.
        """
        apiario = self.get_object()
        
        # Verifica che l'utente sia il proprietario dell'apiario
        if apiario.proprietario != request.user:
            return Response(
                {"detail": "Solo il proprietario può modificare le impostazioni di condivisione."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Ottieni i dati dalla richiesta
        gruppo_id = request.data.get('gruppo')
        condiviso = request.data.get('condiviso_con_gruppo', False)
        
        # Verifica gruppo
        if gruppo_id:
            try:
                gruppo = Gruppo.objects.get(pk=gruppo_id)
                
                # Verifica che l'utente sia membro del gruppo
                if not MembroGruppo.objects.filter(utente=request.user, gruppo=gruppo).exists():
                    return Response(
                        {"detail": "Non sei membro di questo gruppo."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Aggiorna l'apiario
                apiario.gruppo = gruppo
                apiario.condiviso_con_gruppo = condiviso
                apiario.save()
            except Gruppo.DoesNotExist:
                return Response(
                    {"detail": "Gruppo non trovato."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Rimuovi condivisione
            apiario.gruppo = None
            apiario.condiviso_con_gruppo = False
            apiario.save()
        
        serializer = self.get_serializer(apiario)
        return Response(serializer.data)


# Funzione helper per inviare email di invito (a livello di modulo, non dentro una classe)
def invia_email_invito(invito):
    """Funzione per inviare email di invito"""
    subject = f"Invito a unirti al gruppo {invito.gruppo.nome} su Gestione Apiario"

    # Costruisci l'URL per accettare l'invito
    accept_url = reverse('api-attiva-invito', kwargs={'token': invito.token})

    # Contesto per il template
    context = {
        'invito': invito,
        'accept_url': accept_url,
    }

    # Renderizza l'HTML dell'email
    html_message = render_to_string('email/invito_gruppo.html', context)
    plain_message = strip_tags(html_message)

    # Invia l'email
    send_mail(
        subject,
        plain_message,
        'noreply@gestioneapiario.it',  # Indirizzo mittente
        [invito.email],
        html_message=html_message,
        fail_silently=False,
    )


class ArniaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le arnie.
    """
    serializer_class = ArniaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['numero', 'apiario__nome']

    def get_queryset(self):
        """
        Filtra le arnie in base agli apiari accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        return Arnia.objects.filter(apiario__in=apiari_accessibili)
    
    @action(detail=True, methods=['get'])
    def controlli(self, request, pk=None):
        """
        Restituisce i controlli di un'arnia specifica.
        """
        arnia = self.get_object()
        # Filtro opzionale per periodo di tempo
        days = request.query_params.get('days', 90)  # Default: ultimi 90 giorni
        try:
            days = int(days)
        except ValueError:
            days = 90
            
        since_date = timezone.now() - timedelta(days=days)
        
        controlli = ControlloArnia.objects.filter(
            arnia=arnia,
            data__gte=since_date
        ).order_by('-data')
        
        serializer = ControlloArniaDetailSerializer(controlli, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def regina(self, request, pk=None):
        """
        Restituisce i dati della regina associata all'arnia.
        """
        arnia = self.get_object()
        try:
            regina = Regina.objects.get(arnia=arnia)
            serializer = ReginaSerializer(regina)
            return Response(serializer.data)
        except Regina.DoesNotExist:
            return Response(
                {"detail": "Nessuna regina associata a questa arnia."},
                status=status.HTTP_404_NOT_FOUND
            )

class ControlloArniaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i controlli delle arnie.
    """
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['arnia__numero', 'arnia__apiario__nome']

    def get_serializer_class(self):
        if self.action == 'list':
            return ControlloArniaListSerializer
        return ControlloArniaDetailSerializer

    def get_queryset(self):
        """
        Filtra i controlli in base alle arnie accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        return ControlloArnia.objects.filter(arnia__in=arnie_accessibili)

class ReginaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le regine.
    """
    serializer_class = ReginaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['arnia__numero', 'arnia__apiario__nome', 'razza']

    def get_queryset(self):
        """
        Filtra le regine in base alle arnie accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        return Regina.objects.filter(arnia__in=arnie_accessibili)

class FiorituraViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le fioriture.
    """
    serializer_class = FiorituraSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['pianta', 'apiario__nome']

    def get_queryset(self):
        """
        Filtra le fioriture in base agli apiari accessibili all'utente.
        """
        user = self.request.user
        apiari_accessibili = get_apiari_accessibili(user)
        # Fioriture degli apiari accessibili + fioriture senza apiario create dall'utente
        return (
            Fioritura.objects.filter(apiario__in=apiari_accessibili) |
            Fioritura.objects.filter(apiario__isnull=True, creatore=user)
        ).distinct()
    
    @action(detail=False, methods=['get'])
    def attive(self, request):
        """
        Restituisce solo le fioriture attive (in corso).
        """
        oggi = timezone.now().date()
        
        fioriture = self.get_queryset().filter(
            data_inizio__lte=oggi
        ).filter(
            Q(data_fine__isnull=True) | Q(data_fine__gte=oggi)
        )
        
        serializer = self.get_serializer(fioriture, many=True)
        return Response(serializer.data)

class TrattamentoSanitarioViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i trattamenti sanitari.
    """
    serializer_class = TrattamentoSanitarioSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['apiario__nome', 'tipo_trattamento__nome', 'stato']

    def get_queryset(self):
        """
        Filtra i trattamenti in base agli apiari accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        return TrattamentoSanitario.objects.filter(apiario__in=apiari_accessibili)
    
    @action(detail=False, methods=['get'])
    def attivi(self, request):
        """
        Restituisce solo i trattamenti attivi (in corso o programmati).
        """
        trattamenti = self.get_queryset().filter(
            Q(stato='programmato') | Q(stato='in_corso')
        )
        
        serializer = self.get_serializer(trattamenti, many=True)
        return Response(serializer.data)

class TipoTrattamentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i tipi di trattamento.
    """
    queryset = TipoTrattamento.objects.all()
    serializer_class = TipoTrattamentoSerializer
    permission_classes = [permissions.IsAuthenticated]

class MelarioViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i melari.
    """
    serializer_class = MelarioSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ['arnia__numero', 'arnia__apiario__nome', 'stato']

    def get_queryset(self):
        """
        Filtra i melari in base alle arnie accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        return Melario.objects.filter(arnia__in=arnie_accessibili)

class SmielaturaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le smielature.
    """
    serializer_class = SmielaturaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['apiario__nome', 'tipo_miele']
    ordering_fields = ['data', 'quantita_miele']
    ordering = ['-data']  # Ordinamento predefinito

    def get_queryset(self):
        """
        Filtra le smielature in base agli apiari accessibili all'utente.
        """
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        return Smielatura.objects.filter(apiario__in=apiari_accessibili)

# Modifica il GruppoViewSet esistente aggiungendo le nuove azioni
class GruppoViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i gruppi.
    """
    serializer_class = GruppoSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nome', 'descrizione']

    def get_queryset(self):
        """
        Restituisce i gruppi di cui l'utente è membro.
        """
        user = self.request.user
        return Gruppo.objects.filter(membri=user)

    def perform_create(self, serializer):
        """
        FIX #2 - Auto-aggiunge il creatore come membro admin del gruppo.
        Allinea il comportamento API con le web views (views.py gestione_gruppi).
        """
        gruppo = serializer.save(creatore=self.request.user)
        MembroGruppo.objects.create(
            utente=self.request.user,
            gruppo=gruppo,
            ruolo='admin'
        )

    def destroy(self, request, *args, **kwargs):
        """
        FIX #8 - Solo il creatore del gruppo può eliminarlo via API.
        Allinea il comportamento API con il Flutter UI (che mostra il
        bottone delete solo al creatore) e le web views.
        """
        gruppo = self.get_object()
        if gruppo.creatore != request.user:
            return Response(
                {"detail": "Solo il creatore del gruppo può eliminarlo."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'])
    def membri(self, request, pk=None):
        """
        Restituisce i membri di un gruppo.
        FIX #6 - Verifica che l'utente sia membro del gruppo.
        """
        gruppo = self.get_object()
        # Il queryset già filtra per membri, ma verifica esplicitamente
        if not MembroGruppo.objects.filter(utente=request.user, gruppo=gruppo).exists():
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        membri = MembroGruppo.objects.filter(gruppo=gruppo)
        serializer = MembroGruppoSerializer(membri, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def inviti(self, request, pk=None):
        """
        Restituisce gli inviti attivi per un gruppo.
        """
        gruppo = self.get_object()
        
        # Verifica che l'utente sia admin del gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo != 'admin':
                return Response(
                    {"detail": "Solo gli amministratori possono vedere gli inviti."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        inviti = InvitoGruppo.objects.filter(
            gruppo=gruppo,
            stato='inviato',
            data_scadenza__gte=timezone.now()
        )
        
        serializer = InvitoGruppoSerializer(inviti, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def invita(self, request, pk=None):
        """
        Crea un nuovo invito per il gruppo.
        """
        gruppo = self.get_object()
        
        # Verifica che l'utente sia admin del gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo != 'admin':
                return Response(
                    {"detail": "Solo gli amministratori possono inviare inviti."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Validazione dati
        email = request.data.get('email')
        ruolo_proposto = request.data.get('ruolo_proposto', 'viewer')
        
        if not email:
            return Response(
                {"detail": "Email non specificata."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verifica che non esista già un invito attivo
        invito_esistente = InvitoGruppo.objects.filter(
            email=email,
            gruppo=gruppo,
            stato='inviato',
            data_scadenza__gte=timezone.now()
        ).exists()
        
        if invito_esistente:
            return Response(
                {"detail": "Esiste già un invito attivo per questa email."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Crea il nuovo invito
        invito = InvitoGruppo(
            gruppo=gruppo,
            email=email,
            ruolo_proposto=ruolo_proposto,
            invitato_da=request.user,
            token=uuid.uuid4(),
            data_scadenza=timezone.now() + timedelta(days=7)
        )
        invito.save()
        
        # FIX #12 - Invia email di invito con logging errori
        try:
            invia_email_invito(invito)
        except Exception as e:
            # Non fallire se l'email non può essere inviata, ma logga l'errore
            logger.error(f"Errore invio email invito a {email} per gruppo {gruppo.nome}: {e}")
        
        serializer = InvitoGruppoSerializer(invito)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_path='inviti/(?P<invito_id>[^/.]+)')
    def annulla_invito(self, request, pk=None, invito_id=None):
        """
        Annulla un invito esistente.
        """
        gruppo = self.get_object()
        
        # Verifica che l'utente sia admin del gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo != 'admin':
                return Response(
                    {"detail": "Solo gli amministratori possono annullare gli inviti."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Ottieni l'invito specifico
        try:
            invito = InvitoGruppo.objects.get(pk=invito_id, gruppo=gruppo)
        except InvitoGruppo.DoesNotExist:
            return Response(
                {"detail": "Invito non trovato."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Aggiorna lo stato dell'invito
        invito.stato = 'scaduto'
        invito.save()
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['put', 'delete'], url_path='membri/(?P<membro_id>[^/.]+)')
    def gestisci_membro(self, request, pk=None, membro_id=None):
        """
        Gestione di un membro del gruppo (modifica ruolo o rimozione).
        """
        gruppo = self.get_object()
        
        # Verifica che l'utente sia admin del gruppo o stia gestendo se stesso
        try:
            membro_richiedente = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            is_admin = membro_richiedente.ruolo == 'admin'
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Ottieni il membro specifico
        try:
            membro = MembroGruppo.objects.get(pk=membro_id, gruppo=gruppo)
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Membro non trovato."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        is_self_operation = membro.utente == request.user
        
        # Non permettere la modifica del ruolo del creatore del gruppo
        if membro.utente == gruppo.creatore and membro.ruolo == 'admin' and not is_self_operation:
            return Response(
                {"detail": "Non puoi modificare il ruolo del creatore del gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Gestione PUT (aggiornamento ruolo)
        if request.method == 'PUT':
            # FIX #1 - Solo gli admin possono modificare i ruoli.
            # Le self-operation sono permesse solo per auto-demotarsi (non auto-promuoversi).
            if not is_admin and not is_self_operation:
                return Response(
                    {"detail": "Solo gli amministratori possono modificare i ruoli altrui."},
                    status=status.HTTP_403_FORBIDDEN
                )

            ruolo = request.data.get('ruolo')
            if not ruolo:
                return Response(
                    {"detail": "Ruolo non specificato."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Valida che il ruolo sia tra quelli consentiti
            ruoli_validi = [r[0] for r in MembroGruppo.RUOLO_CHOICES]
            if ruolo not in ruoli_validi:
                return Response(
                    {"detail": f"Ruolo non valido. Ruoli consentiti: {', '.join(ruoli_validi)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # FIX #1 - Prevenzione privilege escalation:
            # Un non-admin non può auto-promuoversi
            if is_self_operation and not is_admin:
                ruoli_ordine = {'viewer': 0, 'editor': 1, 'admin': 2}
                ruolo_attuale = ruoli_ordine.get(membro.ruolo, 0)
                ruolo_nuovo = ruoli_ordine.get(ruolo, 0)
                if ruolo_nuovo > ruolo_attuale:
                    return Response(
                        {"detail": "Non puoi auto-promuoverti a un ruolo superiore."},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # Aggiorna il ruolo del membro
            membro.ruolo = ruolo
            membro.save()

            serializer = MembroGruppoSerializer(membro)
            return Response(serializer.data)
        
        # Gestione DELETE (rimozione membro)
        elif request.method == 'DELETE':
            if not (is_admin or is_self_operation):
                return Response(
                    {"detail": "Solo gli amministratori possono rimuovere membri dal gruppo."},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Se è l'ultimo amministratore e si sta rimuovendo
            if is_self_operation and membro.ruolo == 'admin':
                admin_count = MembroGruppo.objects.filter(gruppo=gruppo, ruolo='admin').count()
                if admin_count <= 1:
                    # Trova un altro membro da promuovere ad admin
                    altro_membro = MembroGruppo.objects.filter(gruppo=gruppo).exclude(utente=request.user).first()
                    if altro_membro:
                        altro_membro.ruolo = 'admin'
                        altro_membro.save()
                    else:
                        # Se non ci sono altri membri, elimina il gruppo
                        gruppo.delete()
                        return Response(
                            {"detail": "Gruppo eliminato perché non ha più membri."},
                            status=status.HTTP_204_NO_CONTENT
                        )
            
            # Rimuovi il membro
            membro.delete()
            
            return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['get'])
    def apiari(self, request, pk=None):
        """
        Restituisce gli apiari condivisi con il gruppo.
        """
        gruppo = self.get_object()
        
        # Verifica che l'utente sia membro del gruppo
        try:
            MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        except MembroGruppo.DoesNotExist:
            return Response(
                {"detail": "Non sei membro di questo gruppo."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Ottieni gli apiari condivisi con il gruppo
        apiari = Apiario.objects.filter(
            gruppo=gruppo,
            condiviso_con_gruppo=True
        )
        
        serializer = ApiarioSerializer(apiari, many=True)
        return Response(serializer.data)

class PagamentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i pagamenti.
    """
    serializer_class = PagamentoSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['descrizione', 'utente__username']
    ordering_fields = ['data', 'importo']
    ordering = ['-data']  # Ordinamento predefinito per data decrescente

    def get_queryset(self):
        """
        Filtra i pagamenti in base all'utente autenticato e ai gruppi.
        """
        user = self.request.user
        pagamenti_propri = Pagamento.objects.filter(utente=user)
        gruppi_utente = get_gruppi_utente(user)
        pagamenti_gruppo = Pagamento.objects.filter(
            gruppo__in=gruppi_utente
        ).exclude(utente=user)
        return (pagamenti_propri | pagamenti_gruppo).distinct()
    
    def perform_create(self, serializer):
        """Aggiungi automaticamente l'utente corrente come proprietario"""
        serializer.save(utente=self.request.user)

class QuotaUtenteViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le quote utente.
    """
    serializer_class = QuotaUtenteSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    
    def get_queryset(self):
        """
        Filtra le quote in base all'utente autenticato e ai gruppi.
        """
        user = self.request.user
        
        # Quote dell'utente
        quote_proprie = QuotaUtente.objects.filter(utente=user)
        
        # Quote dei gruppi di cui l'utente è admin
        gruppi_admin = Gruppo.objects.filter(
            membri=user,
            membrogruppo__ruolo='admin'
        )
        quote_gruppo = QuotaUtente.objects.filter(
            gruppo__in=gruppi_admin
        )
        
        return (quote_proprie | quote_gruppo).distinct()
    
    def perform_create(self, serializer):
        """Validazione aggiuntiva prima del salvataggio"""
        # Verifica che la percentuale sia valida (0-100)
        percentuale = serializer.validated_data.get('percentuale', 0)
        if percentuale < 0 or percentuale > 100:
            raise ValidationError({"percentuale": "La percentuale deve essere compresa tra 0 e 100"})
        
        # Se c'è un gruppo, verifica che l'utente sia admin
        gruppo = serializer.validated_data.get('gruppo')
        if gruppo:
            is_admin = MembroGruppo.objects.filter(
                utente=self.request.user,
                gruppo=gruppo,
                ruolo='admin'
            ).exists()
            
            if not is_admin:
                raise ValidationError({"gruppo": "Puoi gestire le quote solo per i gruppi di cui sei amministratore"})
        
        serializer.save()


class AttrezzaturaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le attrezzature.
    """
    serializer_class = AttrezzaturaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nome', 'descrizione', 'marca', 'modello']
    ordering_fields = ['nome', 'data_acquisto', 'prezzo_acquisto', 'stato']
    ordering = ['nome']

    def get_queryset(self):
        user = self.request.user
        proprie = Attrezzatura.objects.filter(proprietario=user)
        gruppi_utente = get_gruppi_utente(user)
        condivise = Attrezzatura.objects.filter(
            condiviso_con_gruppo=True,
            gruppo__in=gruppi_utente
        ).exclude(proprietario=user)
        return (proprie | condivise).distinct()

    def perform_create(self, serializer):
        serializer.save(proprietario=self.request.user)


class SpesaAttrezzaturaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le spese attrezzatura.
    """
    serializer_class = SpesaAttrezzaturaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['descrizione', 'tipo']
    ordering_fields = ['data', 'importo']
    ordering = ['-data']

    def get_queryset(self):
        user = self.request.user
        proprie = SpesaAttrezzatura.objects.filter(utente=user)
        gruppi_utente = get_gruppi_utente(user)
        di_gruppo = SpesaAttrezzatura.objects.filter(
            gruppo__in=gruppi_utente
        ).exclude(utente=user)
        return (proprie | di_gruppo).distinct()

    def perform_create(self, serializer):
        serializer.save(utente=self.request.user)


class ManutenzioneAttrezzaturaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le manutenzioni attrezzatura.
    """
    serializer_class = ManutenzioneAttrezzaturaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['descrizione', 'tipo', 'eseguito_da']
    ordering_fields = ['data_programmata', 'data_esecuzione', 'costo']
    ordering = ['-data_programmata']

    def get_queryset(self):
        user = self.request.user
        proprie = ManutenzioneAttrezzatura.objects.filter(
            attrezzatura__proprietario=user
        )
        gruppi_utente = get_gruppi_utente(user)
        condivise = ManutenzioneAttrezzatura.objects.filter(
            attrezzatura__condiviso_con_gruppo=True,
            attrezzatura__gruppo__in=gruppi_utente
        ).exclude(attrezzatura__proprietario=user)
        return (proprie | condivise).distinct()

    def perform_create(self, serializer):
        serializer.save(utente=self.request.user)


class InvasettamentoViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire gli invasettamenti.
    """
    serializer_class = InvasettamentoSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrGroupRole]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['tipo_miele', 'lotto']
    ordering_fields = ['data', 'numero_vasetti']
    ordering = ['-data']

    def get_queryset(self):
        apiari_accessibili = get_apiari_accessibili(self.request.user)
        return Invasettamento.objects.filter(
            smielatura__apiario__in=apiari_accessibili
        )

    def perform_create(self, serializer):
        serializer.save(utente=self.request.user)


class ClienteViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire i clienti.
    """
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nome', 'email', 'telefono']
    ordering_fields = ['nome']
    ordering = ['nome']

    def get_queryset(self):
        return Cliente.objects.filter(utente=self.request.user)

    def perform_create(self, serializer):
        serializer.save(utente=self.request.user)


class VenditaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le vendite.
    """
    serializer_class = VenditaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['cliente__nome', 'note']
    ordering_fields = ['data']
    ordering = ['-data']

    def get_queryset(self):
        return Vendita.objects.filter(utente=self.request.user)

    def perform_create(self, serializer):
        serializer.save(utente=self.request.user)

    @action(detail=True, methods=['post'])
    def aggiungi_dettaglio(self, request, pk=None):
        """Aggiunge un dettaglio alla vendita."""
        vendita = self.get_object()
        serializer = DettaglioVenditaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(vendita=vendita)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['delete'], url_path='dettaglio/(?P<dettaglio_id>[^/.]+)')
    def rimuovi_dettaglio(self, request, pk=None, dettaglio_id=None):
        """Rimuove un dettaglio dalla vendita."""
        vendita = self.get_object()
        try:
            dettaglio = DettaglioVendita.objects.get(pk=dettaglio_id, vendita=vendita)
            dettaglio.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except DettaglioVendita.DoesNotExist:
            return Response(
                {"detail": "Dettaglio non trovato."},
                status=status.HTTP_404_NOT_FOUND
            )


from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer che aggiunge informazioni dell'utente
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Aggiungi dati personalizzati al token
        token['username'] = user.username
        token['email'] = user.email
        return token

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token view per gestire meglio gli errori
    """
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except Exception as e:
            # Log dell'errore per il debug
            import traceback
            print(f"Error in token endpoint: {str(e)}")
            print(traceback.format_exc())
            
            # Restituisci una risposta più utile
            return Response(
                {"detail": "Si è verificato un errore durante l'autenticazione. Riprova più tardi."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Custom token refresh serializer
    """
    def validate(self, attrs):
        try:
            return super().validate(attrs)
        except TokenError as e:
            # Gestisci in modo specifico gli errori di token
            raise InvalidToken(str(e))

class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view per gestire meglio gli errori
    """
    serializer_class = CustomTokenRefreshSerializer
    
    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except Exception as e:
            # Log dell'errore per il debug
            import traceback
            print(f"Error in token refresh endpoint: {str(e)}")
            print(traceback.format_exc())
            
            # Restituisci una risposta più utile
            return Response(
                {"detail": "Si è verificato un errore durante il refresh del token. Effettua nuovamente il login."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Endpoint per la sincronizzazione
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sync_data(request):
    """
    Endpoint per sincronizzare i dati dell'app mobile.
    Restituisce i dati accessibili all'utente.
    """
    try:
        # Timestamp ultima sincronizzazione
        last_sync = request.query_params.get('last_sync', None)
        if last_sync:
            try:
                last_sync_date = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
            except ValueError:
                return Response(
                    {"detail": "Formato timestamp non valido. Usa ISO 8601 (YYYY-MM-DDTHH:MM:SS.sssZ)."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Se non specificato, imposta una data passata (7 giorni fa)
            last_sync_date = timezone.now() - timedelta(days=7)

        # FIX #10 - Usa helper centralizzato per apiari accessibili
        user = request.user
        apiari_accessibili = get_apiari_accessibili(user)
        gruppi_utente = get_gruppi_utente(user)

        # Recupera i dati accessibili all'utente, senza filtrare per data
        # per evitare problemi con campi che potrebbero non esistere
        apiari = apiari_accessibili
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        arnie = arnie_accessibili
        controlli = ControlloArnia.objects.filter(arnia__in=arnie_accessibili)
        
        try:
            regine = Regina.objects.filter(arnia__in=arnie_accessibili)
        except Exception as e:
            regine = []
            logger.error(f"Errore durante il recupero delle regine: {e}")
        
        try:
            fioriture = (
                Fioritura.objects.filter(apiario__in=apiari_accessibili) |
                Fioritura.objects.filter(apiario__isnull=True, creatore=user)
            ).distinct()
        except Exception as e:
            fioriture = []
            logger.error(f"Errore durante il recupero delle fioriture: {e}")
        
        try:
            trattamenti = TrattamentoSanitario.objects.filter(apiario__in=apiari_accessibili)
        except Exception as e:
            trattamenti = []
            logger.error(f"Errore durante il recupero dei trattamenti: {e}")
        
        try:
            melari = Melario.objects.filter(arnia__in=arnie_accessibili)
        except Exception as e:
            melari = []
            logger.error(f"Errore durante il recupero dei melari: {e}")
        
        try:
            smielature = Smielatura.objects.filter(apiario__in=apiari_accessibili)
        except Exception as e:
            smielature = []
            logger.error(f"Errore durante il recupero delle smielature: {e}")
        try:
            pagamenti = (
                Pagamento.objects.filter(utente=user) |
                Pagamento.objects.filter(gruppo__in=gruppi_utente)
            ).distinct()
        except Exception as e:
            pagamenti = []
            logger.error(f"Errore durante il recupero dei pagamenti: {e}")

        try:
            # FIX #4 - Allinea con QuotaUtenteViewSet: quote gruppo visibili solo agli admin
            gruppi_admin = Gruppo.objects.filter(
                membri=user,
                membrogruppo__ruolo='admin'
            )
            quote = (
                QuotaUtente.objects.filter(utente=user) |
                QuotaUtente.objects.filter(gruppo__in=gruppi_admin)
            ).distinct()
        except Exception as e:
            quote = []
            logger.error(f"Errore durante il recupero delle quote: {e}")

        # Serializza i dati
        data = {
            'timestamp': timezone.now().isoformat(),
            'apiari': ApiarioSerializer(apiari, many=True).data,
            'arnie': ArniaSerializer(arnie, many=True).data,
            'controlli': ControlloArniaDetailSerializer(controlli, many=True).data,
            'regine': ReginaSerializer(regine, many=True).data if regine else [],
            'fioriture': FiorituraSerializer(fioriture, many=True).data if fioriture else [],
            'trattamenti': TrattamentoSanitarioSerializer(trattamenti, many=True).data if trattamenti else [],
            'melari': MelarioSerializer(melari, many=True).data if melari else [],
            'smielature': SmielaturaSerializer(smielature, many=True).data if smielature else [],
            'pagamenti': PagamentoSerializer(pagamenti, many=True).data if pagamenti else [],
            'quote': QuotaUtenteSerializer(quote, many=True).data if quote else [],
        }
        
        return Response(data)
    
    except Exception as e:
        # Log l'errore e restituisci una risposta generica (senza dettagli interni)
        logger.error(f"Errore durante la sincronizzazione per {request.user.username}: {str(e)}")
        return Response(
            {"detail": "Errore durante la sincronizzazione. Riprova più tardi."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """
    Restituisce i dati dell'utente corrente.
    """
    serializer = UserSerializer(request.user)
    return Response(serializer.data)
    
# Aggiungi queste funzioni di vista API per gestire gli inviti
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def inviti_ricevuti(request):
    """
    Restituisce gli inviti ricevuti dall'utente corrente.
    """
    # Ottieni inviti attivi per l'email dell'utente
    inviti = InvitoGruppo.objects.filter(
        email=request.user.email,
        stato='inviato',
        data_scadenza__gte=timezone.now()
    )
    
    serializer = InvitoGruppoSerializer(inviti, many=True)
    return Response({"results": serializer.data})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def accetta_invito(request, token):
    """
    Accetta un invito di gruppo tramite token.
    """
    try:
        invito = InvitoGruppo.objects.get(token=token)
    except InvitoGruppo.DoesNotExist:
        return Response(
            {"detail": "Invito non valido o scaduto."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verifica validità
    if not invito.is_valid():
        return Response(
            {"detail": "Invito scaduto o già utilizzato."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verifica che l'invito sia destinato all'utente corrente
    if invito.email != request.user.email:
        return Response(
            {"detail": "Questo invito è destinato a un altro indirizzo email."},
            status=status.HTTP_403_FORBIDDEN
        )

    # FIX #7 - Verifica che l'utente non sia già membro del gruppo
    if MembroGruppo.objects.filter(utente=request.user, gruppo=invito.gruppo).exists():
        # Aggiorna comunque lo stato dell'invito
        invito.stato = 'accettato'
        invito.save()
        return Response({"detail": "Sei già membro di questo gruppo."})

    # Crea relazione membro-gruppo
    MembroGruppo.objects.create(
        utente=request.user,
        gruppo=invito.gruppo,
        ruolo=invito.ruolo_proposto
    )

    # Aggiorna stato invito
    invito.stato = 'accettato'
    invito.save()

    return Response({"detail": "Invito accettato con successo."})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rifiuta_invito(request, token):
    """
    Rifiuta un invito di gruppo tramite token.
    """
    try:
        invito = InvitoGruppo.objects.get(token=token)
    except InvitoGruppo.DoesNotExist:
        return Response(
            {"detail": "Invito non valido o scaduto."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Verifica validità
    if not invito.is_valid():
        return Response(
            {"detail": "Invito scaduto o già utilizzato."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verifica che l'invito sia destinato all'utente corrente
    if invito.email != request.user.email:
        return Response(
            {"detail": "Questo invito è destinato a un altro indirizzo email."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Aggiorna stato invito
    invito.stato = 'rifiutato'
    invito.save()
    
    return Response({"detail": "Invito rifiutato con successo."})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def meteo_by_location(request):
    """Restituisce dati meteo per latitudine e longitudine."""
    # Get parameters
    lat = request.query_params.get('lat')
    lon = request.query_params.get('lon')
    
    if not lat or not lon:
        return Response(
            {"detail": "Parametri lat e lon richiesti."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Implement your weather fetching logic here
        # This can be similar to what you use in the apiario/<id>/meteo/ endpoint
        
        # For now, return a placeholder response
        weather_data = {
            "temperature": 22.5,
            "humidity": 65,
            "description": "Sereno",
            "icon": "01d"
        }
        
        return Response(weather_data)
    except Exception as e:
        return Response(
            {"detail": f"Errore: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )