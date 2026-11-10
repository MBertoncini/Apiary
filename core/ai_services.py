"""
Servizio Gemini con rotazione automatica dei modelli.
Mimics the model rotation strategy from the Flutter Apiary app.
"""
import json
import base64
import requests
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from datetime import timedelta

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Modelli in ordine di priorità — si ruota automaticamente in caso di quota esaurita
# La famiglia 2.5 / 2.0 / 1.5 è stata ritirata per i nuovi progetti: Google
# risponde 404 NOT_FOUND indicando gemini-3.6-flash come sostituto. Tenere la
# lista corta: generate_raw ruota sui 404 e ogni tentativo ri-invia il payload,
# che per la voce contiene l'audio in base64.
GEMINI_MODELS = [
    'gemini-3.8-flash',        # migliore qualità
    'gemini-3.6-flash',        # fallback indicato da Google sui modelli ritirati
    'gemini-3.5-flash-lite',   # ultimo fallback, economico
]

# Token in piu' concessi al ragionamento interno dei modelli "thinking",
# oltre alla lunghezza della risposta visibile richiesta dal chiamante.
THINKING_HEADROOM_TOKENS = 4096

# Modelli con supporto Vision (immagini)
GEMINI_VISION_MODELS = [
    'gemini-3.8-flash',
    'gemini-3.6-flash',
]


