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

from .models import Apiario, Arnia, ControlloArnia, Fioritura, Pagamento, QuotaUtente, TrattamentoSanitario, TipoTrattamento 
from .forms import ApiarioForm, ArniaForm, ControlloArniaForm, FiorituraForm, PagamentoForm, QuotaUtenteForm, TrattamentoSanitarioForm, TipoTrattamentoForm


@login_required
def dashboard(request):
    """Vista principale della dashboard"""
    apiari = Apiario.objects.all()
    data_odierna = timezone.now().date()
    
    # Ultimi controlli effettuati
    ultimi_controlli = ControlloArnia.objects.order_by('-data')[:10]
    
    # Fioriture attuali
    fioriture_attuali = Fioritura.objects.filter(
        data_inizio__lte=data_odierna,
        data_fine__gte=data_odierna
    ) | Fioritura.objects.filter(
        data_inizio__lte=data_odierna,
        data_fine__isnull=True
    )
    
    context = {
        'apiari': apiari,
        'ultimi_controlli': ultimi_controlli,
        'fioriture_attuali': fioriture_attuali,
        'data_selezionata': data_odierna
    }
    
    return render(request, 'dashboard.html', context)

@login_required
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
    
    # Recupera le fioriture attive per la data selezionata
    fioriture = Fioritura.objects.filter(
        apiario=apiario,
        data_inizio__lte=data_selezionata,
        data_fine__gte=data_selezionata
    ) | Fioritura.objects.filter(
        apiario=apiario,
        data_inizio__lte=data_selezionata,
        data_fine__isnull=True
    )
    
    for controllo in ultimi_controlli:
        # Calcola la distribuzione dei telaini di scorte
        scorte_totali = controllo.telaini_scorte or 0
        controllo.scorte_sinistra = scorte_totali // 2  # divisione intera per la metà sinistra
        controllo.scorte_destra = scorte_totali - controllo.scorte_sinistra  # resto a destra

    context = {
        'apiario': apiario,
        'arnie': arnie,
        'ultimi_controlli': ultimi_controlli,
        'data_selezionata': data_selezionata,
        'fioriture': fioriture,
    }
    
    return render(request, 'arnie/visualizza_apiario.html', context)

@login_required
def nuovo_controllo(request, arnia_id):
    """Aggiunge un nuovo controllo per un'arnia"""
    arnia = get_object_or_404(Arnia, pk=arnia_id)
    
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
def modifica_controllo(request, controllo_id):
    """Modifica un controllo esistente"""
    controllo = get_object_or_404(ControlloArnia, pk=controllo_id)
    
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
def copia_controllo(request, controllo_id):
    """Copia un controllo esistente su altre arnie"""
    controllo_origine = get_object_or_404(ControlloArnia, pk=controllo_id)
    apiario = controllo_origine.arnia.apiario
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
def elimina_controllo(request, pk):
    """Elimina un controllo esistente"""
    controllo = get_object_or_404(ControlloArnia, pk=pk)
    apiario_id = controllo.arnia.apiario.id
    
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
def gestione_fioriture(request):
    """Gestione delle fioriture"""
    fioriture = Fioritura.objects.all().order_by('-data_inizio')
    
    if request.method == 'POST':
        form = FiorituraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('gestione_fioriture')
    else:
        form = FiorituraForm()
    
    context = {
        'fioriture': fioriture,
        'form': form,
    }
    
    return render(request, 'fioriture/gestione_fioriture.html', context)

