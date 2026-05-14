import hashlib
import hmac
import math

from rest_framework import serializers
from django.conf import settings
from django.contrib.auth.models import User
from .models import (
    Apiario, Arnia, Colonia, Nucleo, ControlloNucleo, ControlloArnia,
    Regina, StoriaRegine, Fioritura, FiorituraConferma,
    TrattamentoSanitario, TipoTrattamento, Melario, Smielatura,
    Gruppo, MembroGruppo, InvitoGruppo, Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura,
    Invasettamento, Cliente, Vendita, DettaglioVendita,
    AnalisiTelaino, ApiarioMapLayout, MeteoGiornaliero,
    PreferenzaMaturazione, Maturatore, ContenitoreStoccaggio,
    GIORNI_MATURAZIONE_DEFAULTS,
    VarroaCheckpoint,
)

# Serializzatore utente
class UserSerializer(serializers.ModelSerializer):
    gemini_api_key = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    ai_tier = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'gemini_api_key', 'profile_image', 'ai_tier']

    def get_gemini_api_key(self, obj):
        try:
            return obj.profilo.gemini_api_key or ''
        except Exception:
            return ''

    def get_ai_tier(self, obj):
        try:
            return obj.profilo.ai_tier or 'free'
        except Exception:
            return 'free'

    def get_profile_image(self, obj):
        try:
            immagine = obj.profilo.immagine
            if not immagine:
                return None
            request = self.context.get('request')
            url = immagine.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

# Serializzatore Apiario
class ApiarioSerializer(serializers.ModelSerializer):
    proprietario_username = serializers.ReadOnlyField(source='proprietario.username')
    proprietario_immagine_profilo = serializers.SerializerMethodField()

    class Meta:
        model = Apiario
        fields = [
            'id', 'nome', 'posizione', 'latitudine', 'longitudine',
            'note', 'monitoraggio_meteo', 'proprietario', 'proprietario_username',
            'proprietario_immagine_profilo',
            'gruppo', 'condiviso_con_gruppo', 'visibilita_mappa'
        ]
        read_only_fields = ['proprietario']

    def get_proprietario_immagine_profilo(self, obj):
        try:
            immagine = obj.proprietario.profilo.immagine
            if not immagine:
                return None
            request = self.context.get('request')
            url = immagine.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    def create(self, validated_data):
        validated_data['proprietario'] = self.context['request'].user
        return super().create(validated_data)


# Offuscamento server-side della posizione degli apiari "pubblici" mostrati
# sulla mappa community (anti-furto / anti-doxxing).
#
# - Seed = HMAC-SHA256(SECRET_KEY, "apiario-community-fuzz:<id>"). Senza
#   conoscere SECRET_KEY l'offset non è invertibile dall'id pubblico.
# - Offset uniforme nel quadrato [-_FUZZ_MAX_DEG, +_FUZZ_MAX_DEG] su lat/lon.
#   A 45°N ±0.030° ≈ ±3.3 km in latitudine e ±2.4 km in longitudine: distanza
#   massima dalla posizione vera ~4 km (sufficiente a impedire la
#   triangolazione visiva su radure/cascine isolate).
# - Coordinate troncate a 2 decimali (~1.1 km), così la risoluzione finale
#   esposta è dell'ordine del km anche intercettando la risposta JSON.
# - _COMMUNITY_PRIVACY_RADIUS_M dimensionato per coprire il caso peggiore:
#   errore_max_per_asse = _FUZZ_MAX_DEG + 0.01 (trunc) = 0.040°. A 41°N:
#   lat 4.45 km, lon 3.36 km → diagonale ≈ 5.58 km → cerchio 6 km garantisce
#   che la posizione vera sia SEMPRE dentro il cerchio mostrato all'utente.
_FUZZ_MAX_DEG = 0.030
_COMMUNITY_PRIVACY_RADIUS_M = 6000
_FUZZ_SALT = b'apiario-community-fuzz'


def _community_fuzz_offsets(apiario_id: int) -> tuple[float, float]:
    msg = _FUZZ_SALT + b':' + str(apiario_id).encode('ascii')
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'), msg, hashlib.sha256
    ).digest()
    # Prendo due int 32 bit indipendenti dai primi 8 byte del digest.
    r1 = int.from_bytes(digest[0:4], 'big') / 0xFFFFFFFF  # [0, 1]
    r2 = int.from_bytes(digest[4:8], 'big') / 0xFFFFFFFF
    lat_off = (r1 - 0.5) * 2.0 * _FUZZ_MAX_DEG
    lon_off = (r2 - 0.5) * 2.0 * _FUZZ_MAX_DEG
    return lat_off, lon_off


