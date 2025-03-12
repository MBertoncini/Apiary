
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid

class Gruppo(models.Model):
    """Modello per gestire gruppi di apicoltori collaborativi"""
    nome = models.CharField(max_length=100)
    descrizione = models.TextField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    creatore = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gruppi_creati')
    membri = models.ManyToManyField(User, through='MembroGruppo', related_name='gruppi')
    
    def __str__(self):
        return self.nome
    
    class Meta:
        verbose_name = "Gruppo"
        verbose_name_plural = "Gruppi"

class MembroGruppo(models.Model):
    """Modello per la relazione tra utenti e gruppi con ruoli"""
    RUOLO_CHOICES = [
        ('admin', 'Amministratore'),
        ('editor', 'Editor'),
        ('viewer', 'Visualizzatore'),
    ]
    
    utente = models.ForeignKey(User, on_delete=models.CASCADE)
    gruppo = models.ForeignKey(Gruppo, on_delete=models.CASCADE)
    ruolo = models.CharField(max_length=20, choices=RUOLO_CHOICES, default='viewer')
    data_aggiunta = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.utente.username} - {self.gruppo.nome} ({self.get_ruolo_display()})"
    
    class Meta:
        verbose_name = "Membro Gruppo"
        verbose_name_plural = "Membri Gruppo"
        unique_together = ['utente', 'gruppo']

class InvitoGruppo(models.Model):
    """Modello per gestire gli inviti ai gruppi"""
    STATO_CHOICES = [
        ('inviato', 'Inviato'),
        ('accettato', 'Accettato'),
        ('rifiutato', 'Rifiutato'),
        ('scaduto', 'Scaduto'),
    ]
    
    gruppo = models.ForeignKey(Gruppo, on_delete=models.CASCADE, related_name='inviti')
    email = models.EmailField()
    ruolo_proposto = models.CharField(max_length=20, choices=MembroGruppo.RUOLO_CHOICES, default='viewer')
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    data_invio = models.DateTimeField(auto_now_add=True)
    data_scadenza = models.DateTimeField()
    stato = models.CharField(max_length=20, choices=STATO_CHOICES, default='inviato')
    invitato_da = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inviti_inviati')
    
    def __str__(self):
        return f"Invito a {self.email} per {self.gruppo.nome}"
    
    def save(self, *args, **kwargs):
        # Imposta la data di scadenza predefinita a 7 giorni dal momento dell'invio
        if not self.data_scadenza:
            self.data_scadenza = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)
    
    def is_valid(self):
        """Verifica se l'invito è ancora valido"""
        now = timezone.now()
        return self.stato == 'inviato' and now <= self.data_scadenza
    
    class Meta:
        verbose_name = "Invito Gruppo"
        verbose_name_plural = "Inviti Gruppo"

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
    
    # Aggiungi questi campi
    proprietario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='apiari_posseduti')
    gruppo = models.ForeignKey(Gruppo, on_delete=models.SET_NULL, null=True, blank=True, related_name='apiari')
    condiviso_con_gruppo = models.BooleanField(default=False, help_text="Se abilitato, l'apiario è condiviso con tutti i membri del gruppo")    

    monitoraggio_meteo = models.BooleanField(default=True, help_text="Abilita il monitoraggio meteorologico per questo apiario")

    # Aggiungere questa tupla alla classe Apiario
    VISIBILITA_CHOICES = [
        ('privato', 'Solo proprietario'),
        ('gruppo', 'Membri del gruppo'),
        ('pubblico', 'Tutti gli utenti'),
    ]

    # Aggiungere questo campo alla classe Apiario
    visibilita_mappa = models.CharField(
        max_length=20, 
        choices=VISIBILITA_CHOICES, 
        default='privato',
        help_text="Chi può visualizzare questo apiario sulla mappa"
    )

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
    # Nuovi campi relativi alla regina
    regina_vista = models.BooleanField(default=False, help_text="La regina è stata vista durante il controllo")
    uova_fresche = models.BooleanField(default=False, help_text="Sono state viste uova fresche (indica presenza regina)")
    celle_reali = models.BooleanField(default=False, help_text="Sono presenti celle reali")
    numero_celle_reali = models.PositiveSmallIntegerField(default=0, help_text="Numero di celle reali trovate")
    regina_sostituita = models.BooleanField(default=False, help_text="La regina è stata sostituita durante questo controllo")
    
    def __str__(self):
        return f"Controllo {self.arnia} - {self.data}"
    
    class Meta:
        verbose_name = "Controllo Arnia"
        verbose_name_plural = "Controlli Arnie"
        ordering = ['-data']

