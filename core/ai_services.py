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
GEMINI_MODELS = [
    'gemini-2.5-flash',        # migliore qualità
    'gemini-2.0-flash',        # ottimo bilanciamento
    'gemini-2.0-flash-lite',   # veloce ed economico
    'gemini-1.5-flash',        # stabile fallback
    'gemini-1.5-flash-8b',     # ultimo fallback
]

# Modelli con supporto Vision (immagini)
GEMINI_VISION_MODELS = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash',
]


class GeminiService:
    @property
    def api_key(self):
        return getattr(settings, 'GEMINI_API_KEY', '')

    def _call_model(self, model, payload, timeout=20, api_key=None):
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
                text = parts[0].get('text', '')
                if not text:
                    return False, f'Testo risposta vuoto (finishReason={finish_reason})', -1
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
            'maxOutputTokens': max_tokens,
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
            'generationConfig': {'temperature': temperature, 'maxOutputTokens': 2000},
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


def _reset_if_needed(profilo, now):
    """Azzera i contatori se è passata la mezzanotte."""
    if profilo.ai_requests_reset_at is None or profilo.ai_requests_reset_at <= now:
        profilo.ai_requests_today = 0
        profilo.ai_chat_today = 0
        profilo.ai_voice_today = 0
        profilo.ai_requests_reset_at = _next_midnight_utc()


def check_ai_quota(user, call_type='chat'):
    """Verifica se l'utente ha quota disponibile.

    call_type: 'chat' o 'voice'
    Ritorna (allowed: bool, error_msg: str|None, tier_limits: dict).
    Se l'utente ha chiave personale e tier != free, i limiti per-tier si applicano
    comunque per evitare abusi (ma sono molto più alti).
    Se l'utente ha chiave personale senza tier a pagamento, si applicano i limiti free.
    """
    from .models import AI_TIER_LIMITS, AI_TIER_FREE

    try:
        profilo = user.profilo
    except Exception:
        return True, None, AI_TIER_LIMITS[AI_TIER_FREE]

    tier = profilo.ai_tier or AI_TIER_FREE
    limits = AI_TIER_LIMITS.get(tier, AI_TIER_LIMITS[AI_TIER_FREE])
    now = timezone.now()

    # Reset contatori se necessario (senza salvare — lo fa increment_ai_quota)
    if profilo.ai_requests_reset_at is None or profilo.ai_requests_reset_at <= now:
        # Contatori scaduti → sicuramente ha quota
        return True, None, limits

    # Chiave personale: bypass del limite di sistema, ma i limiti per-tier restano
    has_personal_key = bool(profilo.gemini_api_key)

    # Controlla limite specifico per tipo
    if call_type == 'chat' and profilo.ai_chat_today >= limits['chat']:
        return False, f'Limite chat giornaliero raggiunto ({limits["chat"]}/{limits["chat"]}). ' \
                       f'Piano attuale: {tier}.', limits
    if call_type == 'voice' and profilo.ai_voice_today >= limits['voice']:
        return False, f'Limite voice giornaliero raggiunto ({limits["voice"]}/{limits["voice"]}). ' \
                       f'Piano attuale: {tier}.', limits

    # Controlla limite totale
    if profilo.ai_requests_today >= limits['total']:
        return False, f'Limite totale giornaliero raggiunto ({limits["total"]}/{limits["total"]}). ' \
                       f'Piano attuale: {tier}.', limits

    # Se usa chiave di sistema, controlla anche la quota globale
    if not has_personal_key:
        try:
            from .models import SystemAiQuota
            quota = SystemAiQuota.objects.get(pk=1)
            if quota.reset_at and quota.reset_at > now and quota.requests_today >= AI_DAILY_LIMIT:
                return False, 'Quota di sistema esaurita per oggi. ' \
                              'Inserisci una chiave Gemini personale nelle impostazioni.', limits
        except Exception:
            pass

    return True, None, limits


def increment_ai_quota(user, used_personal_key: bool, call_type='chat'):
    """Incrementa il contatore giornaliero richieste AI.
    Non lancia mai eccezioni — il tracking non deve bloccare la risposta.
    Usa select_for_update per evitare race condition."""
    try:
        now = timezone.now()

        # Aggiorna contatori per-utente (sempre, indipendentemente dalla chiave)
        with transaction.atomic():
            from .models import Profilo
            profilo = Profilo.objects.select_for_update().get(utente=user)
            _reset_if_needed(profilo, now)
            profilo.ai_requests_today += 1
            if call_type == 'chat':
                profilo.ai_chat_today += 1
            elif call_type == 'voice':
                profilo.ai_voice_today += 1
            profilo.save(update_fields=[
                'ai_requests_today', 'ai_chat_today', 'ai_voice_today',
                'ai_requests_reset_at',
            ])

        # Aggiorna anche quota di sistema se usa la chiave condivisa
        if not used_personal_key:
            from .models import SystemAiQuota
            with transaction.atomic():
                quota, created = SystemAiQuota.objects.select_for_update().get_or_create(pk=1)
                if quota.reset_at is None or quota.reset_at <= now:
                    quota.requests_today = 1
                    quota.reset_at = _next_midnight_utc()
                else:
                    quota.requests_today += 1
                quota.save(update_fields=['requests_today', 'reset_at'])
    except Exception:
        pass