class ApiarioCommunitySerializer(serializers.ModelSerializer):
    """Versione "privacy-safe" di ApiarioSerializer per la mappa community.

    Espone il minimo necessario al rendering del marker e applica fuzzing
    server-side delle coordinate. NON include `posizione` (indirizzo
    testuale), `note`, `gruppo`, `visibilita_mappa` né l'id del proprietario.
    """

    proprietario_username = serializers.ReadOnlyField(source='proprietario.username')
    proprietario_immagine_profilo = serializers.SerializerMethodField()
    latitudine = serializers.SerializerMethodField()
    longitudine = serializers.SerializerMethodField()
    privacy_obfuscated = serializers.SerializerMethodField()
    privacy_radius_m = serializers.SerializerMethodField()

    class Meta:
        model = Apiario
        fields = [
            'id', 'nome', 'latitudine', 'longitudine',
            'proprietario_username', 'proprietario_immagine_profilo',
            'privacy_obfuscated', 'privacy_radius_m',
        ]

    def _fuzzed(self, obj):
        if obj.latitudine is None or obj.longitudine is None:
            return None, None
        lat_off, lon_off = _community_fuzz_offsets(obj.id)
        lat = float(obj.latitudine) + lat_off
        lon = float(obj.longitudine) + lon_off
        # Troncamento (non round) a 2 decimali per non rivelare la precisione
        # originale del valore: ~1.1 km di risoluzione finale.
        lat = math.trunc(lat * 100) / 100.0
        lon = math.trunc(lon * 100) / 100.0
        return lat, lon

    def get_privacy_obfuscated(self, obj):
        return True

    def get_privacy_radius_m(self, obj):
        return _COMMUNITY_PRIVACY_RADIUS_M

    def get_latitudine(self, obj):
        return self._fuzzed(obj)[0]

    def get_longitudine(self, obj):
        return self._fuzzed(obj)[1]

    def get_proprietario_immagine_profilo(self, obj):
        try:
            immagine = obj.proprietario.profilo.immagine
            if not immagine:
                return None
            request = self.context.get('request')
            url = immagine.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None


# Serializzatore Arnia
class ArniaSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    
    class Meta:
        model = Arnia
        fields = [
            'id', 'apiario', 'apiario_nome', 'numero', 'colore',
            'colore_hex', 'tipo_arnia', 'data_installazione', 'note', 'attiva',
            'attrezzatura', 'nfc_id'
        ]

# Serializzatore Controllo Arnia (versione dettagliata)
class ControlloArniaDetailSerializer(serializers.ModelSerializer):
    # Dati dalla colonia (FK primario)
    colonia_id   = serializers.ReadOnlyField(source='colonia.id')
    # Dati dall'arnia fisica (denormalizzato, può essere null)
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    # Apiario: preferisce la colonia, fallback sull'arnia legacy
    apiario_nome = serializers.SerializerMethodField()
    apiario_id   = serializers.SerializerMethodField()
    utente_username = serializers.ReadOnlyField(source='utente.username')

    class Meta:
        model = ControlloArnia
        fields = [
            'id', 'colonia', 'colonia_id', 'arnia', 'arnia_numero',
            'apiario_nome', 'apiario_id',
            'data', 'utente', 'utente_username', 'telaini_scorte',
            'telaini_covata', 'presenza_regina', 'sciamatura',
            'data_sciamatura', 'note_sciamatura', 'problemi_sanitari',
            'note_problemi', 'note', 'data_creazione',
            'regina_vista', 'uova_fresche', 'celle_reali',
            'numero_celle_reali', 'regina_sostituita', 'sostituzione_scatola', 'telaini_config'
        ]
        read_only_fields = ['utente']

    def get_apiario_nome(self, obj):
        if obj.colonia_id:
            return obj.colonia.apiario.nome
        if obj.arnia_id:
            return obj.arnia.apiario.nome
        return None

    def get_apiario_id(self, obj):
        if obj.colonia_id:
            return obj.colonia.apiario_id
        if obj.arnia_id:
            return obj.arnia.apiario_id
        return None

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        # Denormalizza arnia dal contenitore della colonia al momento del controllo
        colonia = validated_data.get('colonia')
        if colonia and not validated_data.get('arnia') and colonia.arnia_id:
            validated_data['arnia_id'] = colonia.arnia_id
        return super().create(validated_data)


# Serializzatore Controllo Arnia (versione lista)
class ControlloArniaListSerializer(serializers.ModelSerializer):
    colonia_id   = serializers.ReadOnlyField(source='colonia.id')
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    apiario_nome = serializers.SerializerMethodField()

    class Meta:
        model = ControlloArnia
        fields = [
            'id', 'colonia', 'colonia_id', 'arnia', 'arnia_numero',
            'apiario_nome', 'data', 'telaini_scorte', 'telaini_covata',
            'presenza_regina', 'problemi_sanitari'
        ]

    def get_apiario_nome(self, obj):
        if obj.colonia_id:
            return obj.colonia.apiario.nome
        if obj.arnia_id:
            return obj.arnia.apiario.nome
        return None