class Regina(models.Model):
    """Modello per gestire le informazioni sulla regina dell'arnia"""
    ORIGINE_CHOICES = [
        ('acquistata', 'Acquistata'),
        ('allevata', 'Allevata'),
        ('sciamatura', 'Sciamatura Naturale'),
        ('emergenza', 'Celle di Emergenza'),
        ('sconosciuta', 'Sconosciuta'),
    ]
    
    # Schema internazionale colori per marcatura regine
    # Il colore dipende dall'anno di nascita della regina
    COLORE_MARCATURA_CHOICES = [
        ('bianco', 'Bianco (anni terminanti in 1,6)'),
        ('giallo', 'Giallo (anni terminanti in 2,7)'),
        ('rosso', 'Rosso (anni terminanti in 3,8)'),
        ('verde', 'Verde (anni terminanti in 4,9)'),
        ('blu', 'Blu (anni terminanti in 5,0)'),
        ('non_marcata', 'Non Marcata'),
    ]
    
    RAZZA_CHOICES = [
        ('ligustica', 'Apis mellifera ligustica (Italiana)'),
        ('carnica', 'Apis mellifera carnica (Carnica)'),
        ('buckfast', 'Buckfast'),
        ('caucasica', 'Apis mellifera caucasica'),
        ('sicula', 'Apis mellifera sicula (Siciliana)'),
        ('ibrida', 'Ibrida'),
        ('altro', 'Altro'),
    ]
    
    arnia = models.OneToOneField(Arnia, on_delete=models.CASCADE, related_name='regina')
    data_nascita = models.DateField(null=True, blank=True)
    data_introduzione = models.DateField(help_text="Data in cui la regina è stata introdotta nell'arnia")
    origine = models.CharField(max_length=20, choices=ORIGINE_CHOICES, default='sconosciuta')
    razza = models.CharField(max_length=20, choices=RAZZA_CHOICES, default='ligustica')
    regina_madre = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='figlie',
                                   help_text="Regina da cui proviene (se conosciuta)")
    codice_marcatura = models.CharField(max_length=50, blank=True, null=True, 
                                      help_text="Codice o numero di marcatura")
    colore_marcatura = models.CharField(max_length=20, choices=COLORE_MARCATURA_CHOICES, 
                                      default='non_marcata')
    marcata = models.BooleanField(default=False)
    fecondata = models.BooleanField(default=True, help_text="Indica se la regina è stata fecondata")
    selezionata = models.BooleanField(default=False, help_text="Regina selezionata per caratteristiche genetiche")
    note = models.TextField(blank=True, null=True)
    
    # Storico delle performance
    docilita = models.PositiveSmallIntegerField(null=True, blank=True, 
                                           help_text="Valutazione docilità (1-5)")
    produttivita = models.PositiveSmallIntegerField(null=True, blank=True,
                                               help_text="Valutazione produttività (1-5)")
    resistenza_malattie = models.PositiveSmallIntegerField(null=True, blank=True,
                                                      help_text="Resistenza alle malattie (1-5)")
    tendenza_sciamatura = models.PositiveSmallIntegerField(null=True, blank=True,
                                                      help_text="Tendenza alla sciamatura (1-5)")
    
    def __str__(self):
        return f"Regina dell'arnia {self.arnia.numero} - {self.get_razza_display()}"
    
    def get_eta_giorni(self):
        """Calcola l'età della regina in giorni"""
        if not self.data_nascita:
            return None
        
        oggi = timezone.now().date()
        delta = oggi - self.data_nascita
        return delta.days
    
    def get_eta_anni(self):
        """Calcola l'età della regina in anni"""
        giorni = self.get_eta_giorni()
        if giorni is None:
            return None
        
        return round(giorni / 365, 1)
    
    def genera_colore_marcatura_automatico(self):
        """Imposta il colore di marcatura in base all'anno di nascita della regina"""
        if not self.data_nascita:
            return
        
        anno = self.data_nascita.year
        # Ultima cifra dell'anno
        ultimo_digit = anno % 10
        
        if ultimo_digit in [1, 6]:
            self.colore_marcatura = 'bianco'
        elif ultimo_digit in [2, 7]:
            self.colore_marcatura = 'giallo'
        elif ultimo_digit in [3, 8]:
            self.colore_marcatura = 'rosso'
        elif ultimo_digit in [4, 9]:
            self.colore_marcatura = 'verde'
        elif ultimo_digit in [5, 0]:
            self.colore_marcatura = 'blu'
            
    def save(self, *args, **kwargs):
        # Se la regina è marcata ma non ha un colore specifico, imposta il colore automaticamente
        if self.marcata and self.colore_marcatura == 'non_marcata' and self.data_nascita:
            self.genera_colore_marcatura_automatico()
            
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = "Regina"
        verbose_name_plural = "Regine"
        ordering = ['-data_introduzione']

