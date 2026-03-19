# core/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import (
    Apiario, Arnia, ControlloArnia, Fioritura, Pagamento, QuotaUtente,
    TipoTrattamento, TrattamentoSanitario, Melario, Smielatura, Gruppo, MembroGruppo, InvitoGruppo,
    Regina, CategoriaAttrezzatura, Attrezzatura, ManutenzioneAttrezzatura,
    PrestitoAttrezzatura, SpesaAttrezzatura, Cliente, Vendita, DettaglioVendita,
    Invasettamento, Nucleo, ControlloNucleo, Maturatore, ContenitoreStoccaggio,
)

from django.utils  import timezone

class GruppoForm(forms.ModelForm):
    """Form per la creazione e modifica di un gruppo"""
    class Meta:
        model = Gruppo
        fields = ['nome', 'descrizione']
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
        }

class InvitoGruppoForm(forms.ModelForm):
    """Form per l'invio di un invito a un gruppo"""
    class Meta:
        model = InvitoGruppo
        fields = ['email', 'ruolo_proposto']
        
    def clean_email(self):
        email = self.cleaned_data.get('email')
        gruppo = self.instance.gruppo if self.instance and self.instance.pk else self.initial.get('gruppo')
        
        # Verifica se l'utente con questa email è già membro del gruppo
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            if gruppo and gruppo.membri.filter(id=user.id).exists():
                raise forms.ValidationError("Questo utente è già membro del gruppo.")
        
        # Verifica se esiste già un invito attivo per questa email nel gruppo
        if InvitoGruppo.objects.filter(email=email, gruppo=gruppo, stato='inviato').exists():
            raise forms.ValidationError("Esiste già un invito attivo per questa email.")
            
        return email

class MembroGruppoRoleForm(forms.ModelForm):
    """Form per modificare il ruolo di un membro del gruppo"""
    class Meta:
        model = MembroGruppo
        fields = ['ruolo']

class ApiarioGruppoForm(forms.ModelForm):
    """Form per associare un apiario a un gruppo o modificare le impostazioni di condivisione"""
    class Meta:
        model = Apiario
        fields = ['gruppo', 'condiviso_con_gruppo', 'visibilita_mappa']
        widgets = {
            'gruppo': forms.Select(attrs={'class': 'form-control form-select'}),
            'condiviso_con_gruppo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'visibilita_mappa': forms.RadioSelect(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'gruppo': 'Gruppo',
            'condiviso_con_gruppo': 'Condividi con il gruppo',
            'visibilita_mappa': 'Visibilità sulla mappa',
        }
        help_texts = {
            'condiviso_con_gruppo': 'Se selezionato, tutti i membri del gruppo avranno accesso in base al loro ruolo',
            'visibilita_mappa': 'Scegli chi può vedere questo apiario sulla mappa',
        }
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            # Mostra solo i gruppi di cui l'utente è membro
            self.fields['gruppo'].queryset = Gruppo.objects.filter(membri=user)
            self.fields['gruppo'].empty_label = "Nessun gruppo (privato)"

class DateInput(forms.DateInput):
    input_type = 'date'

class ApiarioForm(forms.ModelForm):
    class Meta:
        model = Apiario
        fields = ['nome', 'posizione', 'latitudine', 'longitudine', 'note', 'monitoraggio_meteo']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 3}),
            'latitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lat-input'}),
            'longitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lng-input'}),
            'monitoraggio_meteo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'monitoraggio_meteo': 'Abilita monitoraggio meteo',
        }
        help_texts = {
            'monitoraggio_meteo': 'Se abilitato, verranno raccolti e visualizzati dati meteorologici per questo apiario',
        }

# Modifica alla classe ArniaForm in forms.py
from django import forms
from django.utils.safestring import mark_safe
from .models import Arnia

class ColoredSelect(forms.Select):
    """Widget personalizzato per visualizzare i colori nel dropdown"""
    
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            color_code = ''
            if value in Arnia.COLORE_HEX:
                hex_color = Arnia.COLORE_HEX[value]
                label_text = dict(Arnia.COLORE_CHOICES).get(value, value)
                color_square = f'<span style="display:inline-block; width:15px; height:15px; background-color:{hex_color}; margin-right:5px; border:1px solid #ccc;"></span>'
                option['label'] = mark_safe(f"{color_square} {label_text}")
        return option

