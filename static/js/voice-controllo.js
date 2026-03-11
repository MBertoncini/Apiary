/**
 * VoiceControllo — Inserimento vocale controlli arnia
 * Porta fedele del sistema Flutter: vocabolario, batch mode, trigger words, Gemini rotation
 */
'use strict';

// ────────────────────────────────────────────────────────────────────────────
// VOCABULARY CORRECTOR  (porto dalla classe BeeVocabularyCorrector dell'app)
// ────────────────────────────────────────────────────────────────────────────
const BEE_VOCAB_RAW = [
  // Multi-word first (più lunghi → priorità più alta)
  ['cella reale',         'celle reali'],
  ['cella reali',         'celle reali'],
  ['celle reale',         'celle reali'],
  ['nova fresche',        'uova fresche'],
  ['uva fresche',         'uova fresche'],
  ['nove fresche',        'uova fresche'],
  ['forte famiglia',      'famiglia forte'],
  ['debole famiglia',     'famiglia debole'],
  ['normale famiglia',    'famiglia normale'],
  ['sciam atura',         'sciamatura'],
  ['inver namento',       'invernamento'],
  ['bay varol',           'bayvarol'],
  ['api stano',           'apistano'],
  ['dia framma',          'diaframma'],
  ['proprio li',          'propoli'],
  ['a tasca',             'a tasca'],     // keep as-is
  // Single words
  ['armia',    'arnia'],   ['arma',     'arnia'],   ['alnia',    'arnia'],
  ['terreni',  'telaini'], ['terrani',  'telaini'], ['teloni',   'telaini'],
  ['telane',   'telaini'], ['telain',   'telaini'], ['terremoti','telaini'],
  ['telaine',  'telaino'], ['telaione', 'telaino'],
  ['codata',   'covata'],  ['cravata',  'covata'],  ['corvata',  'covata'],
  ['cubata',   'covata'],  ['cavata',   'covata'],  ['lobata',   'covata'],
  ['cobata',   'covata'],
  ['varro',    'varroa'],  ['barro',    'varroa'],  ['vaiolo',   'varroa'],
  ['barroa',   'varroa'],  ['varra',    'varroa'],  ['variola',  'varroa'],
  ['resina',   'regina'],  ['retina',   'regina'],  ['vegina',   'regina'],
  ['reina',    'regina'],  ['regime',   'regine'],  ['resine',   'regine'],
  ['chiamatura','sciamatura'],['ciamatura','sciamatura'],['siamatura','sciamatura'],
  ['schiamatura','sciamatura'],
  ['chiame',   'sciame'],  ['siame',    'sciame'],
  ['melanio',  'melario'], ['melaio',   'melario'], ['mellario', 'melario'],
  ['menari',   'melari'],  ['melali',   'melari'],
  ['nosena',   'nosema'],  ['nossema',  'nosema'],
  ['fucky',    'fuchi'],   ['fucci',    'fuchi'],   ['fruchi',   'fuchi'],
  ['foco',     'fuco'],
  ['diagramma','diaframma'],['diagrammi','diaframmi'],
  ['propolis', 'propoli'],
  ['poline',   'polline'], ['polling',  'polline'],
  ['nutritor', 'nutritore'],['nutridor','nutritore'],
  ['siroppo',  'sciroppo'],['sciroppio','sciroppo'],
  ['apistanno','apistano'],
  ['baivarol', 'bayvarol'],
  ['kalistrip','calistrip'],['callistrip','calistrip'],['calli strip','calistrip'],
  ['ossalisco','ossalico'], ['oxalico',  'ossalico'],
  ['smiellatura','smielatura'],['smieliatura','smielatura'],
  ['obercoli', 'opercoli'],
  ['appliario','apiario'],  ['appiario', 'apiario'],  ['apiamo',  'apiario'],
  ['al piario','apiario'],
  ['un un',    'un'],
  // Nuove sostituzioni (richieste 2026-03)
  ['zelarini',              'telaini'],
  ['daini',                 'telaini'],
  ['tritte',                'tre'],
  ['anni',                  'arnia'],
  ['barroa',                'varroa'],
  ['serio',                 'cereo'],
  ['discorsi',              'di scorte'],
  ['serie televisiva casa', 'telaini di covata'],
  // Orari → numeri (Speech API trascrive cifre come orari in certi contesti)
  ['1:00', '1'], ['2:00', '2'], ['3:00', '3'], ['4:00', '4'], ['5:00', '5'],
  ['6:00', '6'], ['7:00', '7'], ['8:00', '8'], ['9:00', '9'], ['10:00', '10'],
];