class StoriaRegine(models.Model):
    """Modello per tracciare la storia delle regine in un'arnia"""
    arnia = models.ForeignKey(Arnia, on_delete=models.CASCADE, related_name='storia_regine')
    regina = models.ForeignKey(Regina, on_delete=models.CASCADE, related_name='storia')
    data_inizio = models.DateField()
    data_fine = models.DateField(null=True, blank=True)
    motivo_fine = models.CharField(max_length=100, blank=True, null=True, 
                                 help_text="Motivo della rimozione/morte della regina")
    note = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Regina in arnia {self.arnia.numero} dal {self.data_inizio}"
    
    class Meta:
        verbose_name = "Storia Regina"
        verbose_name_plural = "Storia Regine"
        ordering = ['-data_inizio']

class Melario(models.Model):
    """Modello per gestire i melari posizionati sulle arnie"""
    STATO_CHOICES = [
        ('posizionato', 'Posizionato'),
        ('rimosso', 'Rimosso'),
        ('in_smielatura', 'In Smielatura'),
        ('smielato', 'Smielato')
    ]
    
    arnia = models.ForeignKey(Arnia, on_delete=models.CASCADE, related_name='melari')
    numero_telaini = models.IntegerField(default=10, help_text="Numero di telaini nel melario")
    posizione = models.IntegerField(help_text="Posizione del melario (1 = più vicino al nido, ecc.)")
    data_posizionamento = models.DateField()
    data_rimozione = models.DateField(null=True, blank=True)
    stato = models.CharField(max_length=20, choices=STATO_CHOICES, default='posizionato')
    note = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"Melario {self.id} - Arnia {self.arnia.numero} (Pos. {self.posizione})"
    
    class Meta:
        verbose_name = "Melario"
        verbose_name_plural = "Melari"
        ordering = ['arnia', 'posizione']