# Serializzatore Regina
class ReginaSerializer(serializers.ModelSerializer):
    colonia_id   = serializers.ReadOnlyField(source='colonia.id')
    arnia_numero = serializers.SerializerMethodField()
    apiario_nome = serializers.SerializerMethodField()
    apiario_id   = serializers.SerializerMethodField()
    # Hint write-only: il client può inviare l'arnia e il serializer risolve
    # (o crea, se mancante) la Colonia attiva associata. Mantiene compatibilità
    # con i client che usano ancora il vecchio payload {arnia: id}.
    arnia = serializers.PrimaryKeyRelatedField(
        write_only=True, required=False, allow_null=True,
        queryset=Arnia.objects.all()
    )

    class Meta:
        model = Regina
        fields = [
            'id', 'colonia', 'colonia_id', 'arnia', 'arnia_numero',
            'apiario_nome', 'apiario_id',
            'data_nascita', 'data_introduzione', 'origine', 'razza',
            'regina_madre', 'marcata', 'codice_marcatura', 'colore_marcatura',
            'fecondata', 'selezionata', 'sospetta_assente',
            'docilita', 'produttivita',
            'resistenza_malattie', 'tendenza_sciamatura', 'note'
        ]
        extra_kwargs = {
            'colonia': {'required': False, 'allow_null': True},
        }

    def get_arnia_numero(self, obj):
        if obj.colonia_id and obj.colonia.arnia_id:
            return obj.colonia.arnia.numero
        return None

    def get_apiario_nome(self, obj):
        if obj.colonia_id:
            return obj.colonia.apiario.nome
        return None

    def get_apiario_id(self, obj):
        if obj.colonia_id:
            return obj.colonia.apiario_id
        return None

    def _resolve_colonia(self, validated_data):
        """Se è stato passato l'hint `arnia` ma non `colonia`, trova la
        Colonia attiva di quell'arnia (o ne crea una se manca) e la imposta."""
        arnia = validated_data.pop('arnia', None)
        if validated_data.get('colonia') or arnia is None:
            return validated_data
        from django.utils import timezone
        colonia = Colonia.objects.filter(
            arnia=arnia, stato='attiva', data_fine__isnull=True
        ).first()
        if colonia is None:
            request = self.context.get('request')
            user = request.user if request is not None else arnia.apiario.proprietario
            colonia = Colonia.objects.create(
                arnia=arnia,
                apiario=arnia.apiario,
                utente=user,
                data_inizio=validated_data.get('data_introduzione') or timezone.now().date(),
                stato='attiva',
            )
        validated_data['colonia'] = colonia
        return validated_data

    def create(self, validated_data):
        validated_data = self._resolve_colonia(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # In update il campo `arnia` è solo un eco lato client: la rilegatura
        # alla colonia avviene tramite endpoint dedicati (sostituisci, sposta).
        validated_data.pop('arnia', None)
        return super().update(instance, validated_data)


# Serializzatore StoriaRegine
class StoriaRegineSerializer(serializers.ModelSerializer):
    colonia_id     = serializers.ReadOnlyField(source='colonia.id')
    regina_razza   = serializers.ReadOnlyField(source='regina.razza')
    regina_origine = serializers.ReadOnlyField(source='regina.origine')

    class Meta:
        model = StoriaRegine
        fields = [
            'id', 'colonia', 'colonia_id',
            'regina', 'regina_razza', 'regina_origine',
            'data_inizio', 'data_fine', 'motivo_fine', 'note'
        ]


# Serializzatore genealogia Regina (madre + figlie + storia nella colonia)
class ReginaGenealogySerializer(serializers.ModelSerializer):
    madre          = serializers.SerializerMethodField()
    figlie         = serializers.SerializerMethodField()
    storia_colonia = serializers.SerializerMethodField()

    class Meta:
        model = Regina
        fields = [
            'id', 'colonia', 'razza', 'origine',
            'data_nascita', 'data_introduzione',
            'marcata', 'colore_marcatura', 'fecondata', 'selezionata', 'note',
            'madre', 'figlie', 'storia_colonia'
        ]

    def get_madre(self, obj):
        if obj.regina_madre:
            m = obj.regina_madre
            return {
                'id': m.id,
                'razza': m.razza,
                'origine': m.origine,
                'data_introduzione': m.data_introduzione,
                'colonia': m.colonia_id,
            }
        return None

    def get_figlie(self, obj):
        return [
            {
                'id': f.id,
                'razza': f.razza,
                'origine': f.origine,
                'data_introduzione': f.data_introduzione,
                'colonia': f.colonia_id,
            }
            for f in obj.figlie.all()
        ]

    def get_storia_colonia(self, obj):
        if not obj.colonia_id:
            return []
        storia = StoriaRegine.objects.filter(colonia=obj.colonia).order_by('-data_inizio')
        return StoriaRegineSerializer(storia, many=True).data


# Serializzatore Fioritura
class FiorituraSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    creatore_username = serializers.ReadOnlyField(source='creatore.username')
    is_active = serializers.SerializerMethodField()
    n_conferme = serializers.SerializerMethodField()
    intensita_media = serializers.SerializerMethodField()
    confermato_da_me = serializers.SerializerMethodField()

    class Meta:
        model = Fioritura
        fields = [
            'id', 'apiario', 'apiario_nome', 'pianta', 'pianta_tipo',
            'data_inizio', 'data_fine', 'latitudine', 'longitudine', 'raggio',
            'note', 'creatore', 'creatore_username', 'is_active',
            'pubblica', 'intensita',
            'n_conferme', 'intensita_media', 'confermato_da_me',
        ]
        read_only_fields = ['creatore']

    def get_is_active(self, obj):
        return obj.is_active()

    def get_n_conferme(self, obj):
        return obj.conferme.count()

    def get_intensita_media(self, obj):
        conferme = obj.conferme.filter(intensita__isnull=False)
        if not conferme.exists():
            return None
        total = sum(c.intensita for c in conferme)
        return round(total / conferme.count(), 1)

    def get_confermato_da_me(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.conferme.filter(utente=request.user).exists()
        return False

    def create(self, validated_data):
        validated_data['creatore'] = self.context['request'].user
        return super().create(validated_data)


class FiorituraConfermaSerializer(serializers.ModelSerializer):
    utente_username = serializers.ReadOnlyField(source='utente.username')

    class Meta:
        model = FiorituraConferma
        fields = ['id', 'fioritura', 'utente', 'utente_username', 'data', 'intensita', 'nota']
        read_only_fields = ['utente', 'data']

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
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
    apiario_nome          = serializers.ReadOnlyField(source='apiario.nome')
    apiario_gruppo_nome   = serializers.SerializerMethodField()
    tipo_trattamento_nome = serializers.ReadOnlyField(source='tipo_trattamento.nome')
    utente_username       = serializers.ReadOnlyField(source='utente.username')
    # stato is always derived from dates at read time; 'annullato' is the only
    # writable value (set via the dedicated /annulla/ action).
    stato = serializers.SerializerMethodField()

    class Meta:
        model = TrattamentoSanitario
        fields = [
            'id', 'apiario', 'apiario_nome', 'apiario_gruppo_nome',
            'tipo_trattamento', 'tipo_trattamento_nome',
            'data_inizio', 'data_fine', 'data_fine_sospensione',
            'stato', 'utente', 'utente_username',
            'colonie', 'arnie', 'note', 'blocco_covata_attivo', 'data_inizio_blocco',
            'data_fine_blocco', 'metodo_blocco', 'note_blocco',
            'metodo_applicazione',
        ]
        read_only_fields = ['utente', 'data_fine_sospensione', 'stato']

    def get_stato(self, obj):
        return obj.stato_effettivo

    def get_apiario_gruppo_nome(self, obj):
        try:
            return obj.apiario.gruppo.nome if obj.apiario.gruppo_id else None
        except Exception:
            return None

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Melario
class MelarioSerializer(serializers.ModelSerializer):
    colonia_id          = serializers.ReadOnlyField(source='colonia.id')
    apiario_id          = serializers.SerializerMethodField()
    apiario_nome        = serializers.SerializerMethodField()
    apiario_gruppo_nome = serializers.SerializerMethodField()
    arnia_id            = serializers.SerializerMethodField()
    arnia_numero        = serializers.SerializerMethodField()

    class Meta:
        model = Melario
        fields = [
            'id', 'colonia', 'colonia_id',
            'arnia_id', 'arnia_numero',
            'apiario_id', 'apiario_nome', 'apiario_gruppo_nome',
            'numero_telaini', 'posizione', 'data_posizionamento',
            'data_rimozione', 'stato', 'tipo_melario', 'stato_favi',
            'escludi_regina', 'peso_stimato', 'note',
            'numero_progressivo',
        ]
        read_only_fields = ['numero_progressivo']

    def _colonia(self, obj):
        if obj.colonia_id:
            return obj.colonia
        return None

    def _apiario(self, obj):
        col = self._colonia(obj)
        return col.apiario if col else None

    def get_arnia_id(self, obj):
        col = self._colonia(obj)
        return col.arnia_id if col and col.arnia_id else None

    def get_arnia_numero(self, obj):
        col = self._colonia(obj)
        return col.arnia.numero if col and col.arnia_id else None

    def get_apiario_id(self, obj):
        ap = self._apiario(obj)
        return ap.id if ap else None

    def get_apiario_nome(self, obj):
        ap = self._apiario(obj)
        return ap.nome if ap else None

    def get_apiario_gruppo_nome(self, obj):
        try:
            ap = self._apiario(obj)
            return ap.gruppo.nome if ap and ap.gruppo_id else None
        except Exception:
            return None

# Serializzatore Smielatura
class SmielaturaSerializer(serializers.ModelSerializer):
    apiario_nome        = serializers.ReadOnlyField(source='apiario.nome')
    apiario_gruppo_nome = serializers.SerializerMethodField()
    utente_username     = serializers.ReadOnlyField(source='utente.username')
    melari_count        = serializers.SerializerMethodField()
    kg_residui          = serializers.ReadOnlyField()
    is_esaurita         = serializers.ReadOnlyField()

    class Meta:
        model = Smielatura
        fields = [
            'id', 'data', 'apiario', 'apiario_nome', 'apiario_gruppo_nome',
            'melari', 'melari_count', 'quantita_miele', 'tipo_miele',
            'kg_trasferiti', 'kg_residui', 'is_esaurita', 'archiviata',
            'utente', 'utente_username', 'note', 'data_registrazione'
        ]
        read_only_fields = ['utente', 'kg_trasferiti']

    def get_apiario_gruppo_nome(self, obj):
        try:
            return obj.apiario.gruppo.nome if obj.apiario.gruppo_id else None
        except Exception:
            return None

    def get_melari_count(self, obj):
        return obj.melari.count()
    
    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

# Serializzatore Gruppo
class GruppoSerializer(serializers.ModelSerializer):
    creatore_username = serializers.ReadOnlyField(source='creatore.username')
    membri_count = serializers.SerializerMethodField()
    apiari_count = serializers.SerializerMethodField()
    immagine_profilo = serializers.SerializerMethodField()

    class Meta:
        model = Gruppo
        fields = [
            'id', 'nome', 'descrizione', 'data_creazione',
            'creatore', 'creatore_username', 'membri_count', 'apiari_count',
            'immagine_profilo'
        ]
        read_only_fields = ['creatore']

    def get_membri_count(self, obj):
        return obj.membri.count()

    def get_apiari_count(self, obj):
        return obj.apiari.filter(condiviso_con_gruppo=True).count()

    def get_immagine_profilo(self, obj):
        try:
            immagine = obj.immagine_profilo.immagine
            if not immagine:
                return None
            request = self.context.get('request')
            url = immagine.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    # FIX #2 - Il metodo create è stato rimosso dal serializer.
    # La logica di creazione (creatore + auto-aggiunta come admin)
    # è ora gestita interamente in GruppoViewSet.perform_create()

# Serializzatore MembroGruppo
class MembroGruppoSerializer(serializers.ModelSerializer):
    utente_username = serializers.ReadOnlyField(source='utente.username')
    gruppo_nome = serializers.ReadOnlyField(source='gruppo.nome')
    immagine_profilo = serializers.SerializerMethodField()

    class Meta:
        model = MembroGruppo
        fields = [
            'id', 'utente', 'utente_username', 'gruppo',
            'gruppo_nome', 'ruolo', 'data_aggiunta', 'immagine_profilo'
        ]

    def get_immagine_profilo(self, obj):
        try:
            immagine = obj.utente.profilo.immagine
            if not immagine:
                return None
            request = self.context.get('request')
            url = immagine.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

# Serializzatore InvitoGruppo
class InvitoGruppoSerializer(serializers.ModelSerializer):
    gruppo_nome = serializers.ReadOnlyField(source='gruppo.nome')
    invitato_da_username = serializers.ReadOnlyField(source='invitato_da.username')

    class Meta:
        model = InvitoGruppo
        fields = [
            'id', 'gruppo', 'gruppo_nome', 'email', 'ruolo_proposto',
            'token',  # FIX #5 - Aggiunto token per permettere accept/reject da Flutter
            'data_invio', 'data_scadenza', 'stato',
            'invitato_da', 'invitato_da_username'
        ]
        read_only_fields = ['invitato_da', 'data_invio', 'data_scadenza', 'token']

    def create(self, validated_data):
        validated_data['invitato_da'] = self.context['request'].user
        return super().create(validated_data)

class PagamentoSerializer(serializers.ModelSerializer):
    utente_username = serializers.SerializerMethodField()
    destinatario_username = serializers.SerializerMethodField()
    gruppo_nome = serializers.SerializerMethodField()

    class Meta:
        model = Pagamento
        fields = ['id', 'utente', 'utente_username', 'destinatario', 'destinatario_username',
                  'importo', 'data', 'descrizione', 'gruppo', 'gruppo_nome']

    def get_utente_username(self, obj):
        return obj.utente.username if obj.utente else None

    def get_destinatario_username(self, obj):
        return obj.destinatario.username if obj.destinatario else None

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
    attrezzatura_nome  = serializers.SerializerMethodField()
    gruppo_nome        = serializers.SerializerMethodField()
    utente_username    = serializers.ReadOnlyField(source='utente.username')
    pagato_da_username = serializers.SerializerMethodField()
    tipo_display       = serializers.SerializerMethodField()

    class Meta:
        model = SpesaAttrezzatura
        fields = [
            'id', 'attrezzatura', 'attrezzatura_nome',
            'gruppo', 'gruppo_nome',
            'tipo', 'tipo_display', 'descrizione', 'importo', 'data',
            'fornitore', 'numero_fattura',
            'utente', 'utente_username',
            'pagato_da', 'pagato_da_username',
            'note', 'data_creazione',
        ]
        read_only_fields = ['utente', 'data_creazione']
        extra_kwargs = {'pagato_da': {'allow_null': True, 'required': False}}

    def get_attrezzatura_nome(self, obj):
        return obj.attrezzatura.nome if obj.attrezzatura else None

    def get_pagato_da_username(self, obj):
        return obj.pagato_da.username if obj.pagato_da_id else None

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


# Serializzatore Invasettamento
class InvasettamentoSerializer(serializers.ModelSerializer):
    smielatura_info     = serializers.SerializerMethodField()
    contenitore_info    = serializers.SerializerMethodField()
    apiario_gruppo_nome = serializers.SerializerMethodField()
    utente_username     = serializers.ReadOnlyField(source='utente.username')
    kg_totali           = serializers.SerializerMethodField()
    vasetti_disponibili = serializers.ReadOnlyField()
    kg_disponibili      = serializers.ReadOnlyField()

    class Meta:
        model = Invasettamento
        fields = [
            'id', 'data', 'smielatura', 'smielatura_info',
            'contenitore', 'contenitore_info',
            'apiario_gruppo_nome',
            'tipo_miele', 'formato_vasetto',
            'numero_vasetti', 'numero_vasetti_venduti', 'vasetti_disponibili',
            'lotto', 'utente', 'utente_username', 'note',
            'data_registrazione', 'kg_totali', 'kg_disponibili',
        ]
        read_only_fields = ['utente']
        extra_kwargs = {
            'smielatura': {'required': False, 'allow_null': True},
            'contenitore': {'required': False, 'allow_null': True},
        }

    def get_smielatura_info(self, obj):
        if obj.smielatura:
            return f"{obj.smielatura.data} - {obj.smielatura.apiario.nome}"
        return None

    def get_contenitore_info(self, obj):
        if obj.contenitore:
            return f"{obj.contenitore.get_tipo_display()} {obj.contenitore.nome} - {obj.contenitore.tipo_miele}"
        return None

    def get_apiario_gruppo_nome(self, obj):
        try:
            if obj.smielatura:
                return obj.smielatura.apiario.gruppo.nome if obj.smielatura.apiario.gruppo_id else None
        except Exception:
            pass
        return None

    def get_kg_totali(self, obj):
        return obj.kg_totali

    def validate(self, data):
        if not data.get('smielatura') and not data.get('contenitore'):
            raise serializers.ValidationError("Specificare almeno smielatura o contenitore.")
        return data

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)



# Serializzatore PreferenzaMaturazione
class PreferenzaMaturazionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreferenzaMaturazione
        fields = ['id', 'tipo_miele', 'giorni_maturazione']
        read_only_fields = ['utente']

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore Maturatore
class MatutatoreSerializer(serializers.ModelSerializer):
    data_pronta       = serializers.ReadOnlyField()
    giorni_rimanenti  = serializers.ReadOnlyField()
    smielatura_info   = serializers.SerializerMethodField()
    tipo_display      = serializers.SerializerMethodField()

    class Meta:
        model = Maturatore
        fields = [
            'id', 'nome', 'capacita_kg', 'kg_attuali', 'tipo_miele',
            'smielatura', 'smielatura_info', 'data_inizio', 'giorni_maturazione',
            'stato', 'tipo_display', 'note', 'data_registrazione',
            'data_pronta', 'giorni_rimanenti',
        ]
        read_only_fields = ['utente']

    def get_smielatura_info(self, obj):
        if obj.smielatura:
            return f"{obj.smielatura.data} - {obj.smielatura.apiario.nome}"
        return None

    def get_tipo_display(self, obj):
        return obj.get_stato_display()

    def validate(self, attrs):
        # Sui CREATE la smielatura è obbligatoria: il flusso impone che
        # ogni maturatore origini da una smielatura specifica. Sugli UPDATE
        # restiamo permissivi per non rompere dati storici già senza FK.
        if self.instance is None and not attrs.get('smielatura'):
            raise serializers.ValidationError(
                {'smielatura': 'La smielatura di origine è obbligatoria per un nuovo maturatore.'}
            )
        # Validazione coerenza kg: non si può iniziare con più di quanto
        # disponibile dalla smielatura selezionata.
        smiel = attrs.get('smielatura')
        kg = attrs.get('kg_attuali')
        if self.instance is None and smiel is not None and kg is not None:
            from decimal import Decimal
            residui = smiel.kg_residui
            if Decimal(kg) > residui + Decimal('0.01'):
                raise serializers.ValidationError({
                    'kg_attuali': f'Disponibili dalla smielatura: {residui} kg, richiesti: {kg} kg.'
                })
        return attrs

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore ContenitoreStoccaggio
class ContenitoreStoccaggioSerializer(serializers.ModelSerializer):
    maturatore_info = serializers.SerializerMethodField()
    tipo_display    = serializers.SerializerMethodField()
    stato_display   = serializers.SerializerMethodField()

    class Meta:
        model = ContenitoreStoccaggio
        fields = [
            'id', 'nome', 'tipo', 'tipo_display', 'capacita_kg', 'kg_attuali',
            'tipo_miele', 'maturatore', 'maturatore_info',
            'data_riempimento', 'stato', 'stato_display',
            'note', 'data_registrazione',
        ]
        read_only_fields = ['utente']

    def get_maturatore_info(self, obj):
        if obj.maturatore:
            return f"{obj.maturatore.nome} - {obj.maturatore.tipo_miele}"
        return None

    def get_tipo_display(self, obj):
        return obj.get_tipo_display()

    def get_stato_display(self, obj):
        return obj.get_stato_display()

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore Cliente
class ClienteSerializer(serializers.ModelSerializer):
    utente_username = serializers.ReadOnlyField(source='utente.username')
    vendite_count   = serializers.SerializerMethodField()
    gruppo_nome     = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id', 'nome', 'telefono', 'email', 'indirizzo',
            'note', 'utente', 'utente_username', 'vendite_count',
            'gruppo', 'gruppo_nome'
        ]
        read_only_fields = ['utente']

    def get_vendite_count(self, obj):
        return obj.vendite.count()

    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo_id else None

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore DettaglioVendita
class DettaglioVenditaSerializer(serializers.ModelSerializer):
    subtotale = serializers.SerializerMethodField()

    class Meta:
        model = DettaglioVendita
        fields = [
            'id', 'vendita', 'categoria', 'tipo_miele', 'formato_vasetto',
            'quantita', 'prezzo_unitario', 'subtotale'
        ]
        read_only_fields = ['vendita']

    def get_subtotale(self, obj):
        return float(obj.subtotale)