class ArniaForm(forms.ModelForm):
    colore_hex = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
        label="Colore personalizzato"
    )

    class Meta:
        model = Arnia
        fields = ['apiario', 'numero', 'colore', 'colore_hex', 'tipo_arnia',
                  'data_installazione', 'note', 'attiva']
        widgets = {
            'data_installazione': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'colore': ColoredSelect(attrs={'class': 'form-select color-select'}),
            'tipo_arnia': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'tipo_arnia': 'Tipo arnia / cassetta',
        }
        help_texts = {
            'tipo_arnia': 'Modello costruttivo della scatola. Può essere cambiato nel tempo mantenendo la stessa famiglia.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['colore'].help_text = "Seleziona 'Altro' per utilizzare un colore personalizzato"

class ControlloArniaForm(forms.ModelForm):
    class Meta:
        model = ControlloArnia
        fields = [
            'data', 'telaini_scorte', 'telaini_covata', 'presenza_regina', 
            'sciamatura', 'data_sciamatura', 'note_sciamatura',
            'problemi_sanitari', 'note_problemi', 'note'
        ]
        widgets = {
            'data': DateInput(),
            'data_sciamatura': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'note_sciamatura': forms.Textarea(attrs={'rows': 2}),
            'note_problemi': forms.Textarea(attrs={'rows': 2}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendi alcuni campi condizionali tramite JavaScript
        self.fields['data_sciamatura'].required = False
        self.fields['note_sciamatura'].required = False
        self.fields['note_problemi'].required = False

# Aggiungi al file forms.py

class ReginaForm(forms.ModelForm):
    """Form per la creazione e modifica di una regina"""
    
    class Meta:
        model = Regina
        fields = [
            'data_nascita', 'data_introduzione', 'origine', 'razza',
            'regina_madre', 'marcata', 'codice_marcatura', 'colore_marcatura',
            'fecondata', 'selezionata', 'docilita', 'produttivita',
            'resistenza_malattie', 'tendenza_sciamatura', 'note'
        ]
        widgets = {
            'data_nascita': DateInput(),
            'data_introduzione': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'codice_marcatura': forms.TextInput(attrs={'placeholder': 'Es. 45AX78'}),
            'docilita': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'produttivita': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'resistenza_malattie': forms.NumberInput(attrs={'min': 1, 'max': 5}),
            'tendenza_sciamatura': forms.NumberInput(attrs={'min': 1, 'max': 5}),
        }
    
    def __init__(self, *args, **kwargs):
        arnia = kwargs.pop('arnia', None)
        super().__init__(*args, **kwargs)
        
        # Limitiamo le regine madri alle regine esistenti
        self.fields['regina_madre'].queryset = Regina.objects.all().order_by('-data_introduzione')
        
        # Imposta data di oggi per data_introduzione se è un nuovo record
        if not self.instance.pk and not self.initial.get('data_introduzione'):
            self.initial['data_introduzione'] = timezone.now().date()
        
        # Modifiche condizionali in base agli attributi
        if self.instance.pk:
            self.fields['docilita'].help_text = "Valutazione docilità (1=bassa, 5=alta)"
            self.fields['produttivita'].help_text = "Valutazione produttività (1=bassa, 5=alta)"
            self.fields['resistenza_malattie'].help_text = "Resistenza alle malattie (1=bassa, 5=alta)"
            self.fields['tendenza_sciamatura'].help_text = "Tendenza alla sciamatura (1=bassa, 5=alta)"
        
        # Aggiungi arnia all'istanza se specificata
        if arnia and not self.instance.pk:
            self.instance.arnia = arnia


class SostituzioneReginaForm(forms.Form):
    """Form per la sostituzione della regina"""
    
    data_sostituzione = forms.DateField(
        widget=DateInput(),
        initial=timezone.now().date(),
        label="Data sostituzione"
    )
    
    motivo = forms.ChoiceField(
        choices=[
            ('età', 'Regina vecchia (età)'),
            ('produttività', 'Scarsa produttività'),
            ('aggressività', 'Eccessiva aggressività'),
            ('sciamatura', 'Tendenza alla sciamatura'),
            ('malattia', 'Problemi sanitari'),
            ('altro', 'Altro (specificare nelle note)'),
        ],
        label="Motivo sostituzione"
    )
    
    nuova_regina_origine = forms.ChoiceField(
        choices=Regina.ORIGINE_CHOICES,
        initial='acquistata',
        label="Origine della nuova regina"
    )
    
    nuova_regina_razza = forms.ChoiceField(
        choices=Regina.RAZZA_CHOICES,
        initial='ligustica',
        label="Razza della nuova regina"
    )
    
    nuova_regina_data_nascita = forms.DateField(
        widget=DateInput(),
        required=False,
        label="Data nascita nuova regina (se conosciuta)"
    )
    
    nuova_regina_marcata = forms.BooleanField(
        required=False,
        initial=False,
        label="La nuova regina è marcata"
    )
    
    nuova_regina_codice = forms.CharField(
        max_length=50,
        required=False,
        label="Codice di marcatura (se presente)"
    )
    
    nuova_regina_colore_marcatura = forms.ChoiceField(
        choices=Regina.COLORE_MARCATURA_CHOICES,
        initial='non_marcata',
        required=False,
        label="Colore di marcatura"
    )
    
    note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Note sulla sostituzione"
    )

class MelarioForm(forms.ModelForm):
    """Form per l'aggiunta e modifica di un melario"""

    class Meta:
        model = Melario
        fields = ['numero_telaini', 'posizione', 'tipo_melario', 'stato_favi',
                  'escludi_regina', 'data_posizionamento', 'note']
        widgets = {
            'data_posizionamento': DateInput(),
            'note': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        arnia = kwargs.pop('arnia', None)
        super().__init__(*args, **kwargs)
        
        # Se è specificata un'arnia, pre-compila il campo posizione
        if arnia and not self.instance.pk:
            # Conta i melari esistenti dell'arnia per suggerire la posizione successiva
            melari_count = Melario.objects.filter(arnia=arnia, stato='posizionato').count()
            self.fields['posizione'].initial = melari_count + 1
            
        # Aggiungi aiuto per il campo numero_telaini
        self.fields['numero_telaini'].help_text = "Numero di telaini presenti nel melario"
        
        # Per l'editing, rendi la posizione non modificabile se il melario è già posizionato
        if self.instance.pk and self.instance.stato == 'posizionato':
            self.fields['posizione'].disabled = True

class RimozioneMelarioForm(forms.Form):
    """Form per la rimozione di un melario"""
    data_rimozione = forms.DateField(
        widget=DateInput(),
        initial=timezone.now().date(),
        label="Data rimozione"
    )
    note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False,
        label="Note sulla rimozione"
    )

class SmielaturaForm(forms.ModelForm):
    """Form per la registrazione di una smielatura"""
    melari = forms.ModelMultipleChoiceField(
        queryset=Melario.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="Melari da smielaturare"
    )
    
    class Meta:
        model = Smielatura
        fields = ['data', 'quantita_miele', 'tipo_miele', 'note', 'melari']
        widgets = {
            'data': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        apiario = kwargs.pop('apiario', None)
        super().__init__(*args, **kwargs)
        
        # Filtra i melari mostrati nel form in base all'apiario
        if apiario:
            # Melari in stato 'in_smielatura' o 'posizionato'
            self.fields['melari'].queryset = Melario.objects.filter(
                arnia__apiario=apiario
            ).filter(
                Q(stato='in_smielatura') | Q(stato='posizionato')
            ).select_related('arnia')

# Modifica a FiorituraForm in core/forms.py
class FiorituraForm(forms.ModelForm):
    class Meta:
        model = Fioritura
        fields = [
            'pianta', 'data_inizio', 'data_fine', 
            'latitudine', 'longitudine', 'raggio', 'apiario', 'note'
        ]
        widgets = {
            'data_inizio': DateInput(),
            'data_fine': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'latitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lat-input'}),
            'longitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lng-input'}),
            'raggio': forms.NumberInput(attrs={'min': '50', 'max': '5000', 'step': '50'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_fine'].required = False
        self.fields['apiario'].required = False        
        self.fields['raggio'].required = False


class PagamentoForm(forms.ModelForm):
    """Form per la creazione e modifica di un pagamento"""
    class Meta:
        model = Pagamento
        fields = ['utente', 'importo', 'data', 'descrizione']
        widgets = {
            'utente': forms.Select(attrs={'class': 'form-control'}),
            'importo': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'data': DateInput(attrs={'class': 'form-control'}),
            'descrizione': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        gruppo = kwargs.pop('gruppo', None)
        super().__init__(*args, **kwargs)
        
        # Se è specificato un gruppo, filtra gli utenti mostrati nel form
        if gruppo:
            self.fields['utente'].queryset = User.objects.filter(gruppi=gruppo)
        else:
            # Se non è specificato un gruppo, mostra solo l'utente corrente
            current_user = kwargs.get('initial', {}).get('utente')
            if current_user:
                self.fields['utente'].queryset = User.objects.filter(id=current_user.id)
            else:
                self.fields['utente'].queryset = User.objects.none()

class QuotaUtenteForm(forms.ModelForm):
    """Form per la creazione e modifica di una quota utente"""
    class Meta:
        model = QuotaUtente
        fields = ['utente', 'percentuale']
        widgets = {
            'utente': forms.Select(attrs={'class': 'form-control'}),
            'percentuale': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'max': '100', 'step': '0.01'}),
        }
        
    def __init__(self, *args, **kwargs):
        gruppo = kwargs.pop('gruppo', None)
        super().__init__(*args, **kwargs)
        
        # Se è specificato un gruppo, filtra gli utenti mostrati nel form
        if gruppo:
            self.fields['utente'].queryset = User.objects.filter(gruppi=gruppo)
        else:
            # Se non è specificato un gruppo, mostra solo l'utente corrente
            current_user = kwargs.get('initial', {}).get('utente')
            if current_user:
                self.fields['utente'].queryset = User.objects.filter(id=current_user.id)
            else:
                self.fields['utente'].queryset = User.objects.none()
                
    def clean_percentuale(self):
        percentuale = self.cleaned_data.get('percentuale')
        if percentuale <= 0 or percentuale > 100:
            raise forms.ValidationError("La percentuale deve essere compresa tra 0 e 100.")
        return percentuale


class TipoTrattamentoForm(forms.ModelForm):
    class Meta:
        model = TipoTrattamento
        fields = [
            'nome', 
            'principio_attivo', 
            'descrizione', 
            'istruzioni', 
            'tempo_sospensione',
            'richiede_blocco_covata',
            'giorni_blocco_covata',
            'nota_blocco_covata'
        ]
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'istruzioni': forms.Textarea(attrs={'rows': 4}),
            'nota_blocco_covata': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendi alcuni campi condizionali tramite JavaScript
        self.fields['giorni_blocco_covata'].required = False
        self.fields['nota_blocco_covata'].required = False

class TrattamentoSanitarioForm(forms.ModelForm):
    class Meta:
        model = TrattamentoSanitario
        fields = [
            'apiario', 
            'tipo_trattamento', 
            'data_inizio', 
            'data_fine', 
            'stato', 
            'arnie',
            'blocco_covata_attivo',
            'data_inizio_blocco',
            'data_fine_blocco',
            'metodo_blocco',
            'note_blocco',
            'note'
        ]
        widgets = {
            'data_inizio': DateInput(),
            'data_fine': DateInput(),
            'data_inizio_blocco': DateInput(),
            'data_fine_blocco': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'note_blocco': forms.Textarea(attrs={'rows': 3}),
            'arnie': forms.CheckboxSelectMultiple(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'apiario' in self.initial:
            apiario_id = self.initial['apiario']
            self.fields['arnie'].queryset = Arnia.objects.filter(apiario_id=apiario_id, attiva=True)
        
        # Aggiungiamo un campo nascosto per gestire la selezione di tutte le arnie
        self.fields['seleziona_tutte_arnie'] = forms.BooleanField(
            required=False,
            initial=False,
            label="Applica a tutte le arnie dell'apiario",
            help_text="Se selezionato, il trattamento sarà applicato a tutte le arnie dell'apiario"
        )
        
        # Campi per gestire il blocco di covata resi condizionali
        self.fields['data_inizio_blocco'].required = False
        self.fields['data_fine_blocco'].required = False
        self.fields['metodo_blocco'].required = False
        self.fields['note_blocco'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        data_inizio = cleaned_data.get('data_inizio')
        data_fine = cleaned_data.get('data_fine')
        
        # Verifica che la data di fine sia successiva alla data di inizio
        if data_inizio and data_fine and data_fine < data_inizio:
            self.add_error('data_fine', "La data di fine deve essere successiva alla data di inizio.")
        
        # Verifica le date del blocco di covata
        blocco_covata_attivo = cleaned_data.get('blocco_covata_attivo')
        data_inizio_blocco = cleaned_data.get('data_inizio_blocco')
        data_fine_blocco = cleaned_data.get('data_fine_blocco')
        
        if blocco_covata_attivo:
            if not data_inizio_blocco:
                self.add_error('data_inizio_blocco', "La data di inizio blocco covata è richiesta se il blocco è attivo.")
            
            if data_inizio_blocco and data_fine_blocco and data_fine_blocco < data_inizio_blocco:
                self.add_error('data_fine_blocco', "La data di fine blocco covata deve essere successiva alla data di inizio.")
        
        return cleaned_data

from django import forms
from django.contrib.auth.models import User
from .models import Profilo, ImmagineProfilo

class UserUpdateForm(forms.ModelForm):
    """Form per aggiornare le informazioni dell'utente"""
    email = forms.EmailField()
    first_name = forms.CharField(max_length=30, required=False, label="Nome")
    last_name = forms.CharField(max_length=30, required=False, label="Cognome")
    
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']

class ProfiloUpdateForm(forms.ModelForm):
    """Form per aggiornare il profilo utente"""
    immagine = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label="Immagine Profilo"
    )
    data_nascita = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label="Data di nascita"
    )
    bio = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
        label="Bio"
    )
    gemini_api_key = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'off',
                                          'placeholder': 'AIzaSy...'},
                                   render_value=True),
        label="Gemini API Key personale",
        help_text="La tua chiave API Google Gemini (da <a href='https://aistudio.google.com/app/apikey' "
                  "target='_blank'>Google AI Studio</a>). Lascia vuoto per usare quella di sistema."
    )

    class Meta:
        model = Profilo
        fields = ['immagine', 'data_nascita', 'bio', 'gemini_api_key']