class Smielatura(models.Model):
    """Modello per gestire le operazioni di smielatura"""
    data = models.DateField()
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='smielature')
    melari = models.ManyToManyField(Melario, related_name='smielature')
    quantita_miele = models.DecimalField(max_digits=7, decimal_places=2, help_text="Quantità di miele in kg")
    tipo_miele = models.CharField(max_length=100, help_text="Tipo di miele/origine botanica principale")
    utente = models.ForeignKey(User, on_delete=models.CASCADE)
    note = models.TextField(blank=True, null=True)
    data_registrazione = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Smielatura {self.data} - {self.apiario.nome} ({self.quantita_miele}kg)"
    
    class Meta:
        verbose_name = "Smielatura"
        verbose_name_plural = "Smielature"
        ordering = ['-data']
        
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Quando si salva una smielatura, aggiorna lo stato dei melari
        for melario in self.melari.all():
            melario.stato = 'smielato'
            melario.save()

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Fioritura(models.Model):
    # Campo apiario opzionale
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='fioriture', null=True, blank=True)
    pianta = models.CharField(max_length=100)
    data_inizio = models.DateField()
    data_fine = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True, null=True)
    
    # Coordinate geografiche obbligatorie
    latitudine = models.DecimalField(max_digits=9, decimal_places=6,
                                   help_text="Latitudine in gradi decimali (es. 45.123456)")
    longitudine = models.DecimalField(max_digits=9, decimal_places=6,
                                    help_text="Longitudine in gradi decimali (es. 9.123456)")
    raggio = models.IntegerField(default=500, blank=True, null=True,
                               help_text="Raggio approssimativo della fioritura in metri")
    
    # Aggiunta del campo creatore per il sistema di permessi
    creatore = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='fioriture_create')
    data_creazione = models.DateTimeField(auto_now_add=True, null=True)
    data_modifica = models.DateTimeField(auto_now=True, null=True)
    
    def __str__(self):
        apiario_nome = self.apiario.nome if self.apiario else "Non associato"
        return f"{self.pianta} - {apiario_nome} ({self.data_inizio})"
    
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
    # Aggiungi questo campo
    gruppo = models.ForeignKey(Gruppo, on_delete=models.SET_NULL, null=True, blank=True, related_name='pagamenti')
    
    def __str__(self):
        return f"Pagamento {self.utente.username} - {self.importo}€ ({self.data})"
    
    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamenti"
        ordering = ['-data']

class QuotaUtente(models.Model):
    utente = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quote')
    percentuale = models.DecimalField(max_digits=5, decimal_places=2)  # Percentuale di partecipazione
    # Aggiungi questo campo
    gruppo = models.ForeignKey(Gruppo, on_delete=models.SET_NULL, null=True, blank=True, related_name='quote')
    
    def __str__(self):
        return f"Quota {self.utente.username} - {self.percentuale}%"
    
    class Meta:
        verbose_name = "Quota Utente"
        verbose_name_plural = "Quote Utenti"


