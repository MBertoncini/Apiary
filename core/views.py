# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth import logout
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import uuid
from functools import wraps

from .models import (
    Apiario, Arnia, ControlloArnia, Fioritura, Pagamento, QuotaUtente, 
    TrattamentoSanitario, TipoTrattamento, Gruppo, MembroGruppo, InvitoGruppo
)
from .forms import (
    ApiarioForm, ArniaForm, ControlloArniaForm, FiorituraForm, PagamentoForm, 
    QuotaUtenteForm, TrattamentoSanitarioForm, TipoTrattamentoForm, GruppoForm,
    InvitoGruppoForm, MembroGruppoRoleForm, ApiarioGruppoForm
)
from .decorators import (
    richiedi_proprietario_o_gruppo, richiedi_appartenenza_gruppo, 
    richiedi_ruolo_admin, richiedi_permesso_scrittura
)


def logout_view(request):
    """Gestisce il logout dell'utente"""
    logout(request)
    messages.success(request, "Hai effettuato il logout con successo.")
    return redirect('homepage')

@login_required
def dashboard(request):
    """Vista principale della dashboard"""
    # Ottieni apiari a cui l'utente ha accesso (propri o condivisi tramite gruppi)
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    
    # Apiari condivisi tramite gruppi
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente, 
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)
    
    # Unisci gli apiari
    apiari = (apiari_propri | apiari_condivisi).distinct()
    data_odierna = timezone.now().date()
    
    # Ultimi controlli effettuati (considera solo arnie a cui l'utente ha accesso)
    arnie_accessibili = Arnia.objects.filter(apiario__in=apiari)
    ultimi_controlli = ControlloArnia.objects.filter(
        arnia__in=arnie_accessibili
    ).order_by('-data')[:10]
    
    # Fioriture attuali
    fioriture_attuali = Fioritura.objects.filter(
        apiario__in=apiari,
        data_inizio__lte=data_odierna
    ).filter(
        Q(data_fine__isnull=True) | Q(data_fine__gte=data_odierna)
    )
    
    context = {
        'apiari': apiari,
        'ultimi_controlli': ultimi_controlli,
        'fioriture_attuali': fioriture_attuali,
        'data_selezionata': data_odierna,
        'apiari_condivisi': apiari_condivisi,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
@richiedi_proprietario_o_gruppo
def visualizza_apiario(request, apiario_id, data=None):
    """Visualizzazione di un apiario in una data specifica"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Se non è specificata una data, usa la data odierna
    if data is None:
        data_selezionata = timezone.now().date()
    else:
        data_selezionata = datetime.strptime(data, '%Y-%m-%d').date()
    
    arnie = Arnia.objects.filter(apiario=apiario, attiva=True)
    
    # Recupera i controlli dell'arnia per la data selezionata
    ultimi_controlli = []
    for arnia in arnie:
        try:
            controllo = ControlloArnia.objects.filter(
                arnia=arnia,
                data__lte=data_selezionata
            ).order_by('-data').first()
            
            if controllo:
                ultimi_controlli.append(controllo)
        except ControlloArnia.DoesNotExist:
            pass
    
    # Recupera i trattamenti attivi per l'apiario alla data selezionata
    trattamenti_attivi = TrattamentoSanitario.objects.filter(
        apiario=apiario,
        data_inizio__lte=data_selezionata
    ).filter(
        Q(data_fine__isnull=True) | Q(data_fine__gte=data_selezionata)
    ).filter(
        Q(stato='programmato') | Q(stato='in_corso')
    )
    
    # Ottieni tutti i trattamenti per visualizzazione sulle singole arnie
    trattamenti_per_arnia = trattamenti_attivi
    
    for controllo in ultimi_controlli:
        # Calcola la distribuzione dei telaini di scorte
        scorte_totali = controllo.telaini_scorte or 0
        controllo.scorte_sinistra = scorte_totali // 2  # divisione intera per la metà sinistra
        controllo.scorte_destra = scorte_totali - controllo.scorte_sinistra  # resto a destra

    # Aggiungi informazioni sul gruppo nella context
    context = {
        'apiario': apiario,
        'arnie': arnie,
        'ultimi_controlli': ultimi_controlli,
        'data_selezionata': data_selezionata,
        'trattamenti_attivi': trattamenti_attivi,
        'trattamenti_per_arnia': trattamenti_per_arnia,
    }
    
    # Se l'apiario è condiviso con un gruppo, aggiungi informazioni
    if apiario.gruppo and apiario.condiviso_con_gruppo:
        # Ottieni il ruolo dell'utente nel gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            context['membro_gruppo'] = membro
            context['is_proprietario'] = apiario.proprietario == request.user
            context['can_edit'] = membro.ruolo in ['admin', 'editor'] or apiario.proprietario == request.user
        except MembroGruppo.DoesNotExist:
            # Se l'utente non è membro del gruppo ma può comunque accedere (es. proprietario)
            context['is_proprietario'] = True
            context['can_edit'] = True
    else:
        # Se non è condiviso, solo il proprietario può modificare
        context['is_proprietario'] = apiario.proprietario == request.user
        context['can_edit'] = apiario.proprietario == request.user
    
    return render(request, 'arnie/visualizza_apiario.html', context)

@login_required
@richiedi_permesso_scrittura
def nuovo_controllo(request, arnia_id):
    """Aggiunge un nuovo controllo per un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    
    # Controlla se l'utente ha accesso all'apiario
    apiario = arnia.apiario
    can_edit = False
    
    # Se è il proprietario, ha accesso completo
    if apiario.proprietario == request.user:
        can_edit = True
    # Se l'apiario è condiviso con un gruppo di cui l'utente fa parte
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per aggiungere controlli a questa arnia.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = ControlloArniaForm(request.POST)
        if form.is_valid():
            controllo = form.save(commit=False)
            controllo.arnia = arnia
            controllo.utente = request.user
            controllo.save()
            return redirect('visualizza_apiario', apiario_id=arnia.apiario.id)
    else:
        # Pre-compila con gli ultimi valori registrati se disponibili
        initial_data = {}
        ultimo_controllo = ControlloArnia.objects.filter(arnia=arnia).order_by('-data').first()
        
        if ultimo_controllo:
            initial_data = {
                'telaini_scorte': ultimo_controllo.telaini_scorte,
                'telaini_covata': ultimo_controllo.telaini_covata,
                'presenza_regina': ultimo_controllo.presenza_regina,
            }
        
        form = ControlloArniaForm(initial=initial_data)
    
    context = {
        'form': form,
        'arnia': arnia,
    }
    
    return render(request, 'arnie/nuovo_controllo.html', context)

@login_required
@richiedi_permesso_scrittura
def modifica_controllo(request, controllo_id):
    """Modifica un controllo esistente"""
    controllo = get_object_or_404(ControlloArnia, pk=controllo_id)
    arnia = controllo.arnia
    apiario = arnia.apiario
    
    # Verifica se l'utente ha diritto di modificare questo controllo
    can_edit = False
    
    # Il proprietario dell'apiario può sempre modificare
    if apiario.proprietario == request.user:
        can_edit = True
    # Chi ha creato il controllo può modificarlo
    elif controllo.utente == request.user:
        can_edit = True
    # Se l'apiario è condiviso con un gruppo di cui l'utente è membro con ruolo adeguato
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per modificare questo controllo.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = ControlloArniaForm(request.POST, instance=controllo)
        if form.is_valid():
            form.save()
            messages.success(request, "Controllo aggiornato con successo.")
            return redirect('visualizza_apiario', apiario_id=controllo.arnia.apiario.id)
    else:
        form = ControlloArniaForm(instance=controllo)
    
    context = {
        'form': form,
        'arnia': controllo.arnia,
        'controllo': controllo,
        'is_edit': True,
    }
    
    return render(request, 'arnie/nuovo_controllo.html', context)

@login_required
@richiedi_permesso_scrittura
def copia_controllo(request, controllo_id):
    """Copia un controllo esistente su altre arnie"""
    controllo_origine = get_object_or_404(ControlloArnia, pk=controllo_id)
    apiario = controllo_origine.arnia.apiario
    
    # Verifica i permessi
    can_edit = False
    if apiario.proprietario == request.user:
        can_edit = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per copiare controlli in questo apiario.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    arnie = Arnia.objects.filter(apiario=apiario, attiva=True).exclude(id=controllo_origine.arnia.id)
    
    if request.method == 'POST':
        arnie_selezionate = request.POST.getlist('arnie')
        data = request.POST.get('data')
        data_controllo = datetime.strptime(data, '%Y-%m-%d').date()
        
        # Campi da copiare
        campi_da_copiare = ['telaini_scorte', 'telaini_covata']
        
        # Opzioni aggiuntive
        if 'copia_regina' in request.POST:
            campi_da_copiare.append('presenza_regina')
        if 'copia_sciamatura' in request.POST:
            campi_da_copiare.extend(['sciamatura', 'data_sciamatura', 'note_sciamatura'])
        if 'copia_problemi' in request.POST:
            campi_da_copiare.extend(['problemi_sanitari', 'note_problemi'])
        if 'copia_note' in request.POST:
            campi_da_copiare.append('note')
        
        # Contatori per i messaggi
        controlli_creati = 0
        controlli_aggiornati = 0
        
        # Crea o aggiorna controlli per le arnie selezionate
        for arnia_id in arnie_selezionate:
            arnia = Arnia.objects.get(pk=arnia_id)
            
            # Verifica se esiste già un controllo per questa arnia nella data specificata
            controllo_esistente = ControlloArnia.objects.filter(
                arnia=arnia,
                data=data_controllo
            ).first()
            
            if controllo_esistente:
                # Aggiorna il controllo esistente
                for campo in campi_da_copiare:
                    setattr(controllo_esistente, campo, getattr(controllo_origine, campo))
                
                controllo_esistente.save()
                controlli_aggiornati += 1
            else:
                # Crea un nuovo controllo
                nuovo_controllo = ControlloArnia(
                    arnia=arnia,
                    data=data_controllo,
                    utente=request.user
                )
                
                # Copia i campi selezionati
                for campo in campi_da_copiare:
                    setattr(nuovo_controllo, campo, getattr(controllo_origine, campo))
                
                nuovo_controllo.save()
                controlli_creati += 1
        
        # Messaggio di successo dettagliato
        if controlli_aggiornati > 0 and controlli_creati > 0:
            messages.success(request, f"Controllo copiato: {controlli_aggiornati} controlli aggiornati e {controlli_creati} controlli creati")
        elif controlli_aggiornati > 0:
            messages.success(request, f"Controllo copiato: {controlli_aggiornati} controlli esistenti aggiornati")
        else:
            messages.success(request, f"Controllo copiato: {controlli_creati} nuovi controlli creati")
            
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    context = {
        'controllo': controllo_origine,
        'arnie': arnie,
        'data_corrente': timezone.now().date(),
    }
    
    return render(request, 'arnie/copia_controllo.html', context)

@login_required
@richiedi_permesso_scrittura
def elimina_controllo(request, pk):
    """Elimina un controllo esistente"""
    controllo = get_object_or_404(ControlloArnia, pk=pk)
    apiario_id = controllo.arnia.apiario.id
    apiario = controllo.arnia.apiario
    
    # Verifica i permessi
    can_delete = False
    if apiario.proprietario == request.user:
        can_delete = True
    elif controllo.utente == request.user:
        can_delete = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_delete = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_delete:
        messages.error(request, "Non hai i permessi per eliminare questo controllo.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        controllo.delete()
        messages.success(request, "Controllo eliminato con successo.")
        
        # Redirect alla pagina di provenienza (se specificata)
        next_url = request.POST.get('next', 'dashboard')
        if next_url == 'apiario':
            return redirect('visualizza_apiario', apiario_id=apiario_id)
        else:
            return redirect('dashboard')
            
    context = {
        'controllo': controllo,
        'next': request.GET.get('next', 'dashboard')
    }
    
    return render(request, 'arnie/conferma_elimina_controllo.html', context)


@login_required
def gestione_apiario_gruppo(request, apiario_id):
    """Vista per gestire le impostazioni di gruppo di un apiario"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Verifica che l'utente sia il proprietario dell'apiario
    if apiario.proprietario != request.user:
        messages.error(request, "Solo il proprietario può modificare le impostazioni di condivisione.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = ApiarioGruppoForm(request.POST, instance=apiario, user=request.user)
        if form.is_valid():
            form.save()
            
            if apiario.condiviso_con_gruppo and apiario.gruppo:
                messages.success(request, f"L'apiario è stato associato al gruppo '{apiario.gruppo.nome}'.")
            else:
                messages.success(request, "L'apiario non è più condiviso con il gruppo.")
                
            return redirect('visualizza_apiario', apiario_id=apiario.id)
    else:
        form = ApiarioGruppoForm(instance=apiario, user=request.user)
    
    context = {
        'form': form,
        'apiario': apiario,
    }
    
    return render(request, 'apiari/gestione_apiario_gruppo.html', context)

def verifica_permessi_fioritura(view_func):
    """
    Decoratore che verifica che l'utente abbia permessi per modificare/eliminare una fioritura.
    Criterio: è il creatore della fioritura o è un amministratore.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        pk = kwargs.get('pk')
        if not pk:
            messages.error(request, "Fioritura non specificata.")
            return redirect('gestione_fioriture')
        
        try:
            fioritura = Fioritura.objects.get(pk=pk)
            
            # Determina se l'utente è un admin
            is_admin = request.user.is_staff or request.user.is_superuser
            
            # Se è una fioritura associata a un apiario, verifica anche i permessi del gruppo
            is_group_admin = False
            if fioritura.apiario and fioritura.apiario.gruppo and fioritura.apiario.condiviso_con_gruppo:
                try:
                    membro = MembroGruppo.objects.get(utente=request.user, gruppo=fioritura.apiario.gruppo)
                    is_group_admin = membro.ruolo in ['admin', 'editor']
                except MembroGruppo.DoesNotExist:
                    pass
            
            # Verifica se l'utente è il creatore della fioritura o ha permessi speciali
            if fioritura.apiario and fioritura.apiario.proprietario == request.user:
                # Proprietario dell'apiario ha sempre accesso
                return view_func(request, *args, **kwargs)
            elif is_admin or is_group_admin:
                # Admin di sistema o del gruppo hanno accesso
                return view_func(request, *args, **kwargs)
            elif hasattr(fioritura, 'creatore') and fioritura.creatore == request.user:
                # Creatore della fioritura ha accesso
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, "Non hai i permessi per modificare questa fioritura.")
                return redirect('gestione_fioriture')
                
        except Fioritura.DoesNotExist:
            messages.error(request, "Fioritura non trovata.")
            return redirect('gestione_fioriture')
    
    return _wrapped_view

@login_required
def gestione_fioriture(request):
    """Gestione delle fioriture"""
    # Ottieni apiari a cui l'utente ha accesso (per visualizzare tutte le fioriture)
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente, 
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)
    apiari = (apiari_propri | apiari_condivisi).distinct()
    
    # Ottieni tutte le fioriture accessibili all'utente
    # Include fioriture associate agli apiari + fioriture senza apiario (creati dall'utente)
    fioriture_apiari = Fioritura.objects.filter(apiario__in=apiari)
    fioriture_senza_apiario = Fioritura.objects.filter(apiario__isnull=True)
    fioriture = (fioriture_apiari | fioriture_senza_apiario).order_by('-data_inizio')
    
    if request.method == 'POST':
        form = FiorituraForm(request.POST)
        if form.is_valid():
            fioritura = form.save(commit=False)
            
            # Salva il creatore della fioritura
            fioritura.creatore = request.user
            
            # Verifica i permessi per l'apiario selezionato se presente
            apiario = fioritura.apiario
            if apiario:
                can_add = False
                if apiario.proprietario == request.user:
                    can_add = True
                elif apiario.gruppo and apiario.condiviso_con_gruppo:
                    try:
                        membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
                        if membro.ruolo in ['admin', 'editor']:
                            can_add = True
                    except MembroGruppo.DoesNotExist:
                        pass
                
                if not can_add:
                    messages.error(request, "Non hai i permessi per aggiungere fioriture a questo apiario.")
                    return redirect('gestione_fioriture')
            
            fioritura.save()
            messages.success(request, "Fioritura aggiunta con successo.")
            return redirect('gestione_fioriture')
    else:
        form = FiorituraForm()
        # Limita le opzioni del campo apiario agli apiari a cui l'utente ha accesso
        form.fields['apiario'].queryset = apiari
        # Imposta l'apiario come non obbligatorio nel form
        form.fields['apiario'].required = False
    
    context = {
        'fioriture': fioriture,
        'form': form,
    }
    
    return render(request, 'fioriture/gestione_fioriture.html', context)