class GruppoImmagineForm(forms.ModelForm):
    """Form per aggiornare l'immagine del profilo del gruppo"""
    immagine = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        label="Immagine del Gruppo"
    )

    class Meta:
        model = ImmagineProfilo
        fields = ['immagine']


# ============================================
# FORMS GESTIONE ATTREZZATURE
# ============================================

class CategoriaAttrezzaturaForm(forms.ModelForm):
    """Form per la creazione e modifica di categorie attrezzature"""
    class Meta:
        model = CategoriaAttrezzatura
        fields = ['nome', 'descrizione', 'icona']
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 2}),
            'icona': forms.TextInput(attrs={'placeholder': 'es. bi-tools'}),
        }


class AttrezzaturaForm(forms.ModelForm):
    """Form per la creazione e modifica di attrezzature"""
    class Meta:
        model = Attrezzatura
        fields = [
            'nome', 'categoria', 'descrizione', 'marca', 'modello', 'numero_serie',
            'gruppo', 'condiviso_con_gruppo', 'stato', 'condizione',
            'apiario', 'posizione', 'prezzo_acquisto', 'data_acquisto',
            'fornitore', 'garanzia_fino_a', 'vita_utile_anni',
            'quantita', 'unita_misura', 'note', 'immagine'
        ]
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'data_acquisto': DateInput(),
            'garanzia_fino_a': DateInput(),
            'prezzo_acquisto': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'vita_utile_anni': forms.NumberInput(attrs={'min': '1', 'max': '50'}),
            'quantita': forms.NumberInput(attrs={'min': '1'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Filtra apiari e gruppi dell'utente
            self.fields['apiario'].queryset = Apiario.objects.filter(proprietario=user)
            self.fields['gruppo'].queryset = Gruppo.objects.filter(membri=user)
            self.fields['gruppo'].empty_label = "Nessun gruppo (privato)"

        # Aiuti per i campi
        self.fields['vita_utile_anni'].help_text = "Anni stimati di utilizzo per calcolo ammortamento"
        self.fields['condiviso_con_gruppo'].help_text = "Se selezionato, tutti i membri del gruppo potranno vedere questa attrezzatura"


class AttrezzaturaFiltroForm(forms.Form):
    """Form per filtrare la lista delle attrezzature"""
    categoria = forms.ModelChoiceField(
        queryset=CategoriaAttrezzatura.objects.all(),
        required=False,
        empty_label="Tutte le categorie"
    )
    stato = forms.ChoiceField(
        choices=[('', 'Tutti gli stati')] + list(Attrezzatura.STATO_CHOICES),
        required=False
    )
    condizione = forms.ChoiceField(
        choices=[('', 'Tutte le condizioni')] + list(Attrezzatura.CONDIZIONE_CHOICES),
        required=False
    )
    cerca = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Cerca per nome, marca, modello...'})
    )


class ManutenzioneAttrezzaturaForm(forms.ModelForm):
    """Form per la registrazione di manutenzioni"""
    class Meta:
        model = ManutenzioneAttrezzatura
        fields = [
            'tipo', 'stato', 'data_programmata', 'data_esecuzione',
            'descrizione', 'costo', 'eseguito_da', 'prossima_manutenzione', 'note'
        ]
        widgets = {
            'data_programmata': DateInput(),
            'data_esecuzione': DateInput(),
            'prossima_manutenzione': DateInput(),
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'costo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_esecuzione'].required = False
        self.fields['costo'].required = False
        self.fields['prossima_manutenzione'].required = False


class PrestitoAttrezzaturaForm(forms.ModelForm):
    """Form per la richiesta di prestito attrezzatura"""
    class Meta:
        model = PrestitoAttrezzatura
        fields = ['data_inizio_prestito', 'data_fine_prevista', 'motivo']
        widgets = {
            'data_inizio_prestito': DateInput(),
            'data_fine_prevista': DateInput(),
            'motivo': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        data_inizio = cleaned_data.get('data_inizio_prestito')
        data_fine = cleaned_data.get('data_fine_prevista')

        if data_inizio and data_fine and data_fine < data_inizio:
            self.add_error('data_fine_prevista',
                          "La data di restituzione deve essere successiva alla data di inizio.")

        return cleaned_data


class RestituzioneAttrezzaturaForm(forms.Form):
    """Form per la restituzione di un'attrezzatura prestata"""
    data_restituzione = forms.DateField(
        widget=DateInput(),
        label="Data restituzione"
    )
    note_restituzione = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        label="Note sullo stato al momento della restituzione"
    )
    nuova_condizione = forms.ChoiceField(
        choices=Attrezzatura.CONDIZIONE_CHOICES,
        required=False,
        label="Condizione attuale dell'attrezzatura"
    )


class SpesaAttrezzaturaForm(forms.ModelForm):
    """Form per la registrazione di spese relative alle attrezzature"""
    class Meta:
        model = SpesaAttrezzatura
        fields = ['tipo', 'descrizione', 'importo', 'data', 'fornitore', 'numero_fattura', 'note']
        widgets = {
            'data': DateInput(),
            'importo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'note': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fornitore'].required = False
        self.fields['numero_fattura'].required = False


# ============================================
# FORMS RICERCA GENEALOGIA REGINE
# ============================================

class RicercaReginaForm(forms.Form):
    """Form per la ricerca avanzata di regine"""
    razza = forms.ChoiceField(
        choices=[('', 'Tutte le razze')] + list(Regina.RAZZA_CHOICES),
        required=False
    )
    origine = forms.ChoiceField(
        choices=[('', 'Tutte le origini')] + list(Regina.ORIGINE_CHOICES),
        required=False
    )
    anno_nascita = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Anno', 'min': 2000, 'max': 2100})
    )
    selezionata = forms.ChoiceField(
        choices=[('', 'Tutte'), ('si', 'Solo selezionate'), ('no', 'Solo non selezionate')],
        required=False
    )
    con_figlie = forms.BooleanField(
        required=False,
        label="Solo regine con discendenza registrata"
    )
    valutazione_minima = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=5,
        widget=forms.NumberInput(attrs={'min': 1, 'max': 5}),
        label="Valutazione minima (media)"
    )