class TipoTrattamento(models.Model):
    """Modello per gestire i diversi tipi di trattamenti sanitari disponibili"""
    nome = models.CharField(max_length=100)
    principio_attivo = models.CharField(max_length=100)
    descrizione = models.TextField(blank=True, null=True)
    istruzioni = models.TextField(blank=True, null=True, help_text="Istruzioni dettagliate per l'applicazione del trattamento")
    tempo_sospensione = models.IntegerField(default=0, help_text="Giorni di sospensione prima della raccolta del miele")
    
    # Nuovi campi per il blocco di covata
    richiede_blocco_covata = models.BooleanField(default=False, 
                                               help_text="Indica se questo trattamento richiede un blocco di covata")
    giorni_blocco_covata = models.IntegerField(default=0, 
                                             help_text="Durata consigliata in giorni del blocco di covata")
    nota_blocco_covata = models.TextField(blank=True, null=True, 
                                        help_text="Note specifiche sul blocco di covata (ad es. metodo, tempistiche)")
    
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
    
    # Nuovi campi per il blocco di covata
    blocco_covata_attivo = models.BooleanField(default=False, 
                                             help_text="Indica se il blocco di covata è attualmente attivo")
    data_inizio_blocco = models.DateField(blank=True, null=True, 
                                        help_text="Data di inizio del blocco di covata")
    data_fine_blocco = models.DateField(blank=True, null=True, 
                                      help_text="Data prevista per la fine del blocco di covata")
    metodo_blocco = models.CharField(max_length=100, blank=True, null=True, 
                                   help_text="Metodo utilizzato per il blocco (es. ingabbiamento, rimozione regina)")
    note_blocco = models.TextField(blank=True, null=True, 
                                 help_text="Note sul blocco di covata")
    
    def __str__(self):
        return f"{self.tipo_trattamento} - {self.apiario} ({self.data_inizio})"
    
    def save(self, *args, **kwargs):
        # Calcola automaticamente la data di fine sospensione
        if self.data_fine and self.tipo_trattamento.tempo_sospensione > 0:
            self.data_fine_sospensione = self.data_fine + timedelta(days=self.tipo_trattamento.tempo_sospensione)
            
        # Calcola automaticamente la data di fine blocco covata se non specificata
        if self.blocco_covata_attivo and self.data_inizio_blocco and not self.data_fine_blocco and self.tipo_trattamento.giorni_blocco_covata > 0:
            self.data_fine_blocco = self.data_inizio_blocco + timedelta(days=self.tipo_trattamento.giorni_blocco_covata)
            
        super().save(*args, **kwargs)
    
    # Aggiunti nuovi metodi utili per la gestione dei trattamenti
    
    def is_active(self, date=None):
        """Verifica se il trattamento è attivo in una data specifica"""
        if date is None:
            date = timezone.now().date()
        
        if self.stato in ['programmato', 'in_corso']:
            if self.data_inizio <= date:
                if self.data_fine is None or self.data_fine >= date:
                    return True
        return False
    
    def applies_to_arnia(self, arnia):
        """Verifica se il trattamento si applica a una specifica arnia"""
        # Se non ci sono arnie specifiche selezionate, si applica a tutte le arnie dell'apiario
        if not self.arnie.exists():
            return arnia.apiario == self.apiario
        # Altrimenti, verifica se l'arnia è tra quelle selezionate
        return self.arnie.filter(pk=arnia.pk).exists()
    
    def get_duration_days(self):
        """Restituisce la durata del trattamento in giorni"""
        if not self.data_fine:
            return None
        
        return (self.data_fine - self.data_inizio).days
    
    def get_remaining_suspension_days(self):
        """Restituisce i giorni rimanenti di sospensione"""
        if not self.data_fine_sospensione:
            return 0
            
        if self.data_fine_sospensione < timezone.now().date():
            return 0
            
        return (self.data_fine_sospensione - timezone.now().date()).days

    def is_blocco_covata_attivo(self, date=None):
        """Verifica se il blocco di covata è attivo in una data specifica"""
        if not self.blocco_covata_attivo or not self.data_inizio_blocco:
            return False
            
        if date is None:
            date = timezone.now().date()
            
        if self.data_inizio_blocco <= date:
            if self.data_fine_blocco is None or self.data_fine_blocco >= date:
                return True
        return False

    class Meta:
        verbose_name = "Trattamento Sanitario"
        verbose_name_plural = "Trattamenti Sanitari"
        ordering = ['-data_inizio']

# Aggiungi questo al file models.py

from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.db.models.signals import post_save
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys
import os