@login_required
@verifica_permessi_fioritura
def fioritura_delete(request, pk):
    """Elimina una fioritura"""
    fioritura = get_object_or_404(Fioritura, pk=pk)
    
    if request.method == 'POST':
        fioritura.delete()
        messages.success(request, "Fioritura eliminata con successo.")
    
    return redirect('gestione_fioriture')

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

@login_required
def gestione_pagamenti(request):
    """Vista per gestire i pagamenti"""
    # Ottieni i gruppi dell'utente
    gruppi = Gruppo.objects.filter(membri=request.user)
    
    # Determina se visualizzare i pagamenti di un gruppo specifico
    gruppo_id = request.GET.get('gruppo_id')
    gruppo_selezionato = None
    
    if gruppo_id:
        try:
            gruppo_selezionato = Gruppo.objects.get(pk=gruppo_id)
            # Verifica che l'utente faccia parte del gruppo
            if not gruppo_selezionato.membri.filter(id=request.user.id).exists():
                messages.error(request, "Non sei membro di questo gruppo.")
                return redirect('gestione_pagamenti')
        except Gruppo.DoesNotExist:
            messages.error(request, "Gruppo non trovato.")
            return redirect('gestione_pagamenti')
            
        # Filtra i pagamenti e le quote per questo gruppo
        pagamenti = Pagamento.objects.filter(gruppo=gruppo_selezionato).order_by('-data')
        quote = QuotaUtente.objects.filter(gruppo=gruppo_selezionato)
        
        # Verifica i permessi per aggiungere/modificare pagamenti nel gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo_selezionato)
            can_edit = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            can_edit = False
    else:
        # Se non è selezionato un gruppo, mostra solo i pagamenti personali
        pagamenti = Pagamento.objects.filter(utente=request.user, gruppo__isnull=True).order_by('-data')
        quote = QuotaUtente.objects.filter(utente=request.user, gruppo__isnull=True)
        
        # Per i pagamenti personali, l'utente ha sempre i permessi
        can_edit = True
    
    # Calcola il totale dei pagamenti per utente
    pagamenti_per_utente = {}
    for quota in quote:
        pagamenti_utente = pagamenti.filter(utente=quota.utente)
        pagamenti_per_utente[quota.utente.id] = {
            'utente': quota.utente,
            'quota_percentuale': quota.percentuale,
            'pagamenti': pagamenti_utente,
            'totale_pagato': pagamenti_utente.aggregate(Sum('importo'))['importo__sum'] or 0,
        }
    
    # Calcola il totale generale dei pagamenti
    totale_pagamenti = pagamenti.aggregate(Sum('importo'))['importo__sum'] or 0
    
    # Calcola quanto dovrebbe pagare ciascun utente in base alla percentuale
    for user_id, dati in pagamenti_per_utente.items():
        dovuto = totale_pagamenti * (dati['quota_percentuale'] / 100)
        saldo = dati['totale_pagato'] - dovuto
        
        pagamenti_per_utente[user_id]['dovuto'] = dovuto
        pagamenti_per_utente[user_id]['saldo'] = saldo
    
    if request.method == 'POST' and can_edit:
        # Creiamo il form con i dati della richiesta
        form = PagamentoForm(request.POST, gruppo=gruppo_selezionato, 
                            initial={'utente': request.user})
        
        if form.is_valid():
            pagamento = form.save(commit=False)
            
            # Se è selezionato un gruppo, associa il pagamento al gruppo
            if gruppo_selezionato:
                pagamento.gruppo = gruppo_selezionato
            
            pagamento.save()
            messages.success(request, "Pagamento registrato con successo.")
            
            # Redirect mantenendo il filtro gruppo se applicato
            if gruppo_id:
                # Correzione: costruisci l'URL completo con i parametri di query
                return redirect(f'{reverse("gestione_pagamenti")}?gruppo_id={gruppo_id}')
            else:
                return redirect('gestione_pagamenti')
    else:
        # Inizializza il form con l'utente corrente
        form = PagamentoForm(gruppo=gruppo_selezionato, initial={'utente': request.user})
    
    context = {
        'pagamenti': pagamenti,
        'pagamenti_per_utente': pagamenti_per_utente,
        'totale_pagamenti': totale_pagamenti,
        'form': form,
        'gruppi': gruppi,
        'gruppo_selezionato': gruppo_selezionato,
        'can_edit': can_edit,
    }
    
    return render(request, 'pagamenti/gestione_pagamenti.html', context)