class GeminiService:
    @property
    def api_key(self):
        return getattr(settings, 'GEMINI_API_KEY', '')

    def _call_model(self, model, payload, timeout=45, api_key=None):
        """Chiama un modello specifico. Ritorna (success, text, status_code)."""
        key = api_key or self.api_key
        if not key:
            return False, 'Nessuna GEMINI_API_KEY configurata (né personale né di sistema)', 403
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get('candidates', [])
                if not candidates:
                    return False, f'Risposta vuota (nessun candidato): {resp.text[:200]}', -1
                candidate = candidates[0]
                finish_reason = candidate.get('finishReason', 'STOP')
                if finish_reason in ('SAFETY', 'RECITATION', 'OTHER'):
                    return False, f'Risposta bloccata da Gemini (finishReason={finish_reason})', -1
                content = candidate.get('content', {})
                parts = content.get('parts', [])
                if not parts:
                    return False, f'Risposta senza contenuto (finishReason={finish_reason})', -1
                # Il testo puo' arrivare spezzato su piu' parti: le unisco tutte,
                # saltando quelle che contengono solo il ragionamento del modello.
                text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
                if not text:
                    return False, f'Testo risposta vuoto (finishReason={finish_reason})', -1
                if finish_reason == 'MAX_TOKENS':
                    text = text.rstrip() + '…'
                return True, text, 200
            else:
                return False, resp.text, resp.status_code
        except requests.exceptions.Timeout:
            return False, 'timeout', 0
        except Exception as e:
            return False, str(e), -1

    def _build_payload(self, messages, system_prompt=None, temperature=0.7, max_tokens=1024,
                       response_mime_type=None):
        contents = []
        for msg in messages:
            if 'parts' in msg:
                contents.append({'role': msg['role'], 'parts': msg['parts']})
            else:
                contents.append({'role': msg['role'], 'parts': [{'text': msg['text']}]})

        gen_config = {
            'temperature': temperature,
            # Sui modelli con ragionamento i token "pensati" contano nel limite:
            # senza margine il ragionamento consuma quasi tutto e la risposta
            # visibile arriva troncata (finishReason=MAX_TOKENS).
            'maxOutputTokens': max_tokens + THINKING_HEADROOM_TOKENS,
        }
        if response_mime_type:
            gen_config['responseMimeType'] = response_mime_type

        payload = {
            'contents': contents,
            'generationConfig': gen_config,
        }
        if system_prompt:
            payload['systemInstruction'] = {'parts': [{'text': system_prompt}]}
        return payload

    def generate(self, messages, system_prompt=None, temperature=0.7, max_tokens=1024,
                 api_key=None, response_mime_type=None):
        """
        Genera una risposta con rotazione automatica dei modelli.
        Ritorna (response_text, model_used) o lancia Exception.
        """
        payload = self._build_payload(messages, system_prompt, temperature, max_tokens,
                                      response_mime_type=response_mime_type)
        last_error = None

        for model in GEMINI_MODELS:
            success, text, status = self._call_model(model, payload, api_key=api_key)
            if success:
                return text, model
            elif status == 429:
                # Distingui tra quota permanentemente esaurita e rate limit temporaneo
                if '"limit":0' in text or '"limit": 0' in text or 'limit: 0' in text:
                    last_error = f"Modello {model} disabilitato (quota 0)"
                    continue  # prova prossimo modello
                else:
                    last_error = f"Rate limit su {model}, provo prossimo"
                    continue  # prova comunque il prossimo
            elif status in (0, -1):
                last_error = f"Errore di rete su {model}: {text}"
                break  # non ritentare su errori di rete
            else:
                last_error = f"Errore {status} su {model}: {text[:200]}"
                continue

        raise Exception(f"Tutti i modelli Gemini hanno fallito. Ultimo errore: {last_error}")

    def generate_raw(self, payload, models=None, timeout=30, api_key=None):
        """
        Inoltra a Gemini un payload generateContent GIA' COMPLETO costruito dal
        client (contents / tools / systemInstruction / generationConfig) e
        ritorna la risposta GREZZA, senza rimodellarla né estrarre il testo.

        Serve al proxy mobile: il client continua a orchestrare il function
        calling (tool MCP) e il parsing, ma la chiave Gemini resta server-side
        e non viene mai spedita nel binario dell'app.

        Ritorna (success: bool, data: dict|str, status: int, model_used: str|None).
        Su success `data` è il JSON Gemini; altrimenti è il testo d'errore.
        Ruota i modelli su 429 / 404 / 502 / 503; si ferma su 4xx client.
        """
        key = api_key or self.api_key
        if not key:
            return False, 'Nessuna GEMINI_API_KEY configurata (né personale né di sistema)', 403, None

        models = models or GEMINI_MODELS
        last_status, last_text = -1, ''
        for model in models:
            url = f"{GEMINI_API_BASE}/{model}:generateContent?key={key}"
            try:
                resp = requests.post(url, json=payload, timeout=timeout)
            except requests.exceptions.Timeout:
                last_status, last_text = 0, 'timeout'
                break
            except Exception as e:
                last_status, last_text = -1, str(e)
                break

            if resp.status_code == 200:
                try:
                    return True, resp.json(), 200, model
                except ValueError:
                    last_status, last_text = -1, 'Risposta Gemini non JSON'
                    break

            last_status, last_text = resp.status_code, resp.text
            # 429 (rate limit / quota modello), o problemi infrastrutturali:
            # prova il modello successivo. Su errori client (400/401/403)
            # cambiare modello non aiuta → esci.
            if resp.status_code in (429, 404, 502, 503):
                continue
            break

        return False, last_text, last_status, None

    def generate_with_image(self, text_prompt, image_data_base64, mime_type='image/jpeg',
                            system_prompt=None, temperature=0.3, api_key=None):
        """
        Genera una risposta con un'immagine (Gemini Vision).
        Ritorna (response_text, model_used) o lancia Exception.
        """
        contents = [{
            'role': 'user',
            'parts': [
                {'text': text_prompt},
                {'inlineData': {'mimeType': mime_type, 'data': image_data_base64}},
            ]
        }]
        payload = {
            'contents': contents,
            'generationConfig': {'temperature': temperature,
                                 'maxOutputTokens': 2000 + THINKING_HEADROOM_TOKENS},
        }
        if system_prompt:
            payload['systemInstruction'] = {'parts': [{'text': system_prompt}]}

        last_error = None
        for model in GEMINI_VISION_MODELS:
            success, text, status = self._call_model(model, payload, timeout=40, api_key=api_key)
            if success:
                return text, model
            elif status == 429:
                last_error = f"Rate limit su {model}"
                continue
            elif status in (0, -1):
                last_error = f"Errore di rete su {model}: {text}"
                break
            else:
                last_error = f"Errore {status} su {model}"
                continue

        raise Exception(f"Tutti i modelli Vision hanno fallito. Ultimo errore: {last_error}")


# Singleton globale
gemini_service = GeminiService()


# ---------------------------------------------------------------------------
# Quota tracking — condiviso tra api_views.py e ai_views.py
# ---------------------------------------------------------------------------

AI_DAILY_LIMIT = 1500  # Gemini free-tier daily limit (chiave di sistema)


def _next_midnight_utc():
    now = timezone.now()
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


_COUNTER_FIELDS = [
    'ai_requests_today', 'ai_chat_today', 'ai_voice_today',
    'ai_stats_today', 'ai_proxy_calls_today', 'ai_requests_reset_at',
]