# Serializzatore Vendita
class VenditaSerializer(serializers.ModelSerializer):
    cliente_nome    = serializers.SerializerMethodField()
    utente_username = serializers.ReadOnlyField(source='utente.username')
    dettagli        = DettaglioVenditaSerializer(many=True, read_only=True)
    totale          = serializers.SerializerMethodField()
    gruppo_nome     = serializers.SerializerMethodField()

    class Meta:
        model = Vendita
        fields = [
            'id', 'data', 'cliente', 'cliente_nome', 'acquirente_nome',
            'canale', 'pagamento',
            'utente', 'utente_username', 'note',
            'data_registrazione', 'dettagli', 'totale',
            'gruppo', 'gruppo_nome'
        ]
        read_only_fields = ['utente']
        extra_kwargs = {
            'cliente': {'allow_null': True, 'required': False},
            'gruppo':  {'allow_null': True, 'required': False},
        }

    def get_cliente_nome(self, obj):
        if obj.cliente_id:
            return obj.cliente.nome
        return obj.acquirente_nome or None

    def get_totale(self, obj):
        return float(obj.totale)

    def get_gruppo_nome(self, obj):
        return obj.gruppo.nome if obj.gruppo_id else None

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# Serializzatore AnalisiTelaino
class AnalisiTelainoSerializer(serializers.ModelSerializer):
    utente_username = serializers.ReadOnlyField(source='utente.username')
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')

    class Meta:
        model = AnalisiTelaino
        fields = [
            'id', 'arnia', 'arnia_numero', 'numero_telaino', 'facciata',
            'data', 'conteggio_api', 'conteggio_regine', 'conteggio_fuchi',
            'conteggio_celle_reali', 'confidence_media', 'note', 'immagine',
            'utente', 'utente_username', 'data_registrazione'
        ]
        read_only_fields = ['utente', 'data', 'data_registrazione']

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


