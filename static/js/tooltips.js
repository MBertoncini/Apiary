/**
 * Contextual tooltip system — shows once per section, tracked via localStorage
 * Also provides addHelpIcon() for inline form help
 */

// ── 1. SECTION TOOLTIPS (show once, then never again) ────────────────────────

class ApiaryTooltip {
    constructor(key, targetSelector, message) {
        this.key = `apiary_tooltip_${key}`;
        this.targetSelector = targetSelector;
        this.message = message;
    }

    shouldShow() { return !localStorage.getItem(this.key); }
    markShown()  { localStorage.setItem(this.key, '1'); }

    show() {
        if (!this.shouldShow()) return;
        const target = document.querySelector(this.targetSelector);
        if (!target) return;

        const tip = document.createElement('div');
        tip.className = 'apiary-section-tooltip';
        tip.innerHTML = `
            <span class="ast-text">${this.message}</span>
            <button class="ast-close" aria-label="Chiudi">&times;</button>
        `;

        // Insert after target
        target.parentNode.insertBefore(tip, target.nextSibling);

        tip.querySelector('.ast-close').addEventListener('click', () => {
            tip.remove();
            this.markShown();
        });

        // Auto-dismiss after 10s
        setTimeout(() => { if (tip.parentNode) { tip.remove(); this.markShown(); } }, 10000);
        this.markShown();
    }
}

const SECTION_TOOLTIPS = {
    dashboard: new ApiaryTooltip(
        'dashboard_v1',
        '.page-header, h1.page-title',
        '👋 Benvenuto nella dashboard — qui trovi il riepilogo di tutte le tue attività: arnie, controlli recenti e raccolti.'
    ),
    apiario: new ApiaryTooltip(
        'apiario_detail_v1',
        '.card:first-of-type .card-header, .page-header',
        '🏠 Qui trovi le arnie del tuo apiario. Clicca su un\'arnia per aprirla e registrare un controllo.'
    ),
    controllo: new ApiaryTooltip(
        'controllo_form_v1',
        '.frame-editor-card .card-header, #controlloForm',
        '📋 Usa il configuratore dei telaini per rappresentare la disposizione nell\'arnia. Clicca o trascina per dipingere ogni telaino.'
    ),
    analisi_telaino: new ApiaryTooltip(
        'analisi_telaino_v1',
        '.drop-zone, .step-wizard',
        '📷 Consiglio: scatta la foto con luce naturale diffusa e tieni il telaio parallelo alla fotocamera per risultati ottimali.'
    ),
};

document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;
    if (path === '/dashboard/' || path === '/dashboard') {
        setTimeout(() => SECTION_TOOLTIPS.dashboard.show(), 1200);
    } else if (path.match(/\/apiario\/\d+\/?$/)) {
        setTimeout(() => SECTION_TOOLTIPS.apiario.show(), 800);
    } else if (path.includes('/controllo/') || path.includes('nuovo_controllo') || path.match(/\/arnia\/\d+\/controllo/)) {
        setTimeout(() => SECTION_TOOLTIPS.controllo.show(), 600);
    } else if (path.includes('analisi-telaino') || path.includes('analisi_telaino')) {
        setTimeout(() => SECTION_TOOLTIPS.analisi_telaino.show(), 600);
    }
});


// ── 2. INLINE FIELD HELP ICONS ────────────────────────────────────────────────
// Call addHelpIcon(fieldId, helpText) after DOMContentLoaded in any template

window.addHelpIcon = function(fieldId, helpText) {
    const label = document.querySelector(`label[for="${fieldId}"]`);
    if (!label) return;

    const icon = document.createElement('span');
    icon.className = 'field-help-icon';
    icon.setAttribute('tabindex', '0');
    icon.setAttribute('role', 'button');
    icon.setAttribute('aria-label', 'Aiuto');
    icon.innerHTML = '?';
    icon.dataset.helpText = helpText;
    label.appendChild(icon);

    // Show popover on click/focus
    let popover = null;
    const toggle = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (popover) { popover.remove(); popover = null; return; }

        popover = document.createElement('div');
        popover.className = 'field-help-popover';
        popover.innerHTML = helpText;
        icon.parentNode.style.position = 'relative';
        icon.parentNode.appendChild(popover);

        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', function handler() {
                if (popover) { popover.remove(); popover = null; }
                document.removeEventListener('click', handler);
            });
        }, 10);
    };

    icon.addEventListener('click', toggle);
    icon.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') toggle(e); });
};