# ──────────────────────────────────────────────
# Vendite & Clienti
# ──────────────────────────────────────────────

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nome', 'telefono', 'email', 'indirizzo', 'note']
        widgets = {
            'nome':      forms.TextInput(attrs={'class': 'form-control'}),
            'telefono':  forms.TextInput(attrs={'class': 'form-control'}),
            'email':     forms.EmailInput(attrs={'class': 'form-control'}),
            'indirizzo': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'note':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class VenditaForm(forms.ModelForm):
    class Meta:
        model = Vendita
        fields = ['data', 'cliente', 'acquirente_nome', 'canale', 'pagamento', 'note']
        widgets = {
            'data':           forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cliente':        forms.Select(attrs={'class': 'form-control form-select'}),
            'acquirente_nome': forms.TextInput(attrs={'class': 'form-control'}),
            'canale':         forms.Select(attrs={'class': 'form-control form-select'}),
            'pagamento':      forms.Select(attrs={'class': 'form-control form-select'}),
            'note':           forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['cliente'].queryset = Cliente.objects.filter(utente=user)
        self.fields['cliente'].required = False
        self.fields['acquirente_nome'].required = False


class DettaglioVenditaForm(forms.ModelForm):
    class Meta:
        model = DettaglioVendita
        fields = ['categoria', 'tipo_miele', 'formato_vasetto', 'quantita', 'prezzo_unitario']
        widgets = {
            'categoria':       forms.Select(attrs={'class': 'form-control form-select det-categoria'}),
            'tipo_miele':      forms.TextInput(attrs={'class': 'form-control det-tipo-miele', 'placeholder': 'es. Acacia'}),
            'formato_vasetto': forms.NumberInput(attrs={'class': 'form-control det-formato', 'placeholder': 'grammi'}),
            'quantita':        forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'prezzo_unitario': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }


DettaglioVenditaFormSet = forms.inlineformset_factory(
    Vendita,
    DettaglioVendita,
    form=DettaglioVenditaForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class InvasettamentoForm(forms.ModelForm):
    class Meta:
        model = Invasettamento
        fields = ['data', 'tipo_miele', 'formato_vasetto', 'numero_vasetti', 'lotto', 'note']
        widgets = {
            'data':           forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'tipo_miele':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Acacia, Millefiori'}),
            'formato_vasetto':forms.Select(attrs={'class': 'form-control form-select'},
                                           choices=[(250,'250g'),(500,'500g'),(1000,'1kg')]),
            'numero_vasetti': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'lotto':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. LOT-2025-001'}),
            'note':           forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lotto'].required = False
        self.fields['note'].required = False
        if not self.instance.pk:
            self.fields['data'].initial = timezone.now().date()


class NucleoForm(forms.ModelForm):
    class Meta:
        model = Nucleo
        fields = ['apiario', 'numero', 'colore_hex', 'data_installazione', 'note']
        widgets = {
            'apiario':           forms.Select(attrs={'class': 'form-control form-select'}),
            'numero':            forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'colore_hex':        forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color', 'style': 'width:60px;'}),
            'data_installazione':forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'note':              forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['apiario'].queryset = Apiario.objects.filter(proprietario=user)
        self.fields['note'].required = False
        if not self.instance.pk:
            self.fields['data_installazione'].initial = timezone.now().date()


class ControlloNucleoForm(forms.ModelForm):
    class Meta:
        model = ControlloNucleo
        fields = ['data', 'n_telaini', 'forza_colonia', 'presenza_regina', 'note']
        widgets = {
            'data':            forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'n_telaini':       forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 20}),
            'forza_colonia':   forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'presenza_regina': forms.Select(attrs={'class': 'form-control form-select'},
                                            choices=[(True,'Sì'),(False,'No'),('','Non verificata')]),
            'note':            forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['n_telaini'].required = False
        self.fields['forza_colonia'].required = False
        self.fields['presenza_regina'].required = False
        self.fields['note'].required = False
        if not self.instance.pk:
            self.fields['data'].initial = timezone.now().date()

# ─── CANTINA FORMS ────────────────────────────────────────────────────────────

class MaturatoreForm(forms.ModelForm):
    class Meta:
        model = Maturatore
        fields = ['nome', 'tipo_miele', 'capacita_kg', 'kg_attuali', 'smielatura', 'data_inizio', 'giorni_maturazione', 'note']
        widgets = {
            'nome':              forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Maturatore 200L'}),
            'tipo_miele':        forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Millefiori, Acacia'}),
            'capacita_kg':       forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.1'}),
            'kg_attuali':        forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.1'}),
            'smielatura':        forms.Select(attrs={'class': 'form-control form-select'}),
            'data_inizio':       forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'giorni_maturazione':forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 365}),
            'note':              forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['smielatura'].required = False
        self.fields['note'].required = False
        if user:
            self.fields['smielatura'].queryset = Smielatura.objects.filter(utente=user).order_by('-data')
            self.fields['smielatura'].label_from_instance = lambda s: f"{s.data.strftime('%d/%m/%Y')} – {s.tipo_miele} ({s.quantita_miele} kg)"
        if not self.instance.pk:
            self.fields['data_inizio'].initial = timezone.now().date()
            self.fields['giorni_maturazione'].initial = 21
            self.fields['kg_attuali'].initial = 0


class ContenitoreStoccaggioForm(forms.ModelForm):
    class Meta:
        model = ContenitoreStoccaggio
        fields = ['nome', 'tipo', 'capacita_kg', 'kg_attuali', 'tipo_miele', 'maturatore', 'data_riempimento', 'stato', 'note']
        widgets = {
            'nome':             forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Secchio 25kg #1'}),
            'tipo':             forms.Select(attrs={'class': 'form-control form-select'}),
            'capacita_kg':      forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.1'}),
            'kg_attuali':       forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'step': '0.1'}),
            'tipo_miele':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Millefiori, Acacia'}),
            'maturatore':       forms.Select(attrs={'class': 'form-control form-select'}),
            'data_riempimento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'stato':            forms.Select(attrs={'class': 'form-control form-select'}),
            'note':             forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nome'].required = False
        self.fields['maturatore'].required = False
        self.fields['note'].required = False
        if user:
            self.fields['maturatore'].queryset = Maturatore.objects.filter(utente=user).exclude(stato='svuotato')
            self.fields['maturatore'].label_from_instance = lambda m: f"{m.nome} – {m.tipo_miele} ({m.kg_attuali} kg)"
        if not self.instance.pk:
            self.fields['data_riempimento'].initial = timezone.now().date()


class InvasettaDaContenitoreForm(forms.ModelForm):
    class Meta:
        model = Invasettamento
        fields = ['data', 'tipo_miele', 'formato_vasetto', 'numero_vasetti', 'lotto', 'note']
        widgets = {
            'data':           forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'tipo_miele':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. Acacia, Millefiori'}),
            'formato_vasetto':forms.Select(attrs={'class': 'form-control form-select'},
                                           choices=[(250,'250g'),(500,'500g'),(1000,'1 kg')]),
            'numero_vasetti': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'lotto':          forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'es. LOT-2025-001'}),
            'note':           forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lotto'].required = False
        self.fields['note'].required = False
        if not self.instance.pk:
            self.fields['data'].initial = timezone.now().date()