# ── Serializzatori Colonia ────────────────────────────────────────────────────

class ColoniaListSerializer(serializers.ModelSerializer):
    """Versione compatta per le liste."""
    apiario_nome       = serializers.ReadOnlyField(source='apiario.nome')
    contenitore        = serializers.SerializerMethodField()
    contenitore_numero = serializers.SerializerMethodField()
    is_attiva          = serializers.SerializerMethodField()

    class Meta:
        model = Colonia
        fields = [
            'id', 'apiario', 'apiario_nome',
            'arnia', 'nucleo', 'contenitore', 'contenitore_numero',
            'data_inizio', 'data_fine', 'stato', 'is_attiva',
        ]

    def get_contenitore(self, obj):
        if obj.arnia_id:
            return 'arnia'
        if obj.nucleo_id:
            return 'nucleo'
        return None

    def get_contenitore_numero(self, obj):
        if obj.arnia_id:
            return obj.arnia.numero
        if obj.nucleo_id:
            return obj.nucleo.numero
        return None

    def get_is_attiva(self, obj):
        return obj.is_attiva()


class ColoniaDetailSerializer(serializers.ModelSerializer):
    """Versione completa con nesting leggero per il dettaglio."""
    apiario_nome        = serializers.ReadOnlyField(source='apiario.nome')
    utente_username     = serializers.ReadOnlyField(source='utente.username')
    contenitore         = serializers.SerializerMethodField()
    contenitore_numero  = serializers.SerializerMethodField()
    is_attiva           = serializers.SerializerMethodField()
    # Genealogia (id + label, non ricorsivi per evitare N+1)
    colonia_origine_label    = serializers.SerializerMethodField()
    colonia_successore_label = serializers.SerializerMethodField()
    n_controlli         = serializers.SerializerMethodField()
    regina_attiva       = serializers.SerializerMethodField()

    class Meta:
        model = Colonia
        fields = [
            'id', 'apiario', 'apiario_nome', 'utente', 'utente_username',
            'arnia', 'nucleo', 'contenitore', 'contenitore_numero',
            'data_inizio', 'data_fine', 'stato', 'is_attiva',
            'motivo_fine', 'note_fine', 'note',
            'colonia_origine', 'colonia_origine_label',
            'colonia_successore', 'colonia_successore_label',
            'n_controlli', 'regina_attiva',
            'data_creazione',
        ]
        read_only_fields = ['utente', 'data_creazione']
        extra_kwargs = {'apiario': {'required': False}}

    def get_contenitore(self, obj):
        if obj.arnia_id:
            return 'arnia'
        if obj.nucleo_id:
            return 'nucleo'
        return None

    def get_contenitore_numero(self, obj):
        if obj.arnia_id:
            return obj.arnia.numero
        if obj.nucleo_id:
            return obj.nucleo.numero
        return None

    def get_is_attiva(self, obj):
        return obj.is_attiva()

    def get_colonia_origine_label(self, obj):
        if obj.colonia_origine_id:
            return str(obj.colonia_origine)
        return None

    def get_colonia_successore_label(self, obj):
        if obj.colonia_successore_id:
            return str(obj.colonia_successore)
        return None

    def get_n_controlli(self, obj):
        return obj.controlli.count()

    def get_regina_attiva(self, obj):
        try:
            r = obj.regina
            return {
                'id': r.id,
                'razza': r.razza,
                'origine': r.origine,
                'data_introduzione': r.data_introduzione,
                'colore_marcatura': r.colore_marcatura,
            }
        except Exception:
            return None

    def validate(self, attrs):
        # Deriva apiario da arnia o nucleo se non fornito esplicitamente
        if not attrs.get('apiario'):
            arnia  = attrs.get('arnia')
            nucleo = attrs.get('nucleo')
            if arnia:
                attrs['apiario'] = arnia.apiario
            elif nucleo:
                attrs['apiario'] = nucleo.apiario
            else:
                raise serializers.ValidationError(
                    {'apiario': 'Fornire apiario, arnia o nucleo.'}
                )
        return attrs

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)


