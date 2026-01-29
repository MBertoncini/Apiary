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
    TrattamentoSanitario, TipoTrattamento, Gruppo, MembroGruppo, InvitoGruppo, Melario, Smielatura, Regina, StoriaRegine,
    CategoriaAttrezzatura, Attrezzatura, ManutenzioneAttrezzatura, PrestitoAttrezzatura, SpesaAttrezzatura, InventarioAttrezzature
)
from .forms import (
    ApiarioForm, ArniaForm, ControlloArniaForm, FiorituraForm, PagamentoForm,
    QuotaUtenteForm, TrattamentoSanitarioForm, TipoTrattamentoForm, GruppoForm,
    InvitoGruppoForm, MembroGruppoRoleForm, ApiarioGruppoForm, RimozioneMelarioForm, SmielaturaForm, MelarioForm, ReginaForm,
    SostituzioneReginaForm, CategoriaAttrezzaturaForm, AttrezzaturaForm, AttrezzaturaFiltroForm, ManutenzioneAttrezzaturaForm,
    PrestitoAttrezzaturaForm, RestituzioneAttrezzaturaForm, SpesaAttrezzaturaForm, RicercaReginaForm,
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
        # Calcola la distribuzione dei telaini di scorte (per retrocompatibilità)
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
            
            # Salva la configurazione dei telaini se presente
            if 'telaini_config' in request.POST:
                controllo.telaini_config = request.POST['telaini_config']
                
            controllo.save()
            messages.success(request, "Controllo registrato con successo.")
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
            controllo = form.save(commit=False)
            
            # Salva la configurazione dei telaini se presente
            if 'telaini_config' in request.POST:
                controllo.telaini_config = request.POST['telaini_config']
                
            controllo.save()
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

# Aggiungi al file views.py

@login_required
@richiedi_permesso_scrittura
def visualizza_regina(request, arnia_id):
    """Vista per visualizzare i dettagli della regina di un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    apiario = arnia.apiario
    
    # Verifica i permessi di accesso
    can_edit = False
    if apiario.proprietario == request.user:
        can_edit = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_edit = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            pass
    
    # Ottieni la regina corrente o None
    try:
        regina = arnia.regina
    except Regina.DoesNotExist:
        regina = None
    
    # Ottieni la storia delle regine per questa arnia
    storia_regine = StoriaRegine.objects.filter(arnia=arnia).order_by('-data_inizio')
    
    # Ottieni l'albero genealogico se la regina esiste
    genealogia = []
    if regina:
        # Prepara la genealogia per 3 generazioni
        current = regina
        genealogia = [current]
        
        # Prima generazione (regina madre)
        if current.regina_madre:
            genealogia.append(current.regina_madre)
            current = current.regina_madre
            
            # Seconda generazione (nonna)
            if current.regina_madre:
                genealogia.append(current.regina_madre)
    
    # Ottieni tutte le figlie della regina corrente
    figlie = []
    if regina:
        figlie = Regina.objects.filter(regina_madre=regina)
    
    context = {
        'arnia': arnia,
        'apiario': apiario,
        'regina': regina,
        'storia_regine': storia_regine,
        'genealogia': genealogia,
        'figlie': figlie,
        'can_edit': can_edit,
    }
    
    return render(request, 'regine/dettaglio_regina.html', context)

@login_required
@richiedi_permesso_scrittura
def aggiungi_regina(request, arnia_id):
    """Vista per aggiungere una regina a un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    apiario = arnia.apiario
    
    # Verifica se esiste già una regina
    regina_esistente = None
    try:
        regina_esistente = arnia.regina
    except Regina.DoesNotExist:
        pass
    
    if regina_esistente:
        messages.error(request, "Questa arnia ha già una regina. Per sostituirla usa l'apposita funzione.")
        return redirect('visualizza_regina', arnia_id=arnia.id)
    
    if request.method == 'POST':
        form = ReginaForm(request.POST, arnia=arnia)
        if form.is_valid():
            regina = form.save(commit=False)
            regina.arnia = arnia
            regina.save()
            
            # Crea un record nella storia delle regine
            StoriaRegine.objects.create(
                arnia=arnia,
                regina=regina,
                data_inizio=form.cleaned_data['data_introduzione']
            )
            
            messages.success(request, "Regina aggiunta con successo.")
            return redirect('visualizza_regina', arnia_id=arnia.id)
    else:
        form = ReginaForm(arnia=arnia)
    
    context = {
        'form': form,
        'arnia': arnia,
        'apiario': apiario,
        'is_new': True,
    }
    
    return render(request, 'regine/form_regina.html', context)

@login_required
@richiedi_permesso_scrittura
def modifica_regina(request, regina_id):
    """Vista per modificare i dati di una regina"""
    regina = get_object_or_404(Regina, pk=regina_id)
    arnia = regina.arnia
    apiario = arnia.apiario
    
    if request.method == 'POST':
        form = ReginaForm(request.POST, instance=regina)
        if form.is_valid():
            form.save()
            messages.success(request, "Dati della regina aggiornati con successo.")
            return redirect('visualizza_regina', arnia_id=arnia.id)
    else:
        form = ReginaForm(instance=regina)
    
    context = {
        'form': form,
        'regina': regina,
        'arnia': arnia,
        'apiario': apiario,
        'is_new': False,
    }
    
    return render(request, 'regine/form_regina.html', context)

@login_required
@richiedi_permesso_scrittura
def sostituisci_regina(request, arnia_id):
    """Vista per sostituire la regina di un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    apiario = arnia.apiario
    
    # Verifica se esiste una regina corrente
    try:
        regina_vecchia = arnia.regina
    except Regina.DoesNotExist:
        messages.error(request, "Non c'è una regina registrata per questa arnia. Usa 'Aggiungi Regina'.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = SostituzioneReginaForm(request.POST)
        if form.is_valid():
            # Aggiorna la regina vecchia
            regina_vecchia.attiva = False
            regina_vecchia.save()
            
            # Aggiorna la storia delle regine
            try:
                storia_regina_vecchia = StoriaRegine.objects.filter(
                    arnia=arnia, 
                    regina=regina_vecchia, 
                    data_fine__isnull=True
                ).latest('data_inizio')
                
                storia_regina_vecchia.data_fine = form.cleaned_data['data_sostituzione']
                storia_regina_vecchia.motivo_fine = form.cleaned_data['motivo']
                storia_regina_vecchia.save()
            except StoriaRegine.DoesNotExist:
                # Se non esiste un record nella storia, lo creiamo
                StoriaRegine.objects.create(
                    arnia=arnia,
                    regina=regina_vecchia,
                    data_inizio=regina_vecchia.data_introduzione,
                    data_fine=form.cleaned_data['data_sostituzione'],
                    motivo_fine=form.cleaned_data['motivo']
                )
            
            # Crea la nuova regina
            nuova_regina = Regina(
                arnia=arnia,
                data_nascita=form.cleaned_data['nuova_regina_data_nascita'],
                data_introduzione=form.cleaned_data['data_sostituzione'],
                origine=form.cleaned_data['nuova_regina_origine'],
                razza=form.cleaned_data['nuova_regina_razza'],
                marcata=form.cleaned_data['nuova_regina_marcata'],
                codice_marcatura=form.cleaned_data['nuova_regina_codice'],
                colore_marcatura=form.cleaned_data['nuova_regina_colore_marcatura'],
                note=form.cleaned_data['note']
            )
            nuova_regina.save()
            
            # Aggiungi alla storia delle regine
            StoriaRegine.objects.create(
                arnia=arnia,
                regina=nuova_regina,
                data_inizio=form.cleaned_data['data_sostituzione'],
                note=form.cleaned_data['note']
            )
            
            messages.success(request, "Regina sostituita con successo.")
            return redirect('visualizza_regina', arnia_id=arnia.id)
    else:
        form = SostituzioneReginaForm()
    
    context = {
        'form': form,
        'arnia': arnia,
        'apiario': apiario,
        'regina_vecchia': regina_vecchia,
    }
    
    return render(request, 'regine/sostituisci_regina.html', context)

@login_required
def albero_genealogico(request, regina_id):
    """Vista per visualizzare l'albero genealogico completo di una regina"""
    regina = get_object_or_404(Regina, pk=regina_id)
    arnia = regina.arnia
    apiario = arnia.apiario
    
    # Verifica accesso
    if apiario.proprietario != request.user:
        # Verifica se l'apiario è condiviso con un gruppo di cui l'utente fa parte
        if apiario.gruppo and apiario.condiviso_con_gruppo:
            if not MembroGruppo.objects.filter(utente=request.user, gruppo=apiario.gruppo).exists():
                messages.error(request, "Non hai accesso a questa risorsa.")
                return redirect('dashboard')
        else:
            messages.error(request, "Non hai accesso a questa risorsa.")
            return redirect('dashboard')
    
    # Costruisci l'albero genealogico
    # In questa versione useremo un approccio semplice, solo fino a 3 generazioni indietro
    
    # Prepariamo i dati per il template
    genealogia = {
        'regina': regina,
        'madre': None,
        'nonna_materna': None,
        'bisnonna_materna': None,
    }
    
    # Trova la madre
    if regina.regina_madre:
        genealogia['madre'] = regina.regina_madre
        
        # Trova la nonna
        if regina.regina_madre.regina_madre:
            genealogia['nonna_materna'] = regina.regina_madre.regina_madre
            
            # Trova la bisnonna
            if regina.regina_madre.regina_madre.regina_madre:
                genealogia['bisnonna_materna'] = regina.regina_madre.regina_madre.regina_madre
    
    # Trova tutte le figlie (sorelle)
    figlie = Regina.objects.filter(regina_madre=regina)
    
    context = {
        'regina': regina,
        'arnia': arnia,
        'apiario': apiario,
        'genealogia': genealogia,
        'figlie': figlie,
    }
    
    return render(request, 'regine/albero_genealogico.html', context)

# Aggiungi questa funzione alle viste esistenti per aggiornare la presenza regina durante i controlli
@login_required
def aggiorna_presenza_regina(request, controllo_id):
    """Aggiorna lo stato della regina dopo un controllo"""
    controllo = get_object_or_404(ControlloArnia, pk=controllo_id)
    arnia = controllo.arnia
    
    # Verifica permessi
    apiario = arnia.apiario
    can_edit = False
    if apiario.proprietario == request.user:
        can_edit = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_edit = membro.ruolo in ['admin', 'editor']
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_edit:
        messages.error(request, "Non hai i permessi necessari.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    try:
        regina = arnia.regina
    except Regina.DoesNotExist:
        regina = None
    
    if request.method == 'POST':
        # Aggiorna i campi relativi alla regina
        regina_vista = request.POST.get('regina_vista') == 'on'
        uova_fresche = request.POST.get('uova_fresche') == 'on'
        celle_reali = request.POST.get('celle_reali') == 'on'
        numero_celle_reali = int(request.POST.get('numero_celle_reali', 0) or 0)
        regina_sostituita = request.POST.get('regina_sostituita') == 'on'
        
        # Aggiorna il controllo
        controllo.regina_vista = regina_vista
        controllo.uova_fresche = uova_fresche
        controllo.celle_reali = celle_reali
        controllo.numero_celle_reali = numero_celle_reali
        controllo.regina_sostituita = regina_sostituita
        controllo.save()
        
        # Se la regina è stata vista, aggiorna la presenza regina
        if regina_vista and regina:
            # Aggiorna l'ultimo avvistamento della regina
            regina.ultimo_avvistamento = controllo.data
            regina.save()
        
        # Se la regina è stata sostituita, reindirizza alla schermata di sostituzione
        if regina_sostituita:
            return redirect('sostituisci_regina', arnia_id=arnia.id)
        
        messages.success(request, "Informazioni sulla regina aggiornate.")
        return redirect('visualizza_apiario', apiario_id=apiario.id)
    
    context = {
        'controllo': controllo,
        'arnia': arnia,
        'regina': regina,
    }
    
    return render(request, 'regine/aggiorna_presenza_regina.html', context)

@login_required
@richiedi_proprietario_o_gruppo
def gestione_melari(request, apiario_id):
    """Vista per la gestione dei melari di un apiario"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Ottieni le arnie attive dell'apiario
    arnie = Arnia.objects.filter(apiario=apiario, attiva=True)
    
    # Recupera i controlli dell'arnia per ogni arnia
    ultimi_controlli = []
    for arnia in arnie:
        try:
            controllo = ControlloArnia.objects.filter(
                arnia=arnia
            ).order_by('-data').first()
            
            if controllo:
                ultimi_controlli.append(controllo)
        except ControlloArnia.DoesNotExist:
            pass
    
    # Recupera tutte le smielature dell'apiario
    smielature = Smielatura.objects.filter(apiario=apiario).order_by('-data')
    
    # Verifica se ci sono melari in stato 'in_smielatura'
    any_melari_in_smielatura = Melario.objects.filter(
        arnia__apiario=apiario,
        stato='in_smielatura'
    ).exists()
    
    # Prepara i melari in smielatura per ogni arnia
    melari_in_smielatura = {}
    for arnia in arnie:
        melari_in_smielatura[arnia.id] = list(Melario.objects.filter(
            arnia=arnia,
            stato='in_smielatura'
        ).order_by('-posizione'))
    
    context = {
        'apiario': apiario,
        'arnie': arnie,
        'ultimi_controlli': ultimi_controlli,
        'smielature': smielature,
        'today': timezone.now().date(),
        'any_melari_in_smielatura': any_melari_in_smielatura,
        'melari_in_smielatura': melari_in_smielatura,
    }
    
    return render(request, 'melari/gestione_melari.html', context)

@login_required
@richiedi_permesso_scrittura
def aggiungi_melario(request, arnia_id):
    """Vista per aggiungere un melario a un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    apiario = arnia.apiario
    
    if request.method == 'POST':
        form = MelarioForm(request.POST, arnia=arnia)
        if form.is_valid():
            melario = form.save(commit=False)
            melario.arnia = arnia
            melario.stato = 'posizionato'
            melario.save()
            
            messages.success(request, f"Melario aggiunto all'arnia {arnia.numero}.")
            return redirect('gestione_melari', apiario_id=apiario.id)
    else:
        form = MelarioForm(arnia=arnia)
    
    context = {
        'form': form,
        'arnia': arnia,
        'apiario': apiario,
    }
    
    return render(request, 'melari/form_melario.html', context)

@login_required
@richiedi_permesso_scrittura
def rimuovi_melario(request, melario_id):
    """Vista per rimuovere un melario da un'arnia"""
    melario = get_object_or_404(Melario, pk=melario_id)
    arnia = melario.arnia
    apiario = arnia.apiario
    
    # Verifica che il melario sia nello stato 'posizionato'
    if melario.stato != 'posizionato':
        messages.error(request, f"Il melario è nello stato '{melario.get_stato_display()}' e non può essere rimosso.")
        return redirect('gestione_melari', apiario_id=apiario.id)
    
    if request.method == 'POST':
        form = RimozioneMelarioForm(request.POST)
        if form.is_valid():
            # Aggiorna lo stato e la data di rimozione
            melario.stato = 'rimosso'
            melario.data_rimozione = form.cleaned_data['data_rimozione']
            if form.cleaned_data['note']:
                melario.note = (melario.note or "") + "\n\nRimozione: " + form.cleaned_data['note']
            melario.save()
            
            messages.success(request, f"Melario rimosso dall'arnia {arnia.numero}.")
            return redirect('gestione_melari', apiario_id=apiario.id)
    else:
        form = RimozioneMelarioForm()
    
    context = {
        'form': form,
        'melario': melario,
        'arnia': arnia,
        'apiario': apiario,
    }
    
    return render(request, 'melari/rimuovi_melario.html', context)

@login_required
@richiedi_permesso_scrittura
def invia_in_smielatura(request, melario_id):
    """Vista per inviare un melario in smielatura"""
    melario = get_object_or_404(Melario, pk=melario_id)
    arnia = melario.arnia
    apiario = arnia.apiario
    
    # Verifica che il melario sia nello stato 'posizionato'
    if melario.stato != 'posizionato':
        messages.error(request, f"Il melario è nello stato '{melario.get_stato_display()}' e non può essere mandato in smielatura.")
        return redirect('gestione_melari', apiario_id=apiario.id)
    
    # Cambia lo stato del melario
    melario.stato = 'in_smielatura'
    melario.data_rimozione = timezone.now().date()
    if request.POST.get('notes'):
        melario.note = (melario.note or "") + "\n\nInvio in smielatura: " + request.POST.get('notes')
    melario.save()
    
    messages.success(request, f"Melario inviato in smielatura.")
    return redirect('gestione_melari', apiario_id=apiario.id)

@login_required
@richiedi_permesso_scrittura
def registra_smielatura(request, apiario_id):
    """Vista per registrare una smielatura"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    if request.method == 'POST':
        form = SmielaturaForm(request.POST, apiario=apiario)
        if form.is_valid():
            smielatura = form.save(commit=False)
            smielatura.apiario = apiario
            smielatura.utente = request.user
            smielatura.save()
            
            # Salva i melari associati alla smielatura
            form.save_m2m()
            
            # Aggiorna lo stato dei melari
            for melario in form.cleaned_data['melari']:
                melario.stato = 'smielato'
                melario.save()
            
            messages.success(request, f"Smielatura registrata con successo: {form.cleaned_data['quantita_miele']} kg di {form.cleaned_data['tipo_miele']}.")
            return redirect('gestione_melari', apiario_id=apiario.id)
    else:
        form = SmielaturaForm(apiario=apiario)
    
    context = {
        'form': form,
        'apiario': apiario,
    }
    
    return render(request, 'melari/form_smielatura.html', context)

@login_required
def dettaglio_smielatura(request, smielatura_id):
    """Vista per visualizzare i dettagli di una smielatura"""
    smielatura = get_object_or_404(Smielatura, pk=smielatura_id)
    apiario = smielatura.apiario
    
    # Verifica permessi
    if apiario.proprietario != request.user:
        # Se l'apiario è condiviso con un gruppo, verifica l'appartenenza dell'utente
        if apiario.gruppo and apiario.condiviso_con_gruppo:
            try:
                membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            except MembroGruppo.DoesNotExist:
                messages.error(request, "Non hai i permessi per visualizzare questa smielatura.")
                return redirect('dashboard')
        else:
            messages.error(request, "Non hai i permessi per visualizzare questa smielatura.")
            return redirect('dashboard')
    
    # Raggruppa i melari per arnia
    melari_per_arnia = {}
    for melario in smielatura.melari.all().select_related('arnia'):
        arnia_id = melario.arnia.id
        if arnia_id not in melari_per_arnia:
            melari_per_arnia[arnia_id] = {
                'arnia': melario.arnia,
                'melari': []
            }
        melari_per_arnia[arnia_id]['melari'].append(melario)
    
    context = {
        'smielatura': smielatura,
        'apiario': apiario,
        'melari_per_arnia': melari_per_arnia,
    }
    
    return render(request, 'melari/dettaglio_smielatura.html', context)

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

# Aggiungi queste funzioni a views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q, F, Count
from datetime import datetime, timedelta
from django.utils import timezone

@login_required
def calendario_apiario(request, apiario_id=None):
    """Vista per visualizzare il calendario degli eventi di un apiario specifico o di tutti gli apiari"""
    # Recupera l'apiario selezionato, se specificato
    apiario = None
    if apiario_id:
        apiario = get_object_or_404(Apiario, pk=apiario_id)
        
        # Verifica che l'utente abbia accesso all'apiario
        if apiario.proprietario != request.user:
            # Se l'apiario è condiviso con un gruppo di cui l'utente fa parte
            if not (apiario.gruppo and apiario.condiviso_con_gruppo and 
                    MembroGruppo.objects.filter(utente=request.user, gruppo=apiario.gruppo).exists()):
                messages.error(request, "Non hai accesso a questo apiario.")
                return redirect('dashboard')
    
    # Recupera il gruppo selezionato, se specificato
    gruppo_id = request.GET.get('gruppo_id')
    gruppo = None
    if gruppo_id:
        gruppo = get_object_or_404(Gruppo, pk=gruppo_id)
        # Verifica che l'utente sia membro del gruppo
        if not MembroGruppo.objects.filter(utente=request.user, gruppo=gruppo).exists():
            messages.error(request, "Non sei membro di questo gruppo.")
            return redirect('calendario_apiario')
    
    # Recupera tutti gli apiari a cui l'utente ha accesso
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    
    # Apiari condivisi tramite gruppi
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente, 
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)
    
    # Unisci gli apiari
    apiari = (apiari_propri | apiari_condivisi).distinct()
    
    context = {
        'apiario': apiario,
        'gruppo': gruppo,
        'apiari': apiari,
        'gruppi': gruppi_utente,
    }
    
    return render(request, 'calendario/calendario_apiario.html', context)

@login_required
def calendario_eventi_json(request):
    """API che restituisce gli eventi del calendario in formato JSON"""
    # Filtra per apiario se specificato
    apiario_id = request.GET.get('apiario_id')
    gruppo_id = request.GET.get('gruppo_id')
    
    # Date di inizio e fine per il periodo richiesto (se specificato dal client)
    start_date = request.GET.get('start', (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.GET.get('end', (timezone.now() + timedelta(days=60)).strftime('%Y-%m-%d'))
    
    # Converti le date in oggetti datetime
    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Lista eventi che verrà restituita
    events = []
    
    # Apiari a cui l'utente ha accesso
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente, 
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)

    # Filtra per gruppo se specificato
    if gruppo_id:
        apiari_propri = apiari_propri.filter(gruppo_id=gruppo_id)
        apiari_condivisi = apiari_condivisi.filter(gruppo_id=gruppo_id)
    
    # Filtra per apiario se specificato
    if apiario_id:
        apiari_propri = apiari_propri.filter(id=apiario_id)
        apiari_condivisi = apiari_condivisi.filter(id=apiario_id)
    
    # Unisci gli apiari
    apiari = list((apiari_propri | apiari_condivisi).distinct())
    apiari_ids = [apiario.id for apiario in apiari]
    
    # ------------------- Recupero Controlli -------------------
    # Arnie degli apiari a cui l'utente ha accesso
    arnie = Arnia.objects.filter(apiario__in=apiari_ids)
    arnie_ids = [arnia.id for arnia in arnie]
    
    # Controlli per le arnie nel periodo selezionato
    controlli = ControlloArnia.objects.filter(
        arnia__in=arnie_ids,
        data__gte=start_date,
        data__lte=end_date
    ).select_related('arnia', 'arnia__apiario', 'utente').order_by('data')
    
    # Dizionario per tenere traccia dell'ultimo controllo per ogni arnia
    # per calcolare i delta dei telaini
    ultimo_controllo_per_arnia = {}
    
    for controllo in controlli:
        arnia_id = controllo.arnia.id
        apiario = controllo.arnia.apiario
        
        # Calcola i delta rispetto al controllo precedente
        delta_scorte = 0
        delta_covata = 0
        if arnia_id in ultimo_controllo_per_arnia:
            prev_controllo = ultimo_controllo_per_arnia[arnia_id]
            delta_scorte = controllo.telaini_scorte - prev_controllo.telaini_scorte
            delta_covata = controllo.telaini_covata - prev_controllo.telaini_covata
        
        # Aggiorna l'ultimo controllo per questa arnia
        ultimo_controllo_per_arnia[arnia_id] = controllo
        
        # Crea il titolo dell'evento
        title = f"Controllo Arnia #{controllo.arnia.numero} - {apiario.nome}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Arnia:</strong> #{controllo.arnia.numero} ({controllo.arnia.get_colore_display()})</p>
            <p><strong>Operatore:</strong> {controllo.utente.username}</p>
            <p><strong>Data:</strong> {controllo.data.strftime('%d/%m/%Y')}</p>
            <h6>Stato Arnia</h6>
            <ul>
                <li><strong>Telaini Scorte:</strong> {controllo.telaini_scorte} 
                    {'<span class="badge bg-success">+' + str(delta_scorte) + '</span>' if delta_scorte > 0 else ''}
                    {'<span class="badge bg-danger">' + str(delta_scorte) + '</span>' if delta_scorte < 0 else ''}
                </li>
                <li><strong>Telaini Covata:</strong> {controllo.telaini_covata} 
                    {'<span class="badge bg-success">+' + str(delta_covata) + '</span>' if delta_covata > 0 else ''}
                    {'<span class="badge bg-danger">' + str(delta_covata) + '</span>' if delta_covata < 0 else ''}
                </li>
                <li><strong>Presenza Regina:</strong> {'Sì' if controllo.presenza_regina else '<span class="text-danger">No</span>'}</li>
            </ul>
        """
        
        # Aggiungi informazioni su sciamatura se necessario
        if controllo.sciamatura:
            details_html += f"""
            <div class="alert alert-warning">
                <h6>Sciamatura Rilevata</h6>
                <p><strong>Data sciamatura:</strong> {controllo.data_sciamatura.strftime('%d/%m/%Y') if controllo.data_sciamatura else 'Non specificata'}</p>
                {'<p><strong>Note:</strong> ' + controllo.note_sciamatura + '</p>' if controllo.note_sciamatura else ''}
            </div>
            """
        
        # Aggiungi informazioni su problemi sanitari se necessario
        if controllo.problemi_sanitari:
            details_html += f"""
            <div class="alert alert-danger">
                <h6>Problemi Sanitari Rilevati</h6>
                {'<p><strong>Note:</strong> ' + controllo.note_problemi + '</p>' if controllo.note_problemi else ''}
            </div>
            """
        
        # Aggiungi note generali se presenti
        if controllo.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{controllo.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/controllo/{controllo.id}/modifica/"
        
        # Crea evento per il calendario
        event = {
            'id': f'controllo_{controllo.id}',
            'title': title,
            'start': controllo.data.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-controllo',
            'eventType': 'controllo',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'arnia': controllo.arnia.numero,
                'deltaScorte': delta_scorte,
                'deltaCovata': delta_covata,
                'eventType': 'controllo',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Eventi Regina -------------------
    # Controllare nel modello StoriaRegine per eventi di sostituzione/morte regine
    storia_regine = StoriaRegine.objects.filter(
        arnia__in=arnie_ids,
        data_inizio__gte=start_date,
        data_inizio__lte=end_date
    ).select_related('arnia', 'arnia__apiario', 'regina')
    
    for storia in storia_regine:
        arnia = storia.arnia
        apiario = arnia.apiario
        
        title = f"Nuova Regina - Arnia #{arnia.numero}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Arnia:</strong> #{arnia.numero} ({arnia.get_colore_display()})</p>
            <p><strong>Data introduzione:</strong> {storia.data_inizio.strftime('%d/%m/%Y')}</p>
            <h6>Informazioni Regina</h6>
            <ul>
                <li><strong>Razza:</strong> {storia.regina.get_razza_display()}</li>
                <li><strong>Origine:</strong> {storia.regina.get_origine_display()}</li>
                <li><strong>Età:</strong> {storia.regina.get_eta_anni() if storia.regina.get_eta_anni() else 'Sconosciuta'}</li>
                <li><strong>Marcata:</strong> {'Sì' if storia.regina.marcata else 'No'}</li>
            </ul>
        """
        
        # Aggiungi informazioni sulla regina precedente se è una sostituzione
        if storia.motivo_fine:
            details_html += f"""
            <div class="alert alert-info">
                <h6>Sostituzione Regina</h6>
                <p><strong>Motivo sostituzione:</strong> {storia.motivo_fine}</p>
            </div>
            """
        
        # Aggiungi note se presenti
        if storia.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{storia.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/arnia/{arnia.id}/regina/"
        
        # Crea evento per il calendario
        event = {
            'id': f'regina_{storia.id}',
            'title': title,
            'start': storia.data_inizio.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-regina',
            'eventType': 'regina',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'arnia': arnia.numero,
                'eventType': 'regina',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Eventi Melari -------------------
    # Melari posizionati
    melari_posizionati = Melario.objects.filter(
        arnia__in=arnie_ids,
        data_posizionamento__gte=start_date,
        data_posizionamento__lte=end_date
    ).select_related('arnia', 'arnia__apiario')
    
    for melario in melari_posizionati:
        arnia = melario.arnia
        apiario = arnia.apiario
        
        title = f"Melario Aggiunto - Arnia #{arnia.numero}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Arnia:</strong> #{arnia.numero} ({arnia.get_colore_display()})</p>
            <p><strong>Data:</strong> {melario.data_posizionamento.strftime('%d/%m/%Y')}</p>
            <h6>Dettagli Melario</h6>
            <ul>
                <li><strong>Posizione:</strong> {melario.posizione}</li>
                <li><strong>Telaini:</strong> {melario.numero_telaini}</li>
                <li><strong>Stato:</strong> {melario.get_stato_display()}</li>
            </ul>
        """
        
        # Aggiungi note se presenti
        if melario.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{melario.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/apiario/{apiario.id}/melari/"
        
        # Crea evento per il calendario
        event = {
            'id': f'melario_add_{melario.id}',
            'title': title,
            'start': melario.data_posizionamento.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-melario',
            'eventType': 'melario',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'arnia': arnia.numero,
                'eventType': 'melario',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # Melari rimossi
    melari_rimossi = Melario.objects.filter(
        arnia__in=arnie_ids,
        data_rimozione__gte=start_date,
        data_rimozione__lte=end_date
    ).select_related('arnia', 'arnia__apiario')
    
    for melario in melari_rimossi:
        arnia = melario.arnia
        apiario = arnia.apiario
        
        title = f"Melario Rimosso - Arnia #{arnia.numero}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Arnia:</strong> #{arnia.numero} ({arnia.get_colore_display()})</p>
            <p><strong>Data:</strong> {melario.data_rimozione.strftime('%d/%m/%Y')}</p>
            <h6>Dettagli Melario</h6>
            <ul>
                <li><strong>Posizione:</strong> {melario.posizione}</li>
                <li><strong>Telaini:</strong> {melario.numero_telaini}</li>
                <li><strong>Stato:</strong> {melario.get_stato_display()}</li>
                <li><strong>Data posizionamento:</strong> {melario.data_posizionamento.strftime('%d/%m/%Y')}</li>
            </ul>
        """
        
        # Aggiungi note se presenti
        if melario.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{melario.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/apiario/{apiario.id}/melari/"
        
        # Crea evento per il calendario
        event = {
            'id': f'melario_remove_{melario.id}',
            'title': title,
            'start': melario.data_rimozione.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-melario',
            'eventType': 'melario',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'arnia': arnia.numero,
                'eventType': 'melario',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Eventi Trattamenti -------------------
    # Inizio trattamenti
    trattamenti_inizio = TrattamentoSanitario.objects.filter(
        apiario__in=apiari_ids,
        data_inizio__gte=start_date,
        data_inizio__lte=end_date
    ).select_related('apiario', 'tipo_trattamento', 'utente')
    
    for trattamento in trattamenti_inizio:
        apiario = trattamento.apiario
        
        title = f"Inizio Trattamento - {trattamento.tipo_trattamento.nome}"
        
        # Conta il numero di arnie coinvolte
        num_arnie = trattamento.arnie.count()
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Data inizio:</strong> {trattamento.data_inizio.strftime('%d/%m/%Y')}</p>
            <p><strong>Operatore:</strong> {trattamento.utente.username}</p>
            <h6>Dettagli Trattamento</h6>
            <ul>
                <li><strong>Tipo:</strong> {trattamento.tipo_trattamento.nome}</li>
                <li><strong>Principio attivo:</strong> {trattamento.tipo_trattamento.principio_attivo}</li>
                <li><strong>Stato:</strong> {trattamento.get_stato_display()}</li>
                <li><strong>Arnie trattate:</strong> {num_arnie if num_arnie > 0 else "Tutte le arnie dell'apiario"}</li>
            </ul>
        """
        
        # Aggiungi informazioni sul blocco di covata se presente
        if trattamento.blocco_covata_attivo:
            details_html += f"""
            <div class="alert alert-warning">
                <h6>Blocco di Covata Attivo</h6>
                <p><strong>Data inizio blocco:</strong> {trattamento.data_inizio_blocco.strftime('%d/%m/%Y') if trattamento.data_inizio_blocco else 'Non specificata'}</p>
                <p><strong>Data fine prevista:</strong> {trattamento.data_fine_blocco.strftime('%d/%m/%Y') if trattamento.data_fine_blocco else 'Non specificata'}</p>
                {'<p><strong>Metodo:</strong> ' + trattamento.metodo_blocco + '</p>' if trattamento.metodo_blocco else ''}
            </div>
            """
        
        # Aggiungi note se presenti
        if trattamento.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{trattamento.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/trattamento/{trattamento.id}/modifica/"
        
        # Crea evento per il calendario
        event = {
            'id': f'trattamento_start_{trattamento.id}',
            'title': title,
            'start': trattamento.data_inizio.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-trattamento',
            'eventType': 'trattamento',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'eventType': 'trattamento',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # Fine trattamenti
    trattamenti_fine = TrattamentoSanitario.objects.filter(
        apiario__in=apiari_ids,
        data_fine__gte=start_date,
        data_fine__lte=end_date
    ).select_related('apiario', 'tipo_trattamento', 'utente')
    
    for trattamento in trattamenti_fine:
        apiario = trattamento.apiario
        
        title = f"Fine Trattamento - {trattamento.tipo_trattamento.nome}"
        
        # Conta il numero di arnie coinvolte
        num_arnie = trattamento.arnie.count()
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Data fine:</strong> {trattamento.data_fine.strftime('%d/%m/%Y')}</p>
            <p><strong>Operatore:</strong> {trattamento.utente.username}</p>
            <h6>Dettagli Trattamento</h6>
            <ul>
                <li><strong>Tipo:</strong> {trattamento.tipo_trattamento.nome}</li>
                <li><strong>Principio attivo:</strong> {trattamento.tipo_trattamento.principio_attivo}</li>
                <li><strong>Stato:</strong> {trattamento.get_stato_display()}</li>
                <li><strong>Arnie trattate:</strong> {num_arnie if num_arnie > 0 else "Tutte le arnie dell'apiario"}</li>
                <li><strong>Data inizio:</strong> {trattamento.data_inizio.strftime('%d/%m/%Y')}</li>
            </ul>
        """
        
        # Aggiungi informazioni sulla sospensione
        if trattamento.data_fine_sospensione and trattamento.data_fine_sospensione > trattamento.data_fine:
            details_html += f"""
            <div class="alert alert-danger">
                <h6>Periodo di Sospensione</h6>
                <p><strong>Fine sospensione:</strong> {trattamento.data_fine_sospensione.strftime('%d/%m/%Y')}</p>
                <p><strong>Giorni rimanenti:</strong> {trattamento.get_remaining_suspension_days()}</p>
            </div>
            """
        
        # Aggiungi note se presenti
        if trattamento.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{trattamento.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/trattamento/{trattamento.id}/modifica/"
        
        # Crea evento per il calendario
        event = {
            'id': f'trattamento_end_{trattamento.id}',
            'title': title,
            'start': trattamento.data_fine.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-trattamento',
            'eventType': 'trattamento',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'eventType': 'trattamento',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Fioriture -------------------
    # Inizio fioriture
    fioriture_inizio = Fioritura.objects.filter(
        Q(apiario__in=apiari_ids) | Q(apiario__isnull=True),
        data_inizio__gte=start_date,
        data_inizio__lte=end_date
    ).select_related('apiario')
    
    for fioritura in fioriture_inizio:
        title = f"Inizio Fioritura - {fioritura.pianta}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Pianta:</strong> {fioritura.pianta}</p>
            <p><strong>Data inizio:</strong> {fioritura.data_inizio.strftime('%d/%m/%Y')}</p>
            {'<p><strong>Apiario:</strong> ' + fioritura.apiario.nome + '</p>' if fioritura.apiario else '<p><strong>Apiario:</strong> Non associato</p>'}
            <h6>Dettagli Fioritura</h6>
            <ul>
                <li><strong>Coordinate:</strong> {fioritura.latitudine}, {fioritura.longitudine}</li>
                <li><strong>Raggio:</strong> {fioritura.raggio} metri</li>
                {'<li><strong>Data fine prevista:</strong> ' + fioritura.data_fine.strftime('%d/%m/%Y') + '</li>' if fioritura.data_fine else ''}
            </ul>
        """
        
        # Aggiungi note se presenti
        if fioritura.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{fioritura.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/fioritura/{fioritura.id}/modifica/"
        
        # Crea evento per il calendario
        event = {
            'id': f'fioritura_start_{fioritura.id}',
            'title': title,
            'start': fioritura.data_inizio.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-fioritura',
            'eventType': 'fioritura',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': fioritura.apiario.nome if fioritura.apiario else None,
                'eventType': 'fioritura',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # Fine fioriture
    fioriture_fine = Fioritura.objects.filter(
        Q(apiario__in=apiari_ids) | Q(apiario__isnull=True),
        data_fine__gte=start_date,
        data_fine__lte=end_date
    ).select_related('apiario')
    
    for fioritura in fioriture_fine:
        title = f"Fine Fioritura - {fioritura.pianta}"
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Pianta:</strong> {fioritura.pianta}</p>
            <p><strong>Data fine:</strong> {fioritura.data_fine.strftime('%d/%m/%Y')}</p>
            {'<p><strong>Apiario:</strong> ' + fioritura.apiario.nome + '</p>' if fioritura.apiario else '<p><strong>Apiario:</strong> Non associato</p>'}
            <h6>Dettagli Fioritura</h6>
            <ul>
                <li><strong>Coordinate:</strong> {fioritura.latitudine}, {fioritura.longitudine}</li>
                <li><strong>Raggio:</strong> {fioritura.raggio} metri</li>
                <li><strong>Data inizio:</strong> {fioritura.data_inizio.strftime('%d/%m/%Y')}</li>
                <li><strong>Durata:</strong> {(fioritura.data_fine - fioritura.data_inizio).days} giorni</li>
            </ul>
        """
        
        # Aggiungi note se presenti
        if fioritura.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{fioritura.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/fioritura/{fioritura.id}/modifica/"
        
        # Crea evento per il calendario
        event = {
            'id': f'fioritura_end_{fioritura.id}',
            'title': title,
            'start': fioritura.data_fine.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-fioritura',
            'eventType': 'fioritura',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': fioritura.apiario.nome if fioritura.apiario else None,
                'eventType': 'fioritura',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Smielature -------------------
    smielature = Smielatura.objects.filter(
        apiario__in=apiari_ids,
        data__gte=start_date,
        data__lte=end_date
    ).select_related('apiario', 'utente')
    
    for smielatura in smielature:
        apiario = smielatura.apiario
        
        title = f"Smielatura - {apiario.nome}"
        
        # Conta i melari smielati
        num_melari = smielatura.melari.count()
        
        # Prepara HTML per i dettagli
        details_html = f"""
        <div class="event-details">
            <p><strong>Apiario:</strong> {apiario.nome}</p>
            <p><strong>Data:</strong> {smielatura.data.strftime('%d/%m/%Y')}</p>
            <p><strong>Operatore:</strong> {smielatura.utente.username}</p>
            <h6>Dettagli Smielatura</h6>
            <ul>
                <li><strong>Quantità miele:</strong> {smielatura.quantita_miele} kg</li>
                <li><strong>Tipo miele:</strong> {smielatura.tipo_miele}</li>
                <li><strong>Melari smielati:</strong> {num_melari}</li>
            </ul>
        """
        
        # Aggiungi note se presenti
        if smielatura.note:
            details_html += f"""
            <div class="mt-3">
                <h6>Note</h6>
                <p>{smielatura.note}</p>
            </div>
            """
        
        details_html += "</div>"
        
        # Link ai dettagli completi
        detail_url = f"/app/smielatura/{smielatura.id}/"
        
        # Crea evento per il calendario
        event = {
            'id': f'smielatura_{smielatura.id}',
            'title': title,
            'start': smielatura.data.strftime('%Y-%m-%d'),
            'allDay': True,
            'className': 'event-smielatura',
            'eventType': 'smielatura',
            'detailsHtml': details_html,
            'detailUrl': detail_url,
            'extendedProps': {
                'apiario': apiario.nome,
                'eventType': 'smielatura',
                'detailsHtml': details_html,
                'detailUrl': detail_url
            }
        }
        
        events.append(event)
    
    # ------------------- Recupero Dati Meteo -------------------
    # Verificare se i filtri meteo sono attivi
    show_meteo = request.GET.get('show_meteo', 'true') == 'true'
    
    if show_meteo and apiari_ids:
        # Recupera i dati meteo per il periodo selezionato
        dati_meteo = DatiMeteo.objects.filter(
            apiario__in=apiari_ids,
            data__date__gte=start_date,
            data__date__lte=end_date
        ).select_related('apiario')
        
        # Raggruppa i dati meteo per giorno e apiario
        dati_meteo_per_giorno = {}
        for dato in dati_meteo:
            giorno = dato.data.date().strftime('%Y-%m-%d')
            apiario_id = dato.apiario.id
            
            if giorno not in dati_meteo_per_giorno:
                dati_meteo_per_giorno[giorno] = {}
            
            if apiario_id not in dati_meteo_per_giorno[giorno]:
                dati_meteo_per_giorno[giorno][apiario_id] = []
            
            dati_meteo_per_giorno[giorno][apiario_id].append(dato)
        
        # Calcola la media dei dati meteo per ogni giorno e apiario
        for giorno, apiari_data in dati_meteo_per_giorno.items():
            for apiario_id, dati in apiari_data.items():
                # Trova l'apiario corrispondente
                apiario = next((a for a in apiari if a.id == apiario_id), None)
                if not apiario:
                    continue
                
                # Calcola temperatura media, umidità media, ecc.
                temp_values = [float(d.temperatura) for d in dati if d.temperatura is not None]
                umidita_values = [d.umidita for d in dati if d.umidita is not None]
                vento_values = [float(d.velocita_vento) for d in dati if d.velocita_vento is not None]
                
                # Estrai descrizione e icona dal dato più recente della giornata
                dato_recente = sorted(dati, key=lambda x: x.data)[-1]
                
                # Solo se ci sono dati meteo validi, crea un evento
                if temp_values:
                    temp_avg = sum(temp_values) / len(temp_values)
                    umidita_avg = sum(umidita_values) / len(umidita_values) if umidita_values else None
                    vento_avg = sum(vento_values) / len(vento_values) if vento_values else None
                    
                    descrizione = dato_recente.descrizione
                    icona = dato_recente.icona
                    
                    # Direzione vento in testo
                    direzione_testo = ""
                    if dato_recente.direzione_vento:
                        direzione_testo = get_wind_direction_text(dato_recente.direzione_vento)
                    
                    # Prepara HTML per i dettagli
                    details_html = f"""
                    <div class="event-details">
                        <p><strong>Apiario:</strong> {apiario.nome}</p>
                        <p><strong>Data:</strong> {giorno}</p>
                        <div class="d-flex align-items-center mb-3">
                            <img src="https://openweathermap.org/img/wn/{icona}@2x.png" alt="{descrizione}" width="60" height="60">
                            <div>
                                <h3 class="mb-0">{temp_avg:.1f}°C</h3>
                                <p class="text-capitalize mb-0">{descrizione}</p>
                            </div>
                        </div>
                        <div class="row">
                            <div class="col-6">
                                <p><i class="bi bi-droplet"></i> <strong>Umidità:</strong> {umidita_avg:.0f}%</p>
                            </div>
                            <div class="col-6">
                                <p><i class="bi bi-wind"></i> <strong>Vento:</strong> {vento_avg:.1f} km/h {direzione_testo}</p>
                            </div>
                        </div>
                    """
                    
                    # Aggiungere eventuali consigli in base al meteo
                    if temp_avg < 10:
                        details_html += f"""
                        <div class="alert alert-warning mt-2">
                            <i class="bi bi-exclamation-triangle"></i> Temperatura bassa per l'attività delle api ({temp_avg:.1f}°C)
                        </div>
                        """
                    elif temp_avg > 30:
                        details_html += f"""
                        <div class="alert alert-warning mt-2">
                            <i class="bi bi-exclamation-triangle"></i> Temperatura elevata, verificare ventilazione arnie ({temp_avg:.1f}°C)
                        </div>
                        """
                    
                    if "pioggia" in descrizione.lower() or "temporale" in descrizione.lower():
                        details_html += f"""
                        <div class="alert alert-info mt-2">
                            <i class="bi bi-cloud-rain"></i> Attività di bottinatura potenzialmente ridotta
                        </div>
                        """
                    
                    details_html += "</div>"
                    
                    # Link ai dettagli completi
                    detail_url = f"/app/apiario/{apiario_id}/meteo/"
                    
                    # Crea evento meteo per il calendario
                    event = {
                        'id': f'meteo_{apiario_id}_{giorno}',
                        'title': f"{temp_avg:.1f}°C - {apiario.nome}",
                        'start': giorno,
                        'allDay': True,
                        'className': 'event-meteo',
                        'display': 'background',  # Rende l'evento come sfondo non cliccabile
                        'eventType': 'meteo',
                        'detailsHtml': details_html,
                        'detailUrl': detail_url,
                        'extendedProps': {
                            'apiario': apiario.nome,
                            'temperatura': f"{temp_avg:.1f}",
                            'descrizione': descrizione,
                            'icona': icona,
                            'umidita': f"{umidita_avg:.0f}" if umidita_avg else "",
                            'vento': f"{vento_avg:.1f}" if vento_avg else "",
                            'direzione': direzione_testo,
                            'eventType': 'meteo',
                            'detailsHtml': details_html,
                            'detailUrl': detail_url
                        }
                    }
                    
                    events.append(event)
    
    # ------------------- Recupero Previsioni Meteo -------------------
    show_previsioni = request.GET.get('show_previsioni', 'true') == 'true'
    
    if show_previsioni and apiari_ids:
        # Recupera le previsioni future per il periodo selezionato
        oggi = timezone.now().date()
        previsioni = PrevisioneMeteo.objects.filter(
            apiario__in=apiari_ids,
            data_riferimento__date__gte=max(oggi, start_date),
            data_riferimento__date__lte=end_date
        ).select_related('apiario')
        
        # Raggruppa le previsioni per giorno e apiario (prende solo la prima previsione del giorno)
        previsioni_per_giorno = {}
        for previsione in previsioni:
            giorno = previsione.data_riferimento.date().strftime('%Y-%m-%d')
            apiario_id = previsione.apiario.id
            
            if giorno not in previsioni_per_giorno:
                previsioni_per_giorno[giorno] = {}
            
            # Salva solo la prima previsione per quel giorno e apiario
            if apiario_id not in previsioni_per_giorno[giorno]:
                previsioni_per_giorno[giorno][apiario_id] = previsione
        
        # Crea eventi per le previsioni
        for giorno, apiari_data in previsioni_per_giorno.items():
            for apiario_id, previsione in apiari_data.items():
                # Trova l'apiario corrispondente
                apiario = next((a for a in apiari if a.id == apiario_id), None)
                if not apiario:
                    continue
                
                # Prepara HTML per i dettagli
                details_html = f"""
                <div class="event-details">
                    <p><strong>Apiario:</strong> {apiario.nome}</p>
                    <p><strong>Previsione per:</strong> {giorno}</p>
                    <div class="d-flex align-items-center mb-3">
                        <img src="https://openweathermap.org/img/wn/{previsione.icona}@2x.png" alt="{previsione.descrizione}" width="60" height="60">
                        <div>
                            <h3 class="mb-0">{previsione.temperatura}°C</h3>
                            <p class="text-capitalize mb-0">{previsione.descrizione}</p>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-6">
                            <p><i class="bi bi-droplet"></i> <strong>Umidità:</strong> {previsione.umidita}%</p>
                        </div>
                        <div class="col-6">
                            <p><i class="bi bi-wind"></i> <strong>Vento:</strong> {previsione.velocita_vento} km/h</p>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-6">
                            <p><i class="bi bi-cloud-rain"></i> <strong>Prob. pioggia:</strong> {previsione.probabilita_pioggia}%</p>
                        </div>
                        <div class="col-6">
                            <p><i class="bi bi-thermometer"></i> <strong>Min/Max:</strong> {previsione.temperatura_min}°/{previsione.temperatura_max}°C</p>
                        </div>
                    </div>
                </div>
                """
                
                # Link ai dettagli completi
                detail_url = f"/app/apiario/{apiario_id}/meteo/"
                
                # Crea evento per la previsione
                event = {
                    'id': f'previsione_{apiario_id}_{giorno}',
                    'title': f"Previsione: {previsione.temperatura}°C - {apiario.nome}",
                    'start': giorno,
                    'allDay': True,
                    'className': 'event-previsione',
                    'display': 'background',  # Rende l'evento come sfondo non cliccabile
                    'eventType': 'previsione',
                    'detailsHtml': details_html,
                    'detailUrl': detail_url,
                    'extendedProps': {
                        'apiario': apiario.nome,
                        'temperatura': f"{previsione.temperatura}",
                        'descrizione': previsione.descrizione,
                        'icona': previsione.icona,
                        'umidita': f"{previsione.umidita}",
                        'probabilita_pioggia': f"{previsione.probabilita_pioggia}",
                        'eventType': 'previsione',
                        'detailsHtml': details_html,
                        'detailUrl': detail_url
                    }
                }
                
                events.append(event)
    
    # Restituisci gli eventi in formato JSON
    return JsonResponse(events, safe=False)

# core/views.py
# Aggiungi queste viste al file views.py esistente

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Avg

from .models import Apiario, DatiMeteo, PrevisioneMeteo, ControlloArnia
from .meteo_utils import ottieni_dati_meteo_correnti, ottieni_previsioni_meteo, get_wind_direction_text

@login_required
def visualizza_meteo_apiario(request, apiario_id):
    """Vista per visualizzare i dati meteo di un apiario"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Verifica che l'utente abbia accesso all'apiario
    can_view = False
    if apiario.proprietario == request.user:
        can_view = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_view = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_view:
        messages.error(request, "Non hai accesso a questo apiario.")
        return redirect('dashboard')
    
    # Ottieni i dati meteo attuali
    dati_meteo = ottieni_dati_meteo_correnti(apiario)
    
    # Ottieni le previsioni meteo
    previsioni = ottieni_previsioni_meteo(apiario)
    
    # Formatta i dati meteo attuali per una migliore visualizzazione
    if dati_meteo and dati_meteo.direzione_vento:
        dati_meteo.direzione_testo = get_wind_direction_text(dati_meteo.direzione_vento)
    
    # Raggruppa le previsioni per giorno
    previsioni_per_giorno = {}
    for previsione in previsioni:
        giorno = previsione.data_riferimento.strftime('%Y-%m-%d')
        if giorno not in previsioni_per_giorno:
            previsioni_per_giorno[giorno] = []
        previsioni_per_giorno[giorno].append(previsione)
    
    context = {
        'apiario': apiario,
        'dati_meteo': dati_meteo,
        'previsioni': previsioni,
        'previsioni_per_giorno': previsioni_per_giorno,
    }
    
    return render(request, 'meteo/visualizza_meteo.html', context)

@login_required
def grafici_meteo_apiario(request, apiario_id):
    """Vista per visualizzare grafici dei dati meteo per un apiario"""
    apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    # Verifica che l'utente abbia accesso all'apiario
    can_view = False
    if apiario.proprietario == request.user:
        can_view = True
    elif apiario.gruppo and apiario.condiviso_con_gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=apiario.gruppo)
            can_view = True
        except MembroGruppo.DoesNotExist:
            pass
    
    if not can_view:
        messages.error(request, "Non hai accesso a questo apiario.")
        return redirect('dashboard')
    
    # Recupera i dati meteo storici
    periodo = request.GET.get('periodo', '7d')  # Default: 7 giorni
    
    if periodo == '7d':
        data_inizio = timezone.now() - timedelta(days=7)
    elif periodo == '30d':
        data_inizio = timezone.now() - timedelta(days=30)
    elif periodo == '90d':
        data_inizio = timezone.now() - timedelta(days=90)
    else:  # anno corrente
        data_inizio = timezone.now().replace(month=1, day=1, hour=0, minute=0, second=0)
    
    dati_meteo = DatiMeteo.objects.filter(
        apiario=apiario,
        data__gte=data_inizio
    ).order_by('data')
    
    # Raggruppa i dati meteo per giorno (media)
    dati_per_giorno = {}
    for dato in dati_meteo:
        giorno = dato.data.strftime('%Y-%m-%d')
        if giorno not in dati_per_giorno:
            dati_per_giorno[giorno] = {
                'date': giorno,
                'temp_values': [],
                'umid_values': [],
                'wind_values': [],
                'press_values': []
            }
        
        if dato.temperatura:
            dati_per_giorno[giorno]['temp_values'].append(float(dato.temperatura))
        if dato.umidita:
            dati_per_giorno[giorno]['umid_values'].append(dato.umidita)
        if dato.velocita_vento:
            dati_per_giorno[giorno]['wind_values'].append(float(dato.velocita_vento))
        if dato.pressione:
            dati_per_giorno[giorno]['press_values'].append(dato.pressione)
    
    # Calcola le medie giornaliere
    dati_aggregati = []
    for giorno, valori in dati_per_giorno.items():
        aggregato = {
            'date': giorno,
            'temperatura': round(sum(valori['temp_values']) / len(valori['temp_values']), 1) if valori['temp_values'] else None,
            'umidita': round(sum(valori['umid_values']) / len(valori['umid_values'])) if valori['umid_values'] else None,
            'vento': round(sum(valori['wind_values']) / len(valori['wind_values']), 1) if valori['wind_values'] else None,
            'pressione': round(sum(valori['press_values']) / len(valori['press_values'])) if valori['press_values'] else None
        }
        dati_aggregati.append(aggregato)
    
    # Ordina i dati per data
    dati_aggregati.sort(key=lambda x: x['date'])
    
    # Recupera i controlli delle arnie nello stesso periodo
    controlli = ControlloArnia.objects.filter(
        arnia__apiario=apiario,
        data__gte=data_inizio.date()
    ).order_by('data')
    
    # Raggruppa i controlli per giorno (somma telaini per arnia)
    controlli_per_giorno = {}
    arnie_per_giorno = {}
    
    for controllo in controlli:
        giorno = controllo.data.strftime('%Y-%m-%d')
        if giorno not in controlli_per_giorno:
            controlli_per_giorno[giorno] = {
                'date': giorno,
                'telaini_covata': 0,
                'telaini_scorte': 0,
                'arnie_controllate': set()
            }
        
        controlli_per_giorno[giorno]['telaini_covata'] += controllo.telaini_covata
        controlli_per_giorno[giorno]['telaini_scorte'] += controllo.telaini_scorte
        controlli_per_giorno[giorno]['arnie_controllate'].add(controllo.arnia.id)
    
    # Calcola la media per arnia
    dati_controlli = []
    for giorno, valori in controlli_per_giorno.items():
        num_arnie = len(valori['arnie_controllate'])
        if num_arnie > 0:
            dati_controllo = {
                'date': giorno,
                'telaini_covata_media': round(valori['telaini_covata'] / num_arnie, 1),
                'telaini_scorte_media': round(valori['telaini_scorte'] / num_arnie, 1),
                'arnie_controllate': num_arnie
            }
            dati_controlli.append(dati_controllo)
    
    # Ordina i dati per data
    dati_controlli.sort(key=lambda x: x['date'])
    
    # Prepara dati per i grafici
    date_meteo = [dato['date'] for dato in dati_aggregati]
    temperature = [dato['temperatura'] for dato in dati_aggregati]
    umidita = [dato['umidita'] for dato in dati_aggregati]
    vento = [dato['vento'] for dato in dati_aggregati]
    
    # Dati delle arnie per confronto
    date_controlli = [dato['date'] for dato in dati_controlli]
    telaini_covata_media = [dato['telaini_covata_media'] for dato in dati_controlli]
    telaini_scorte_media = [dato['telaini_scorte_media'] for dato in dati_controlli]
    
    context = {
        'apiario': apiario,
        'periodo': periodo,
        'date_meteo': date_meteo,
        'temperature': temperature,
        'umidita': umidita,
        'vento': vento,
        'date_controlli': date_controlli,
        'telaini_covata_media': telaini_covata_media,
        'telaini_scorte_media': telaini_scorte_media,
        'dati_aggregati': dati_aggregati,
        'dati_controlli': dati_controlli,
    }
    
    return render(request, 'meteo/grafici_meteo.html', context)

@login_required
def mappa_meteo(request):
    """Vista per la mappa meteo degli apiari"""
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
    
    # Recupera solo apiari con coordinate e monitoraggio meteo abilitato
    apiari_con_meteo = [a for a in apiari if a.has_coordinates() and a.monitoraggio_meteo]
    
    # Recupera i dati meteo per gli apiari
    dati_meteo = {}
    previsioni_domani = {}
    
    for apiario in apiari_con_meteo:
        # Dati meteo attuali
        meteo_recente = DatiMeteo.objects.filter(
            apiario=apiario,
            data__gte=timezone.now() - timedelta(hours=3)
        ).order_by('-data').first()
        
        if meteo_recente:
            # Aggiungi la direzione del vento in formato testuale
            if meteo_recente.direzione_vento:
                meteo_recente.direzione_testo = get_wind_direction_text(meteo_recente.direzione_vento)
            dati_meteo[apiario.id] = meteo_recente
        
        # Previsioni per domani
        domani = timezone.now().date() + timedelta(days=1)
        previsione_domani = PrevisioneMeteo.objects.filter(
            apiario=apiario,
            data_riferimento__date=domani
        ).order_by('data_riferimento').first()
        
        if previsione_domani:
            # Aggiungi la direzione del vento in formato testuale
            if previsione_domani.direzione_vento:
                previsione_domani.direzione_testo = get_wind_direction_text(previsione_domani.direzione_vento)
            previsioni_domani[apiario.id] = previsione_domani
    
    context = {
        'apiari': apiari,
        'apiari_propri': apiari_propri,
        'apiari_condivisi': apiari_condivisi,
        'apiari_visibili_gruppo': apiari_visibili_gruppo,
        'apiari_pubblici': apiari_pubblici,
        'dati_meteo': dati_meteo,
        'previsioni_domani': previsioni_domani,
        'is_mappa_meteo': True,  # Indica che siamo nella vista mappa meteo
    }
    
    return render(request, 'maps/mappa_meteo.html', context)

# Modifica della vista mappa_apiari per includere i dati meteo
@login_required
def mappa_apiari(request):
    """Vista per la mappa degli apiari e delle fioriture, con dati meteo"""
    # ... Codice esistente per recuperare apiari ...
    
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
    
    # ... Codice esistente per recuperare fioriture ...
    
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
    
    # Recupera i dati meteo per gli apiari
    dati_meteo = {}
    for apiario in apiari:
        if apiario.has_coordinates() and apiario.monitoraggio_meteo:
            # Cerca dati meteo recenti (ultimi 60 minuti)
            meteo_recente = DatiMeteo.objects.filter(
                apiario=apiario,
                data__gte=timezone.now() - timedelta(minutes=60)
            ).order_by('-data').first()
            
            if meteo_recente:
                # Aggiungi la direzione del vento in formato testuale
                if meteo_recente.direzione_vento:
                    meteo_recente.direzione_testo = get_wind_direction_text(meteo_recente.direzione_vento)
                dati_meteo[apiario.id] = meteo_recente
    
    context = {
        'apiari': apiari,
        'apiari_propri': apiari_propri,
        'apiari_condivisi': apiari_condivisi,
        'apiari_visibili_gruppo': apiari_visibili_gruppo,
        'apiari_pubblici': apiari_pubblici,
        'fioriture_attive': fioriture_attive,
        'fioriture_programmate': fioriture_programmate,
        'fioriture_passate': fioriture_passate,
        'dati_meteo': dati_meteo,
    }
    
    return render(request, 'maps/mappa_apiari.html', context)

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


# ============================================
# GESTIONE ATTREZZATURE E STRUMENTI
# ============================================

@login_required
def gestione_attrezzature(request):
    """Vista principale per la gestione delle attrezzature"""
    # Attrezzature proprie
    attrezzature_proprie = Attrezzatura.objects.filter(proprietario=request.user)

    # Attrezzature condivise tramite gruppi
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    attrezzature_gruppo = Attrezzatura.objects.filter(
        gruppo__in=gruppi_utente,
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)

    # Applicare filtri
    filtro_form = AttrezzaturaFiltroForm(request.GET)
    tutte_attrezzature = attrezzature_proprie | attrezzature_gruppo

    if filtro_form.is_valid():
        if filtro_form.cleaned_data.get('categoria'):
            tutte_attrezzature = tutte_attrezzature.filter(
                categoria=filtro_form.cleaned_data['categoria'])
        if filtro_form.cleaned_data.get('stato'):
            tutte_attrezzature = tutte_attrezzature.filter(
                stato=filtro_form.cleaned_data['stato'])
        if filtro_form.cleaned_data.get('condizione'):
            tutte_attrezzature = tutte_attrezzature.filter(
                condizione=filtro_form.cleaned_data['condizione'])
        if filtro_form.cleaned_data.get('cerca'):
            cerca = filtro_form.cleaned_data['cerca']
            tutte_attrezzature = tutte_attrezzature.filter(
                Q(nome__icontains=cerca) |
                Q(marca__icontains=cerca) |
                Q(modello__icontains=cerca) |
                Q(descrizione__icontains=cerca)
            )

    tutte_attrezzature = tutte_attrezzature.select_related('categoria', 'proprietario', 'gruppo', 'apiario')

    # Statistiche
    stats = {
        'totale': tutte_attrezzature.count(),
        'disponibili': tutte_attrezzature.filter(stato='disponibile').count(),
        'in_manutenzione': tutte_attrezzature.filter(stato='manutenzione').count(),
        'prestate': tutte_attrezzature.filter(stato='prestato').count(),
        'valore_totale': sum(a.prezzo_acquisto or 0 for a in attrezzature_proprie),
        'valore_residuo': sum(a.get_valore_residuo() or 0 for a in attrezzature_proprie),
    }

    # Manutenzioni programmate
    manutenzioni_programmate = ManutenzioneAttrezzatura.objects.filter(
        attrezzatura__in=tutte_attrezzature,
        stato='programmata',
        data_programmata__lte=timezone.now().date() + timedelta(days=30)
    ).select_related('attrezzatura')[:5]

    # Prestiti in corso
    prestiti_in_corso = PrestitoAttrezzatura.objects.filter(
        Q(attrezzatura__proprietario=request.user) | Q(richiedente=request.user),
        stato='in_corso'
    ).select_related('attrezzatura', 'richiedente')[:5]

    context = {
        'attrezzature': tutte_attrezzature,
        'attrezzature_proprie': attrezzature_proprie,
        'attrezzature_gruppo': attrezzature_gruppo,
        'filtro_form': filtro_form,
        'stats': stats,
        'manutenzioni_programmate': manutenzioni_programmate,
        'prestiti_in_corso': prestiti_in_corso,
        'categorie': CategoriaAttrezzatura.objects.all(),
    }

    return render(request, 'attrezzature/gestione_attrezzature.html', context)


@login_required
def aggiungi_attrezzatura(request):
    """Aggiunge una nuova attrezzatura"""
    if request.method == 'POST':
        form = AttrezzaturaForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            attrezzatura = form.save(commit=False)
            attrezzatura.proprietario = request.user
            attrezzatura.save()

            # Se c'è un prezzo di acquisto, crea automaticamente un Pagamento
            if attrezzatura.prezzo_acquisto and attrezzatura.prezzo_acquisto > 0:
                # Crea la spesa attrezzatura
                spesa = SpesaAttrezzatura.objects.create(
                    attrezzatura=attrezzatura,
                    gruppo=attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None,
                    tipo='acquisto',
                    descrizione=f"Acquisto: {attrezzatura.nome}",
                    importo=attrezzatura.prezzo_acquisto,
                    data=attrezzatura.data_acquisto or timezone.now().date(),
                    fornitore=attrezzatura.fornitore,
                    utente=request.user
                )

                # Crea il pagamento corrispondente
                Pagamento.objects.create(
                    utente=request.user,
                    importo=attrezzatura.prezzo_acquisto,
                    data=attrezzatura.data_acquisto or timezone.now().date(),
                    descrizione=f"Acquisto attrezzatura: {attrezzatura.nome}",
                    gruppo=attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None
                )

                messages.success(request, f"Attrezzatura '{attrezzatura.nome}' aggiunta e pagamento registrato automaticamente.")
            else:
                messages.success(request, f"Attrezzatura '{attrezzatura.nome}' aggiunta con successo.")

            return redirect('gestione_attrezzature')
    else:
        form = AttrezzaturaForm(user=request.user)

    context = {
        'form': form,
        'titolo': 'Aggiungi Attrezzatura',
    }
    return render(request, 'attrezzature/form_attrezzatura.html', context)


@login_required
def dettaglio_attrezzatura(request, attrezzatura_id):
    """Visualizza il dettaglio di un'attrezzatura"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Verifica accesso
    can_view = False
    can_edit = False

    if attrezzatura.proprietario == request.user:
        can_view = True
        can_edit = True
    elif attrezzatura.condiviso_con_gruppo and attrezzatura.gruppo:
        if MembroGruppo.objects.filter(utente=request.user, gruppo=attrezzatura.gruppo).exists():
            can_view = True
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=attrezzatura.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True

    if not can_view:
        messages.error(request, "Non hai accesso a questa attrezzatura.")
        return redirect('gestione_attrezzature')

    # Storico manutenzioni
    manutenzioni = attrezzatura.manutenzioni.all()[:10]

    # Storico prestiti
    prestiti = attrezzatura.prestiti.all()[:10]

    # Spese associate
    spese = attrezzatura.spese.all()[:10]
    totale_spese = attrezzatura.spese.aggregate(totale=Sum('importo'))['totale'] or 0

    context = {
        'attrezzatura': attrezzatura,
        'can_edit': can_edit,
        'manutenzioni': manutenzioni,
        'prestiti': prestiti,
        'spese': spese,
        'totale_spese': totale_spese,
    }

    return render(request, 'attrezzature/dettaglio_attrezzatura.html', context)


@login_required
def modifica_attrezzatura(request, attrezzatura_id):
    """Modifica un'attrezzatura esistente"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Verifica permessi
    if attrezzatura.proprietario != request.user:
        if not (attrezzatura.condiviso_con_gruppo and attrezzatura.gruppo):
            messages.error(request, "Non hai i permessi per modificare questa attrezzatura.")
            return redirect('gestione_attrezzature')

        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=attrezzatura.gruppo)
            if membro.ruolo not in ['admin', 'editor']:
                messages.error(request, "Non hai i permessi per modificare questa attrezzatura.")
                return redirect('gestione_attrezzature')
        except MembroGruppo.DoesNotExist:
            messages.error(request, "Non hai i permessi per modificare questa attrezzatura.")
            return redirect('gestione_attrezzature')

    if request.method == 'POST':
        form = AttrezzaturaForm(request.POST, request.FILES, instance=attrezzatura, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Attrezzatura '{attrezzatura.nome}' modificata con successo.")
            return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)
    else:
        form = AttrezzaturaForm(instance=attrezzatura, user=request.user)

    context = {
        'form': form,
        'attrezzatura': attrezzatura,
        'titolo': f'Modifica {attrezzatura.nome}',
    }
    return render(request, 'attrezzature/form_attrezzatura.html', context)


@login_required
def elimina_attrezzatura(request, attrezzatura_id):
    """Elimina un'attrezzatura"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Solo il proprietario può eliminare
    if attrezzatura.proprietario != request.user:
        messages.error(request, "Solo il proprietario può eliminare questa attrezzatura.")
        return redirect('gestione_attrezzature')

    if request.method == 'POST':
        nome = attrezzatura.nome
        attrezzatura.delete()
        messages.success(request, f"Attrezzatura '{nome}' eliminata con successo.")
        return redirect('gestione_attrezzature')

    context = {
        'attrezzatura': attrezzatura,
    }
    return render(request, 'attrezzature/elimina_attrezzatura.html', context)


@login_required
def aggiungi_manutenzione(request, attrezzatura_id):
    """Aggiunge una manutenzione per un'attrezzatura"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Verifica permessi
    can_edit = False
    if attrezzatura.proprietario == request.user:
        can_edit = True
    elif attrezzatura.condiviso_con_gruppo and attrezzatura.gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=attrezzatura.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass

    if not can_edit:
        messages.error(request, "Non hai i permessi per aggiungere manutenzioni.")
        return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)

    if request.method == 'POST':
        form = ManutenzioneAttrezzaturaForm(request.POST)
        if form.is_valid():
            manutenzione = form.save(commit=False)
            manutenzione.attrezzatura = attrezzatura
            manutenzione.utente = request.user
            manutenzione.save()

            # Se la manutenzione è in corso, aggiorna lo stato dell'attrezzatura
            if manutenzione.stato == 'in_corso':
                attrezzatura.stato = 'manutenzione'
                attrezzatura.save()

            # Se la manutenzione ha un costo, crea SpesaAttrezzatura e Pagamento
            if manutenzione.costo and manutenzione.costo > 0:
                # Crea la spesa attrezzatura
                SpesaAttrezzatura.objects.create(
                    attrezzatura=attrezzatura,
                    gruppo=attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None,
                    tipo='manutenzione',
                    descrizione=f"{manutenzione.get_tipo_display()}: {attrezzatura.nome}",
                    importo=manutenzione.costo,
                    data=manutenzione.data_esecuzione or manutenzione.data_programmata,
                    utente=request.user
                )

                # Crea il pagamento corrispondente
                Pagamento.objects.create(
                    utente=request.user,
                    importo=manutenzione.costo,
                    data=manutenzione.data_esecuzione or manutenzione.data_programmata,
                    descrizione=f"Manutenzione attrezzatura: {attrezzatura.nome} - {manutenzione.get_tipo_display()}",
                    gruppo=attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None
                )

                messages.success(request, "Manutenzione registrata e pagamento aggiunto automaticamente.")
            else:
                messages.success(request, "Manutenzione registrata con successo.")

            return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)
    else:
        form = ManutenzioneAttrezzaturaForm(initial={
            'data_programmata': timezone.now().date()
        })

    context = {
        'form': form,
        'attrezzatura': attrezzatura,
    }
    return render(request, 'attrezzature/form_manutenzione.html', context)


@login_required
def richiedi_prestito(request, attrezzatura_id):
    """Richiede il prestito di un'attrezzatura"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Verifica che l'attrezzatura sia condivisa con il gruppo dell'utente
    if not attrezzatura.condiviso_con_gruppo or not attrezzatura.gruppo:
        messages.error(request, "Questa attrezzatura non è disponibile per il prestito.")
        return redirect('gestione_attrezzature')

    if not MembroGruppo.objects.filter(utente=request.user, gruppo=attrezzatura.gruppo).exists():
        messages.error(request, "Non sei membro del gruppo che possiede questa attrezzatura.")
        return redirect('gestione_attrezzature')

    if attrezzatura.stato != 'disponibile':
        messages.error(request, f"L'attrezzatura non è disponibile. Stato attuale: {attrezzatura.get_stato_display()}")
        return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)

    if request.method == 'POST':
        form = PrestitoAttrezzaturaForm(request.POST)
        if form.is_valid():
            prestito = form.save(commit=False)
            prestito.attrezzatura = attrezzatura
            prestito.richiedente = request.user
            prestito.save()
            messages.success(request, "Richiesta di prestito inviata. In attesa di approvazione.")
            return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)
    else:
        form = PrestitoAttrezzaturaForm(initial={
            'data_inizio_prestito': timezone.now().date(),
            'data_fine_prevista': timezone.now().date() + timedelta(days=7)
        })

    context = {
        'form': form,
        'attrezzatura': attrezzatura,
    }
    return render(request, 'attrezzature/form_prestito.html', context)


@login_required
def gestisci_prestito(request, prestito_id, azione):
    """Approva, rifiuta o completa un prestito"""
    prestito = get_object_or_404(PrestitoAttrezzatura, pk=prestito_id)
    attrezzatura = prestito.attrezzatura

    # Verifica che l'utente sia il proprietario dell'attrezzatura
    if attrezzatura.proprietario != request.user:
        # O admin del gruppo
        if not (attrezzatura.gruppo and MembroGruppo.objects.filter(
            utente=request.user,
            gruppo=attrezzatura.gruppo,
            ruolo='admin'
        ).exists()):
            messages.error(request, "Non hai i permessi per gestire questo prestito.")
            return redirect('gestione_attrezzature')

    if azione == 'approva' and prestito.stato == 'richiesto':
        prestito.stato = 'in_corso'
        prestito.approvato_da = request.user
        prestito.data_approvazione = timezone.now()
        prestito.save()
        messages.success(request, "Prestito approvato.")

    elif azione == 'rifiuta' and prestito.stato == 'richiesto':
        prestito.stato = 'rifiutato'
        prestito.save()
        messages.info(request, "Prestito rifiutato.")

    elif azione == 'restituisci' and prestito.stato == 'in_corso':
        if request.method == 'POST':
            form = RestituzioneAttrezzaturaForm(request.POST)
            if form.is_valid():
                prestito.stato = 'restituito'
                prestito.data_restituzione = form.cleaned_data['data_restituzione']
                prestito.note_restituzione = form.cleaned_data.get('note_restituzione', '')
                prestito.save()

                if form.cleaned_data.get('nuova_condizione'):
                    attrezzatura.condizione = form.cleaned_data['nuova_condizione']
                    attrezzatura.save()

                messages.success(request, "Attrezzatura restituita correttamente.")
                return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)
        else:
            form = RestituzioneAttrezzaturaForm(initial={
                'data_restituzione': timezone.now().date(),
                'nuova_condizione': attrezzatura.condizione
            })

        return render(request, 'attrezzature/form_restituzione.html', {
            'form': form,
            'prestito': prestito,
            'attrezzatura': attrezzatura,
        })

    return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)


@login_required
def aggiungi_spesa_attrezzatura(request, attrezzatura_id):
    """Aggiunge una spesa per un'attrezzatura"""
    attrezzatura = get_object_or_404(Attrezzatura, pk=attrezzatura_id)

    # Verifica permessi
    can_edit = False
    if attrezzatura.proprietario == request.user:
        can_edit = True
    elif attrezzatura.condiviso_con_gruppo and attrezzatura.gruppo:
        try:
            membro = MembroGruppo.objects.get(utente=request.user, gruppo=attrezzatura.gruppo)
            if membro.ruolo in ['admin', 'editor']:
                can_edit = True
        except MembroGruppo.DoesNotExist:
            pass

    if not can_edit:
        messages.error(request, "Non hai i permessi per aggiungere spese.")
        return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)

    if request.method == 'POST':
        form = SpesaAttrezzaturaForm(request.POST)
        if form.is_valid():
            spesa = form.save(commit=False)
            spesa.attrezzatura = attrezzatura
            spesa.gruppo = attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None
            spesa.utente = request.user
            spesa.save()

            # Crea automaticamente un Pagamento corrispondente
            Pagamento.objects.create(
                utente=request.user,
                importo=spesa.importo,
                data=spesa.data,
                descrizione=f"Spesa attrezzatura ({spesa.get_tipo_display()}): {attrezzatura.nome} - {spesa.descrizione}",
                gruppo=attrezzatura.gruppo if attrezzatura.condiviso_con_gruppo else None
            )

            messages.success(request, "Spesa registrata e pagamento aggiunto automaticamente.")
            return redirect('dettaglio_attrezzatura', attrezzatura_id=attrezzatura.id)
    else:
        form = SpesaAttrezzaturaForm(initial={
            'data': timezone.now().date()
        })

    context = {
        'form': form,
        'attrezzatura': attrezzatura,
    }
    return render(request, 'attrezzature/form_spesa.html', context)


@login_required
def inventario_attrezzature(request, gruppo_id=None):
    """Visualizza e genera l'inventario delle attrezzature"""
    gruppo = None
    if gruppo_id:
        gruppo = get_object_or_404(Gruppo, pk=gruppo_id)
        if not MembroGruppo.objects.filter(utente=request.user, gruppo=gruppo).exists():
            messages.error(request, "Non sei membro di questo gruppo.")
            return redirect('gestione_attrezzature')

    if gruppo:
        attrezzature = Attrezzatura.objects.filter(
            gruppo=gruppo,
            condiviso_con_gruppo=True
        ).exclude(stato='dismesso')
    else:
        attrezzature = Attrezzatura.objects.filter(
            proprietario=request.user
        ).exclude(stato='dismesso')

    # Calcola statistiche per categoria
    stats_categoria = {}
    for attrezzatura in attrezzature:
        cat_nome = attrezzatura.categoria.nome if attrezzatura.categoria else 'Senza categoria'
        if cat_nome not in stats_categoria:
            stats_categoria[cat_nome] = {
                'count': 0,
                'valore': 0,
                'valore_residuo': 0
            }
        stats_categoria[cat_nome]['count'] += 1
        stats_categoria[cat_nome]['valore'] += float(attrezzatura.prezzo_acquisto or 0)
        stats_categoria[cat_nome]['valore_residuo'] += float(attrezzatura.get_valore_residuo() or 0)

    # Totali
    totale_valore = sum(float(a.prezzo_acquisto or 0) for a in attrezzature)
    totale_residuo = sum(float(a.get_valore_residuo() or 0) for a in attrezzature)

    # Inventari precedenti
    if gruppo:
        inventari_precedenti = InventarioAttrezzature.objects.filter(gruppo=gruppo)[:5]
    else:
        inventari_precedenti = InventarioAttrezzature.objects.filter(
            proprietario=request.user,
            gruppo__isnull=True
        )[:5]

    # Generazione nuovo inventario
    if request.method == 'POST':
        inventario = InventarioAttrezzature(
            gruppo=gruppo,
            proprietario=request.user,
            data=timezone.now().date(),
            descrizione=request.POST.get('descrizione', f'Inventario {timezone.now().strftime("%d/%m/%Y")}'),
            note=request.POST.get('note', '')
        )
        inventario.save()
        inventario.calcola_valori()
        messages.success(request, "Inventario generato con successo.")
        return redirect('inventario_attrezzature', gruppo_id=gruppo_id) if gruppo_id else redirect('inventario_attrezzature')

    context = {
        'attrezzature': attrezzature,
        'gruppo': gruppo,
        'stats_categoria': stats_categoria,
        'totale_valore': totale_valore,
        'totale_residuo': totale_residuo,
        'inventari_precedenti': inventari_precedenti,
    }

    return render(request, 'attrezzature/inventario.html', context)


@login_required
def gestione_categorie_attrezzature(request):
    """Gestisce le categorie di attrezzature"""
    categorie = CategoriaAttrezzatura.objects.annotate(
        num_attrezzature=Count('attrezzature')
    )

    if request.method == 'POST':
        form = CategoriaAttrezzaturaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria creata con successo.")
            return redirect('gestione_categorie_attrezzature')
    else:
        form = CategoriaAttrezzaturaForm()

    context = {
        'categorie': categorie,
        'form': form,
    }

    return render(request, 'attrezzature/gestione_categorie.html', context)


# ============================================
# RICERCA AVANZATA GENEALOGIA REGINE
# ============================================

@login_required
def ricerca_regine(request):
    """Ricerca avanzata delle regine con filtri genealogici"""
    # Ottieni apiari accessibili
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente,
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)

    apiari_accessibili = apiari_propri | apiari_condivisi

    # Regine accessibili
    regine = Regina.objects.filter(
        arnia__apiario__in=apiari_accessibili
    ).select_related('arnia', 'arnia__apiario', 'regina_madre')

    # Applica filtri
    form = RicercaReginaForm(request.GET)
    if form.is_valid():
        if form.cleaned_data.get('razza'):
            regine = regine.filter(razza=form.cleaned_data['razza'])
        if form.cleaned_data.get('origine'):
            regine = regine.filter(origine=form.cleaned_data['origine'])
        if form.cleaned_data.get('anno_nascita'):
            regine = regine.filter(data_nascita__year=form.cleaned_data['anno_nascita'])
        if form.cleaned_data.get('selezionata') == 'si':
            regine = regine.filter(selezionata=True)
        elif form.cleaned_data.get('selezionata') == 'no':
            regine = regine.filter(selezionata=False)
        if form.cleaned_data.get('con_figlie'):
            regine = regine.filter(figlie__isnull=False).distinct()
        if form.cleaned_data.get('valutazione_minima'):
            val_min = form.cleaned_data['valutazione_minima']
            # Filtra per media valutazioni
            regine = [r for r in regine if r.docilita and r.produttivita and
                     (r.docilita + r.produttivita + (r.resistenza_malattie or 0) +
                      (5 - (r.tendenza_sciamatura or 5))) / 4 >= val_min]

    # Statistiche
    stats = {
        'totale': regine.count() if hasattr(regine, 'count') else len(regine),
        'per_razza': {},
        'per_origine': {},
        'con_genealogia': 0,
    }

    for regina in regine:
        razza = regina.get_razza_display()
        origine = regina.get_origine_display()
        stats['per_razza'][razza] = stats['per_razza'].get(razza, 0) + 1
        stats['per_origine'][origine] = stats['per_origine'].get(origine, 0) + 1
        if regina.regina_madre:
            stats['con_genealogia'] += 1

    context = {
        'regine': regine,
        'form': form,
        'stats': stats,
    }

    return render(request, 'regine/ricerca_regine.html', context)


@login_required
def albero_genealogico_completo(request, regina_id):
    """Vista avanzata dell'albero genealogico con più generazioni"""
    regina = get_object_or_404(Regina, pk=regina_id)
    arnia = regina.arnia
    apiario = arnia.apiario

    # Verifica accesso
    if apiario.proprietario != request.user:
        if apiario.gruppo and apiario.condiviso_con_gruppo:
            if not MembroGruppo.objects.filter(utente=request.user, gruppo=apiario.gruppo).exists():
                messages.error(request, "Non hai accesso a questa risorsa.")
                return redirect('dashboard')
        else:
            messages.error(request, "Non hai accesso a questa risorsa.")
            return redirect('dashboard')

    def get_ascendenti(regina, livello=0, max_livelli=5):
        """Recupera ricorsivamente gli ascendenti"""
        if not regina or livello >= max_livelli:
            return None

        return {
            'regina': regina,
            'livello': livello,
            'madre': get_ascendenti(regina.regina_madre, livello + 1, max_livelli)
        }

    def get_discendenti(regina, livello=0, max_livelli=3):
        """Recupera ricorsivamente i discendenti"""
        if not regina or livello >= max_livelli:
            return None

        figlie = Regina.objects.filter(regina_madre=regina)
        return {
            'regina': regina,
            'livello': livello,
            'figlie': [get_discendenti(f, livello + 1, max_livelli) for f in figlie]
        }

    # Costruisci l'albero
    ascendenti = get_ascendenti(regina)
    discendenti = get_discendenti(regina)

    # Conta le generazioni
    def conta_generazioni_su(nodo):
        if not nodo or not nodo.get('madre'):
            return 0
        return 1 + conta_generazioni_su(nodo['madre'])

    def conta_generazioni_giu(nodo):
        if not nodo or not nodo.get('figlie'):
            return 0
        max_figli = max((conta_generazioni_giu(f) for f in nodo['figlie']), default=0)
        return 1 + max_figli

    num_generazioni_su = conta_generazioni_su(ascendenti)
    num_generazioni_giu = conta_generazioni_giu(discendenti)

    # Trova tutte le regine della stessa linea per statistiche
    def raccogli_tutte_regine(nodo, regine_list=None):
        if regine_list is None:
            regine_list = []
        if not nodo:
            return regine_list
        regine_list.append(nodo['regina'])
        if nodo.get('madre'):
            raccogli_tutte_regine(nodo['madre'], regine_list)
        if nodo.get('figlie'):
            for f in nodo['figlie']:
                raccogli_tutte_regine(f, regine_list)
        return regine_list

    tutte_regine = raccogli_tutte_regine(ascendenti)
    tutte_regine.extend([r['regina'] for r in (discendenti.get('figlie') or []) if r])

    # Statistiche linea
    stats_linea = {
        'num_regine': len(set(tutte_regine)),
        'razze': list(set(r.razza for r in tutte_regine)),
        'media_docilita': sum(r.docilita or 0 for r in tutte_regine if r.docilita) /
                         max(1, sum(1 for r in tutte_regine if r.docilita)),
        'media_produttivita': sum(r.produttivita or 0 for r in tutte_regine if r.produttivita) /
                             max(1, sum(1 for r in tutte_regine if r.produttivita)),
    }

    context = {
        'regina': regina,
        'arnia': arnia,
        'apiario': apiario,
        'ascendenti': ascendenti,
        'discendenti': discendenti,
        'num_generazioni_su': num_generazioni_su,
        'num_generazioni_giu': num_generazioni_giu,
        'stats_linea': stats_linea,
    }

    return render(request, 'regine/albero_genealogico_completo.html', context)


@login_required
def confronta_regine(request):
    """Confronta due o più regine"""
    regine_ids = request.GET.getlist('regina')

    if len(regine_ids) < 2:
        messages.warning(request, "Seleziona almeno due regine da confrontare.")
        return redirect('ricerca_regine')

    # Ottieni apiari accessibili
    apiari_propri = Apiario.objects.filter(proprietario=request.user)
    gruppi_utente = Gruppo.objects.filter(membri=request.user)
    apiari_condivisi = Apiario.objects.filter(
        gruppo__in=gruppi_utente,
        condiviso_con_gruppo=True
    ).exclude(proprietario=request.user)
    apiari_accessibili = apiari_propri | apiari_condivisi

    # Verifica accesso e recupera regine
    regine = Regina.objects.filter(
        pk__in=regine_ids,
        arnia__apiario__in=apiari_accessibili
    ).select_related('arnia', 'arnia__apiario', 'regina_madre')

    if regine.count() < 2:
        messages.error(request, "Non hai accesso a tutte le regine selezionate.")
        return redirect('ricerca_regine')

    # Prepara dati per il confronto
    confronto = []
    for regina in regine:
        # Calcola metriche
        media_valutazione = None
        if regina.docilita and regina.produttivita:
            vals = [regina.docilita, regina.produttivita]
            if regina.resistenza_malattie:
                vals.append(regina.resistenza_malattie)
            if regina.tendenza_sciamatura:
                vals.append(5 - regina.tendenza_sciamatura)  # Inverti: bassa sciamatura = buono
            media_valutazione = sum(vals) / len(vals)

        # Conta discendenti
        num_figlie = Regina.objects.filter(regina_madre=regina).count()

        confronto.append({
            'regina': regina,
            'media_valutazione': round(media_valutazione, 1) if media_valutazione else None,
            'num_figlie': num_figlie,
            'eta_giorni': regina.get_eta_giorni(),
        })

    context = {
        'confronto': confronto,
    }

    return render(request, 'regine/confronta_regine.html', context)