def _reset_if_needed(profilo, now):
    """Azzera i contatori se è passata la mezzanotte."""
    if profilo.ai_requests_reset_at is None or profilo.ai_requests_reset_at <= now:
        profilo.ai_requests_today = 0
        profilo.ai_chat_today = 0
        profilo.ai_voice_today = 0
        profilo.ai_stats_today = 0
        profilo.ai_proxy_calls_today = 0
        profilo.ai_requests_reset_at = _next_midnight_utc()


def _tier_limits(profilo):
    from .models import AI_TIER_LIMITS, AI_TIER_FREE
    tier = (profilo.ai_tier if profilo else None) or AI_TIER_FREE
    return tier, AI_TIER_LIMITS.get(tier, AI_TIER_LIMITS[AI_TIER_FREE])


def _system_quota_exhausted(now):
    try:
        from .models import SystemAiQuota
        quota = SystemAiQuota.objects.get(pk=1)
        return bool(quota.reset_at and quota.reset_at > now
                    and quota.requests_today >= AI_DAILY_LIMIT)
    except Exception:
        return False


def check_ai_quota(user, call_type='chat'):
    """Verifica se l'utente ha quota disponibile.

    call_type: 'chat' o 'voice'
    Ritorna (allowed: bool, error_msg: str|None, tier_limits: dict).

    Con una chiave Gemini personale i limiti del tier NON si applicano:
    l'utente paga Google direttamente e la chiave condivisa non viene toccata
    (tutti i percorsi server usano la chiave personale quando è impostata,
    quindi impostarne una fasulla non dà accesso a quella di sistema).
    """
    from .models import AI_TIER_LIMITS, AI_TIER_FREE

    # Legge dal DB e non da user.profilo: quest'ultimo resta in cache
    # sull'istanza e mostrerebbe contatori vecchi.
    from .models import Profilo
    try:
        profilo = Profilo.objects.get(utente=user)
    except Exception:
        return True, None, AI_TIER_LIMITS[AI_TIER_FREE]

    tier, limits = _tier_limits(profilo)
    now = timezone.now()

    if profilo.gemini_api_key:
        return True, None, limits

    # Contatori scaduti → valgono zero (li azzera il prossimo incremento).
    expired = profilo.ai_requests_reset_at is None or profilo.ai_requests_reset_at <= now
    chat_today = 0 if expired else profilo.ai_chat_today
    voice_today = 0 if expired else profilo.ai_voice_today
    total_today = 0 if expired else profilo.ai_requests_today

    # Controlla limite specifico per tipo
    if call_type == 'chat' and chat_today >= limits['chat']:
        return False, f'Limite chat giornaliero raggiunto ({limits["chat"]}/{limits["chat"]}). ' \
                       f'Piano attuale: {tier}.', limits
    if call_type == 'voice' and voice_today >= limits['voice']:
        return False, f'Limite voice giornaliero raggiunto ({limits["voice"]}/{limits["voice"]}). ' \
                       f'Piano attuale: {tier}.', limits

    # Controlla limite totale
    if total_today >= limits['total']:
        return False, f'Limite totale giornaliero raggiunto ({limits["total"]}/{limits["total"]}). ' \
                       f'Piano attuale: {tier}.', limits

    # Usa la chiave di sistema: controlla anche la quota globale
    if _system_quota_exhausted(now):
        return False, 'Quota di sistema esaurita per oggi. ' \
                      'Inserisci una chiave Gemini personale nelle impostazioni.', limits

    return True, None, limits


def _increment_system_quota(now):
    from .models import SystemAiQuota
    with transaction.atomic():
        quota, created = SystemAiQuota.objects.select_for_update().get_or_create(pk=1)
        if quota.reset_at is None or quota.reset_at <= now:
            quota.requests_today = 1
            quota.reset_at = _next_midnight_utc()
        else:
            quota.requests_today += 1
        quota.save(update_fields=['requests_today', 'reset_at'])


def increment_ai_quota(user, used_personal_key: bool, call_type='chat'):
    """Incrementa il contatore giornaliero richieste AI.
    Non lancia mai eccezioni — il tracking non deve bloccare la risposta.
    Usa select_for_update per evitare race condition.

    I contatori misurano SOLO l'uso della chiave condivisa: le chiamate fatte
    con la chiave personale non consumano il tier e non vengono contate."""
    if used_personal_key:
        return
    try:
        now = timezone.now()

        with transaction.atomic():
            from .models import Profilo
            profilo = Profilo.objects.select_for_update().get(utente=user)
            _reset_if_needed(profilo, now)
            profilo.ai_requests_today += 1
            if call_type == 'chat':
                profilo.ai_chat_today += 1
            elif call_type == 'voice':
                profilo.ai_voice_today += 1
            profilo.save(update_fields=_COUNTER_FIELDS)

        _increment_system_quota(now)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Proxy Gemini — il conteggio avviene QUI, lato server