@login_required
def gestione_pagamenti(request):
    """Gestione dei pagamenti"""
    pagamenti = Pagamento.objects.all().order_by('-data')
    quote = QuotaUtente.objects.all()
    
    # Calcola il totale dei pagamenti per utente
    pagamenti_per_utente = {}
    for quota in quote:
        pagamenti_utente = Pagamento.objects.filter(utente=quota.utente)
        pagamenti_per_utente[quota.utente.id] = {
            'utente': quota.utente,
            'quota_percentuale': quota.percentuale,
            'pagamenti': pagamenti_utente,
            'totale_pagato': pagamenti_utente.aggregate(Sum('importo'))['importo__sum'] or 0,
        }
    
    # Calcola il totale generale dei pagamenti
    totale_pagamenti = Pagamento.objects.aggregate(Sum('importo'))['importo__sum'] or 0
    
    # Calcola quanto dovrebbe pagare ciascun utente in base alla percentuale
    for user_id, dati in pagamenti_per_utente.items():
        dovuto = totale_pagamenti * (dati['quota_percentuale'] / 100)
        saldo = dati['totale_pagato'] - dovuto
        
        pagamenti_per_utente[user_id]['dovuto'] = dovuto
        pagamenti_per_utente[user_id]['saldo'] = saldo
    
    if request.method == 'POST':
        form = PagamentoForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('gestione_pagamenti')
    else:
        form = PagamentoForm()
    
    context = {
        'pagamenti': pagamenti,
        'pagamenti_per_utente': pagamenti_per_utente,
        'totale_pagamenti': totale_pagamenti,
        'form': form,
    }
    
    return render(request, 'pagamenti/gestione_pagamenti.html', context)

@login_required
def quota_update(request, pk):
    """Vista per modificare una quota utente esistente"""
    quota = get_object_or_404(QuotaUtente, pk=pk)
    
    if request.method == 'POST':
        form = QuotaUtenteForm(request.POST, instance=quota)
        if form.is_valid():
            form.save()
            messages.success(request, "Quota aggiornata con successo.")
            return redirect('gestione_quote')
    else:
        form = QuotaUtenteForm(instance=quota)
    
    context = {
        'form': form,
        'quota': quota,
        'is_update': True,
    }
    
    return render(request, 'pagamenti/form_quota.html', context)

@login_required
def quota_delete(request, pk):
    """Vista per eliminare una quota utente"""
    quota = get_object_or_404(QuotaUtente, pk=pk)
    
    if request.method == 'POST':
        quota.delete()
        messages.success(request, "Quota eliminata con successo.")
        return redirect('gestione_quote')
    
    context = {
        'quota': quota,
    }
    
    return render(request, 'pagamenti/conferma_elimina_quota.html', context)

@login_required
def fioritura_delete(request, pk):
    fioritura = get_object_or_404(Fioritura, pk=pk)
    fioritura.delete()
    return redirect('gestione_fioriture')

