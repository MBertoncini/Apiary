"""
Viste AI: chat, elaborazione voce, analisi telaino (Gemini + YOLO).
"""
import json
import base64
import os

from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings

from .ai_services import gemini_service
from .models import Apiario, Arnia


# ---------------------------------------------------------------------------
# Prompt di sistema per il chat AI
# ---------------------------------------------------------------------------
BEE_SYSTEM_PROMPT = """Sei ApiarioAI, un assistente esperto in apicoltura integrato nell'app Apiary.
Rispondi SEMPRE in italiano, in modo conciso e pratico.
Puoi aiutare con: gestione arnie, controlli sanitari, trattamenti varroa, produzione miele,
identificazione problemi (nosema, covata calcificata, favi saccheggiati, ecc.),
gestione calendario, regine e nuclei.
Non usare markdown (niente **, ##, liste con trattini). Scrivi in testo semplice.
Sii diretto come un apicoltore esperto che risponde a un collega."""


def _build_user_context(user):
    """Costruisce il contesto dati apiario dell'utente per il prompt."""
    try:
        apiari = list(Apiario.objects.filter(proprietario=user).values('id', 'nome')[:8])
        total_arnie = Arnia.objects.filter(apiario__proprietario=user).count()
        if not apiari:
            return ""
        nomi = ", ".join(a['nome'] for a in apiari)
        return f"Gestisce {len(apiari)} apiari ({nomi}) con {total_arnie} arnie totali."
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Chat AI
# ---------------------------------------------------------------------------
@login_required
@require_POST
def chat_ai(request):
    """Endpoint POST: riceve messaggio + cronologia, ritorna risposta AI."""
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        history = data.get('history', [])  # [{role: 'user'|'model', text: '...'}]

        if not message:
            return JsonResponse({'error': 'Messaggio vuoto'}, status=400)

        # System prompt arricchito con contesto utente
        user_ctx = _build_user_context(request.user)
        system = BEE_SYSTEM_PROMPT
        if user_ctx:
            system += f"\n\nDati utente: {user_ctx}"

        # Costruisci messaggi (ultimi 12 per gestire la finestra di contesto)
        messages = []
        for h in history[-12:]:
            role = h.get('role', 'user')
            text = h.get('text', '')
            if role in ('user', 'model') and text:
                messages.append({'role': role, 'text': text})
        messages.append({'role': 'user', 'text': message})

        response_text, model_used = gemini_service.generate(
            messages, system_prompt=system, temperature=0.7, max_tokens=800
        )
        return JsonResponse({'response': response_text, 'model': model_used})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Voce AI
# ---------------------------------------------------------------------------
@login_required
@require_POST
def voice_ai(request):
    """
    Processa una trascrizione vocale (da Web Speech API).
    Ritorna JSON strutturato con azione, dati estratti e risposta testuale.
    """
    try:
        data = json.loads(request.body)
        transcript = data.get('transcript', '').strip()
        context = data.get('context', '')  # contesto pagina (es. nome apiario corrente)

        if not transcript:
            return JsonResponse({'error': 'Trascrizione vuota'}, status=400)

        context_line = f"\nContesto pagina: {context}" if context else ""

        prompt = f"""Sei un assistente per l'inserimento dati in un'app di apicoltura.
L'utente ha parlato (trascrizione): "{transcript}"{context_line}

Analizza cosa vuole fare e rispondi con un JSON con questi campi:
- "azione": stringa tra ("nuovo_controllo", "nuova_arnia", "info_apiario", "naviga", "chat")
- "dati": oggetto con i dati estratti (vedi campi per azione)
- "risposta": risposta breve in italiano da mostrare all'utente (max 120 caratteri)
- "navigare": URL relativo opzionale (es. "/app/arnia/3/controllo/")

Campi dati per nuovo_controllo: arnia_numero (int), presenza_regina (bool), uova_fresche (bool),
  covata_opercolata (bool), telaini_covata (int), telaini_scorte (int), problemi (string)
Campi dati per chat: (vuoto, usa solo "risposta")

Rispondi SOLO con il JSON grezzo, senza markdown."""

        response_text, model_used = gemini_service.generate(
            [{'role': 'user', 'text': prompt}],
            temperature=0.1, max_tokens=500
        )

        # Pulisci e parsa il JSON
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            parts = cleaned.split('```')
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith('json'):
                cleaned = cleaned[4:]
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            result = {'azione': 'chat', 'risposta': response_text[:200], 'dati': {}}

        result['model'] = model_used
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Analisi Telaino (Vision + YOLO)
# ---------------------------------------------------------------------------
@login_required
def analisi_telaino(request):
    """Pagina analisi telaino con upload foto."""
    if request.method == 'GET':
        return render(request, 'ai/analisi_telaino.html')

    # POST: analizza l'immagine
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'Nessuna immagine caricata'}, status=400)

    try:
        image_file = request.FILES['image']
        image_data = image_file.read()
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        content_type = image_file.content_type or 'image/jpeg'

        # --- YOLO (opzionale) ---
        yolo_result = None
        yolo_model_path = getattr(settings, 'YOLO_MODEL_PATH', '')
        if yolo_model_path and os.path.exists(yolo_model_path):
            try:
                from ultralytics import YOLO
                import io
                from PIL import Image as PILImage

                yolo_model = YOLO(yolo_model_path)
                img = PILImage.open(io.BytesIO(image_data))
                results = yolo_model(img, verbose=False)

                detections = []
                for r in results:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = r.names.get(cls_id, str(cls_id))
                        conf = float(box.conf[0])
                        detections.append({'class': cls_name, 'confidence': round(conf, 2)})

                class_counts = {}
                for d in detections:
                    class_counts[d['class']] = class_counts.get(d['class'], 0) + 1

                yolo_result = {
                    'detections': detections[:60],
                    'summary': class_counts,
                }
            except ImportError:
                yolo_result = {'nota': 'ultralytics non installato'}
            except Exception as e:
                yolo_result = {'error': str(e)}

        # --- Gemini Vision ---
        yolo_ctx = ""
        if yolo_result and 'summary' in yolo_result and yolo_result['summary']:
            counts_str = ", ".join(f"{k}: {v}" for k, v in yolo_result['summary'].items())
            yolo_ctx = f"\nIl modello di segmentazione ha rilevato: {counts_str}."

        vision_prompt = f"""Sei un apicoltore esperto. Analizza attentamente questa foto di telaino/favo.{yolo_ctx}

Fornisci un'analisi strutturata in italiano con questi punti:
1. PRESENZA REGINA: sì / no / probabile — motivazione breve
2. UOVA E COVATA: presenza uova, larve aperte, covata opercolata, qualità del pattern
3. SCORTE: miele opercolato, polline, posizione e abbondanza stimata
4. STATO SANITARIO: varroa visibile, covata calcificata, saccheggio, altri problemi
5. CONSIGLIO PRATICO: una o due azioni raccomandate

Scrivi in testo semplice, senza markdown, conciso e diretto."""

        analysis_text, model_used = gemini_service.generate_with_image(
            vision_prompt, image_b64, mime_type=content_type
        )

        return JsonResponse({
            'analysis': analysis_text,
            'model': model_used,
            'yolo': yolo_result,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
