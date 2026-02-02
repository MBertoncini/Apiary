from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Apiario, Arnia, ControlloArnia, Regina, Fioritura,
    TrattamentoSanitario, TipoTrattamento, Melario, Smielatura,
    Gruppo, MembroGruppo, InvitoGruppo, Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura
)

# Serializzatore utente
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

# Serializzatore Apiario
class ApiarioSerializer(serializers.ModelSerializer):
    proprietario_username = serializers.ReadOnlyField(source='proprietario.username')
    
    class Meta:
        model = Apiario
        fields = [
            'id', 'nome', 'posizione', 'latitudine', 'longitudine', 
            'note', 'monitoraggio_meteo', 'proprietario', 'proprietario_username',
            'gruppo', 'condiviso_con_gruppo', 'visibilita_mappa'
        ]
        read_only_fields = ['proprietario']
    
    def create(self, validated_data):
        # Imposta automaticamente l'utente corrente come proprietario
        validated_data['proprietario'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Arnia
class ArniaSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    
    class Meta:
        model = Arnia
        fields = [
            'id', 'apiario', 'apiario_nome', 'numero', 'colore', 
            'colore_hex', 'data_installazione', 'note', 'attiva'
        ]

# Serializzatore Controllo Arnia (versione dettagliata)
class ControlloArniaDetailSerializer(serializers.ModelSerializer):
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    apiario_nome = serializers.ReadOnlyField(source='arnia.apiario.nome')
    apiario_id = serializers.ReadOnlyField(source='arnia.apiario.id')
    utente_username = serializers.ReadOnlyField(source='utente.username')
    
    class Meta:
        model = ControlloArnia
        fields = [
            'id', 'arnia', 'arnia_numero', 'apiario_nome', 'apiario_id',
            'data', 'utente', 'utente_username', 'telaini_scorte', 
            'telaini_covata', 'presenza_regina', 'sciamatura',
            'data_sciamatura', 'note_sciamatura', 'problemi_sanitari',
            'note_problemi', 'note', 'data_creazione',
            'regina_vista', 'uova_fresche', 'celle_reali',
            'numero_celle_reali', 'regina_sostituita'
        ]
        read_only_fields = ['utente']
    
    def create(self, validated_data):
        # Imposta automaticamente l'utente corrente
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Controllo Arnia (versione lista)
class ControlloArniaListSerializer(serializers.ModelSerializer):
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    apiario_nome = serializers.ReadOnlyField(source='arnia.apiario.nome')
    
    class Meta:
        model = ControlloArnia
        fields = [
            'id', 'arnia', 'arnia_numero', 'apiario_nome',
            'data', 'telaini_scorte', 'telaini_covata', 
            'presenza_regina', 'problemi_sanitari'
        ]

# Serializzatore Regina
class ReginaSerializer(serializers.ModelSerializer):
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    apiario_nome = serializers.ReadOnlyField(source='arnia.apiario.nome')
    apiario_id = serializers.ReadOnlyField(source='arnia.apiario.id')
    
    class Meta:
        model = Regina
        fields = [
            'id', 'arnia', 'arnia_numero', 'apiario_nome', 'apiario_id',
            'data_nascita', 'data_introduzione', 'origine', 'razza',
            'regina_madre', 'marcata', 'codice_marcatura', 'colore_marcatura',
            'fecondata', 'selezionata', 'docilita', 'produttivita',
            'resistenza_malattie', 'tendenza_sciamatura', 'note'
        ]

# Serializzatore Fioritura
class FiorituraSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome') if 'apiario' else None
    creatore_username = serializers.ReadOnlyField(source='creatore.username')
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = Fioritura
        fields = [
            'id', 'apiario', 'apiario_nome', 'pianta', 'data_inizio', 
            'data_fine', 'latitudine', 'longitudine', 'raggio', 
            'note', 'creatore', 'creatore_username', 'is_active'
        ]
        read_only_fields = ['creatore']
    
    def get_is_active(self, obj):
        return obj.is_active()
    
    def create(self, validated_data):
        validated_data['creatore'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore TipoTrattamento
class TipoTrattamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoTrattamento
        fields = [
            'id', 'nome', 'principio_attivo', 'descrizione', 'istruzioni',
            'tempo_sospensione', 'richiede_blocco_covata', 
            'giorni_blocco_covata', 'nota_blocco_covata'
        ]

# Serializzatore TrattamentoSanitario
class TrattamentoSanitarioSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    tipo_trattamento_nome = serializers.ReadOnlyField(source='tipo_trattamento.nome')
    utente_username = serializers.ReadOnlyField(source='utente.username')
    
    class Meta:
        model = TrattamentoSanitario
        fields = [
            'id', 'apiario', 'apiario_nome', 'tipo_trattamento', 
            'tipo_trattamento_nome', 'data_inizio', 'data_fine', 
            'data_fine_sospensione', 'stato', 'utente', 'utente_username',
            'arnie', 'note', 'blocco_covata_attivo', 'data_inizio_blocco',
            'data_fine_blocco', 'metodo_blocco', 'note_blocco'
        ]
        read_only_fields = ['utente', 'data_fine_sospensione']
    
    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Melario
class MelarioSerializer(serializers.ModelSerializer):
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    apiario_id = serializers.ReadOnlyField(source='arnia.apiario.id')
    apiario_nome = serializers.ReadOnlyField(source='arnia.apiario.nome')
    
    class Meta:
        model = Melario
        fields = [
            'id', 'arnia', 'arnia_numero', 'apiario_id', 'apiario_nome',
            'numero_telaini', 'posizione', 'data_posizionamento', 
            'data_rimozione', 'stato', 'note'
        ]

# Serializzatore Smielatura
class SmielaturaSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    utente_username = serializers.ReadOnlyField(source='utente.username')
    melari_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Smielatura
        fields = [
            'id', 'data', 'apiario', 'apiario_nome', 'melari', 
            'melari_count', 'quantita_miele', 'tipo_miele', 
            'utente', 'utente_username', 'note', 'data_registrazione'
        ]
        read_only_fields = ['utente']
    
    def get_melari_count(self, obj):
        return obj.melari.count()
    
    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Gruppo
class GruppoSerializer(serializers.ModelSerializer):
    creatore_username = serializers.ReadOnlyField(source='creatore.username')
    membri_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Gruppo
        fields = [
            'id', 'nome', 'descrizione', 'data_creazione', 
            'creatore', 'creatore_username', 'membri_count'
        ]
        read_only_fields = ['creatore']
    
    def get_membri_count(self, obj):
        return obj.membri.count()
    
    def create(self, validated_data):
        validated_data['creatore'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore MembroGruppo
class MembroGruppoSerializer(serializers.ModelSerializer):
    utente_username = serializers.ReadOnlyField(source='utente.username')
    gruppo_nome = serializers.ReadOnlyField(source='gruppo.nome')
    
    class Meta:
        model = MembroGruppo
        fields = [
            'id', 'utente', 'utente_username', 'gruppo', 
            'gruppo_nome', 'ruolo', 'data_aggiunta'
        ]

# Serializzatore InvitoGruppo
class InvitoGruppoSerializer(serializers.ModelSerializer):
    gruppo_nome = serializers.ReadOnlyField(source='gruppo.nome')
    invitato_da_username = serializers.ReadOnlyField(source='invitato_da.username')
    
    class Meta:
        model = InvitoGruppo
        fields = [
            'id', 'gruppo', 'gruppo_nome', 'email', 'ruolo_proposto',
            'data_invio', 'data_scadenza', 'stato', 
            'invitato_da', 'invitato_da_username'
        ]
        read_only_fields = ['invitato_da', 'data_invio', 'data_scadenza']
    
    def create(self, validated_data):
        validated_data['invitato_da'] = self.context['request'].user
        return super().create(validated_data)

class PagamentoSerializer(serializers.ModelSerializer):
    utente_username = serializers.SerializerMethodField()
    gruppo_nome = serializers.SerializerMethodField()
    
    class Meta:
        model = Pagamento
        fields = ['id', 'utente', 'utente_username', 'importo', 'data', 
                 'descrizione', 'gruppo', 'gruppo_nome']
    
    def get_utente_username(self, obj):
        return obj.utente.username if obj.utente else None
    
    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo else None

class QuotaUtenteSerializer(serializers.ModelSerializer):
    utente_username = serializers.SerializerMethodField()
    gruppo_nome = serializers.SerializerMethodField()

    class Meta:
        model = QuotaUtente
        fields = ['id', 'utente', 'utente_username', 'percentuale', 'gruppo', 'gruppo_nome']

    def get_utente_username(self, obj):
        return obj.utente.username if obj.utente else None

    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo else None


# Serializzatore Attrezzatura
class AttrezzaturaSerializer(serializers.ModelSerializer):
    proprietario_username = serializers.ReadOnlyField(source='proprietario.username')
    categoria_nome = serializers.SerializerMethodField()
    gruppo_nome = serializers.SerializerMethodField()
    apiario_nome = serializers.SerializerMethodField()

    class Meta:
        model = Attrezzatura
        fields = [
            'id', 'nome', 'categoria', 'categoria_nome', 'descrizione',
            'marca', 'modello', 'numero_serie',
            'proprietario', 'proprietario_username',
            'gruppo', 'gruppo_nome', 'condiviso_con_gruppo',
            'stato', 'condizione',
            'apiario', 'apiario_nome', 'posizione',
            'prezzo_acquisto', 'data_acquisto', 'fornitore',
            'garanzia_fino_a', 'vita_utile_anni',
            'quantita', 'unita_misura',
            'note', 'immagine',
            'data_creazione', 'data_modifica',
        ]
        read_only_fields = ['proprietario', 'data_creazione', 'data_modifica']

    def get_categoria_nome(self, obj):
        return obj.categoria.nome if obj.categoria else None

    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo else None

    def get_apiario_nome(self, obj):
        return obj.apiario.nome if obj.apiario else None

    def create(self, validated_data):
        validated_data['proprietario'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore SpesaAttrezzatura
class SpesaAttrezzaturaSerializer(serializers.ModelSerializer):
    attrezzatura_nome = serializers.SerializerMethodField()
    gruppo_nome = serializers.SerializerMethodField()
    utente_username = serializers.ReadOnlyField(source='utente.username')
    tipo_display = serializers.SerializerMethodField()

    class Meta:
        model = SpesaAttrezzatura
        fields = [
            'id', 'attrezzatura', 'attrezzatura_nome',
            'gruppo', 'gruppo_nome',
            'tipo', 'tipo_display', 'descrizione', 'importo', 'data',
            'fornitore', 'numero_fattura',
            'utente', 'utente_username',
            'note', 'data_creazione',
        ]
        read_only_fields = ['utente', 'data_creazione']

    def get_attrezzatura_nome(self, obj):
        return obj.attrezzatura.nome if obj.attrezzatura else None

    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo else None

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore ManutenzioneAttrezzatura
class ManutenzioneAttrezzaturaSerializer(serializers.ModelSerializer):
    attrezzatura_nome = serializers.SerializerMethodField()
    utente_username = serializers.ReadOnlyField(source='utente.username')
    tipo_display = serializers.SerializerMethodField()
    stato_display = serializers.SerializerMethodField()

    class Meta:
        model = ManutenzioneAttrezzatura
        fields = [
            'id', 'attrezzatura', 'attrezzatura_nome',
            'tipo', 'tipo_display', 'stato', 'stato_display',
            'data_programmata', 'data_esecuzione',
            'descrizione', 'costo', 'eseguito_da',
            'prossima_manutenzione',
            'note', 'utente', 'utente_username',
            'data_creazione',
        ]
        read_only_fields = ['utente', 'data_creazione']

    def get_attrezzatura_nome(self, obj):
        return obj.attrezzatura.nome if obj.attrezzatura else None

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()

    def get_stato_display(self, obj):
        return obj.get_stato_display()

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)