@login_required
def pagamento_update(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    
    if request.method == 'POST':
        form = PagamentoForm(request.POST, instance=pagamento)
        if form.is_valid():
            form.save()
            return redirect('gestione_pagamenti')
    else:
        form = PagamentoForm(instance=pagamento)
    
    context = {
        'form': form,
        'pagamento': pagamento,
    }
    
    return render(request, 'pagamenti/form_pagamento.html', context)

@login_required
def pagamento_delete(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    pagamento.delete()
    return redirect('gestione_pagamenti')

@login_required
def gestione_quote(request):
    quote = QuotaUtente.objects.all()
    
    if request.method == 'POST':
        form = QuotaUtenteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('gestione_quote')
    else:
        form = QuotaUtenteForm()
    
    context = {
        'quote': quote,
        'form': form,
    }
    
    return render(request, 'pagamenti/gestione_quote.html', context)

# Aggiungi queste views in core/views.py

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

@login_required
def nuovo_trattamento(request, apiario_id=None):
    """Vista per aggiungere un nuovo trattamento sanitario"""
    apiario = None
    if apiario_id:
        apiario = get_object_or_404(Apiario, pk=apiario_id)
    
    if request.method == 'POST':
        form = TrattamentoSanitarioForm(request.POST)
        if form.is_valid():
            trattamento = form.save(commit=False)
            trattamento.utente = request.user
            
            # Se è selezionato "Applica a tutte le arnie", non salviamo specifiche arnie
            seleziona_tutte = form.cleaned_data.get('seleziona_tutte_arnie')
            
            trattamento.save()
            
            if not seleziona_tutte:
                # Salva le arnie selezionate
                form.save_m2m()
            else:
                # Non selezionare arnie specifiche (si applica a tutto l'apiario)
                trattamento.arnie.clear()
            
            messages.success(request, f"Trattamento {trattamento.tipo_trattamento} programmato con successo.")
            return redirect('gestione_trattamenti')
    else:
        initial_data = {}
        if apiario:
            initial_data['apiario'] = apiario.id
        
        form = TrattamentoSanitarioForm(initial=initial_data)
    
    context = {
        'form': form,
        'apiario': apiario,
    }
    
    return render(request, 'trattamenti/form_trattamento.html', context)

@login_required
def modifica_trattamento(request, pk):
    """Vista per modificare un trattamento esistente"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    
    # Verifica se tutte le arnie dell'apiario sono incluse nel trattamento
    tutte_arnie_apiario = set(Arnia.objects.filter(apiario=trattamento.apiario, attiva=True).values_list('id', flat=True))
    arnie_trattamento = set(trattamento.arnie.values_list('id', flat=True))
    seleziona_tutte = len(arnie_trattamento) == 0 or arnie_trattamento == tutte_arnie_apiario
    
    if request.method == 'POST':
        form = TrattamentoSanitarioForm(request.POST, instance=trattamento)
        if form.is_valid():
            trattamento = form.save(commit=False)
            
            # Gestione della selezione "tutte le arnie"
            seleziona_tutte = form.cleaned_data.get('seleziona_tutte_arnie')
            
            trattamento.save()
            
            if not seleziona_tutte:
                # Salva le arnie selezionate
                form.save_m2m()
            else:
                # Non selezionare arnie specifiche (si applica a tutto l'apiario)
                trattamento.arnie.clear()
            
            messages.success(request, f"Trattamento aggiornato con successo.")
            return redirect('gestione_trattamenti')
    else:
        form = TrattamentoSanitarioForm(instance=trattamento, initial={'seleziona_tutte_arnie': seleziona_tutte})
    
    context = {
        'form': form,
        'trattamento': trattamento,
    }
    
    return render(request, 'trattamenti/form_trattamento.html', context)

@login_required
def elimina_trattamento(request, pk):
    """Vista per eliminare un trattamento"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    
    if request.method == 'POST':
        trattamento.delete()
        messages.success(request, "Trattamento eliminato con successo.")
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
def cambio_stato_trattamento(request, pk, nuovo_stato):
    """Vista per cambiare rapidamente lo stato di un trattamento"""
    trattamento = get_object_or_404(TrattamentoSanitario, pk=pk)
    stati_validi = dict(TrattamentoSanitario.STATO_CHOICES).keys()
    
    if nuovo_stato in stati_validi:
        trattamento.stato = nuovo_stato
        
        # Se stiamo completando il trattamento, impostiamo la data di fine se non è già impostata
        if nuovo_stato == 'completato' and not trattamento.data_fine:
            trattamento.data_fine = timezone.now().date()
        
        trattamento.save()
        messages.success(request, f"Stato del trattamento aggiornato a: {dict(TrattamentoSanitario.STATO_CHOICES)[nuovo_stato]}")
    else:
        messages.error(request, "Stato non valido.")
    
    return redirect('gestione_trattamenti')

# Aggiungi queste viste in core/views.py

@login_required
def mappa_apiari(request):
    """Vista per la mappa degli apiari e delle fioriture"""
    apiari = Apiario.objects.all()
    
    # Ottieni la data corrente
    oggi = timezone.now().date()
    
    # Recupera le fioriture attive
    fioriture_attive = Fioritura.objects.filter(
        data_inizio__lte=oggi
    ).filter(
        Q(data_fine__isnull=True) | Q(data_fine__gte=oggi)
    )
    
    # Recupera le fioriture programmate (future)
    fioriture_programmate = Fioritura.objects.filter(
        data_inizio__gt=oggi
    )
    
    # Recupera le fioriture passate (ultimi 6 mesi)
    sei_mesi_fa = oggi - timedelta(days=180)
    fioriture_passate = Fioritura.objects.filter(
        data_fine__lt=oggi,
        data_fine__gte=sei_mesi_fa
    )
    
    context = {
        'apiari': apiari,
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

# Altre viste necessarie per la gestione completa
class ArniaCreateView(LoginRequiredMixin, CreateView):
    model = Arnia
    form_class = ArniaForm
    template_name = 'arnie/form_arnia.html'
    
    def get_success_url(self):
        return reverse_lazy('visualizza_apiario', kwargs={'apiario_id': self.object.apiario.id})

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

class FiorituraUpdateView(LoginRequiredMixin, UpdateView):
    model = Fioritura
    form_class = FiorituraForm
    template_name = 'fioriture/form_fioritura.html'
    success_url = reverse_lazy('gestione_fioriture')

