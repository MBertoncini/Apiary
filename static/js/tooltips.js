/**
 * Contextual tooltip system — shows once per section, tracked via localStorage
 */

class ApiaryTooltip {
    constructor(key, targetSelector, message, placement = 'bottom') {
        this.key = `tooltip_shown_${key}`;
        this.targetSelector = targetSelector;
        this.message = message;
        this.placement = placement;
    }

    shouldShow() {
        return !localStorage.getItem(this.key);
    }

    markShown() {
        localStorage.setItem(this.key, '1');
    }

    show() {
        if (!this.shouldShow()) return;
        const target = document.querySelector(this.targetSelector);
        if (!target) return;

        const tooltip = document.createElement('div');
        tooltip.className = 'apiary-contextual-tooltip';
        tooltip.innerHTML = `
            <span class="tooltip-text">${this.message}</span>
            <button class="tooltip-close" aria-label="Chiudi">&#x2715;</button>
        `;

        // Position relative to target
        target.style.position = 'relative';
        target.appendChild(tooltip);

        // Close button
        tooltip.querySelector('.tooltip-close').addEventListener('click', () => {
            tooltip.remove();
            this.markShown();
        });

        // Auto-dismiss after 8 seconds
        setTimeout(() => {
            if (tooltip.parentNode) {
                tooltip.remove();
                this.markShown();
            }
        }, 8000);

        this.markShown();
    }
}

// Define contextual tooltips for each section
const TOOLTIPS = {
    dashboard: new ApiaryTooltip(
        'dashboard',
        '.dashboard-stats, .card:first-of-type, main .container-fluid',
        '👋 Qui trovi il riepilogo di tutte le tue attività — arnie, controlli recenti e raccolti.'
    ),
    arnie: new ApiaryTooltip(
        'arnie_list',
        '.arnie-list, .arnia-card:first-of-type, .list-group:first-of-type',
        '🏠 Le icone colorate indicano lo stato dell\'arnia: 🟢 ok, 🟡 attenzione, 🔴 critico.'
    ),
    controllo: new ApiaryTooltip(
        'controllo_form',
        '#id_forza_colonia, [name="forza_colonia"]',
        '💪 Forza colonia: quanti favi sono occupati dalle api. 1 = debolissima, 10 = fortissima.'
    ),
    analisi_telaino: new ApiaryTooltip(
        'analisi_telaino',
        '.upload-area, #id_immagine, [name="immagine"]',
        '📷 Usa luce naturale diffusa e tieni il telaio parallelo alla fotocamera per risultati ottimali.'
    ),
};

// Auto-detect current page and show appropriate tooltip
document.addEventListener('DOMContentLoaded', () => {
    const path = window.location.pathname;

    if (path.includes('/dashboard')) {
        setTimeout(() => TOOLTIPS.dashboard.show(), 1000);
    } else if (path.match(/\/apiario\/\d+\//)) {
        setTimeout(() => TOOLTIPS.arnie.show(), 800);
    } else if (path.includes('/controllo/')) {
        setTimeout(() => TOOLTIPS.controllo.show(), 600);
    } else if (path.includes('/analisi-telaino/') || path.includes('/analisi_telaino/')) {
        setTimeout(() => TOOLTIPS.analisi_telaino.show(), 600);
    }
});