@login_required
def pagamento_update(request, pk):
    """Vista per modificare un pagamento esistente"""
    pagamento = get_object_or_404(Pagamento, pk=pk)
    gruppo = pagamento.gruppo
    
    # Verifica i permessi
    can_edit = False
    
    # Se è un pagamento personale dell'utente, può sempre modificarlo
    if pagamento.utente == request.user and not gruppo:
        can_edit = True
    # Se fa parte di un gruppo, verifica i permessi nel gruppo
    elif gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo in ['admin', 'editor'] or (pagamento.utente == request.user and membro.ruolo == 'viewer'):
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per modificare questo pagamento.")
        if gruppo:
            return redirect(f'{reverse("gestione_pagamenti")}?gruppo_id={gruppo.id}')
        return redirect('gestione_pagamenti')
    
    if request.method == 'POST':
        form = PagamentoForm(request.POST, instance=pagamento, gruppo=gruppo)
        if form.is_valid():
            form.save()
            messages.success(request, "Pagamento aggiornato con successo.")
            
            # Redirect mantenendo il filtro gruppo se applicato
            if gruppo:
                # Correzione: costruisci l'URL completo con i parametri di query
                return redirect(f'{reverse("gestione_pagamenti")}?gruppo_id={gruppo.id}')
            else:
                return redirect('gestione_pagamenti')
    else:
        form = PagamentoForm(instance=pagamento, gruppo=gruppo)
    
    context = {
        'form': form,
        'pagamento': pagamento,
        'gruppo': gruppo,
    }
    
    return render(request, 'pagamenti/form_pagamento.html', context)

@login_required
def pagamento_delete(request, pk):
    """Vista per eliminare un pagamento"""
    pagamento = get_object_or_404(Pagamento, pk=pk)
    gruppo = pagamento.gruppo
    
    # Verifica i permessi
    can_delete = False
    
    # Se è un pagamento personale dell'utente, può sempre eliminarlo
    if pagamento.utente == request.user and not gruppo:
        can_delete = True
    # Se fa parte di un gruppo, verifica i permessi nel gruppo
    elif gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo in ['admin', 'editor'] or (pagamento.utente == request.user and membro.ruolo == 'viewer'):
                can_delete = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_delete:
        messages.error(request, "Non hai i permessi per eliminare questo pagamento.")
        if gruppo:
            return redirect(f'{reverse("gestione_pagamenti")}?gruppo_id={gruppo.id}')
        return redirect('gestione_pagamenti')
    
    # Memorizza l'ID del gruppo per il redirect
    gruppo_id = gruppo.id if gruppo else None
    
    pagamento.delete()
    messages.success(request, "Pagamento eliminato con successo.")
    
    # Redirect mantenendo il filtro gruppo se applicato
    if gruppo_id:
        # Correzione: costruisci l'URL completo con i parametri di query
        return redirect(f'{reverse("gestione_pagamenti")}?gruppo_id={gruppo_id}')
    else:
        return redirect('gestione_pagamenti')

@login_required
def gestione_quote(request):
    """Vista per gestire le quote utente"""
    # Ottieni i gruppi dell'utente
    gruppi = Gruppo.objects.filter(membri=request.user)
    
    # Determina se visualizzare le quote di un gruppo specifico
    gruppo_id = request.GET.get('gruppo_id')
    gruppo_selezionato = None
    
    if gruppo_id:
        try:
            gruppo_selezionato = Gruppo.objects.get(pk=gruppo_id)
            # Verifica che l'utente faccia parte del gruppo
            if not gruppo_selezionato.membri.filter(id=request.user.id).exists():
                messages.error(request, "Non sei membro di questo gruppo.")
                return redirect('gestione_quote')
        except Gruppo.DoesNotExist:
            messages.error(request, "Gruppo non trovato.")
            return redirect('gestione_quote')
            
        # Filtra le quote per questo gruppo
        quote = QuotaUtente.objects.filter(gruppo=gruppo_selezionato)
        
        # Verifica i permessi per aggiungere/modificare quote nel gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo_selezionato)
            can_add = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            can_add = False
    else:
        # Se non è selezionato un gruppo, mostra solo le quote personali
        quote = QuotaUtente.objects.filter(utente=request.user, gruppo__isnull=True)
        
        # Per le quote personali, l'utente ha sempre i permessi
        can_add = True
    
    # Calcola il totale delle percentuali per verificare se arrivano a 100%
    total_percentuale = sum(q.percentuale for q in quote)
    
    if request.method == 'POST':
        # Se siamo in modalità gruppo, ricontrolliamo i permessi
        if gruppo_selezionato and not can_add:
            messages.error(request, "Non hai i permessi per aggiungere quote in questo gruppo.")
            return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo_id}')
            
        form = QuotaUtenteForm(request.POST, gruppo=gruppo_selezionato)
        if form.is_valid():
            quota = form.save(commit=False)
            
            # Se è selezionato un gruppo, associa la quota al gruppo
            if gruppo_selezionato:
                quota.gruppo = gruppo_selezionato
            
            quota.save()
            messages.success(request, "Quota aggiunta con successo.")
            
            # Redirect mantenendo il filtro gruppo se applicato
            if gruppo_id:
                # Correzione: costruisci l'URL completo con i parametri di query
                return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo_id}')
            else:
                return redirect('gestione_quote')
    else:
        form = QuotaUtenteForm(gruppo=gruppo_selezionato)
    
    context = {
        'quote': quote,
        'form': form,
        'gruppi': gruppi,
        'gruppo_selezionato': gruppo_selezionato,
        'can_add': can_add,
        'total_percentuale': total_percentuale,
    }
    
    return render(request, 'pagamenti/gestione_quote.html', context)

