"""
Viste AI: chat, elaborazione voce, analisi telaino (Gemini + YOLO segmentation).
"""
import json
import base64
import os
import io

from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.conf import settings

from datetime import date

from .ai_services import gemini_service
from .models import Apiario, Arnia, ControlloArnia

# Cache del modello YOLO (caricato una volta sola alla prima richiesta)
_yolo_model = None

def _get_yolo_model():
    """Carica e cachea il modello YOLO segmentazione."""
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    yolo_path = getattr(settings, 'YOLO_MODEL_PATH', '')
    if not yolo_path or not os.path.exists(yolo_path):
        return None
    try:
        from ultralytics import YOLO
        _yolo_model = YOLO(yolo_path)
        return _yolo_model
    except Exception:
        return None


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

        # --- YOLO segmentazione ---
        yolo_result = None
        yolo_model = _get_yolo_model()
        if yolo_model is not None:
            try:
                from PIL import Image as PILImage
                import numpy as np

                # Apri immagine
                img = PILImage.open(io.BytesIO(image_data)).convert('RGB')

                # Predizione con stessi parametri dello script di test
                results = yolo_model.predict(
                    source=img,
                    conf=0.5,
                    iou=0.4,
                    verbose=False,
                )
                r = results[0]

                # Conta detection per classe
                detections = []
                if r.boxes is not None:
                    for box in r.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = r.names.get(cls_id, str(cls_id))
                        conf_val = float(box.conf[0])
                        detections.append({'class': cls_name, 'confidence': round(conf_val, 2)})

                class_counts = {}
                for d in detections:
                    class_counts[d['class']] = class_counts.get(d['class'], 0) + 1

                # Genera immagine annotata con maschere disegnate
                annotated_bgr = r.plot()          # numpy array BGR (da ultralytics)
                annotated_rgb = annotated_bgr[:, :, ::-1]  # BGR → RGB
                annotated_pil = PILImage.fromarray(annotated_rgb.astype('uint8'))
                buf = io.BytesIO()
                annotated_pil.save(buf, format='JPEG', quality=88)
                annotated_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

                yolo_result = {
                    'detections': detections[:80],
                    'summary': class_counts,
                    'annotated_image': annotated_b64,  # JPEG base64
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


# ---------------------------------------------------------------------------
# Controllo Vocale — pagina dedicata
# ---------------------------------------------------------------------------
@login_required
def voice_controllo_page(request):
    """Pagina batch inserimento vocale controlli."""
    apiari = list(
        Apiario.objects.filter(proprietario=request.user).order_by('nome').values('id', 'nome')
    )
    return render(request, 'ai/controllo_vocale.html', {'apiari': apiari})


# ---------------------------------------------------------------------------
# Processa trascrizione → JSON strutturato (stesso prompt dell'app Flutter)
# ---------------------------------------------------------------------------
@login_required
@require_POST
def voice_process(request):
    """
    Riceve una trascrizione vocale + apiario_id.
    Chiama Gemini con il prompt identico all'app Flutter.
    Ritorna JSON con i campi del controllo arnia.
    """
    try:
        data = json.loads(request.body)
        transcript = data.get('transcript', '').strip()
        apiario_id = data.get('apiario_id')

        if not transcript:
            return JsonResponse({'error': 'Trascrizione vuota'}, status=400)

        # Context sessione (come nell'app)
        context_info = "Nessun apiario selezionato come contesto sessione."
        if apiario_id:
            apiario = Apiario.objects.filter(id=apiario_id, proprietario=request.user).first()
            if apiario:
                context_info = (
                    f'Contesto sessione: apiario "{apiario.nome}" (ID: {apiario.id}). '
                    f"L'utente parlerà solo del numero arnia, non ripeterà il nome dell'apiario."
                )

        # Prompt identico all'app Flutter
        prompt = f"""Sei un assistente per apicoltori. Estrai dati strutturati da una trascrizione vocale.

{context_info}

Trascrizione: "{transcript}"

Rispondi SOLO con un oggetto JSON valido (nessun testo aggiuntivo, nessun markdown) con questi campi:
{{
  "arnia_numero": <intero o null>,
  "presenza_regina": <true/false o null>,
  "uova_fresche": <true/false o null>,
  "celle_reali": <true/false o null>,
  "numero_celle_reali": <intero o null>,
  "telaini_totali": <intero o null>,
  "telaini_covata": <intero o null>,
  "telaini_scorte": <intero o null>,
  "forza_famiglia": <"debole"/"normale"/"forte" o null>,
  "sciamatura": <true/false o null>,
  "problemi_sanitari": <true/false o null>,
  "tipo_problema": <stringa o null>,
  "note": <stringa con osservazioni libere o null>
}}

Regole:
- Se viene menzionato "arnia N", arnia_numero = N
- "famiglia forte/normale/debole" → forza_famiglia
- "presenza regina" o "regina presente" → presenza_regina = true
- "regina assente" → presenza_regina = false
- "celle reali" → celle_reali = true; se viene dato un numero, numero_celle_reali
- "sciamatura" o "rischio sciamatura" → sciamatura = true
- "problemi sanitari", "varroa", "nosema", "covata calcificata" → problemi_sanitari = true + tipo_problema
- Le osservazioni non strutturate vanno in note"""

        response_text, model_used = gemini_service.generate(
            [{'role': 'user', 'text': prompt}],
            temperature=0, max_tokens=400
        )

        # Pulisci e parsa JSON
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            parts = cleaned.split('```')
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.startswith('json'):
                cleaned = cleaned[4:]
        result = json.loads(cleaned.strip())
        result['_model'] = model_used
        result['_transcript'] = transcript
        return JsonResponse(result)

    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Risposta Gemini non valida: {e}', '_transcript': transcript}, status=500)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Salva batch di controlli
# ---------------------------------------------------------------------------
@login_required
@require_POST
def voice_save(request):
    """
    Riceve un array di voci estratte e le salva come ControlloArnia.
    Formato input: { apiario_id: int, entries: [{arnia_numero, presenza_regina, ...}] }
    """
    try:
        data = json.loads(request.body)
        apiario_id = data.get('apiario_id')
        entries = data.get('entries', [])

        if not apiario_id or not entries:
            return JsonResponse({'error': 'Dati mancanti'}, status=400)

        apiario = Apiario.objects.filter(id=apiario_id, proprietario=request.user).first()
        if not apiario:
            return JsonResponse({'error': 'Apiario non trovato'}, status=404)

        results = []
        for entry in entries:
            arnia_numero = entry.get('arnia_numero')
            if not arnia_numero:
                results.append({'arnia': arnia_numero, 'success': False, 'error': 'Numero arnia mancante'})
                continue

            arnia = Arnia.objects.filter(apiario=apiario, numero=arnia_numero).first()
            if not arnia:
                results.append({'arnia': arnia_numero, 'success': False,
                                 'error': f'Arnia #{arnia_numero} non trovata in "{apiario.nome}"'})
                continue

            try:
                presenza = entry.get('presenza_regina')
                if presenza is None:
                    presenza = True

                note_parts = []
                if entry.get('forza_famiglia'):
                    note_parts.append(f"Forza famiglia: {entry['forza_famiglia']}")
                if entry.get('uova_fresche') is True:
                    note_parts.append("Uova fresche presenti")
                if entry.get('celle_reali') is True:
                    n = entry.get('numero_celle_reali', '')
                    note_parts.append(f"Celle reali presenti{(' (' + str(n) + ')') if n else ''}")
                if entry.get('note'):
                    note_parts.append(entry['note'])

                controllo = ControlloArnia(
                    arnia=arnia,
                    utente=request.user,
                    data=date.today(),
                    telaini_scorte=int(entry.get('telaini_scorte') or 0),
                    telaini_covata=int(entry.get('telaini_covata') or 0),
                    presenza_regina=presenza,
                    sciamatura=bool(entry.get('sciamatura')),
                    note_sciamatura=entry.get('note_sciamatura') or '',
                    problemi_sanitari=bool(entry.get('problemi_sanitari')),
                    note_problemi=entry.get('tipo_problema') or '',
                    note='\n'.join(note_parts) if note_parts else '',
                )
                controllo.save()
                results.append({'arnia': arnia_numero, 'success': True,
                                 'id': controllo.id, 'arnia_id': arnia.id})
            except Exception as e:
                results.append({'arnia': arnia_numero, 'success': False, 'error': str(e)})

        saved = sum(1 for r in results if r['success'])
        return JsonResponse({'results': results, 'saved': saved, 'total': len(entries)})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
