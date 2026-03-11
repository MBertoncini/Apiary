"""
Servizio Gemini con rotazione automatica dei modelli.
Mimics the model rotation strategy from the Flutter Apiary app.
"""
import json
import base64
import requests
from django.conf import settings

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
                text = data['candidates'][0]['content']['parts'][0]['text']
                return True, text, 200
            else:
                return False, resp.text, resp.status_code
        except requests.exceptions.Timeout:
            return False, 'timeout', 0
        except Exception as e:
            return False, str(e), -1

    def _build_payload(self, messages, system_prompt=None, temperature=0.7, max_tokens=1024):
        contents = []
        for msg in messages:
            if 'parts' in msg:
                contents.append({'role': msg['role'], 'parts': msg['parts']})
            else:
                contents.append({'role': msg['role'], 'parts': [{'text': msg['text']}]})

        payload = {
            'contents': contents,
            'generationConfig': {
                'temperature': temperature,
                'maxOutputTokens': max_tokens,
            },
        }
        if system_prompt:
            payload['systemInstruction'] = {'parts': [{'text': system_prompt}]}
        return payload

    def generate(self, messages, system_prompt=None, temperature=0.7, max_tokens=1024, api_key=None):
        """
        Genera una risposta con rotazione automatica dei modelli.
        Ritorna (response_text, model_used) o lancia Exception.
        """
        payload = self._build_payload(messages, system_prompt, temperature, max_tokens)
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