function correctVocabulary(text) {
  let result = text;
  for (const [wrong, correct] of BEE_VOCAB_RAW) {
    const escaped = wrong.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&')
                         .replace(/\\ /g, '\\s+');
    const re = new RegExp(`\\b${escaped}\\b`, 'gi');
    result = result.replace(re, (match) => {
      // Preserva la maiuscola iniziale
      return match[0] === match[0].toUpperCase()
        ? correct.charAt(0).toUpperCase() + correct.slice(1)
        : correct;
    });
  }
  return result;
}

// Versione con highlight HTML: le parole corrette appaiono marcate in <mark>
function correctVocabularyHighlighted(text) {
  let result = text;
  for (const [wrong, correct] of BEE_VOCAB_RAW) {
    const escaped = wrong.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&')
                         .replace(/\\ /g, '\\s+');
    const re = new RegExp(`\\b${escaped}\\b`, 'gi');
    result = result.replace(re, (match) => {
      const correctedWord = match[0] === match[0].toUpperCase()
        ? correct.charAt(0).toUpperCase() + correct.slice(1)
        : correct;
      return `\x00\x01${correctedWord}\x01\x00`;  // placeholder sicuro
    });
  }
  // Separa testo normale dai token corretti, escape HTML solo sul testo normale
  return result.split(/(\x00\x01[^\x01]*\x01\x00)/).map(part => {
    const m = part.match(/^\x00\x01([\s\S]*)\x01\x00$/);
    if (m) return `<mark class="vc-mark">${escHtml(m[1])}</mark>`;
    return escHtml(part);
  }).join('');
}

// ────────────────────────────────────────────────────────────────────────────
// TRIGGER WORDS  (come nell'app Flutter)
// ────────────────────────────────────────────────────────────────────────────
const TRIGGER_ADVANCE = ['avanti', 'ok', 'vai', 'continua', 'registra', 'pronto',
                          'inizia', 'next', 'prossima', 'prossimo', 'seguente'];
const TRIGGER_STOP    = ['stop', 'fine', 'finito', 'basta', 'termina', 'ho finito',
                          'concludi', 'concluso'];

function containsTrigger(text, words) {
  const low = text.toLowerCase();
  return words.some(w => {
    const re = new RegExp(`\\b${w}\\b`, 'i');
    return re.test(low);
  });
}

// ────────────────────────────────────────────────────────────────────────────
// CSRF
// ────────────────────────────────────────────────────────────────────────────
function getCsrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}

// ────────────────────────────────────────────────────────────────────────────
// VOICE CONTROLLO CONTROLLER
// ────────────────────────────────────────────────────────────────────────────
class VoiceControllo {
  constructor() {
    this.apiarioId   = null;
    this.apiarioNome = '';
    this.batchMode   = false;

    // State machine: idle | recording | awaiting_trigger | processing | review
    this.state = 'idle';

    // Batch queue: array of raw transcripts (strings)
    this.pendingTranscripts = [];
    // Processed entries (from Gemini)
    this.entries = [];

    // Speech recognition
    this.recognition  = null;
    this.recFinal     = '';
    this.recInterim   = '';
    this.silenceTimer = null;
    this.SILENCE_MS   = 1800;   // auto-finalise after silence (like Flutter's VAD handling)

    this._initUI();
    this._initSpeech();
  }