@login_required
def quota_update(request, pk):
    """Vista per modificare una quota utente esistente"""
    quota = get_object_or_404(QuotaUtente, pk=pk)
    gruppo = quota.gruppo
    
    # Verifica i permessi per aggiornare la quota
    can_update = False
    
    # Se è una quota personale dell'utente, può sempre modificarla
    if quota.utente == request.user and not gruppo:
        can_update = True
    # Se fa parte di un gruppo, verifica i permessi nel gruppo
    elif gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo in ['admin', 'editor'] or (quota.utente == request.user and membro.ruolo == 'viewer'):
                can_update = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_update:
        messages.error(request, "Non hai i permessi per modificare questa quota.")
        if gruppo:
            return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo.id}')
        return redirect('gestione_quote')
    
    if request.method == 'POST':
        form = QuotaUtenteForm(request.POST, instance=quota, gruppo=gruppo)
        if form.is_valid():
            form.save()
            messages.success(request, "Quota aggiornata con successo.")
            
            # Redirect mantenendo il filtro gruppo se applicato
            if gruppo:
                # Correzione: costruisci l'URL completo con i parametri di query
                return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo.id}')
            else:
                return redirect('gestione_quote')
    else:
        form = QuotaUtenteForm(instance=quota, gruppo=gruppo)
    
    context = {
        'form': form,
        'quota': quota,
        'gruppo': gruppo,
        'is_update': True,
    }
    
    return render(request, 'pagamenti/form_quota.html', context)

@login_required
def quota_delete(request, pk):
    """Vista per eliminare una quota utente"""
    quota = get_object_or_404(QuotaUtente, pk=pk)
    gruppo = quota.gruppo
    
    # Verifica i permessi per eliminare la quota
    can_delete = False
    
    # Se è una quota personale dell'utente, può sempre eliminarla
    if quota.utente == request.user and not gruppo:
        can_delete = True
    # Se fa parte di un gruppo, verifica i permessi nel gruppo
    elif gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_delete = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_delete:
        messages.error(request, "Non hai i permessi per eliminare questa quota.")
        if gruppo:
            return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo.id}')
        return redirect('gestione_quote')
    
    # Memorizza l'ID del gruppo per il redirect
    gruppo_id = gruppo.id if gruppo else None
    
    if request.method == 'POST':
        quota.delete()
        messages.success(request, "Quota eliminata con successo.")
        
        # Redirect mantenendo il filtro gruppo se applicato
        if gruppo_id:
            # Correzione: costruisci l'URL completo con i parametri di query
            return redirect(f'{reverse("gestione_quote")}?gruppo_id={gruppo_id}')
        else:
            return redirect('gestione_quote')
    
    context = {
        'quota': quota,
        'gruppo': gruppo,
    }
    
    return render(request, 'pagamenti/conferma_elimina_quota.html', context)

@login_required
def gestione_trattamenti(request):
    """Vista per gestire tutti i trattamenti sanitari"""
    # Ottieni trattamenti recenti (ultimi 6 mesi)
    sei_mesi_fa = timezone.now().date() - timedelta(days=180)
    trattamenti_recenti = TrattamentoSanitario.objects.filter(
        data_inizio__gte=sei_mesi_fa
    ).order_by('-data_inizio')
    
    # Trattamenti in corso o programmati
    trattamenti_attivi = TrattamentoSanitario.objects.filter(
        Q(stato='programmato') | Q(stato='in_corso')
    ).order_by('data_inizio')
    
    # Trattamenti in sospensione (completati ma ancora nel periodo di sospensione)
    oggi = timezone.now().date()
    trattamenti_sospensione = TrattamentoSanitario.objects.filter(
        stato='completato',
        data_fine_sospensione__gte=oggi
    ).order_by('data_fine_sospensione')
    
    # Tipi di trattamento disponibili
    tipi_trattamento = TipoTrattamento.objects.all()
    
    context = {
        'trattamenti_recenti': trattamenti_recenti,
        'trattamenti_attivi': trattamenti_attivi,
        'trattamenti_sospensione': trattamenti_sospensione,
        'tipi_trattamento': tipi_trattamento,
    }
    
    return render(request, 'trattamenti/gestione_trattamenti.html', context)

# Aggiornamento delle funzioni in views.py per gestire il blocco di covata