# ---------------------------------------------------------------------------

def reserve_proxy_call(user, call_type='chat'):
    """Gate atomico per una chiamata al proxy Gemini con la chiave condivisa.

    Oltre ai limiti del tier (check_ai_quota) prenota una chiamata grezza sul
    tetto giornaliero `total * AI_PROXY_CALLS_PER_UNIT`. La prenotazione è
    atomica e avviene PRIMA di contattare Gemini, quindi richieste parallele
    non possono superare il tetto.

    Ritorna (allowed, error_msg, tier_limits).
    """
    from .models import Profilo, AI_PROXY_CALLS_PER_UNIT

    allowed, error, limits = check_ai_quota(user, call_type=call_type)
    if not allowed:
        return allowed, error, limits

    now = timezone.now()
    with transaction.atomic():
        try:
            profilo = Profilo.objects.select_for_update().get(utente=user)
        except Profilo.DoesNotExist:
            profilo = Profilo.objects.create(utente=user)
        if profilo.gemini_api_key:
            return True, None, limits
        _reset_if_needed(profilo, now)
        cap = limits['total'] * AI_PROXY_CALLS_PER_UNIT
        if profilo.ai_proxy_calls_today >= cap:
            return False, 'Troppe richieste AI per oggi. Riprova dopo il reset giornaliero.', limits
        profilo.ai_proxy_calls_today += 1
        profilo.save(update_fields=_COUNTER_FIELDS)
    return True, None, limits


def gemini_response_has_function_call(data):
    """True se la risposta Gemini chiede al client di eseguire dei tool
    (giro intermedio del function calling, non una risposta finale)."""
    try:
        for candidate in data.get('candidates') or []:
            for part in (candidate.get('content') or {}).get('parts') or []:
                if isinstance(part, dict) and ('functionCall' in part or 'function_call' in part):
                    return True
    except AttributeError:
        pass
    return False


def record_proxy_success(user, call_type, data):
    """Contabilizza una chiamata al proxy andata a buon fine con la chiave
    condivisa. La risposta finale consuma un'unità di quota chat/voice; i giri
    intermedi di function calling contano solo sulla quota di sistema (e sul
    tetto grezzo già prenotato da reserve_proxy_call)."""
    if gemini_response_has_function_call(data):
        try:
            _increment_system_quota(timezone.now())
        except Exception:
            pass
        return
    increment_ai_quota(user, used_personal_key=False, call_type=call_type)


# ---------------------------------------------------------------------------
# Statistiche in linguaggio naturale (Groq)
# ---------------------------------------------------------------------------

def check_stats_quota(user):
    """Ritorna (allowed, error_msg, tier_limits) per le domande AI nelle
    statistiche fatte con la chiave Groq di sistema."""
    from .models import AI_TIER_LIMITS, AI_TIER_FREE
    # Legge dal DB e non da user.profilo: quest'ultimo resta in cache
    # sull'istanza e mostrerebbe contatori vecchi.
    from .models import Profilo
    try:
        profilo = Profilo.objects.get(utente=user)
    except Exception:
        return True, None, AI_TIER_LIMITS[AI_TIER_FREE]
    tier, limits = _tier_limits(profilo)
    now = timezone.now()
    expired = profilo.ai_requests_reset_at is None or profilo.ai_requests_reset_at <= now
    used = 0 if expired else profilo.ai_stats_today
    if used >= limits['stats']:
        return False, f'Limite giornaliero domande AI raggiunto ({limits["stats"]}/{limits["stats"]}). ' \
                      f'Riprova dopo il reset o configura una chiave Groq personale.', limits
    return True, None, limits


def increment_stats_quota(user):
    """Incrementa il contatore stats e ritorna il nuovo valore (None su errore)."""
    try:
        now = timezone.now()
        with transaction.atomic():
            from .models import Profilo
            profilo = Profilo.objects.select_for_update().get(utente=user)
            _reset_if_needed(profilo, now)
            profilo.ai_stats_today += 1
            profilo.save(update_fields=_COUNTER_FIELDS)
            return profilo.ai_stats_today
    except Exception:
        return None