  // ── UI refs ───────────────────────────────────────────────────────────────
  _initUI() {
    this.ui = {
      apiarioSel:      document.getElementById('vc-apiario'),
      modeToggle:      document.getElementById('vc-batch-toggle'),
      startBtn:        document.getElementById('vc-start-btn'),
      stopBtn:         document.getElementById('vc-stop-btn'),
      statusDot:       document.getElementById('vc-status-dot'),
      statusText:      document.getElementById('vc-status-text'),
      transcriptBox:   document.getElementById('vc-transcript'),
      correctedBox:    document.getElementById('vc-corrected'),
      queueList:       document.getElementById('vc-queue'),
      queueSection:    document.getElementById('vc-queue-section'),
      processBtn:      document.getElementById('vc-process-btn'),
      reviewSection:   document.getElementById('vc-review-section'),
      reviewGrid:      document.getElementById('vc-review-grid'),
      saveBtn:         document.getElementById('vc-save-btn'),
      saveResult:      document.getElementById('vc-save-result'),
      triggerHint:     document.getElementById('vc-trigger-hint'),
    };

    // Apiario selector
    this.ui.apiarioSel?.addEventListener('change', () => {
      const opt = this.ui.apiarioSel.selectedOptions[0];
      this.apiarioId   = this.ui.apiarioSel.value || null;
      this.apiarioNome = opt ? opt.text : '';
    });

    // Mode toggle
    this.ui.modeToggle?.addEventListener('change', () => {
      this.batchMode = this.ui.modeToggle.checked;
      if (this.ui.triggerHint) {
        this.ui.triggerHint.style.display = this.batchMode ? 'block' : 'none';
      }
    });

    // Start / Stop
    this.ui.startBtn?.addEventListener('click', () => this._startRecording());
    this.ui.stopBtn?.addEventListener('click',  () => this._stopRecording(true));

    // Process batch
    this.ui.processBtn?.addEventListener('click', () => this._processBatch());

    // Save
    this.ui.saveBtn?.addEventListener('click', () => this._saveAll());
  }

