from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta

from .models import (
    Apiario, Arnia, ControlloArnia, Regina, Fioritura, 
    TrattamentoSanitario, TipoTrattamento, Melario, Smielatura,
    Gruppo, MembroGruppo, InvitoGruppo, DatiMeteo, PrevisioneMeteo
)
from .serializers import (
    ApiarioSerializer, ArniaSerializer, ControlloArniaDetailSerializer,
    ControlloArniaListSerializer, ReginaSerializer, FiorituraSerializer,
    TrattamentoSanitarioSerializer, TipoTrattamentoSerializer,
    MelarioSerializer, SmielaturaSerializer, GruppoSerializer,
    MembroGruppoSerializer, InvitoGruppoSerializer, UserSerializer
)

# Permessi personalizzati
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

class ApiarioViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire gli apiari.
    """
    serializer_class = ApiarioSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['nome', 'posizione']

    def get_queryset(self):
        """
        Filtra gli apiari in base all'utente autenticato.
        Restituisce gli apiari di cui l'utente è proprietario o 
        che sono condivisi con i gruppi di cui l'utente è membro.
        """
        user = self.request.user
        
        # Apiari di cui l'utente è proprietario
        apiari_propri = Apiario.objects.filter(proprietario=user)
        
        # Apiari condivisi con gruppi di cui l'utente è membro
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        # Unisci gli apiari e rimuovi i duplicati
        return (apiari_propri | apiari_condivisi).distinct()
    
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

    # Funzione helper per inviare email di invito (riutilizzata dal file views.py)
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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['numero', 'apiario__nome']

    def get_queryset(self):
        """
        Filtra le arnie in base agli apiari accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le arnie in base agli apiari accessibili
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
    permission_classes = [permissions.IsAuthenticated]
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
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le arnie in base agli apiari accessibili
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        
        # Filtra i controlli in base alle arnie accessibili
        return ControlloArnia.objects.filter(arnia__in=arnie_accessibili)

class ReginaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le regine.
    """
    serializer_class = ReginaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['arnia__numero', 'arnia__apiario__nome', 'razza']

    def get_queryset(self):
        """
        Filtra le regine in base alle arnie accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le arnie in base agli apiari accessibili
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        
        # Filtra le regine in base alle arnie accessibili
        return Regina.objects.filter(arnia__in=arnie_accessibili)

class FiorituraViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le fioriture.
    """
    serializer_class = FiorituraSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['pianta', 'apiario__nome']

    def get_queryset(self):
        """
        Filtra le fioriture in base agli apiari accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le fioriture in base agli apiari accessibili + fioriture senza apiario create dall'utente
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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['apiario__nome', 'tipo_trattamento__nome', 'stato']

    def get_queryset(self):
        """
        Filtra i trattamenti in base agli apiari accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra i trattamenti in base agli apiari accessibili
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
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['arnia__numero', 'arnia__apiario__nome', 'stato']

    def get_queryset(self):
        """
        Filtra i melari in base alle arnie accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le arnie in base agli apiari accessibili
        arnie_accessibili = Arnia.objects.filter(apiario__in=apiari_accessibili)
        
        # Filtra i melari in base alle arnie accessibili
        return Melario.objects.filter(arnia__in=arnie_accessibili)

class SmielaturaViewSet(viewsets.ModelViewSet):
    """
    API endpoint per gestire le smielature.
    """
    serializer_class = SmielaturaSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['apiario__nome', 'tipo_miele']
    ordering_fields = ['data', 'quantita_miele']
    ordering = ['-data']  # Ordinamento predefinito

    def get_queryset(self):
        """
        Filtra le smielature in base agli apiari accessibili all'utente.
        """
        user = self.request.user
        
        # Recupera gli apiari accessibili all'utente
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        # Filtra le smielature in base agli apiari accessibili
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
    
    @action(detail=True, methods=['get'])
    def membri(self, request, pk=None):
        """
        Restituisce i membri di un gruppo.
        """
        gruppo = self.get_object()
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
            data_scadenza=timezone.now() + timezone.timedelta(days=7)
        )
        invito.save()
        
        # Invia email di invito
        try:
            invia_email_invito(invito)
        except:
            # Non fallire se l'email non può essere inviata
            pass
        
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

# Endpoint per la sincronizzazione
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

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
        
        # Filtro per apiari accessibili all'utente
        user = request.user
        apiari_propri = Apiario.objects.filter(proprietario=user)
        gruppi_utente = Gruppo.objects.filter(membri=user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=user)
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
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
            print(f"Errore durante il recupero delle regine: {e}")
        
        try:
            fioriture = (
                Fioritura.objects.filter(apiario__in=apiari_accessibili) |
                Fioritura.objects.filter(apiario__isnull=True, creatore=user)
            ).distinct()
        except Exception as e:
            fioriture = []
            print(f"Errore durante il recupero delle fioriture: {e}")
        
        try:
            trattamenti = TrattamentoSanitario.objects.filter(apiario__in=apiari_accessibili)
        except Exception as e:
            trattamenti = []
            print(f"Errore durante il recupero dei trattamenti: {e}")
        
        try:
            melari = Melario.objects.filter(arnia__in=arnie_accessibili)
        except Exception as e:
            melari = []
            print(f"Errore durante il recupero dei melari: {e}")
        
        try:
            smielature = Smielatura.objects.filter(apiario__in=apiari_accessibili)
        except Exception as e:
            smielature = []
            print(f"Errore durante il recupero delle smielature: {e}")
        
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
            'smielature': SmielaturaSerializer(smielature, many=True).data if smielature else []
        }
        
        return Response(data)
    
    except Exception as e:
        # Log l'errore e restituisci una risposta generica
        print(f"Errore durante la sincronizzazione: {str(e)}")
        return Response(
            {"detail": f"Errore durante la sincronizzazione: {str(e)}"},
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