@login_required
@richiedi_permesso_scrittura
def nuovo_trattamento(request, apiario_id=None):
    """Vista per aggiungere un nuovo trattamento sanitario"""
    apiario = None
    if apiario_id:
        apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Verifica se l'utente ha i permessi per aggiungere un trattamento
    can_add_treatment = False
    if apiario:
        # Se l'utente è il proprietario dell'apiario
        if apiario.proprietario == request.user:
            can_add_treatment = True
        # Se l'utente è membro del gruppo dell'apiario con ruolo admin o editor
        elif apiario.gruppo and apiario.condiviso_con_gruppo:
            try:
                membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
                if membro.ruolo in ['admin', 'editor']:
                    can_add_treatment = True
            except MembroGruppo.DoesNotExist:
                pass
    
    # Se l'utente non ha i permessi, mostra un messaggio di errore
    if not can_add_treatment and apiario:
        messages.error(request, "Non hai i permessi per aggiungere un trattamento a questo apiario.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)

    # Ottieni informazioni sul tipo di trattamento selezionato
    tipo_trattamento_info = None
    if request.method == 'POST' and 'tipo_trattamento' in request.POST:
        try:
            tipo_id = int(request.POST.get('tipo_trattamento'))
            tipo_trattamento_info = TipoTrattamento.objects.get(pk=tipo_id)
        except (ValueError, TipoTrattamento.DoesNotExist):
            pass

    # Procedi con il salvataggio del trattamento
    if request.method == 'POST' and 'save' in request.POST:
        form = TrattamentoSanitarioForm(request.POST)
        if form.is_valid():
            trattamento = form.save(commit=False)
            trattamento.utente = request.user
            
            # Se è selezionato "Applica a tutte le arnie", non salviamo specifiche arnie
            seleziona_tutte = form.cleaned_data.get('seleziona_tutte_arnie')
            
            # Calcola automaticamente la data_fine_sospensione se è stato completato il trattamento
            if trattamento.stato == 'completato' and trattamento.data_fine and trattamento.tipo_trattamento.tempo_sospensione > 0:
                trattamento.data_fine_sospensione = trattamento.data_fine + timedelta(days=trattamento.tipo_trattamento.tempo_sospensione)
            
            # Se il tipo di trattamento richiede blocco di covata e l'utente lo ha attivato
            if trattamento.blocco_covata_attivo and trattamento.data_inizio_blocco:
                # Se non è specificata la data di fine blocco, calcolarla in base ai giorni consigliati
                if not trattamento.data_fine_blocco and trattamento.tipo_trattamento.giorni_blocco_covata > 0:
                    trattamento.data_fine_blocco = trattamento.data_inizio_blocco + timedelta(days=trattamento.tipo_trattamento.giorni_blocco_covata)
                
                # Se non è specificato un metodo di blocco, suggerire il valore predefinito
                if not trattamento.metodo_blocco:
                    trattamento.metodo_blocco = "Gabbia"
            
            trattamento.save()
            
            if not seleziona_tutte:
                # Salva le arnie selezionate
                form.save_m2m()
            else:
                # Non selezionare arnie specifiche (si applica a tutto l'apiario)
                trattamento.arnie.clear()
            
            messages.success(request, f"Trattamento {trattamento.tipo_trattamento} programmato con successo.")
            
            # Reindirizza alla pagina dell'apiario se applicabile
            if apiario:
                return redirect('visualizza_apiario', apiario_id=apiario.id)
            else:
                return redirect('gestione_trattamenti')
    else:
        initial_data = {}
        if apiario:
            initial_data['apiario'] = apiario.id
        
        # Se è stato selezionato un tipo che richiede blocco covata, pre-popoliamo alcuni valori
        if tipo_trattamento_info and tipo_trattamento_info.richiede_blocco_covata:
            initial_data['blocco_covata_attivo'] = True
            
            # Calcoliamo una data di inizio per il blocco (potrebbe essere la stessa del trattamento)
            today = timezone.now().date()
            initial_data['data_inizio_blocco'] = today
            if tipo_trattamento_info.giorni_blocco_covata > 0:
                initial_data['data_fine_blocco'] = today + timedelta(days=tipo_trattamento_info.giorni_blocco_covata)
        
        form = TrattamentoSanitarioForm(initial=initial_data)
        
        # Limita le opzioni alle arnie dell'apiario selezionato
        if apiario:
            form.fields['arnie'].queryset = Arnia.objects.filter(apiario=apiario, attiva=True)
            # Disabilita il campo apiario se siamo già in un apiario specifico
            form.fields['apiario'].disabled = True
        elif 'apiario' in request.POST:
            try:
                apiario_id = int(request.POST.get('apiario'))
                apiario = Apiario.objects.get(pk=apiario_id)
                form.fields['arnie'].queryset = Arnia.objects.filter(apiario=apiario, attiva=True)
            except (ValueError, Apiario.DoesNotExist):
                form.fields['arnie'].queryset = Arnia.objects.none()
        else:
            form.fields['arnie'].queryset = Arnia.objects.none()
    
    context = {
        'form': form,
        'apiario': apiario,
        'tipo_trattamento_info': tipo_trattamento_info,
    }
    
    return render(request, 'trattamenti/form_trattamento.html', context)


@login_required
@richiedi_permesso_scrittura
def modifica_trattamento(request, pk):
    """Vista per modificare un trattamento esistente"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    apiario = trattamento.apiario
    
    # Verifica i permessi
    can_edit = False
    if apiario.proprietario == request.user:
        can_edit = True
    elif trattamento.utente == request.user:
        can_edit = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_edit = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per modificare questo trattamento.")
        return redirect('gestione_trattamenti')
    
    # Verifica se tutte le arnie dell'apiario sono incluse nel trattamento
    tutte_arnie_apiario = set(Arnia.objects.filter(apiario=trattamento.apiario, attiva=True).values_list('id', flat=True))
    arnie_trattamento = set(trattamento.arnie.values_list('id', flat=True))
    seleziona_tutte = len(arnie_trattamento) == 0 or arnie_trattamento == tutte_arnie_apiario
    
    # Ottieni informazioni sul tipo di trattamento selezionato
    tipo_trattamento_info = trattamento.tipo_trattamento
    
    if request.method == 'POST':
        form = TrattamentoSanitarioForm(request.POST, instance=trattamento)
        if form.is_valid():
            trattamento = form.save(commit=False)
            
            # Gestione della selezione "tutte le arnie"
            seleziona_tutte = form.cleaned_data.get('seleziona_tutte_arnie')
            
            # Calcola automaticamente la data_fine_sospensione se è stato completato il trattamento
            if trattamento.stato == 'completato' and trattamento.data_fine and trattamento.tipo_trattamento.tempo_sospensione > 0:
                trattamento.data_fine_sospensione = trattamento.data_fine + timedelta(days=trattamento.tipo_trattamento.tempo_sospensione)
            
            # Gestione del blocco di covata
            if trattamento.blocco_covata_attivo and trattamento.data_inizio_blocco:
                # Se non è specificata la data di fine blocco, calcolarla in base ai giorni consigliati
                if not trattamento.data_fine_blocco and trattamento.tipo_trattamento.giorni_blocco_covata > 0:
                    trattamento.data_fine_blocco = trattamento.data_inizio_blocco + timedelta(days=trattamento.tipo_trattamento.giorni_blocco_covata)
            
            trattamento.save()
            
            if not seleziona_tutte:
                # Salva le arnie selezionate
                form.save_m2m()
            else:
                # Non selezionare arnie specifiche (si applica a tutto l'apiario)
                trattamento.arnie.clear()
            
            messages.success(request, f"Trattamento aggiornato con successo.")
            
            # Redirect mantenendo il filtro gruppo se applicato
            if apiario.gruppo and apiario.condiviso_con_gruppo:
                return redirect(f'gestione_trattamenti?gruppo_id={apiario.gruppo.id}')
            return redirect('gestione_trattamenti')
    else:
        # Ottieni apiari a cui l'utente ha accesso
        apiari_propri = Apiario.objects.filter(proprietario=request.user)
        gruppi_utente = Gruppo.objects.filter(membri=request.user)
        apiari_condivisi = Apiario.objects.filter(
            gruppo__in=gruppi_utente, 
            condiviso_con_gruppo=True
        ).exclude(proprietario=request.user)
        apiari_accessibili = (apiari_propri | apiari_condivisi).distinct()
        
        form = TrattamentoSanitarioForm(instance=trattamento, initial={'seleziona_tutte_arnie': seleziona_tutte})
        # Limita gli apiari a quelli a cui l'utente ha accesso
        form.fields['apiario'].queryset = apiari_accessibili
    
    context = {
        'form': form,
        'trattamento': trattamento,
        'apiario': apiario,
        'tipo_trattamento_info': tipo_trattamento_info,
        'is_edit': True,
    }
    
    return render(request, 'trattamenti/form_trattamento.html', context)

@login_required
@richiedi_permesso_scrittura
def elimina_trattamento(request, pk):
    """Vista per eliminare un trattamento"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    apiario = trattamento.apiario
    
    # Verifica i permessi
    can_delete = False
    if apiario.proprietario == request.user:
        can_delete = True
    elif trattamento.utente == request.user:
        can_delete = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_delete = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_delete:
        messages.error(request, "Non hai i permessi per eliminare questo trattamento.")
        return redirect('gestione_trattamenti')
    
    # Memorizza il gruppo per il redirect
    gruppo_id = apiario.gruppo.id if apiario.gruppo and apiario.condiviso_con_gruppo else None
    
    if request.method == 'POST':
        trattamento.delete()
        messages.success(request, "Trattamento eliminato con successo.")
        
        # Redirect mantenendo il filtro gruppo se applicato
        if gruppo_id:
            return redirect(f'gestione_trattamenti?gruppo_id={gruppo_id}')
        return redirect('gestione_trattamenti')
    
    context = {
        'trattamento': trattamento,
    }
    
    return render(request, 'trattamenti/conferma_elimina.html', context)

@login_required
def tipi_trattamento(request):
    """Vista per gestire i tipi di trattamento"""
    tipi = TipoTrattamento.objects.all()
    
    if request.method == 'POST':
        form = TipoTrattamentoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Nuovo tipo di trattamento aggiunto con successo.")
            return redirect('tipi_trattamento')
    else:
        form = TipoTrattamentoForm()
    
    context = {
        'tipi': tipi,
        'form': form,
    }
    
    return render(request, 'trattamenti/tipi_trattamento.html', context)

@login_required
@richiedi_permesso_scrittura
def modifica_tipo_trattamento(request, pk):
    """Vista per modificare un tipo di trattamento"""
    tipo = get_object_or_404(TipoTrattamento, pk=pk)
    
    if request.method == 'POST':
        form = TipoTrattamentoForm(request.POST, instance=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, "Tipo di trattamento aggiornato con successo.")
            return redirect('tipi_trattamento')
    else:
        form = TipoTrattamentoForm(instance=tipo)
    
    context = {
        'form': form,
        'tipo': tipo,
    }
    
    return render(request, 'trattamenti/form_tipo_trattamento.html', context)

@login_required
@richiedi_permesso_scrittura
def elimina_tipo_trattamento(request, pk):
    """Vista per eliminare un tipo di trattamento"""
    tipo = get_object_or_404(TipoTrattamento, pk=pk)
    
    if request.method == 'POST':
        nome = tipo.nome  # Store name for feedback message
        tipo.delete()
        messages.success(request, f"Tipo di trattamento '{nome}' eliminato con successo.")
        return redirect('tipi_trattamento')
    
    context = {
        'tipo': tipo,
    }
    
    return render(request, 'trattamenti/conferma_elimina_tipo.html', context)

@login_required
@richiedi_permesso_scrittura
def cambio_stato_trattamento(request, pk, nuovo_stato):
    """Vista per cambiare rapidamente lo stato di un trattamento"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    apiario = trattamento.apiario
    stati_validi = dict(TrattamentoSanitario.STATO_CHOICES).keys()
    
    # Verifica i permessi
    can_edit = False
    if apiario.proprietario == request.user:
        can_edit = True
    elif trattamento.utente == request.user:
        can_edit = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_edit = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi per modificare lo stato di questo trattamento.")
        return redirect('gestione_trattamenti')
    
    if nuovo_stato in stati_validi:
        trattamento.stato = nuovo_stato
        
        # Se stiamo completando il trattamento, impostiamo la data di fine se non è già impostata
        if nuovo_stato == 'completato' and not trattamento.data_fine:
            trattamento.data_fine = timezone.now().date()
        
        trattamento.save()
        messages.success(request, f"Stato del trattamento aggiornato a: {dict(TrattamentoSanitario.STATO_CHOICES)[nuovo_stato]}")
    else:
        messages.error(request, "Stato non valido.")
    
    # Redirect mantenendo il filtro gruppo se applicato
    if apiario.gruppo and apiario.condiviso_con_gruppo:
        return redirect(f'gestione_trattamenti?gruppo_id={apiario.gruppo.id}')
    return redirect('gestione_trattamenti')

@login_required
def mappa_apiari(request):
    """Vista per la mappa degli apiari e delle fioriture"""
    # Ottieni apiari a cui l'utente ha accesso diretto (propri o condivisi in gruppo)
    apiari_propri = list(Apiario.objects.filter(proprietario=request.user))
    
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = list(Apiario.objects.filter(
        gruppo__in=gruppi_utente, 
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user))
    
    # Ottieni apiari visibili sulla mappa in base alle impostazioni di visibilità
    apiari_visibili_gruppo = list(Apiario.objects.filter(
        visibilita_mappa='gruppo',
        gruppo__in=gruppi_utente
    ).exclude(id__in=[a.id for a in apiari_propri]).exclude(id__in=[a.id for a in apiari_condivisi]))
    
    apiari_pubblici = list(Apiario.objects.filter(
        visibilita_mappa='pubblico'
    ).exclude(id__in=[a.id for a in apiari_propri])
     .exclude(id__in=[a.id for a in apiari_condivisi])
     .exclude(id__in=[a.id for a in apiari_visibili_gruppo]))
    
    # Combina tutti gli apiari accessibili all'utente
    apiari = apiari_propri + apiari_condivisi + apiari_visibili_gruppo + apiari_pubblici
    
    # Ottieni la data corrente
    oggi = timezone.now().date()
    
    # Recupera le fioriture attive per gli apiari accessibili
    fioriture_attive = Fioritura.objects.filter(
        apiario__in=apiari,
        data_inizio__lte=oggi
    ).filter(
        Q(data_fine__isnull=True) | Q(data_fine__gte=oggi)
    )
    
    # Recupera le fioriture programmate (future)
    fioriture_programmate = Fioritura.objects.filter(
        apiario__in=apiari,
        data_inizio__gt=oggi
    )
    
    # Recupera le fioriture passate (ultimi 6 mesi)
    sei_mesi_fa = oggi - timedelta(days=180)
    fioriture_passate = Fioritura.objects.filter(
        apiario__in=apiari,
        data_fine__lt=oggi,
        data_fine__gte=sei_mesi_fa
    )
    
    context = {
        'apiari': apiari,
        'apiari_propri': apiari_propri,
        'apiari_condivisi': apiari_condivisi,
        'apiari_visibili_gruppo': apiari_visibili_gruppo,
        'apiari_pubblici': apiari_pubblici,
        'fioriture_attive': fioriture_attive,
        'fioriture_programmate': fioriture_programmate,
        'fioriture_passate': fioriture_passate,
    }
    
    return render(request, 'maps/mappa_apiari.html', context)

@login_required
def seleziona_posizione(request):
    """Vista per selezionare una posizione sulla mappa"""
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    
    context = {
        'lat': lat,
        'lng': lng,
    }
    
    return render(request, 'maps/seleziona_posizione.html', context)

def homepage(request):
    """Vista per la homepage"""
    context = {}
    
    # Se l'utente è autenticato, aggiungi statistiche
    if request.user.is_authenticated:
        # Ottieni la data corrente
        oggi = timezone.now().date()
        primo_del_mese = oggi.replace(day=1)
        
        # Statistiche per arnie attive
        arnie_count = Arnia.objects.filter(attiva=True).count()
        
        # Statistiche per controlli questo mese
        controlli_count = ControlloArnia.objects.filter(
            data__gte=primo_del_mese,
            data__lte=oggi
        ).count()
        
        # Statistiche per fioriture attive
        fioriture_attive = Fioritura.objects.filter(
            data_inizio__lte=oggi
        ).filter(
            Q(data_fine__isnull=True) | Q(data_fine__gte=oggi)
        ).count()
        
        # Statistiche per trattamenti attivi
        trattamenti_attivi = TrattamentoSanitario.objects.filter(
            Q(stato='programmato') | Q(stato='in_corso')
        ).count()
        
        # Aggiungi statistiche al contesto
        context['stats'] = {
            'arnie_count': arnie_count,
            'controlli_count': controlli_count,
            'fioriture_attive': fioriture_attive,
            'trattamenti_attivi': trattamenti_attivi,
        }
    
    return render(request, 'homepage.html', context)

# core/views.py
# Aggiungi queste viste al file esistente

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.db.models import Q

from .models import Gruppo, MembroGruppo, InvitoGruppo
from .forms import GruppoForm, InvitoGruppoForm, MembroGruppoRoleForm, ApiarioGruppoForm

@login_required
def gestione_gruppi(request):
    """Vista per visualizzare e gestire i gruppi dell'utente"""
    # Gruppi di cui l'utente è membro
    gruppi = Gruppo.objects.filter(membri=request.user).distinct()
    
    # Gruppi creati dall'utente
    gruppi_creati = Gruppo.objects.filter(creatore=request.user)
    
    # Inviti ricevuti (basati sull'email dell'utente)
    inviti_ricevuti = InvitoGruppo.objects.filter(
        email=request.user.email,
        stato='inviato',
        data_scadenza__gte=timezone.now()
    )
    
    if request.method == 'POST':
        form = GruppoForm(request.POST)
        if form.is_valid():
            gruppo = form.save(commit=False)
            gruppo.creatore = request.user
            gruppo.save()
            
            # Aggiungi l'utente corrente come membro amministratore
            MembroGruppo.objects.create(
                utente=request.user,
                gruppo=gruppo,
                ruolo='admin'
            )
            
            messages.success(request, f"Gruppo '{gruppo.nome}' creato con successo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    else:
        form = GruppoForm()
    
    context = {
        'gruppi': gruppi,
        'gruppi_creati': gruppi_creati,
        'inviti_ricevuti': inviti_ricevuti,
        'form': form,
    }
    
    return render(request, 'gruppi/gestione_gruppi.html', context)

@login_required
def dettaglio_gruppo(request, gruppo_id):
    """Vista per visualizzare i dettagli di un gruppo"""
    gruppo = get_object_or_404(Gruppo, pk=gruppo_id)
    
    # Verifica che l'utente sia membro del gruppo
    if not gruppo.membri.filter(id=request.user.id).exists():
        messages.error(request, "Non hai accesso a questo gruppo.")
        return redirect('gestione_gruppi')
    
    # Ottieni il ruolo dell'utente nel gruppo
    membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
    is_admin = membro.ruolo == 'admin'
    
    # Ottieni tutti i membri del gruppo
    membri = MembroGruppo.objects.filter(gruppo=gruppo).select_related('utente')
    
    # Ottieni gli inviti attivi
    inviti_attivi = InvitoGruppo.objects.filter(
        gruppo=gruppo,
        stato='inviato',
        data_scadenza__gte=timezone.now()
    )
    
    # Ottieni gli apiari condivisi nel gruppo
    apiari_gruppo = gruppo.apiari.filter(condiviso_con_gruppo=True)
    
    # Form per invitare nuovi membri
    if request.method == 'POST':
        if 'invita' in request.POST and is_admin:
            form_invito = InvitoGruppoForm(request.POST)
            if form_invito.is_valid():
                invito = form_invito.save(commit=False)
                invito.gruppo = gruppo
                invito.invitato_da = request.user
                invito.save()
                
                # Invia email di invito
                invia_email_invito(invito)
                
                messages.success(request, f"Invito inviato a {invito.email}.")
                return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
        elif 'modifica' in request.POST and is_admin:
            form_gruppo = GruppoForm(request.POST, instance=gruppo)
            if form_gruppo.is_valid():
                form_gruppo.save()
                messages.success(request, "Informazioni del gruppo aggiornate.")
                return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    else:
        form_invito = InvitoGruppoForm(initial={'gruppo': gruppo})
        form_gruppo = GruppoForm(instance=gruppo)
    
    context = {
        'gruppo': gruppo,
        'membri': membri,
        'inviti_attivi': inviti_attivi,
        'apiari_gruppo': apiari_gruppo,
        'is_admin': is_admin,
        'form_invito': form_invito,
        'form_gruppo': form_gruppo,
    }
    
    return render(request, 'gruppi/dettaglio_gruppo.html', context)

@login_required
def invita_utente(request, user_id):
    """Vista per invitare un utente a un gruppo"""
    if request.method != 'POST':
        messages.error(request, "Metodo non valido.")
        return redirect('ricerca')
    
    try:
        utente = User.objects.get(pk=user_id)
        gruppo_id = request.POST.get('gruppo')
        ruolo = request.POST.get('ruolo')
        
        if not gruppo_id or not ruolo:
            messages.error(request, "Dati mancanti.")
            return redirect('ricerca')
        
        gruppo = Gruppo.objects.get(pk=gruppo_id)
        
        # Verifica che l'utente corrente sia admin del gruppo
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
            if membro.ruolo != 'admin' and request.user != gruppo.creatore:
                messages.error(request, "Non hai i permessi per invitare utenti a questo gruppo.")
                return redirect('ricerca')
        except MembroGruppo.DoesNotExist:
            messages.error(request, "Non sei membro di questo gruppo.")
            return redirect('ricerca')
        
        # Verifica che l'utente non sia già membro del gruppo
        if gruppo.membri.filter(id=utente.id).exists():
            messages.error(request, f"{utente.username} è già membro del gruppo.")
            return redirect('ricerca')
        
        # Verifica che non esista già un invito attivo
        invito_esistente = InvitoGruppo.objects.filter(
            email=utente.email,
            gruppo=gruppo,
            stato='inviato',
            data_scadenza__gte=timezone.now()
        ).exists()
        
        if invito_esistente:
            messages.error(request, f"Esiste già un invito attivo per {utente.username}.")
            return redirect('ricerca')
        
        # Crea l'invito
        invito = InvitoGruppo(
            gruppo=gruppo,
            email=utente.email,
            ruolo_proposto=ruolo,
            invitato_da=request.user,
            data_scadenza=timezone.now() + timezone.timedelta(days=7)
        )
        invito.save()
        
        # Invia l'email (se la funzione è disponibile)
        try:
            from .views import invia_email_invito
            invia_email_invito(invito)
        except:
            pass
        
        messages.success(request, f"Invito inviato a {utente.username}.")
        return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
        
    except User.DoesNotExist:
        messages.error(request, "Utente non trovato.")
    except Gruppo.DoesNotExist:
        messages.error(request, "Gruppo non trovato.")
    except Exception as e:
        messages.error(request, f"Si è verificato un errore: {str(e)}")

@login_required
def modifica_ruolo_membro(request, membro_id):
    """Vista per modificare il ruolo di un membro del gruppo"""
    membro = get_object_or_404(MembroGruppo, pk=membro_id)
    gruppo = membro.gruppo
    
    # Verifica che l'utente sia amministratore del gruppo
    try:
        membro_richiedente = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        if membro_richiedente.ruolo != 'admin':
            messages.error(request, "Non hai i permessi per modificare i ruoli dei membri.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    except MembroGruppo.DoesNotExist:
        messages.error(request, "Non sei membro di questo gruppo.")
        return redirect('gestione_gruppi')
    
    # Non permettere la modifica del ruolo del creatore del gruppo
    if membro.utente == gruppo.creatore and membro.ruolo == 'admin':
        messages.error(request, "Non puoi modificare il ruolo del creatore del gruppo.")
        return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    
    if request.method == 'POST':
        form = MembroGruppoRoleForm(request.POST, instance=membro)
        if form.is_valid():
            form.save()
            messages.success(request, f"Ruolo di {membro.utente.username} aggiornato a {membro.get_ruolo_display()}.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    else:
        form = MembroGruppoRoleForm(instance=membro)
    
    context = {
        'form': form,
        'membro': membro,
        'gruppo': gruppo,
    }
    
    return render(request, 'gruppi/modifica_ruolo.html', context)

@login_required
def rimuovi_membro(request, membro_id):
    """Vista per rimuovere un membro dal gruppo"""
    membro = get_object_or_404(MembroGruppo, pk=membro_id)
    gruppo = membro.gruppo
    
    # Verifica che l'utente sia amministratore del gruppo o si stia rimuovendo da solo
    is_self_removal = membro.utente == request.user
    
    try:
        membro_richiedente = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        is_admin = membro_richiedente.ruolo == 'admin'
        
        if not (is_admin or is_self_removal):
            messages.error(request, "Non hai i permessi per rimuovere membri dal gruppo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    except MembroGruppo.DoesNotExist:
        messages.error(request, "Non sei membro di questo gruppo.")
        return redirect('gestione_gruppi')
    
    # Non permettere la rimozione del creatore del gruppo
    if membro.utente == gruppo.creatore and not is_self_removal:
        messages.error(request, "Non puoi rimuovere il creatore del gruppo.")
        return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    
    if request.method == 'POST':
        # Se è l'ultimo amministratore e si sta rimuovendo
        if is_self_removal and membro.ruolo == 'admin':
            admin_count = MembroGruppo.objects.filter(gruppo=gruppo, ruolo='admin').count()
            if admin_count <= 1:
                # Trova un altro membro da promuovere ad admin
                altro_membro = MembroGruppo.objects.filter(gruppo=gruppo).exclude(utente=request.user).first()
                if altro_membro:
                    altro_membro.ruolo = 'admin'
                    altro_membro.save()
                    messages.info(request, f"{altro_membro.utente.username} è stato promosso ad amministratore.")
                else:
                    # Se non ci sono altri membri, elimina il gruppo
                    nome_gruppo = gruppo.nome
                    gruppo.delete()
                    messages.info(request, f"Il gruppo '{nome_gruppo}' è stato eliminato poiché non ha più membri.")
                    return redirect('gestione_gruppi')
        
        # Ottieni il nome dell'utente prima di rimuoverlo
        nome_utente = membro.utente.username
        
        # Rimuovi il membro
        membro.delete()
        
        if is_self_removal:
            messages.success(request, f"Hai lasciato il gruppo '{gruppo.nome}'.")
            return redirect('gestione_gruppi')
        else:
            messages.success(request, f"{nome_utente} è stato rimosso dal gruppo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    
    context = {
        'membro': membro,
        'gruppo': gruppo,
        'is_self_removal': is_self_removal,
    }
    
    return render(request, 'gruppi/conferma_rimozione.html', context)

@login_required
def elimina_gruppo(request, gruppo_id):
    """Vista per eliminare un gruppo"""
    gruppo = get_object_or_404(Gruppo, pk=gruppo_id)
    
    # Verifica che l'utente sia il creatore o un amministratore del gruppo
    try:
        membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        if membro.ruolo != 'admin':
            messages.error(request, "Solo gli amministratori possono eliminare il gruppo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    except MembroGruppo.DoesNotExist:
        messages.error(request, "Non sei membro di questo gruppo.")
        return redirect('gestione_gruppi')
    
    if request.method == 'POST':
        nome_gruppo = gruppo.nome
        gruppo.delete()
        messages.success(request, f"Il gruppo '{nome_gruppo}' è stato eliminato.")
        return redirect('gestione_gruppi')
    
    context = {
        'gruppo': gruppo,
    }
    
    return render(request, 'gruppi/conferma_eliminazione_gruppo.html', context)

@login_required
def gestisci_invito(request, invito_id, azione):
    """Vista per accettare o rifiutare un invito"""
    invito = get_object_or_404(InvitoGruppo, pk=invito_id)
    
    # Verifica che l'invito sia per l'utente corrente
    if invito.email != request.user.email:
        messages.error(request, "Questo invito non è destinato a te.")
        return redirect('gestione_gruppi')
    
    # Verifica che l'invito sia ancora valido
    if not invito.is_valid():
        messages.error(request, "Questo invito è scaduto o non è più valido.")
        return redirect('gestione_gruppi')
    
    if azione == 'accetta':
        # Crea una nuova relazione membro-gruppo
        MembroGruppo.objects.create(
            utente=request.user,
            gruppo=invito.gruppo,
            ruolo=invito.ruolo_proposto
        )
        
        # Aggiorna lo stato dell'invito
        invito.stato = 'accettato'
        invito.save()
        
        messages.success(request, f"Hai accettato l'invito al gruppo '{invito.gruppo.nome}'.")
        return redirect('dettaglio_gruppo', gruppo_id=invito.gruppo.id)
    
    elif azione == 'rifiuta':
        # Aggiorna lo stato dell'invito
        invito.stato = 'rifiutato'
        invito.save()
        
        messages.info(request, f"Hai rifiutato l'invito al gruppo '{invito.gruppo.nome}'.")
        return redirect('gestione_gruppi')
    
    return redirect('gestione_gruppi')

@login_required
def annulla_invito(request, invito_id):
    """Vista per annullare un invito inviato"""
    invito = get_object_or_404(InvitoGruppo, pk=invito_id)
    gruppo = invito.gruppo
    
    # Verifica che l'utente sia amministratore del gruppo
    try:
        membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        if membro.ruolo != 'admin':
            messages.error(request, "Solo gli amministratori possono annullare gli inviti.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    except MembroGruppo.DoesNotExist:
        messages.error(request, "Non sei membro di questo gruppo.")
        return redirect('gestione_gruppi')
    
    # Annulla l'invito
    invito.stato = 'scaduto'
    invito.save()
    
    messages.success(request, f"Invito a {invito.email} annullato.")
    return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)

@login_required
def condividi_apiario(request, apiario_id):
    """Vista per condividere un apiario con un gruppo"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Verifica che l'utente sia il proprietario dell'apiario
    if apiario.proprietario != request.user:
        messages.error(request, "Solo il proprietario può condividere l'apiario.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = ApiarioGruppoForm(request.POST, instance=apiario, user=request.user)
        if form.is_valid():
            form.save()
            
            if apiario.condiviso_con_gruppo and apiario.gruppo:
                messages.success(request, f"L'apiario è stato condiviso con il gruppo '{apiario.gruppo.nome}'.")
            else:
                messages.success(request, "L'apiario non è più condiviso con il gruppo.")
                
            return redirect('visualizza_apiario', apiario_id=apiario.id)
    else:
        form = ApiarioGruppoForm(instance=apiario, user=request.user)
    
    context = {
        'form': form,
        'apiario': apiario,
    }
    
    return render(request, 'gruppi/condividi_apiario.html', context)

def invia_email_invito(invito):
    """Funzione per inviare email di invito"""
    subject = f"Invito a unirti al gruppo {invito.gruppo.nome} su Gestione Apiario"
    
    # Costruisci l'URL per accettare l'invito
    accept_url = reverse('attiva_invito', kwargs={'token': invito.token})
    
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

@login_required
def attiva_invito(request, token):
    """Vista per attivare un invito tramite token (da link email)"""
    try:
        invito = InvitoGruppo.objects.get(token=token)
    except InvitoGruppo.DoesNotExist:
        messages.error(request, "Invito non valido o scaduto.")
        return redirect('gestione_gruppi')
    
    # Verifica che l'invito sia ancora valido
    if not invito.is_valid():
        messages.error(request, "Questo invito è scaduto o non è più valido.")
        return redirect('gestione_gruppi')
    
    # Verifica che l'email dell'invito corrisponda all'utente corrente
    if invito.email != request.user.email:
        messages.error(request, "Questo invito è destinato a un altro indirizzo email.")
        return redirect('gestione_gruppi')
    
    # Mostra la pagina di conferma
    if request.method == 'POST':
        if 'accetta' in request.POST:
            # Crea una nuova relazione membro-gruppo
            MembroGruppo.objects.create(
                utente=request.user,
                gruppo=invito.gruppo,
                ruolo=invito.ruolo_proposto
            )
            
            # Aggiorna lo stato dell'invito
            invito.stato = 'accettato'
            invito.save()
            
            messages.success(request, f"Hai accettato l'invito al gruppo '{invito.gruppo.nome}'.")
            return redirect('dettaglio_gruppo', gruppo_id=invito.gruppo.id)
        
        elif 'rifiuta' in request.POST:
            # Aggiorna lo stato dell'invito
            invito.stato = 'rifiutato'
            invito.save()
            
            messages.info(request, f"Hai rifiutato l'invito al gruppo '{invito.gruppo.nome}'.")
            return redirect('gestione_gruppi')
    
    context = {
        'invito': invito,
    }
    
    return render(request, 'gruppi/attiva_invito.html', context)

from django.contrib.auth.models import User
from django.db.models import Q
@login_required
def ricerca(request):
    """Vista per la ricerca di utenti e gruppi"""
    query = request.GET.get('q', '')
    tipo = request.GET.get('tipo', 'tutti')  # 'utenti', 'gruppi', o 'tutti'
    
    utenti = []
    gruppi = []
    
    if query:
        if tipo in ['utenti', 'tutti']:
            # Ricerca utenti
            utenti = User.objects.filter(
                Q(username__icontains=query) | 
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).distinct()
        
        if tipo in ['gruppi', 'tutti']:
            # Ricerca gruppi
            gruppi_query = Gruppo.objects.filter(
                Q(nome__icontains=query) | 
                Q(descrizione__icontains=query)
            )
            
            # Filtra in base ai gruppi a cui l'utente ha accesso
            gruppi_propri = gruppi_query.filter(creatore=request.user)
            gruppi_membro = gruppi_query.filter(membri=request.user)
            
            # Unisci i risultati
            gruppi = (gruppi_propri | gruppi_membro).distinct()
    
    context = {
        'query': query,
        'tipo': tipo,
        'utenti': utenti,
        'gruppi': gruppi,
    }
    
    return render(request, 'ricerca/risultati.html', context)

# Aggiungi queste viste al file views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Profilo, ImmagineProfilo, MembroGruppo
from .forms import UserUpdateForm, ProfiloUpdateForm, GruppoImmagineForm
from .decorators import richiedi_ruolo_admin, richiedi_permesso_scrittura

@login_required
def profilo(request, username=None):
    """Vista per visualizzare il profilo di un utente"""
    # Se non è specificato un username, mostra il profilo dell'utente loggato
    if username is None:
        user = request.user
    else:
        user = get_object_or_404(User, username=username)
    
    # Ottieni gli apiari dell'utente
    apiari_propri = user.apiari_posseduti.all()
    
    # Ottieni i gruppi dell'utente
    gruppi = user.gruppi.all()
    
    # Controlla se l'utente corrente può modificare questo profilo
    can_edit = (user == request.user)
    
    context = {
        'user_profile': user,
        'apiari': apiari_propri,
        'gruppi': gruppi,
        'can_edit': can_edit,
    }
    
    return render(request, 'profilo/profilo.html', context)

@login_required
def modifica_profilo(request):
    """Vista per modificare il proprio profilo"""
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfiloUpdateForm(request.POST, request.FILES, instance=request.user.profilo)
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, "Il tuo profilo è stato aggiornato con successo.")
            return redirect('profilo')
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfiloUpdateForm(instance=request.user.profilo)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    
    return render(request, 'profilo/modifica_profilo.html', context)

@login_required
@richiedi_permesso_scrittura
def modifica_immagine_gruppo(request, gruppo_id):
    """Vista per modificare l'immagine del profilo del gruppo"""
    gruppo = get_object_or_404(request.user.gruppi, id=gruppo_id)
    
    # Verifica se l'utente ha i permessi per modificare il gruppo (admin o editor)
    try:
        membro = MembroGruppo.objects.get(utente=request.user, gruppo=gruppo)
        if membro.ruolo not in ['admin', 'editor']:
            messages.error(request, "Non hai i permessi per modificare l'immagine del gruppo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    except MembroGruppo.DoesNotExist:
        messages.error(request, "Non sei membro di questo gruppo.")
        return redirect('gestione_gruppi')
    
    # Ottieni o crea l'oggetto immagine profilo
    try:
        immagine_profilo = gruppo.immagine_profilo
    except:
        immagine_profilo = ImmagineProfilo.objects.create(gruppo=gruppo)
    
    if request.method == 'POST':
        form = GruppoImmagineForm(request.POST, request.FILES, instance=immagine_profilo)
        if form.is_valid():
            form.save()
            messages.success(request, "L'immagine del gruppo è stata aggiornata con successo.")
            return redirect('dettaglio_gruppo', gruppo_id=gruppo.id)
    else:
        form = GruppoImmagineForm(instance=immagine_profilo)
    
    context = {
        'form': form,
        'gruppo': gruppo,
    }
    
    return render(request, 'gruppi/modifica_immagine_gruppo.html', context)

# Altre viste necessarie per la gestione completa
class ArniaCreateView(LoginRequiredMixin, CreateView):
    model = Arnia
    form_class = ArniaForm
    template_name = 'arnie/form_arnia.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Verifica i permessi prima di procedere
        apiario_id = self.request.GET.get('apiario_id') or self.request.POST.get('apiario')
        if apiario_id:
            apiario = get_object_or_404(Apiario, pk=apiario_id)
            
            # Se l'utente è il proprietario, ha sempre accesso
            if apiario.proprietario == request.user:
                return super().dispatch(request, *args, **kwargs)
            
            # Se l'apiario è condiviso con un gruppo
            if apiario.gruppo and apiario.condiviso_con_gruppo:
                # Verifica che l'utente sia membro del gruppo con ruolo appropriato
                try:
                    membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
                    if membro.ruolo in ['admin', 'editor']:
                        return super().dispatch(request, *args, **kwargs)
                    else:
                        messages.error(request, "Non hai i permessi necessari per aggiungere arnie in questo gruppo.")
                        return redirect('visualizza_apiario', apiario_id=apiario.id)
                except MembroGruppo.DoesNotExist:
                    messages.error(request, "Non sei membro del gruppo che ha accesso a questo apiario.")
                    return redirect('dashboard')
            else:
                messages.error(request, "Non hai accesso a questo apiario.")
                return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_success_url(self):
        return reverse_lazy('visualizza_apiario', kwargs={'apiario_id': self.object.apiario.id})

    def form_valid(self, form):
        # Imposta il proprietario predefinito come l'utente corrente se non specificato
        apiario = form.cleaned_data.get('apiario')
        if apiario and not hasattr(apiario, 'proprietario'):
            apiario.proprietario = self.request.user
            apiario.save()
            
        return super().form_valid(form)

class ArniaUpdateView(LoginRequiredMixin, UpdateView):
    model = Arnia
    form_class = ArniaForm
    template_name = 'arnie/form_arnia.html'
    
    def get_success_url(self):
        return reverse_lazy('visualizza_apiario', kwargs={'apiario_id': self.object.apiario.id})

class ApiarioCreateView(LoginRequiredMixin, CreateView):
    model = Apiario
    form_class = ApiarioForm
    template_name = 'apiari/form_apiario.html'
    success_url = reverse_lazy('dashboard')

class FiorituraUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Fioritura
    form_class = FiorituraForm
    template_name = 'fioriture/form_fioritura.html'
    success_url = reverse_lazy('gestione_fioriture')
    
    def test_func(self):
        # Verifica dei permessi
        fioritura = self.get_object()
        
        # Admin hanno sempre accesso
        if self.request.user.is_staff or self.request.user.is_superuser:
            return True
            
        # Proprietario dell'apiario ha sempre accesso
        if fioritura.apiario and fioritura.apiario.proprietario == self.request.user:
            return True
            
        # Admin del gruppo hanno accesso
        if fioritura.apiario and fioritura.apiario.gruppo and fioritura.apiario.condiviso_con_gruppo:
            try:
                membro = MembroGruppo.objects.get(utente=self.request.user, gruppo=fioritura.apiario.gruppo)
                if membro.ruolo in ['admin', 'editor']:
                    return True
            except MembroGruppo.DoesNotExist:
                pass
        
        # Creatore della fioritura ha accesso
        if hasattr(fioritura, 'creatore') and fioritura.creatore == self.request.user:
            return True
            
        return False

