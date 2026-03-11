/**
 * Apiary — Notification Center
 * Gestisce il pannello dropdown notifiche nella topbar e il polling periodico.
 */
(function () {
  'use strict';

  const API_URL = '/notifiche/api/recenti/';
  const POLL_INTERVAL = 60000; // 60 secondi
  const CSRF = () => document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

  const badge      = document.getElementById('notificheBadge');
  const dropList   = document.getElementById('notificheDropList');
  const segnaBtn   = document.getElementById('segnaLetteTutte');

  // ---------- Helpers ----------
  function iconForTipo(tipo) {
    const map = {
      invito_gruppo:         '<i class="bi bi-person-plus-fill text-primary"></i>',
      invito_accettato:      '<i class="bi bi-check-circle-fill text-success"></i>',
      invito_rifiutato:      '<i class="bi bi-x-circle-fill text-danger"></i>',
      membro_aggiunto:       '<i class="bi bi-people-fill text-info"></i>',
      membro_rimosso:        '<i class="bi bi-person-dash-fill text-warning"></i>',
      fioritura_vicina:      '<i class="bi bi-flower1 text-warning"></i>',
      controllo_scaduto:     '<i class="bi bi-exclamation-triangle-fill text-warning"></i>',
      trattamento_scaduto:   '<i class="bi bi-capsule text-danger"></i>',
      trattamento_promemoria:'<i class="bi bi-capsule text-primary"></i>',
      regina_assente:        '<i class="bi bi-crown-fill text-danger"></i>',
      sistema:               '<i class="bi bi-info-circle-fill text-secondary"></i>',
    };
    return map[tipo] || map.sistema;
  }

  function updateBadge(count) {
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.classList.remove('d-none');
    } else {
      badge.classList.add('d-none');
    }
  }

  function renderDropList(notifiche) {
    if (!dropList) return;
    if (!notifiche.length) {
      dropList.innerHTML = `
        <div class="notifiche-empty">
          <i class="bi bi-bell-slash"></i>
          <p>Nessuna notifica</p>
        </div>`;
      return;
    }
    dropList.innerHTML = notifiche.map(n => `
      <div class="notifica-item ${n.letta ? '' : 'non-letta'} priorita-${n.priorita}"
           data-id="${n.id}" data-link="${n.link || ''}">
        <div class="notifica-icon">${iconForTipo(n.tipo)}</div>
        <div class="notifica-body">
          <div class="notifica-titolo">${escHtml(n.titolo)}</div>
          <div class="notifica-meta">${escHtml(n.data)}</div>
        </div>
        <button class="notifica-close" data-id="${n.id}" title="Elimina">
          <i class="bi bi-x"></i>
        </button>
      </div>`).join('');
    attachItemHandlers();
  }

  function escHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ---------- API calls ----------
  function fetchNotifiche() {
    fetch(API_URL, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(r => r.json())
      .then(data => {
        updateBadge(data.non_lette);
        renderDropList(data.notifiche);
      })
      .catch(() => {}); // silenzioso se offline
  }

  function segnaNotiLetta(id) {
    return fetch(`/notifiche/${id}/segna-letta/`, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': CSRF(),
      },
    }).then(r => r.json());
  }

  function eliminaNotifica(id) {
    return fetch(`/notifiche/${id}/elimina/`, {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': CSRF(),
      },
    }).then(r => r.json());
  }

  function segnaTutteLette() {
    return fetch('/notifiche/segna-tutte-lette/', {
      method: 'POST',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': CSRF(),
      },
    }).then(r => r.json());
  }

  // ---------- Event handlers ----------
  function attachItemHandlers() {
    if (!dropList) return;

    // Click su item → segna letta + naviga al link
    dropList.querySelectorAll('.notifica-item').forEach(function (item) {
      item.addEventListener('click', function (e) {
        if (e.target.closest('.notifica-close')) return; // gestito separatamente
        const id   = this.dataset.id;
        const link = this.dataset.link;
        segnaNotiLetta(id).then(data => {
          updateBadge(data.non_lette);
          if (link) window.location.href = link;
          else fetchNotifiche();
        });
      });
    });

    // Click su X → elimina notifica
    dropList.querySelectorAll('.notifica-close').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        const id   = this.dataset.id;
        const item = dropList.querySelector(`.notifica-item[data-id="${id}"]`);
        eliminaNotifica(id).then(data => {
          if (item) item.remove();
          updateBadge(data.non_lette);
          if (!dropList.querySelector('.notifica-item')) {
            dropList.innerHTML = `
              <div class="notifiche-empty">
                <i class="bi bi-bell-slash"></i>
                <p>Nessuna notifica</p>
              </div>`;
          }
        });
      });
    });
  }

  // Pulsante "Segna tutte lette" nel dropdown
  if (segnaBtn) {
    segnaBtn.addEventListener('click', function (e) {
      e.preventDefault();
      segnaTutteLette().then(data => {
        updateBadge(0);
        fetchNotifiche();
      });
    });
  }

  // Aggiorna lista al click sul campanello (se il dropdown Bootstrap sta aprendo)
  const bellBtn = document.getElementById('notificheBell');
  if (bellBtn) {
    bellBtn.addEventListener('click', fetchNotifiche);
  }

  // ---------- Init & polling ----------
  // Prima fetch al caricamento pagina (con leggero delay per non bloccare il render)
  setTimeout(fetchNotifiche, 1500);
  // Polling periodico
  setInterval(fetchNotifiche, POLL_INTERVAL);

})();
