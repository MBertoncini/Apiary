# core/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import (
    Apiario, Arnia, ControlloArnia, Fioritura, Pagamento, QuotaUtente,
    TipoTrattamento, TrattamentoSanitario
)

# core/forms.py
# Aggiungi questi form al file esistente 

from django import forms
from django.contrib.auth.models import User
from .models import Gruppo, MembroGruppo, InvitoGruppo, Apiario

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
        fields = ['nome', 'posizione', 'latitudine', 'longitudine', 'note']
        widgets = {
            'note': forms.Textarea(attrs={'rows': 3}),
            'latitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lat-input'}),
            'longitudine': forms.NumberInput(attrs={'step': '0.000001', 'class': 'coordinate-input lng-input'}),
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
        fields = ['apiario', 'numero', 'colore', 'colore_hex', 'data_installazione', 'note', 'attiva']
        widgets = {
            'data_installazione': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
            'colore': ColoredSelect(attrs={'class': 'form-select color-select'}),
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
    
    class Meta:
        model = Profilo
        fields = ['immagine', 'data_nascita', 'bio']

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