class ColoniaChiudiSerializer(serializers.Serializer):
    """Payload per POST /colonie/{id}/chiudi/ — chiude il ciclo di vita."""
    stato = serializers.ChoiceField(choices=[
        ('morta',     'Colonia morta'),
        ('venduta',   'Ceduta / Venduta'),
        ('sciamata',  'Sciamata e non recuperata'),
        ('unita',     'Unita ad altra colonia'),
        ('nucleo',    'Ridotta a nucleo'),
        ('eliminata', 'Eliminata'),
    ])
    data_fine          = serializers.DateField(required=False)
    motivo_fine        = serializers.CharField(required=False, allow_blank=True)
    note_fine          = serializers.CharField(required=False, allow_blank=True)
    colonia_successore = serializers.PrimaryKeyRelatedField(
        queryset=Colonia.objects.all(), required=False, allow_null=True
    )


class ColoniaSpostaSerializer(serializers.Serializer):
    """
    Payload per POST /colonie/{id}/sposta_contenitore/
    Sposta la colonia in un'altra Arnia o Nucleo (es. nomadismo, conversione).
    """
    arnia  = serializers.PrimaryKeyRelatedField(
        queryset=Arnia.objects.all(), required=False, allow_null=True
    )
    nucleo = serializers.PrimaryKeyRelatedField(
        queryset=Nucleo.objects.all(), required=False, allow_null=True  # type: ignore[misc]
    )
    data_spostamento = serializers.DateField(required=False)
    note             = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        if data.get('arnia') and data.get('nucleo'):
            raise serializers.ValidationError(
                "Specificare solo 'arnia' oppure solo 'nucleo', non entrambi."
            )
        if not data.get('arnia') and not data.get('nucleo'):
            raise serializers.ValidationError(
                "Specificare 'arnia' o 'nucleo' come destinazione."
            )
        return data


