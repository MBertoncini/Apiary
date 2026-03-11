"""
Viste AI: chat, elaborazione voce, analisi telaino (ONNX bee detection locale).
"""
import json
import re
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

# ---------------------------------------------------------------------------
# ONNX bee detector — modello YOLOv8-seg esportato da best.pt
# Stessa logica di parsing di bee_detection_service.dart (Flutter)
# ---------------------------------------------------------------------------

_CLASS_NAMES = ['bees', 'drone', 'queenbees', 'royal cell']
_CLASS_COLORS = [
    (255, 165,   0),   # bees      → arancione
    (  0, 120, 255),   # drone     → blu
    (160,   0, 220),   # queenbees → viola
    (220, 180,   0),   # royal cell → ambra
]
_INPUT_SIZE     = 640
_CONF_THRESHOLD = 0.25
_IOU_THRESHOLD  = 0.45

# Cache sessione ONNX
_onnx_session    = None
_onnx_load_error = None


def _get_onnx_session():
    """Carica e cachea la sessione ONNX Runtime. Ritorna (session, error_str)."""
    global _onnx_session, _onnx_load_error
    if _onnx_session is not None:
        return _onnx_session, None
    if _onnx_load_error is not None:
        return None, _onnx_load_error

    model_path = getattr(settings, 'ONNX_MODEL_PATH', '')
    if not model_path or not os.path.exists(model_path):
        _onnx_load_error = f'Modello ONNX non trovato: {model_path}'
        return None, _onnx_load_error
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        _onnx_session = sess
        return sess, None
    except ImportError:
        _onnx_load_error = 'onnxruntime non installato (pip install onnxruntime)'
        return None, _onnx_load_error
    except Exception as e:
        _onnx_load_error = str(e)
        return None, _onnx_load_error


def _letterbox_chw(pil_img, target=640):
    """
    Letterbox + resize a target×target.
    Ritorna tensor float32 [1,3,H,W] (CHW, valori 0-1) + parametri di rescale.
    """
    import numpy as np
    orig_w, orig_h = pil_img.size
    scale  = min(target / orig_w, target / orig_h)
    new_w  = round(orig_w * scale)
    new_h  = round(orig_h * scale)

    from PIL import Image as PILImage
    resized = pil_img.resize((new_w, new_h), PILImage.BILINEAR)

    pad_x = (target - new_w) / 2.0
    pad_y = (target - new_h) / 2.0
    px, py = round(pad_x), round(pad_y)

    canvas = np.full((target, target, 3), 114, dtype=np.float32)
    canvas[py:py + new_h, px:px + new_w] = np.array(resized, dtype=np.float32)
    canvas /= 255.0

    # HWC → CHW → batch
    tensor = canvas.transpose(2, 0, 1)[np.newaxis]   # [1, 3, H, W]
    return tensor, scale, pad_x, pad_y


def _iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1])
    x2 = min(a[2], b[2]); y2 = min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0


def _nms(detections, iou_thr):
    detections.sort(key=lambda d: d['confidence'], reverse=True)
    kept = []
    suppressed = [False] * len(detections)
    for i, di in enumerate(detections):
        if suppressed[i]:
            continue
        kept.append(di)
        for j in range(i + 1, len(detections)):
            if suppressed[j] or detections[j]['class_idx'] != di['class_idx']:
                continue
            if _iou(di['bbox'], detections[j]['bbox']) > iou_thr:
                suppressed[j] = True
    return kept


