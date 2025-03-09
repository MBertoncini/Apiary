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

class FiorituraForm(forms.ModelForm):
    class Meta:
        model = Fioritura
        fields = [
            'apiario', 'pianta', 'data_inizio', 'data_fine', 
            'latitudine', 'longitudine', 'raggio', 'note'
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
        self.fields['latitudine'].required = False
        self.fields['longitudine'].required = False
        self.fields['raggio'].required = False
        
        # Aggiungi un campo per copiare le coordinate dall'apiario
        self.fields['use_apiario_coordinates'] = forms.BooleanField(
            required=False,
            initial=False,
            label="Usa coordinate dell'apiario",
            help_text="Se selezionato, verranno utilizzate le coordinate dell'apiario selezionato"
        )

class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ['utente', 'importo', 'data', 'descrizione']
        widgets = {
            'utente': forms.Select(attrs={'class': 'form-control'}),
            'importo': forms.NumberInput(attrs={'class': 'form-control'}),
            'data': DateInput(attrs={'class': 'form-control'}),
            'descrizione': forms.TextInput(attrs={'class': 'form-control'}),
        }

class QuotaUtenteForm(forms.ModelForm):
    class Meta:
        model = QuotaUtente
        fields = ['utente', 'percentuale']
        
    def clean_percentuale(self):
        percentuale = self.cleaned_data.get('percentuale')
        if percentuale <= 0 or percentuale > 100:
            raise forms.ValidationError("La percentuale deve essere compresa tra 0 e 100.")
        return percentuale

class TipoTrattamentoForm(forms.ModelForm):
    class Meta:
        model = TipoTrattamento
        fields = ['nome', 'principio_attivo', 'descrizione', 'istruzioni', 'tempo_sospensione']
        widgets = {
            'descrizione': forms.Textarea(attrs={'rows': 3}),
            'istruzioni': forms.Textarea(attrs={'rows': 4}),
        }

class TrattamentoSanitarioForm(forms.ModelForm):
    class Meta:
        model = TrattamentoSanitario
        fields = ['apiario', 'tipo_trattamento', 'data_inizio', 'data_fine', 'stato', 'arnie', 'note']
        widgets = {
            'data_inizio': DateInput(),
            'data_fine': DateInput(),
            'note': forms.Textarea(attrs={'rows': 3}),
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
    
    def clean(self):
        cleaned_data = super().clean()
        data_inizio = cleaned_data.get('data_inizio')
        data_fine = cleaned_data.get('data_fine')
        
        # Verifica che la data di fine sia successiva alla data di inizio
        if data_inizio and data_fine and data_fine < data_inizio:
            self.add_error('data_fine', "La data di fine deve essere successiva alla data di inizio.")
        
        return cleaned_data

# Aggiungi questi form al file forms.py

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