# ── Serializzatori Nucleo ─────────────────────────────────────────────────────

class NucleoSerializer(serializers.ModelSerializer):
    apiario_nome = serializers.ReadOnlyField(source='apiario.nome')
    arnia_numero = serializers.ReadOnlyField(source='arnia.numero')
    convertito = serializers.SerializerMethodField()

    class Meta:
        model = Nucleo
        fields = [
            'id', 'apiario', 'apiario_nome', 'numero', 'colore_hex',
            'data_installazione', 'note', 'attiva',
            'arnia', 'arnia_numero', 'data_conversione', 'data_creazione',
            'convertito',
        ]
        read_only_fields = ['data_creazione', 'arnia', 'data_conversione']

    def get_convertito(self, obj):
        return obj.arnia is not None


class ControlloNucleoSerializer(serializers.ModelSerializer):
    colonia_id = serializers.ReadOnlyField(source='colonia.id')

    class Meta:
        model = ControlloNucleo
        fields = [
            'id', 'nucleo', 'colonia', 'colonia_id', 'utente', 'data',
            'n_telaini', 'forza_colonia', 'presenza_regina', 'note', 'data_creazione',
        ]
        read_only_fields = ['utente', 'data_creazione']


class ApiarioMapLayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiarioMapLayout
        fields = ['id', 'apiario', 'layout_json', 'updated_at']
        read_only_fields = ['updated_at']