def _run_detection(image_data_bytes):
    """
    Bee detection con ONNX Runtime.
    Output YOLOv8-seg: [1, 4+num_cls+32, 8400] — usiamo solo bbox+cls.
    Ritorna dict con: detections, summary, avg_confidence, annotated_image (base64 JPEG).
    """
    import numpy as np
    from PIL import Image as PILImage, ImageDraw, ImageFont

    sess, err = _get_onnx_session()
    if err:
        return {'error': err}

    pil_img = PILImage.open(io.BytesIO(image_data_bytes)).convert('RGB')
    tensor, scale, pad_x, pad_y = _letterbox_chw(pil_img, _INPUT_SIZE)

    input_name = sess.get_inputs()[0].name
    outputs    = sess.run(None, {input_name: tensor})
    # output[0]: [1, features, detections]  features = 4bbox + num_cls + 32masks
    out = outputs[0][0]   # [features, detections]

    num_cls = len(_CLASS_NAMES)
    _, num_det = out.shape   # features × detections

    raw = []
    for d in range(num_det):
        cls_scores = out[4:4 + num_cls, d]
        best_cls   = int(cls_scores.argmax())
        max_conf   = float(cls_scores[best_cls])
        if max_conf < _CONF_THRESHOLD:
            continue

        cx, cy, w, h = float(out[0,d]), float(out[1,d]), float(out[2,d]), float(out[3,d])
        x1 = (cx - w/2 - pad_x) / scale
        y1 = (cy - h/2 - pad_y) / scale
        x2 = (cx + w/2 - pad_x) / scale
        y2 = (cy + h/2 - pad_y) / scale

        raw.append({
            'class_idx':  best_cls,
            'class':      _CLASS_NAMES[best_cls],
            'confidence': round(max_conf, 3),
            'bbox':       [x1, y1, x2, y2],
        })

    filtered   = _nms(raw, _IOU_THRESHOLD)
    summary    = {n: 0 for n in _CLASS_NAMES}
    total_conf = 0.0
    for det in filtered:
        summary[det['class']] += 1
        total_conf += det['confidence']
    avg_conf = total_conf / len(filtered) if filtered else 0.0

    # Bounding box annotati con PIL
    draw = ImageDraw.Draw(pil_img)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    for det in filtered:
        x1, y1, x2, y2 = det['bbox']
        color = _CLASS_COLORS[det['class_idx']]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
        label = f"{det['class']} {det['confidence']*100:.0f}%"
        lw = len(label) * 7
        draw.rectangle([x1, y1 - 14, x1 + lw, y1], fill=color)
        draw.text((x1 + 2, y1 - 14), label, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    pil_img.save(buf, format='JPEG', quality=88)

    return {
        'detections':      [{'class': d['class'], 'confidence': d['confidence']} for d in filtered],
        'summary':         summary,
        'avg_confidence':  round(avg_conf, 3),
        'annotated_image': base64.b64encode(buf.getvalue()).decode('utf-8'),
    }


# ---------------------------------------------------------------------------
# Prompt di sistema per il chat AI
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    """
    Estrae il primo oggetto JSON valido da una stringa, gestendo markdown,
    commenti JS e testo extra restituito da Gemini.
    """
    s = text.strip()

    # Rimuovi blocco markdown ```json ... ``` o ``` ... ```
    s = re.sub(r'^```(?:json)?\s*', '', s)
    s = re.sub(r'\s*```$', '', s)
    s = s.strip()

    # Prova il parse diretto
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # Estrai il primo oggetto {...} o array [...] con regex
    m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', s)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("Nessun JSON valido trovato", s, 0)


BEE_SYSTEM_PROMPT = """Sei ApiarioAI, un assistente esperto in apicoltura integrato nell'app Apiary.
Rispondi SEMPRE in italiano, in modo conciso e pratico.
Puoi aiutare con: gestione arnie, controlli sanitari, trattamenti varroa, produzione miele,
identificazione problemi (nosema, covata calcificata, favi saccheggiati, ecc.),
gestione calendario, regine e nuclei.
Non usare markdown (niente **, ##, liste con trattini). Scrivi in testo semplice.
Sii diretto come un apicoltore esperto che risponde a un collega."""


def _get_user_api_key(user):
    """Ritorna la chiave Gemini personale dell'utente, o stringa vuota."""
    try:
        return user.profilo.gemini_api_key or ''
    except Exception:
        return ''


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
            messages, system_prompt=system, temperature=0.7, max_tokens=800,
            api_key=_get_user_api_key(request.user)
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
            temperature=0.1, max_tokens=1024,
            api_key=_get_user_api_key(request.user),
            response_mime_type='application/json',
        )

        # Pulisci e parsa il JSON
        try:
            result = _extract_json(response_text)
        except json.JSONDecodeError:
            result = {'azione': 'chat', 'risposta': response_text[:200], 'dati': {}}

        result['model'] = model_used
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _genera_analisi_yolo(yolo_result):
    """Genera un testo di analisi strutturato dai risultati del detector TFLite."""
    if not yolo_result or 'error' in yolo_result:
        err = yolo_result.get('error', 'modello non disponibile') if yolo_result else 'modello non disponibile'
        return f"Analisi non disponibile: {err}"

    summary = yolo_result.get('summary', {})
    if not summary or all(v == 0 for v in summary.values()):
        return "Nessun elemento rilevato nell'immagine. Verifica che la foto mostri chiaramente il telaino."

    # Nomi classe TFLite: bees, drone, queenbees, royal cell
    api         = summary.get('bees', 0)
    fuchi       = summary.get('drone', 0)
    regine      = summary.get('queenbees', 0)
    celle_reali = summary.get('royal cell', 0)

    righe = []

    # Regina
    if regine > 0:
        righe.append(f"PRESENZA REGINA: rilevata ({regine} individuo/i identificato/i dal modello).")
    else:
        righe.append("PRESENZA REGINA: non rilevata direttamente nell'immagine. Presenza incerta.")

    # Celle reali
    if celle_reali > 0:
        righe.append(f"CELLE REALI: rilevate {celle_reali}. Attenzione: possibile preparazione alla sciamatura o sostituzione della regina.")
    else:
        righe.append("CELLE REALI: nessuna rilevata.")

    # Forza della famiglia (api operaie)
    if api > 100:
        forza = "famiglia molto numerosa"
    elif api > 50:
        forza = "famiglia di buona forza"
    elif api > 20:
        forza = "famiglia di media forza"
    elif api > 0:
        forza = "famiglia debole"
    else:
        forza = "nessuna ape operaia rilevata"
    righe.append(f"POPOLAZIONE: {api} api operaie rilevate ({forza}).")

    # Fuchi
    if fuchi > 0:
        righe.append(f"FUCHI: rilevati {fuchi}. Presenza normale in primavera/estate.")

    # Riepilogo conteggi
    tutti = ", ".join(f"{cls}: {n}" for cls, n in summary.items())
    righe.append(f"RIEPILOGO RILEVAZIONI: {tutti}.")

    # Consiglio pratico
    consigli = []
    if celle_reali > 0:
        consigli.append("Controlla lo stato di sciamatura e valuta se intervenire.")
    if regine == 0:
        consigli.append("Verifica la presenza della regina ispezionando i favi centrali alla ricerca di uova.")
    if api < 20:
        consigli.append("La famiglia sembra debole: valuta un'unione o un rinforzo con covata.")
    if not consigli:
        consigli.append("Famiglia nella norma. Prosegui con i controlli periodici.")
    righe.append("CONSIGLIO: " + " ".join(consigli))

    return "\n\n".join(righe)


# ---------------------------------------------------------------------------
# Analisi Telaino (YOLO locale)
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
        image_data = request.FILES['image'].read()

        # --- TFLite bee detection (stesso modello dell'app Flutter) ---
        det_result = _run_detection(image_data)

        analysis_text = _genera_analisi_yolo(det_result)

        return JsonResponse({
            'analysis':  analysis_text,
            'model':     'TFLite bee detector',
            'yolo':      det_result,   # chiave invariata per compatibilità template
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
            temperature=0, max_tokens=1024,
            api_key=_get_user_api_key(request.user),
            response_mime_type='application/json',
        )

        # Pulisci e parsa JSON
        result = _extract_json(response_text)
        result['_model'] = model_used
        result['_transcript'] = transcript
        return JsonResponse(result)

    except json.JSONDecodeError as e:
        return JsonResponse({'error': f'Risposta Gemini non valida: {e}', '_transcript': transcript, '_raw': response_text[:300]}, status=500)
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
