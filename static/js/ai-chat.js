/**
 * ApiarioAI — Chat widget + Voice input
 * Gemini-powered beekeeping assistant with Web Speech API
 */
(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // Config
  // -------------------------------------------------------------------------
  const CHAT_URL = '/app/ai/chat/';
  const VOICE_URL = '/app/ai/voice/';

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  let history = [];      // [{role: 'user'|'model', text: '...'}]
  let isOpen = false;
  let isListening = false;
  let recognition = null;
  let recognition_final = '';

  // -------------------------------------------------------------------------
  // CSRF helper
  // -------------------------------------------------------------------------
  function getCsrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  // -------------------------------------------------------------------------
  // DOM: build widget HTML
  // -------------------------------------------------------------------------
  const widgetHTML = `
<div id="ai-fab" title="ApiarioAI" aria-label="Apri chat AI">
  <i class="bi bi-stars"></i>
</div>

<div id="ai-panel" role="dialog" aria-label="ApiarioAI Chat" aria-hidden="true">
  <div id="ai-panel-header">
    <div class="ai-header-left">
      <i class="bi bi-stars me-2"></i>
      <span>ApiarioAI</span>
    </div>
    <div class="ai-header-right">
      <button id="ai-clear-btn" title="Nuova conversazione" aria-label="Cancella cronologia">
        <i class="bi bi-trash3"></i>
      </button>
      <button id="ai-close-btn" title="Chiudi" aria-label="Chiudi chat">
        <i class="bi bi-x-lg"></i>
      </button>
    </div>
  </div>

  <div id="ai-messages" role="log" aria-live="polite"></div>

  <div id="ai-typing" style="display:none">
    <span class="ai-typing-dot"></span>
    <span class="ai-typing-dot"></span>
    <span class="ai-typing-dot"></span>
  </div>

  <div id="ai-input-bar">
    <button id="ai-voice-btn" title="Inserimento vocale" aria-label="Attiva voce" type="button">
      <i class="bi bi-mic"></i>
    </button>
    <textarea
      id="ai-input"
      placeholder="Scrivi un messaggio…"
      rows="1"
      aria-label="Messaggio"
    ></textarea>
    <button id="ai-send-btn" title="Invia" aria-label="Invia messaggio" type="button">
      <i class="bi bi-send-fill"></i>
    </button>
  </div>

  <div id="ai-voice-status" style="display:none">
    <i class="bi bi-mic-fill me-1 text-danger"></i>
    <span id="ai-voice-text">In ascolto…</span>
  </div>
</div>`;

  // -------------------------------------------------------------------------
  // CSS: inject styles
  // -------------------------------------------------------------------------
  const widgetCSS = `
#ai-fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #F5A623, #e8920f);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(245,166,35,.45);
  z-index: 1200;
  transition: transform .2s, box-shadow .2s;
  user-select: none;
}
#ai-fab:hover { transform: scale(1.08); box-shadow: 0 6px 20px rgba(245,166,35,.55); }
#ai-fab.active { background: linear-gradient(135deg, #2C1810, #3d2215); }

#ai-panel {
  position: fixed;
  bottom: 90px;
  right: 24px;
  width: 360px;
  max-width: calc(100vw - 32px);
  height: 520px;
  max-height: calc(100vh - 110px);
  background: #fff;
  border: 1px solid #EAD9BF;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0,0,0,.18);
  display: flex;
  flex-direction: column;
  z-index: 1199;
  opacity: 0;
  pointer-events: none;
  transform-origin: center center;
  will-change: transform, opacity, border-radius;
}

#ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(135deg, #2C1810, #3d2215);
  border-radius: 16px 16px 0 0;
  color: #F5A623;
  font-family: 'Caveat', cursive;
  font-size: 1.1rem;
  font-weight: 600;
}
.ai-header-left { display: flex; align-items: center; }
.ai-header-right { display: flex; gap: 4px; }
.ai-header-right button {
  background: none;
  border: none;
  color: #EAD9BF;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 6px;
  font-size: .95rem;
  transition: color .15s, background .15s;
}
.ai-header-right button:hover { color: #fff; background: rgba(255,255,255,.12); }

#ai-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  scrollbar-width: thin;
  scrollbar-color: #EAD9BF transparent;
}

.ai-msg {
  max-width: 88%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: .875rem;
  line-height: 1.5;
  word-break: break-word;
  animation: msgIn .18s ease;
}
@keyframes msgIn { from { opacity: 0; transform: translateY(6px); } }
.ai-msg-user {
  align-self: flex-end;
  background: linear-gradient(135deg, #F5A623, #e8920f);
  color: #fff;
  border-bottom-right-radius: 4px;
}
.ai-msg-model {
  align-self: flex-start;
  background: #f7f3ec;
  color: #2C1810;
  border-bottom-left-radius: 4px;
  border: 1px solid #EAD9BF;
}
.ai-msg-model small { display: block; font-size: .68rem; color: #bbb; margin-top: 4px; }

#ai-typing {
  padding: 6px 16px 4px;
  display: flex;
  gap: 5px;
  align-items: center;
}
.ai-typing-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #F5A623;
  animation: typingBounce 1.1s infinite;
}
.ai-typing-dot:nth-child(2) { animation-delay: .18s; }
.ai-typing-dot:nth-child(3) { animation-delay: .36s; }
@keyframes typingBounce {
  0%, 80%, 100% { transform: scale(.8); opacity: .5; }
  40% { transform: scale(1.2); opacity: 1; }
}

#ai-input-bar {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid #EAD9BF;
}
#ai-input {
  flex: 1;
  border: 1px solid #EAD9BF;
  border-radius: 20px;
  padding: 7px 12px;
  font-size: .875rem;
  font-family: 'Poppins', sans-serif;
  resize: none;
  max-height: 96px;
  outline: none;
  transition: border-color .15s;
  background: #FFFDF5;
  line-height: 1.4;
}
#ai-input:focus { border-color: #F5A623; }

#ai-send-btn, #ai-voice-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.1rem;
  padding: 6px 8px;
  border-radius: 50%;
  transition: background .15s, color .15s;
  line-height: 1;
}
#ai-send-btn { color: #F5A623; }
#ai-send-btn:hover { background: #FFF3D6; }
#ai-voice-btn { color: #888; }
#ai-voice-btn:hover { background: #f0f0f0; }
#ai-voice-btn.listening { color: #dc3545; animation: pulse 1s infinite; }
@keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.15); } }

#ai-voice-status {
  text-align: center;
  font-size: .8rem;
  color: #dc3545;
  padding: 0 12px 8px;
  min-height: 24px;
}

/* Welcome message */
.ai-welcome {
  text-align: center;
  padding: 20px 12px;
  color: #999;
  font-size: .85rem;
}
.ai-welcome i { font-size: 2rem; color: #F5A623; display: block; margin-bottom: 8px; }
`;

  // -------------------------------------------------------------------------
  // Init
  // -------------------------------------------------------------------------
  function init() {
    // Inject CSS
    const style = document.createElement('style');
    style.textContent = widgetCSS;
    document.head.appendChild(style);

    // Inject HTML
    const wrapper = document.createElement('div');
    wrapper.innerHTML = widgetHTML;
    document.body.appendChild(wrapper);

    // Bind events
    document.getElementById('ai-fab').addEventListener('click', togglePanel);
    document.getElementById('ai-close-btn').addEventListener('click', closePanel);
    document.getElementById('ai-clear-btn').addEventListener('click', clearHistory);
    document.getElementById('ai-send-btn').addEventListener('click', sendMessage);
    document.getElementById('ai-voice-btn').addEventListener('click', toggleVoice);

    const input = document.getElementById('ai-input');
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    input.addEventListener('input', autoResize);

    // Show welcome on first open
    showWelcome();

    // Init Web Speech API
    setupSpeechRecognition();
  }

  function showWelcome() {
    const messages = document.getElementById('ai-messages');
    messages.innerHTML = `
      <div class="ai-welcome">
        <i class="bi bi-stars"></i>
        Ciao! Sono ApiarioAI.<br>
        Chiedimi tutto sull'apicoltura o i tuoi apiari.
      </div>`;
  }

  // -------------------------------------------------------------------------
  // Panel open/close  (morph animation: panel ↔ FAB)
  // -------------------------------------------------------------------------
  let _animating = false;

  function togglePanel() {
    if (_animating) return;
    isOpen ? closePanel() : openPanel();
  }

  /*
   * Calcola il vettore dal centro del panel (posizione CSS, ignorando transform)
   * al centro del FAB. Usa valori CSS fissi per evitare che getBoundingClientRect
   * restituisca rettangoli distorti dalla trasformazione dell'animazione precedente.
   */
  function _morphVector() {
    const fr = document.getElementById('ai-fab').getBoundingClientRect();
    const panelRight  = 24;
    const panelBottom = 90;
    const panelW = Math.min(360, window.innerWidth  - 32);
    const panelH = Math.min(520, window.innerHeight - 110);
    const pcx = window.innerWidth  - panelRight  - panelW / 2;
    const pcy = window.innerHeight - panelBottom - panelH / 2;
    return {
      tx: (fr.left + fr.width  / 2) - pcx,
      ty: (fr.top  + fr.height / 2) - pcy,
    };
  }

  function openPanel() {
    if (_animating) return;
    _animating = true;
    isOpen = true;

    const fab   = document.getElementById('ai-fab');
    const panel = document.getElementById('ai-panel');

    fab.classList.add('active');
    fab.innerHTML = '<i class="bi bi-x-lg"></i>';
    panel.setAttribute('aria-hidden', 'false');
    panel.style.pointerEvents = 'none';
    panel.style.opacity = '0';  // stato di partenza noto

    const { tx, ty } = _morphVector();

    /* Parte dal punto del FAB (traslato + scala 0) → espande nella sua posizione */
    const anim = panel.animate([
      { transform: `translate(${tx}px,${ty}px) scale(0)`,           opacity: 0,  borderRadius: '50%'  },
      { transform: `translate(${tx*.4}px,${ty*.4}px) scale(.55)`,   opacity: .7, borderRadius: '24px', offset: .45 },
      { transform: 'translate(0,0) scale(1)',                        opacity: 1,  borderRadius: '16px' }
    ], { duration: 380, easing: 'cubic-bezier(.22,.68,0,1.15)' }); // no fill — gestiamo noi lo stato finale

    anim.onfinish = () => {
      panel.style.opacity       = '1';
      panel.style.pointerEvents = 'all';
      _animating = false;
      setTimeout(() => document.getElementById('ai-input').focus(), 50);
    };
  }

  function closePanel() {
    if (_animating) return;
    _animating = true;
    isOpen = false;

    const fab   = document.getElementById('ai-fab');
    const panel = document.getElementById('ai-panel');

    panel.setAttribute('aria-hidden', 'true');
    panel.style.pointerEvents = 'none';
    if (isListening) stopListening();

    const { tx, ty } = _morphVector();

    /* Si rimpicciolisce e vola verso il FAB */
    const anim = panel.animate([
      { transform: 'translate(0,0) scale(1)',                       opacity: 1,  borderRadius: '16px' },
      { transform: `translate(${tx*.45}px,${ty*.45}px) scale(.5)`, opacity: .7, borderRadius: '28px', offset: .5 },
      { transform: `translate(${tx}px,${ty}px) scale(0)`,          opacity: 0,  borderRadius: '50%'  }
    ], { duration: 360, easing: 'cubic-bezier(.4,0,.6,1)' });

    anim.onfinish = () => {
      panel.style.opacity = '0';
      fab.classList.remove('active');
      fab.innerHTML = '<i class="bi bi-stars"></i>';
      /* Piccolo pulse sul FAB: ricorda all'utente dove è andato il panel */
      fab.animate([
        { transform: 'scale(1)'    },
        { transform: 'scale(1.25)' },
        { transform: 'scale(1)'    }
      ], { duration: 340, easing: 'ease-out' });
      _animating = false;
    };
  }

  function clearHistory() {
    history = [];
    showWelcome();
  }

  // -------------------------------------------------------------------------
  // Messaging
  // -------------------------------------------------------------------------
  function appendMessage(role, text, modelName) {
    const messages = document.getElementById('ai-messages');

    // Remove welcome if present
    const welcome = messages.querySelector('.ai-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = `ai-msg ai-msg-${role}`;
    div.textContent = text;
    if (role === 'model' && modelName) {
      const small = document.createElement('small');
      small.textContent = modelName;
      div.appendChild(small);
    }
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  function showTyping(show) {
    document.getElementById('ai-typing').style.display = show ? 'flex' : 'none';
    if (show) {
      const m = document.getElementById('ai-messages');
      m.scrollTop = m.scrollHeight;
    }
  }

  async function sendMessage() {
    const input = document.getElementById('ai-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    autoResize.call(input);

    appendMessage('user', text);
    history.push({ role: 'user', text });
    showTyping(true);

    try {
      const resp = await fetch(CHAT_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrf(),
        },
        body: JSON.stringify({ message: text, history: history.slice(-12) }),
      });
      const data = await resp.json();
      showTyping(false);

      if (data.error) {
        appendMessage('model', 'Errore: ' + data.error);
        return;
      }

      appendMessage('model', data.response, data.model);
      history.push({ role: 'model', text: data.response });

    } catch (err) {
      showTyping(false);
      appendMessage('model', 'Errore di rete. Controlla la connessione.');
    }
  }

  function autoResize() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 96) + 'px';
  }

  // -------------------------------------------------------------------------
  // Web Speech API (voice input)
  // -------------------------------------------------------------------------
  function setupSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      document.getElementById('ai-voice-btn').style.display = 'none';
      return;
    }

    recognition = new SpeechRecognition();
    recognition.lang = 'it-IT';
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = e => {
      let interim = '';
      let final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      recognition_final += final;
      const display = recognition_final + interim;
      document.getElementById('ai-voice-text').textContent = display || 'In ascolto…';
      document.getElementById('ai-input').value = display;
    };

    recognition.onend = () => {
      setListening(false);
      // Auto-send if we have a transcript
      const input = document.getElementById('ai-input');
      if (input.value.trim()) {
        // Optional: short delay then send
        sendMessage();
      }
    };

    recognition.onerror = e => {
      setListening(false);
      if (e.error !== 'no-speech') {
        document.getElementById('ai-voice-text').textContent = 'Errore microfono: ' + e.error;
        setTimeout(() => {
          document.getElementById('ai-voice-status').style.display = 'none';
        }, 2000);
      }
    };
  }

  function toggleVoice() {
    if (!recognition) return;
    isListening ? stopListening() : startListening();
  }

  function startListening() {
    recognition_final = '';
    document.getElementById('ai-input').value = '';
    setListening(true);
    recognition.start();
  }

  function stopListening() {
    setListening(false);
    try { recognition.stop(); } catch (_) {}
  }

  function setListening(val) {
    isListening = val;
    const btn = document.getElementById('ai-voice-btn');
    const status = document.getElementById('ai-voice-status');
    if (val) {
      btn.classList.add('listening');
      btn.innerHTML = '<i class="bi bi-mic-fill"></i>';
      status.style.display = 'block';
      document.getElementById('ai-voice-text').textContent = 'In ascolto…';
    } else {
      btn.classList.remove('listening');
      btn.innerHTML = '<i class="bi bi-mic"></i>';
      status.style.display = 'none';
    }
  }

  // -------------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------------
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