class MeteoGiornalieroSerializer(serializers.ModelSerializer):
    """Serializzatore del dataset meteo giornaliero per-apiario (dataset ML)."""

    class Meta:
        model = MeteoGiornaliero
        fields = [
            'id', 'apiario', 'data',
            'temp_min', 'temp_max', 'temp_mean',
            'precip_mm', 'precip_hours',
            'umidita_media', 'vento_medio', 'vento_raffica_max', 'pressione_media',
            'ore_sole', 'radiazione_mj', 'gdd_base10',
            'weather_code_dominante', 'source', 'updated_at',
        ]
        read_only_fields = fields


class VarroaCheckpointSerializer(serializers.ModelSerializer):
    """Serializzatore per i checkpoint di monitoraggio Varroa."""
    colonia_nome = serializers.SerializerMethodField()
    metodo_display = serializers.ReadOnlyField(source='get_metodo_display')

    class Meta:
        model = VarroaCheckpoint
        fields = [
            'id', 'colonia', 'colonia_nome',
            'data_campionamento', 'metodo', 'metodo_display',
            'api_campionate', 'acari_contati', 'giorni_misurazione',
            'telaini_covata',
            'percentuale_calcolata', 'caduta_giornaliera', 'confidenza',
            'note', 'utente', 'data_creazione',
        ]
        read_only_fields = ['percentuale_calcolata', 'caduta_giornaliera', 'confidenza', 'utente', 'data_creazione']

    def get_colonia_nome(self, obj):
        return obj.colonia.contenitore_display() if obj.colonia else None

    def create(self, validated_data):
        validated_data['utente'] = self.context['request'].user
        return super().create(validated_data)

    def validate(self, data):
        metodo = data.get('metodo')
        if metodo in ('lavaggio_alcolico', 'sugar_shake') and not data.get('api_campionate'):
            raise serializers.ValidationError(
                {'api_campionate': 'Campo obbligatorio per lavaggio alcolico e sugar shake.'}
            )
        if metodo == 'caduta_naturale' and not data.get('giorni_misurazione'):
            raise serializers.ValidationError(
                {'giorni_misurazione': 'Campo obbligatorio per la caduta naturale.'}
            )
        return data