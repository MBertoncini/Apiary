# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Apiario(models.Model):
    nome = models.CharField(max_length=100)
    posizione = models.CharField(max_length=200)
    note = models.TextField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    # Aggiungi questi campi per le coordinate geografiche
    latitudine = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True, 
                                     help_text="Latitudine in gradi decimali (es. 45.123456)")
    longitudine = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True,
                                      help_text="Longitudine in gradi decimali (es. 9.123456)")
    
    def __str__(self):
        return self.nome
    
    def has_coordinates(self):
        """Controlla se l'apiario ha coordinate geografiche valide"""
        return self.latitudine is not None and self.longitudine is not None
    
    class Meta:
        verbose_name = "Apiario"
        verbose_name_plural = "Apiari"

class Arnia(models.Model):
    COLORE_CHOICES = [
        ('bianco', 'Bianco'),
        ('giallo', 'Giallo'),
        ('blu', 'Blu'),
        ('verde', 'Verde'),
        ('rosso', 'Rosso'),
        ('arancione', 'Arancione'),
        ('viola', 'Viola'),
        ('nero', 'Nero'),
        ('altro', 'Altro'),
    ]

    # Mapping dei colori comuni a codici esadecimali
    COLORE_HEX = {
        'bianco': '#FFFFFF',
        'giallo': '#FFC107',
        'blu': '#0d6efd',
        'verde': '#198754',
        'rosso': '#dc3545',
        'arancione': '#fd7e14',
        'viola': '#6f42c1',
        'nero': '#212529',
        'altro': '#6c757d',
    }
    
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='arnie')
    numero = models.IntegerField()
    colore = models.CharField(max_length=20, choices=COLORE_CHOICES, default='bianco')
    colore_hex = models.CharField(max_length=7, default='#FFFFFF', help_text="Codice esadecimale del colore")
    data_installazione = models.DateField()
    note = models.TextField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Arnia {self.numero} ({self.colore}) - {self.apiario.nome}"
    
    def save(self, *args, **kwargs):
        # Se il colore è uno dei colori predefiniti, imposta il colore_hex corrispondente
        if self.colore in self.COLORE_HEX and not self.colore_hex:
            self.colore_hex = self.COLORE_HEX[self.colore]
        # Se il colore è 'altro' ma non è stato specificato un colore_hex, imposta un colore di default
        elif self.colore == 'altro' and not self.colore_hex:
            self.colore_hex = self.COLORE_HEX['altro']
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Arnia"
        verbose_name_plural = "Arnie"
        unique_together = ['apiario', 'numero']  # Evita numeri duplicati nello stesso apiario

class ControlloArnia(models.Model):
    arnia = models.ForeignKey(Arnia, on_delete=models.CASCADE, related_name='controlli')
    data = models.DateField()
    utente = models.ForeignKey(User, on_delete=models.CASCADE)
    telaini_scorte = models.IntegerField()
    telaini_covata = models.IntegerField()
    presenza_regina = models.BooleanField(default=True)
    sciamatura = models.BooleanField(default=False)
    data_sciamatura = models.DateField(blank=True, null=True, help_text="Data in cui si è verificata la sciamatura")
    note_sciamatura = models.TextField(blank=True, null=True, help_text="Dettagli sulla sciamatura")
    problemi_sanitari = models.BooleanField(default=False)
    note_problemi = models.TextField(blank=True, null=True, help_text="Dettagli su eventuali problemi sanitari")
    note = models.TextField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Controllo {self.arnia} - {self.data}"
    
    class Meta:
        verbose_name = "Controllo Arnia"
        verbose_name_plural = "Controlli Arnie"
        ordering = ['-data']