  // ── Speech Recognition init ───────────────────────────────────────────────
  _initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      this._setStatus('error', 'Web Speech API non supportata in questo browser (usa Chrome o Edge)');
      if (this.ui.startBtn) this.ui.startBtn.disabled = true;
      return;
    }
    this.recognition = new SR();
    this.recognition.lang = 'it-IT';
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;

    this.recognition.onresult = (e) => this._onResult(e);
    this.recognition.onend    = ()  => this._onEnd();
    this.recognition.onerror  = (e) => this._onError(e);
  }

  // ── Recording control ─────────────────────────────────────────────────────
  _startRecording() {
    if (!this.apiarioId) {
      alert('Seleziona prima un apiario.');
      return;
    }
    if (!this.recognition) return;

    this.recFinal   = '';
    this.recInterim = '';
    this.state      = 'recording';
    this._updateTranscript('');
    this._setStatus('recording', this.batchMode
      ? 'In ascolto… Parla dell\'arnia, poi dì "avanti" per la prossima o "stop" per finire'
      : 'In ascolto… Parla dell\'arnia');

    this.ui.startBtn.style.display = 'none';
    this.ui.stopBtn.style.display  = 'flex';

    try { this.recognition.start(); } catch (_) {}
    this._resetSilenceTimer();
  }

  _stopRecording(manual = false) {
    clearTimeout(this.silenceTimer);
    try { this.recognition.stop(); } catch (_) {}

    if (manual && this.recFinal.trim()) {
      this._finaliseTranscript(this.recFinal.trim());
    } else if (!manual) {
      this._finaliseTranscript(this.recFinal.trim());
    }
    this._resetRecordingUI();
  }

  _resetRecordingUI() {
    this.state = 'idle';
    this.ui.startBtn.style.display = 'flex';
    this.ui.stopBtn.style.display  = 'none';
    this._setStatus('idle', 'Pronto');
  }

  // ── Speech callbacks ──────────────────────────────────────────────────────
  _onResult(event) {
    let interim = '';
    let final   = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += t;
      else interim += t;
    }
    this.recFinal += final;
    this.recInterim = interim;

    const display = this.recFinal + (interim ? ` [${interim}]` : '');
    this._updateTranscript(display);
    this._resetSilenceTimer();

    // Trigger word detection in batch mode
    if (this.batchMode && this.state === 'recording') {
      const combined = (this.recFinal + ' ' + interim).toLowerCase();
      if (containsTrigger(combined, TRIGGER_STOP)) {
        this._stopRecording(false);
        if (this.pendingTranscripts.length > 0 || this.recFinal.trim()) {
          this._processBatch();
        }
        return;
      }
      if (containsTrigger(combined, TRIGGER_ADVANCE)) {
        // Rimuovi la trigger word dal testo
        let clean = this.recFinal.replace(/\b(avanti|ok|vai|continua|registra|pronto|inizia|next|prossima|prossimo|seguente)\b/gi, '').trim();
        if (clean) this._enqueueTranscript(clean);
        this.recFinal   = '';
        this.recInterim = '';
        this._updateTranscript('');
        this._setStatus('recording', 'Prossima arnia — parla ora…');
        return;
      }
    }
  }

  _onEnd() {
    if (this.state === 'recording') {
      // Riavvio automatico (come Flutter per Android VAD)
      try { this.recognition.start(); } catch (_) {
        this._finaliseTranscript(this.recFinal.trim());
        this._resetRecordingUI();
      }
    }
  }

  _onError(e) {
    if (e.error === 'no-speech') return;  // normale
    if (e.error === 'not-allowed') {
      this._setStatus('error', 'Microfono non autorizzato. Controlla i permessi del browser.');
    } else {
      this._setStatus('error', `Errore microfono: ${e.error}`);
    }
    this._resetRecordingUI();
  }

  // ── Silence timer (auto-stop in single mode) ──────────────────────────────
  _resetSilenceTimer() {
    clearTimeout(this.silenceTimer);
    if (!this.batchMode) {
      this.silenceTimer = setTimeout(() => {
        if (this.state === 'recording' && this.recFinal.trim()) {
          this._stopRecording(false);
          // Non auto-processa: l'utente rivede il trascritto in coda e preme "Elabora con AI"
        }
      }, this.SILENCE_MS);
    }
  }

  // ── Transcript management ─────────────────────────────────────────────────
  _finaliseTranscript(text) {
    if (!text) return;
    const corrected = correctVocabulary(text);
    // Aggiunge sempre alla coda — l'utente deve premere "Elabora con AI" per inviare a Gemini
    this._enqueueTranscript(corrected);
  }

  _enqueueTranscript(text) {
    if (!text) return;
    this.pendingTranscripts.push(text);
    this._renderQueue();
    if (this.ui.processBtn) this.ui.processBtn.disabled = false;
  }

  _renderQueue() {
    if (!this.ui.queueList) return;
    this.ui.queueSection.style.display = this.pendingTranscripts.length > 0 ? 'block' : 'none';
    this.ui.queueList.innerHTML = this.pendingTranscripts.map((t, i) => `
      <li class="list-group-item vc-queue-item" data-qi="${i}">
        <div class="d-flex align-items-start gap-2">
          <span class="badge bg-amber text-dark rounded-pill mt-1 flex-shrink-0">${i + 1}</span>
          <div class="flex-grow-1 min-w-0">
            <div class="vc-queue-text small lh-base">${correctVocabularyHighlighted(t)}</div>
            <textarea class="form-control form-control-sm vc-queue-edit mt-1"
                      rows="2" style="display:none">${escHtml(t)}</textarea>
          </div>
          <div class="d-flex flex-column gap-1 flex-shrink-0">
            <button class="btn btn-sm btn-link text-primary p-0 vc-edit-btn"
                    onclick="window._vc.editQueue(${i})" title="Modifica">
              <i class="bi bi-pencil-square"></i>
            </button>
            <button class="btn btn-sm btn-link text-danger p-0"
                    onclick="window._vc.removeQueue(${i})" title="Rimuovi">
              <i class="bi bi-x-circle"></i>
            </button>
          </div>
        </div>
      </li>`).join('');
  }

  editQueue(idx) {
    const li = this.ui.queueList.querySelector(`[data-qi="${idx}"]`);
    if (!li) return;
    const textDiv  = li.querySelector('.vc-queue-text');
    const textarea = li.querySelector('.vc-queue-edit');
    const editBtn  = li.querySelector('.vc-edit-btn');
    const isEditing = textarea.style.display !== 'none';

    if (!isEditing) {
      // Entra in modalità modifica: mostra il testo grezzo originale (non corretto)
      textarea.value = this.pendingTranscripts[idx];
      textDiv.style.display  = 'none';
      textarea.style.display = 'block';
      textarea.focus();
      editBtn.innerHTML = '<i class="bi bi-check-circle-fill"></i>';
      editBtn.title = 'Conferma';
      editBtn.classList.replace('text-primary', 'text-success');
    } else {
      // Conferma: aggiorna e ri-renderizza per mostrare il testo corretto evidenziato
      const newText = textarea.value.trim();
      if (newText) this.pendingTranscripts[idx] = newText;
      this._renderQueue();
    }
  }

  removeQueue(idx) {
    this.pendingTranscripts.splice(idx, 1);
    this._renderQueue();
    if (this.pendingTranscripts.length === 0 && this.ui.processBtn) {
      this.ui.processBtn.disabled = true;
    }
  }

  // ── Gemini processing ─────────────────────────────────────────────────────
  async _processBatch() {
    if (this.pendingTranscripts.length === 0) return;

    this.state = 'processing';
    const total = this.pendingTranscripts.length;
    // Copia locale — la coda originale resta intatta finché non siamo sicuri del successo
    const toProcess = [...this.pendingTranscripts];
    this.pendingTranscripts = [];
    this._renderQueue();
    if (this.ui.processBtn) this.ui.processBtn.disabled = true;

    this._setStatus('processing', `Elaborazione con Gemini AI… (0/${total})`);

    const newEntries  = [];
    const failedTexts = [];   // transcript che non si sono riusciti a processare

    for (let i = 0; i < toProcess.length; i++) {
      this._setStatus('processing', `Elaborazione con Gemini AI… (${i + 1}/${total})`);
      try {
        const resp = await fetch(VOICE_PROCESS_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({ transcript: toProcess[i], apiario_id: this.apiarioId }),
        });
        const data = await resp.json();
        if (data.error) {
          // Errore Gemini: rimetti il transcript in coda per un eventuale nuovo tentativo
          failedTexts.push(toProcess[i]);
          console.warn('[VoiceControllo] Gemini error:', data.error, '| transcript:', toProcess[i]);
        } else {
          newEntries.push(data);
        }
      } catch (e) {
        // Errore di rete: il transcript non va perso
        failedTexts.push(toProcess[i]);
        console.warn('[VoiceControllo] Network error:', e.message, '| transcript:', toProcess[i]);
      }

      // Piccola pausa tra chiamate (come nell'app — evita rate limit)
      if (i < toProcess.length - 1) await sleep(600);
    }

    // I transcript falliti tornano in coda — l'utente può riprovare
    if (failedTexts.length > 0) {
      this.pendingTranscripts.push(...failedTexts);
      this._renderQueue();
      if (this.ui.processBtn) this.ui.processBtn.disabled = false;
      this._showToast(
        `⚠️ ${failedTexts.length} trascrizione/i non elaborate (errore AI/rete) — rimesse in coda per riprovare.`,
        'warning'
      );
    }

    this.entries.push(...newEntries);
    this._renderReview();

    const status = newEntries.length > 0
      ? `Elaborazione completata — ${newEntries.length} arnie ok${failedTexts.length ? `, ${failedTexts.length} in coda da riprovare` : ''}`
      : 'Errore — trascrizioni rimesse in coda, riprova';
    this._setStatus(failedTexts.length > 0 && newEntries.length === 0 ? 'error' : 'idle', status);
    this.state = this.entries.length > 0 ? 'review' : 'idle';
  }

  // ── Toast notifica ────────────────────────────────────────────────────────
  _showToast(message, type = 'info') {
    const colors = { warning: '#F5A623', error: '#dc3545', success: '#198754', info: '#0dcaf0' };
    const el = document.createElement('div');
    el.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999;
      background:#fff; border-left:4px solid ${colors[type] || colors.info};
      border-radius:8px; padding:12px 16px; max-width:360px;
      box-shadow:0 4px 16px rgba(0,0,0,.15); font-size:.88rem;
      color:#2C1810; animation:fadeInUp .3s ease;
    `;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  // ── Review UI ─────────────────────────────────────────────────────────────
  _renderReview() {
    if (!this.ui.reviewGrid) return;

    const html = this.entries.map((e, idx) => {
      if (e._error) {
        return `
          <div class="col-12">
            <div class="alert alert-danger d-flex gap-2 align-items-start">
              <i class="bi bi-exclamation-triangle-fill mt-1"></i>
              <div>
                <strong>Errore elaborazione</strong><br>
                <span class="small">${escHtml(e._transcript || '')}</span><br>
                <span class="small text-muted">${escHtml(e._error)}</span>
              </div>
            </div>
          </div>`;
      }

      const arniaNum = e.arnia_numero ?? '';
      const label = (v) => v === true ? 'Sì' : v === false ? 'No' : '—';

      return `
        <div class="col-md-6 col-lg-4">
          <div class="card review-card" data-idx="${idx}">
            <div class="card-header d-flex justify-content-between align-items-center">
              <span class="fw-bold">
                <i class="bi bi-hexagon-fill me-1 text-amber"></i>
                Arnia <span class="arnia-num-display">#${arniaNum || '?'}</span>
              </span>
              <button class="btn btn-sm btn-link text-danger p-0" onclick="window._vc.removeEntry(${idx})" title="Rimuovi">
                <i class="bi bi-trash3"></i>
              </button>
            </div>
            <div class="card-body">
              <div class="row g-2 mb-2">
                <div class="col-6">
                  <label class="form-label-sm">N° Arnia</label>
                  <input type="number" class="form-control form-control-sm" data-field="arnia_numero"
                         value="${arniaNum}" min="1">
                </div>
                <div class="col-6">
                  <label class="form-label-sm">Forza</label>
                  <select class="form-select form-select-sm" data-field="forza_famiglia">
                    <option value="">—</option>
                    <option value="debole"  ${e.forza_famiglia==='debole'  ?'selected':''}>Debole</option>
                    <option value="normale" ${e.forza_famiglia==='normale' ?'selected':''}>Normale</option>
                    <option value="forte"   ${e.forza_famiglia==='forte'   ?'selected':''}>Forte</option>
                  </select>
                </div>
              </div>
              <div class="row g-2 mb-2">
                <div class="col-6">
                  <label class="form-label-sm">Tel. covata</label>
                  <input type="number" class="form-control form-control-sm" data-field="telaini_covata"
                         value="${e.telaini_covata ?? ''}" min="0">
                </div>
                <div class="col-6">
                  <label class="form-label-sm">Tel. scorte</label>
                  <input type="number" class="form-control form-control-sm" data-field="telaini_scorte"
                         value="${e.telaini_scorte ?? ''}" min="0">
                </div>
              </div>
              <div class="row g-2 mb-2">
                <div class="col-6">
                  <label class="form-label-sm">Presenza regina</label>
                  <select class="form-select form-select-sm" data-field="presenza_regina">
                    <option value="true"  ${e.presenza_regina !== false  ?'selected':''}>Sì</option>
                    <option value="false" ${e.presenza_regina === false  ?'selected':''}>No</option>
                  </select>
                </div>
                <div class="col-6">
                  <label class="form-label-sm">Sciamatura</label>
                  <select class="form-select form-select-sm" data-field="sciamatura">
                    <option value="false" ${!e.sciamatura ?'selected':''}>No</option>
                    <option value="true"  ${ e.sciamatura ?'selected':''}>Sì</option>
                  </select>
                </div>
              </div>
              <div class="mb-2">
                <label class="form-label-sm">Problemi sanitari</label>
                <select class="form-select form-select-sm" data-field="problemi_sanitari">
                  <option value="false" ${!e.problemi_sanitari ?'selected':''}>No</option>
                  <option value="true"  ${ e.problemi_sanitari ?'selected':''}>Sì</option>
                </select>
              </div>
              ${e.problemi_sanitari || e.tipo_problema ? `
              <div class="mb-2">
                <label class="form-label-sm">Tipo problema</label>
                <input type="text" class="form-control form-control-sm" data-field="tipo_problema"
                       value="${escHtml(e.tipo_problema || '')}">
              </div>` : ''}
              <div>
                <label class="form-label-sm">Note</label>
                <textarea class="form-control form-control-sm" rows="2" data-field="note">${escHtml(e.note || '')}</textarea>
              </div>
              <div class="mt-2 small text-muted">
                <i class="bi bi-mic-fill me-1"></i>
                <em>"${escHtml((e._transcript || '').substring(0, 80))}${(e._transcript||'').length>80?'…':''}"</em>
              </div>
            </div>
          </div>
        </div>`;
    }).join('');

    this.ui.reviewGrid.innerHTML = html;

    // Sync field changes back to this.entries
    this.ui.reviewGrid.querySelectorAll('[data-field]').forEach(el => {
      el.addEventListener('change', () => this._syncCard(el));
      el.addEventListener('input',  () => this._syncCard(el));
    });

    this.ui.reviewSection.style.display = this.entries.length > 0 ? 'block' : 'none';
    if (this.ui.saveBtn) this.ui.saveBtn.disabled = this.entries.every(e => e._error);
  }

  _syncCard(el) {
    const card = el.closest('[data-idx]');
    if (!card) return;
    const idx   = parseInt(card.dataset.idx);
    const field = el.dataset.field;
    let val = el.value;
    if (val === 'true')  val = true;
    if (val === 'false') val = false;
    if (el.type === 'number' && val !== '') val = parseInt(val);
    this.entries[idx][field] = val;

    // Update displayed arnia number in header
    if (field === 'arnia_numero') {
      const disp = card.querySelector('.arnia-num-display');
      if (disp) disp.textContent = '#' + (val || '?');
    }
  }

  removeEntry(idx) {
    this.entries.splice(idx, 1);
    this._renderReview();
  }

  // ── Save all ──────────────────────────────────────────────────────────────
  async _saveAll() {
    const valid = this.entries.filter(e => !e._error && e.arnia_numero);
    if (valid.length === 0) {
      alert('Nessuna arnia valida da salvare. Controlla i numeri arnia.');
      return;
    }

    this.ui.saveBtn.disabled = true;
    this.ui.saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Salvataggio…';

    try {
      const resp = await fetch(VOICE_SAVE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ apiario_id: this.apiarioId, entries: valid }),
      });
      const data = await resp.json();

      const ok    = (data.results || []).filter(r => r.success);
      const errs  = (data.results || []).filter(r => !r.success);

      let html = `<div class="alert alert-success mb-2">
        <i class="bi bi-check-circle-fill me-2"></i>
        <strong>${ok.length} controlli salvati</strong>
        ${ok.length > 0 ? '— ' + ok.map(r => `Arnia #${r.arnia}`).join(', ') : ''}
      </div>`;

      if (errs.length > 0) {
        html += `<div class="alert alert-warning mb-0">
          <strong>${errs.length} errori:</strong><br>
          ${errs.map(r => `Arnia #${r.arnia}: ${escHtml(r.error)}`).join('<br>')}
        </div>`;
      }

      this.ui.saveResult.innerHTML = html;
      this.ui.saveResult.style.display = 'block';

      if (ok.length > 0) {
        // Rimuovi le entry salvate con successo
        const savedArnias = new Set(ok.map(r => r.arnia));
        this.entries = this.entries.filter(e => !savedArnias.has(e.arnia_numero));
        this._renderReview();
      }
    } catch (err) {
      this.ui.saveResult.innerHTML = `<div class="alert alert-danger">Errore di rete: ${escHtml(err.message)}</div>`;
      this.ui.saveResult.style.display = 'block';
    }

    this.ui.saveBtn.disabled = false;
    this.ui.saveBtn.innerHTML = '<i class="bi bi-cloud-check me-2"></i>Salva tutti i controlli';
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  _setStatus(type, text) {
    if (!this.ui.statusText) return;
    this.ui.statusText.textContent = text;
    const dot = this.ui.statusDot;
    if (!dot) return;
    dot.className = 'vc-status-dot';
    if (type === 'recording')  dot.classList.add('recording');
    if (type === 'processing') dot.classList.add('processing');
    if (type === 'error')      dot.classList.add('error');
  }

  _updateTranscript(text) {
    if (this.ui.transcriptBox) this.ui.transcriptBox.textContent = text || '…';
    if (this.ui.correctedBox) {
      if (text) {
        this.ui.correctedBox.innerHTML = correctVocabularyHighlighted(text);
      } else {
        this.ui.correctedBox.innerHTML = '';
      }
    }
  }
}

// ────────────────────────────────────────────────────────────────────────────
// VOICE FILL — pulsante mic sul form nuovo_controllo.html
// ────────────────────────────────────────────────────────────────────────────
class VoiceFill {
  constructor() {
    this.recognition = null;
    this.recFinal    = '';
    this.modalEl     = document.getElementById('voiceFillModal');
    if (!this.modalEl) return;

    this.modal      = new bootstrap.Modal(this.modalEl);
    this.recBtn     = document.getElementById('vf-record-btn');
    this.statusTxt  = document.getElementById('vf-status');
    this.transcript = document.getElementById('vf-transcript');
    this.applyBtn   = document.getElementById('vf-apply-btn');
    this.parsed     = null;

    document.getElementById('vc-fill-btn')?.addEventListener('click', () => {
      this.parsed = null;
      this.recFinal = '';
      this._setStatus('idle', 'Clicca il microfono e parla');
      if (this.transcript) this.transcript.textContent = '…';
      if (this.applyBtn)   this.applyBtn.style.display = 'none';
      this.modal.show();
    });

    this.recBtn?.addEventListener('click', () => this._toggle());

    this._initSpeech();
  }

  _initSpeech() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    this.recognition = new SR();
    this.recognition.lang = 'it-IT';
    this.recognition.continuous = false;
    this.recognition.interimResults = true;

    this.recognition.onresult = (e) => {
      let final = '', interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t; else interim += t;
      }
      this.recFinal += final;
      const display = this.recFinal + (interim ? ` [${interim}]` : '');
      if (this.transcript) this.transcript.textContent = correctVocabulary(display) || '…';
    };

    this.recognition.onend = () => {
      this._setRecording(false);
      if (this.recFinal.trim()) this._process(correctVocabulary(this.recFinal.trim()));
    };

    this.recognition.onerror = (e) => {
      this._setRecording(false);
      if (e.error !== 'no-speech') this._setStatus('error', 'Errore: ' + e.error);
    };
  }

  _toggle() {
    if (!this.recognition) return;
    if (this.recBtn.classList.contains('recording')) {
      this.recognition.stop();
    } else {
      this.recFinal = '';
      if (this.transcript) this.transcript.textContent = '…';
      if (this.applyBtn)   this.applyBtn.style.display = 'none';
      this._setRecording(true);
      this.recognition.start();
    }
  }

  _setRecording(on) {
    if (!this.recBtn) return;
    this.recBtn.classList.toggle('recording', on);
    this.recBtn.innerHTML = on
      ? '<i class="bi bi-stop-fill me-2"></i>Stop'
      : '<i class="bi bi-mic-fill me-2"></i>Registra';
    this._setStatus(on ? 'recording' : 'idle', on ? 'In ascolto…' : 'Elaborazione…');
  }

  async _process(text) {
    this._setStatus('processing', 'Elaborazione con AI…');
    const apiarioId = document.getElementById('vc-form-apiario-id')?.value || null;
    try {
      const resp = await fetch(VOICE_PROCESS_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ transcript: text, apiario_id: apiarioId }),
      });
      const data = await resp.json();
      if (data.error) { this._setStatus('error', data.error); return; }

      this.parsed = data;
      this._setStatus('ok', `Estratto — Modello: ${data._model || ''}`);
      if (this.applyBtn) this.applyBtn.style.display = 'inline-flex';
      this.applyBtn.onclick = () => { this._fillForm(data); this.modal.hide(); };
    } catch (e) {
      this._setStatus('error', 'Errore di rete: ' + e.message);
    }
  }

  _fillForm(data) {
    const set = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
    const chk = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.checked = Boolean(val); };

    if (data.telaini_covata != null) set('id_telaini_covata', data.telaini_covata);
    if (data.telaini_scorte != null) set('id_telaini_scorte', data.telaini_scorte);
    if (data.presenza_regina != null) chk('id_presenza_regina', data.presenza_regina);
    if (data.sciamatura)              chk('id_sciamatura', true);
    if (data.problemi_sanitari)       chk('id_problemi_sanitari', true);
    if (data.tipo_problema)           set('id_note_problemi', data.tipo_problema);

    // Note aggregate
    const noteParts = [];
    if (data.forza_famiglia) noteParts.push(`Forza famiglia: ${data.forza_famiglia}`);
    if (data.uova_fresche)   noteParts.push('Uova fresche presenti');
    if (data.celle_reali) {
      noteParts.push(`Celle reali${data.numero_celle_reali ? ' (' + data.numero_celle_reali + ')' : ''}`);
    }
    if (data.note) noteParts.push(data.note);
    if (noteParts.length > 0) set('id_note', noteParts.join('\n'));

    // Trigger frame editor sync se presente
    ['id_telaini_covata', 'id_telaini_scorte'].forEach(id => {
      document.getElementById(id)?.dispatchEvent(new Event('change'));
    });
    // Trigger conditional fields
    ['id_sciamatura', 'id_problemi_sanitari'].forEach(id => {
      document.getElementById(id)?.dispatchEvent(new Event('change'));
    });
  }

  _setStatus(type, text) {
    if (!this.statusTxt) return;
    this.statusTxt.textContent = text;
    this.statusTxt.className = 'small mt-2 mb-0 ' + {
      idle: 'text-muted', recording: 'text-danger fw-semibold',
      processing: 'text-amber', ok: 'text-success', error: 'text-danger',
    }[type];
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Utils
// ────────────────────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ────────────────────────────────────────────────────────────────────────────
// Bootstrap  (espone URL configurati dal template)
// ────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('vc-apiario')) {
    window._vc = new VoiceControllo();
  }
  if (document.getElementById('voiceFillModal')) {
    window._vf = new VoiceFill();
  }
});