class Profilo(models.Model):
    """Modello per il profilo utente esteso"""
    utente = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profilo')
    immagine = models.ImageField(upload_to='profili/', default='profili/default.png')
    data_nascita = models.DateField(null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    
    def __str__(self):
        return f"Profilo di {self.utente.username}"
    
    def save(self, *args, **kwargs):
        # Compressione dell'immagine se è stata caricata una nuova immagine
        if self.immagine and hasattr(self.immagine, 'name') and not self.immagine.name.endswith('default.png'):
            img = Image.open(self.immagine)
            
            # Converti in RGB se l'immagine è in RGBA (per PNG trasparenti)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
                
            # Ridimensiona l'immagine per mantenerla ragionevolmente piccola
            output_size = (300, 300)
            img.thumbnail(output_size)
            
            # Salva l'immagine compressa
            output = BytesIO()
            img.save(output, format='JPEG', quality=75)
            output.seek(0)
            
            # Sostituisci l'immagine originale con quella compressa
            self.immagine = InMemoryUploadedFile(
                output, 'ImageField', 
                f"{os.path.splitext(self.immagine.name)[0]}.jpg", 
                'image/jpeg', 
                sys.getsizeof(output), 
                None
            )
        
        super().save(*args, **kwargs)

# Crea automaticamente un profilo per ogni nuovo utente
@receiver(post_save, sender=User)
def crea_profilo(sender, instance, created, **kwargs):
    if created:
        Profilo.objects.create(utente=instance)

# Salva il profilo quando l'utente viene salvato
@receiver(post_save, sender=User)
def salva_profilo(sender, instance, **kwargs):
    instance.profilo.save()

# Aggiungiamo questa estensione al modello Gruppo esistente
class ImmagineProfilo(models.Model):
    """Estensione del modello Gruppo per aggiungere l'immagine del profilo"""
    gruppo = models.OneToOneField('Gruppo', on_delete=models.CASCADE, related_name='immagine_profilo')
    immagine = models.ImageField(upload_to='gruppi/', default='gruppi/default.png')
    
    def __str__(self):
        return f"Immagine del gruppo {self.gruppo.nome}"
    
    def save(self, *args, **kwargs):
        # Compressione dell'immagine
        if self.immagine and hasattr(self.immagine, 'name') and not self.immagine.name.endswith('default.png'):
            img = Image.open(self.immagine)
            
            # Converti in RGB se l'immagine è in RGBA
            if img.mode == 'RGBA':
                img = img.convert('RGB')
                
            # Ridimensiona l'immagine
            output_size = (400, 400)
            img.thumbnail(output_size)
            
            # Salva l'immagine compressa
            output = BytesIO()
            img.save(output, format='JPEG', quality=75)
            output.seek(0)
            
            self.immagine = InMemoryUploadedFile(
                output, 'ImageField', 
                f"{os.path.splitext(self.immagine.name)[0]}.jpg", 
                'image/jpeg', 
                sys.getsizeof(output), 
                None
            )
        
        super().save(*args, **kwargs)

# Crea automaticamente un'immagine di profilo per ogni nuovo gruppo
@receiver(post_save, sender=Gruppo)
def crea_immagine_gruppo(sender, instance, created, **kwargs):
    if created:
        ImmagineProfilo.objects.create(gruppo=instance)


class DatiMeteo(models.Model):
    """Modello per memorizzare i dati meteorologici relativi agli apiari"""
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='dati_meteo')
    data = models.DateTimeField()
    temperatura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    umidita = models.IntegerField(null=True, blank=True)
    pressione = models.IntegerField(null=True, blank=True)
    velocita_vento = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    direzione_vento = models.IntegerField(null=True, blank=True)
    descrizione = models.CharField(max_length=100, null=True, blank=True)
    icona = models.CharField(max_length=20, null=True, blank=True)
    pioggia = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    class Meta:
        verbose_name = "Dato Meteo"
        verbose_name_plural = "Dati Meteo"
        ordering = ['-data']
        
    def __str__(self):
        return f"Meteo {self.apiario.nome} - {self.data.strftime('%d/%m/%Y %H:%M')}"

class PrevisioneMeteo(models.Model):
    """Modello per memorizzare le previsioni meteorologiche future"""
    apiario = models.ForeignKey(Apiario, on_delete=models.CASCADE, related_name='previsioni_meteo')
    data_previsione = models.DateTimeField()  # Data e ora della previsione
    data_riferimento = models.DateTimeField()  # Data e ora a cui si riferisce la previsione
    temperatura_min = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperatura_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperatura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    umidita = models.IntegerField(null=True, blank=True)
    pressione = models.IntegerField(null=True, blank=True)
    velocita_vento = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    direzione_vento = models.IntegerField(null=True, blank=True)
    probabilita_pioggia = models.IntegerField(null=True, blank=True)
    descrizione = models.CharField(max_length=100, null=True, blank=True)
    icona = models.CharField(max_length=20, null=True, blank=True)
    
    class Meta:
        verbose_name = "Previsione Meteo"
        verbose_name_plural = "Previsioni Meteo"
        ordering = ['data_riferimento']
        
    def __str__(self):
        return f"Previsione {self.apiario.nome} - {self.data_riferimento.strftime('%d/%m/%Y %H:%M')}"