# Modifica al modello Fioritura in core/models.py
class Fioritura(models.Model):
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='fioriture')
    pianta = models.CharField(max_length=100)
    data_inizio = models.DateField()
    data_fine = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    
    # Aggiungi questi campi per le coordinate geografiche
    latitudine = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True,
                                     help_text="Latitudine in gradi decimali (es. 45.123456)")
    longitudine = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True,
                                      help_text="Longitudine in gradi decimali (es. 9.123456)")
    raggio = models.IntegerField(default=500, blank=True, null=True,
                                 help_text="Raggio approssimativo della fioritura in metri")
    
    def __str__(self):
        return f"{self.pianta} - {self.apiario.nome} ({self.data_inizio})"
    
    def has_coordinates(self):
        """Controlla se la fioritura ha coordinate geografiche valide"""
        return self.latitudine is not None and self.longitudine is not None
    
    def is_active(self, date=None):
        """Verifica se la fioritura è attiva in una data specifica"""
        if date is None:
            date = timezone.now().date()
        
        if self.data_inizio <= date:
            if self.data_fine is None or self.data_fine >= date:
                return True
        return False
    
    class Meta:
        verbose_name = "Fioritura"
        verbose_name_plural = "Fioriture"
        ordering = ['-data_inizio']

class Pagamento(models.Model):
    utente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pagamenti')
    importo = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField()
    descrizione = models.CharField(max_length=200)
    
    def __str__(self):
        return f"Pagamento {self.utente.username} - {self.importo}€ ({self.data})"
    
    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamenti"
        ordering = ['-data']

class QuotaUtente(models.Model):
    utente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quote')
    percentuale = models.DecimalField(max_digits=5, decimal_places=2)  # Percentuale di partecipazione
    
    def __str__(self):
        return f"Quota {self.utente.username} - {self.percentuale}%"
    
    class Meta:
        verbose_name = "Quota Utente"
        verbose_name_plural = "Quote Utenti"


# Aggiungi questo modello in core/models.py

class TipoTrattamento(models.Model):
    """Modello per gestire i diversi tipi di trattamenti sanitari disponibili"""
    nome = models.CharField(max_length=100)
    principio_attivo = models.CharField(max_length=100)
    descrizione = models.TextField(blank=True, null=True)
    istruzioni = models.TextField(blank=True, null=True, help_text="Istruzioni dettagliate per l'applicazione del trattamento")
    tempo_sospensione = models.IntegerField(default=0, help_text="Giorni di sospensione prima della raccolta del miele")
    
    def __str__(self):
        return self.nome
    
    class Meta:
        verbose_name = "Tipo Trattamento"
        verbose_name_plural = "Tipi Trattamento"
        ordering = ['nome']

class TrattamentoSanitario(models.Model):
    """Modello per gestire i trattamenti sanitari effettuati sulle arnie"""
    STATO_CHOICES = [
        ('programmato', 'Programmato'),
        ('in_corso', 'In Corso'),
        ('completato', 'Completato'),
        ('annullato', 'Annullato'),
    ]
    
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='trattamenti')
    tipo_trattamento = models.ForeignKey(TipoTrattamento, on_delete=models.CASCADE)
    data_inizio = models.DateField()
    data_fine = models.DateField(blank=True, null=True)
    data_fine_sospensione = models.DateField(blank=True, null=True, help_text="Data dopo la quale si può raccogliere il miele")
    stato = models.CharField(max_length=20, choices=STATO_CHOICES, default='programmato')
    utente = models.ForeignKey(User, on_delete=models.CASCADE)
    arnie = models.ManyToManyField(Arnia, related_name='trattamenti', blank=True, help_text="Lasciare vuoto se il trattamento è per tutto l'apiario")
    note = models.TextField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.tipo_trattamento} - {self.apiario} ({self.data_inizio})"
    
    def save(self, *args, **kwargs):
        # Calcola automaticamente la data di fine sospensione
        if self.data_fine and self.tipo_trattamento.tempo_sospensione > 0:
            self.data_fine_sospensione = self.data_fine + timedelta(days=self.tipo_trattamento.tempo_sospensione)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Trattamento Sanitario"
        verbose_name_plural = "Trattamenti Sanitari"
        ordering = ['-data_inizio']