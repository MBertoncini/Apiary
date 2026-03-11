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
_yolo_load_error = None  # memorizza l'errore di caricamento per debug

def _get_yolo_model():
    """Carica e cachea il modello YOLO segmentazione. Ritorna (model, error_str)."""
    global _yolo_model, _yolo_load_error
    if _yolo_model is not None:
        return _yolo_model, None
    if _yolo_load_error is not None:
        return None, _yolo_load_error
    yolo_path = getattr(settings, 'YOLO_MODEL_PATH', '')
    if not yolo_path:
        _yolo_load_error = 'YOLO_MODEL_PATH non configurato'
        return None, _yolo_load_error
    if not os.path.exists(yolo_path):
        _yolo_load_error = f'File modello non trovato: {yolo_path}'
        return None, _yolo_load_error
    try:
        from ultralytics import YOLO
        _yolo_model = YOLO(yolo_path)
        return _yolo_model, None
    except ImportError:
        _yolo_load_error = 'ultralytics non installato'
        return None, _yolo_load_error
    except Exception as e:
        _yolo_load_error = str(e)
        return None, _yolo_load_error


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


def _genera_analisi_yolo(yolo_result):
    """Genera un testo di analisi strutturato basato sui risultati YOLO."""
    if not yolo_result or 'error' in yolo_result:
        err = yolo_result.get('error', 'modello non disponibile') if yolo_result else 'modello non disponibile'
        return f"Analisi YOLO non disponibile: {err}"
    if 'nota' in yolo_result:
        return f"Analisi YOLO non disponibile: {yolo_result['nota']}"

    summary = yolo_result.get('summary', {})
    if not summary:
        return "Nessun elemento rilevato nell'immagine. Verifica che la foto mostri chiaramente il telaino."

    # Leggi conteggi (nomi classi in inglese come da modello)
    api = summary.get('bee', summary.get('bees', 0))
    fuchi = summary.get('drone', summary.get('drones', 0))
    regine = summary.get('queenbee', summary.get('queenbees', summary.get('queen', 0)))
    celle_reali = summary.get('royal cell', summary.get('royalcell', summary.get('queen_cell', 0)))

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
        image_file = request.FILES['image']
        image_data = image_file.read()

        # --- YOLO segmentazione ---
        yolo_result = None
        yolo_model, yolo_load_err = _get_yolo_model()
        if yolo_load_err:
            yolo_result = {'error': yolo_load_err}
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

        # --- Analisi basata solo su YOLO ---
        analysis_text = _genera_analisi_yolo(yolo_result)

        return JsonResponse({
            'analysis': analysis_text,
            'model': 'YOLO locale',
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
