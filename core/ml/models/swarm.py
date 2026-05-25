"""Swarm-risk model — target #1 (pilot).

Phase 1 ships a *mechanistic, rule-based* baseline that needs zero training data
and is fully interpretable: it scores a colony 0-100 from the signals beekeeping
practice treats as predictive of swarming, with charged queen cells as the
dominant driver. As labelled swarm events accumulate across pooled colonies, a
fitted logistic layer (``fit``/``predict_proba``) will replace the hand-tuned
weights while keeping the same explanation contract.

The output always carries (a) a level, (b) a confidence + low_data flag, and
(c) the top contributing factors in Italian for the UI — non-negotiable since
beekeepers must understand and trust the call (project_predictive_models memory).
"""

MODEL_VERSION = 'swarm-baseline-rules-v1'

# Score -> level thresholds, evaluated high-to-low.
_LEVELS = [(70, 'critico'), (45, 'alto'), (20, 'medio'), (0, 'basso')]

# Months treated as deep off-season (brood low, swarming implausible).
_OFF_SEASON_MONTHS = (11, 12, 1, 2)


def assess(features, n_controls=None, days_since_last_control=None):
    """Score swarm risk from the latest causal feature row.

    Parameters
    ----------
    features : dict | None
        A row from :func:`core.ml.features.latest_features`. ``None`` => no data.
    n_controls : int, optional
        Number of controls available for the colony (drives confidence).
    days_since_last_control : int, optional
        Staleness of the latest control (drives confidence).
    """
    if not features:
        return _no_data_result()

    f = features
    contribs = []  # (italian_label, signed_points)

    # 1 ── Queen cells: the dominant signal. ────────────────────────────────
    n_cells = int(f.get('numero_celle_reali') or 0)
    if f.get('celle_reali') or n_cells > 0:
        pts = 45 + min(25, 5 * max(0, n_cells - 1))
        label = 'Celle reali presenti'
        if n_cells:
            label += f' ({n_cells})'
        contribs.append((label, pts))

    # 2 ── Brood strength and rapid expansion (congestion proxy). ────────────
    covata = f.get('telaini_covata')
    if covata is not None and covata > 6:
        contribs.append(('Covata molto estesa', min(18, (covata - 6) * 4)))
    rate = f.get('covata_rate_day')
    if rate is not None and rate > 0.1:
        contribs.append(('Forte espansione della covata', min(12, round(rate * 40))))

    # 3 ── Seasonality (additive prior). ─────────────────────────────────────
    month = f.get('month')
    if f.get('in_swarm_season'):
        contribs.append(('Piena stagione di sciamatura', 8))
    elif month in _OFF_SEASON_MONTHS:
        contribs.append(('Fuori stagione (inverno)', -20))

    # 4 ── Queen age. ────────────────────────────────────────────────────────
    age = f.get('queen_age_days')
    if age is not None:
        if age >= 730:
            contribs.append(('Regina anziana (≥2 anni)', 8))
        elif age >= 365:
            contribs.append(('Regina di 1+ anno', 3))
        elif age < 60:
            contribs.append(('Regina molto giovane', -8))

    # 5 ── Beekeeper-rated swarming tendency of the line (1-5). ───────────────
    tend = f.get('queen_tendenza_sciamatura')
    if tend is not None:
        if tend >= 4:
            contribs.append(('Linea genetica incline a sciamare', (tend - 3) * 6))
        elif tend <= 2:
            contribs.append(('Linea genetica poco incline a sciamare', -(3 - tend) * 4))

    score = int(round(max(0, min(100, sum(p for _, p in contribs)))))
    level = _level_for(score)
    confidence, low_data, notes = _confidence(
        f, n_controls, days_since_last_control,
    )

    # Top factors by absolute impact for the UI explanation.
    factors = [
        {'label': lbl, 'impact': int(round(pts))}
        for lbl, pts in sorted(contribs, key=lambda x: -abs(x[1]))[:4]
    ]

    return {
        'target': 'swarm_risk',
        'model': MODEL_VERSION,
        'score': score,
        'level': level,
        'probability': None,  # populated once the fitted logistic layer exists
        'confidence': confidence,
        'low_data': low_data,
        'factors': factors,
        'summary': _summary(level, factors),
        'notes': notes,
    }


def _level_for(score):
    for threshold, name in _LEVELS:
        if score >= threshold:
            return name
    return 'basso'


def _confidence(f, n_controls, days_since_last_control):
    notes = []
    low_data = False

    if n_controls is not None and n_controls < 3:
        low_data = True
        notes.append('Pochi controlli storici: stima poco affidabile.')
    if f.get('telaini_covata') is None:
        low_data = True
        notes.append('Telaini di covata non registrati nell\'ultimo controllo.')
    if days_since_last_control is not None and days_since_last_control > 30:
        notes.append('Ultimo controllo non recente: il quadro potrebbe essere cambiato.')

    if low_data:
        confidence = 'bassa'
    elif (
        n_controls is not None and n_controls >= 5
        and (days_since_last_control or 0) <= 14
        and f.get('in_swarm_season')
    ):
        confidence = 'alta'
    else:
        confidence = 'media'

    if not f.get('in_swarm_season') and f.get('month') in _OFF_SEASON_MONTHS:
        notes.append('Periodo fuori stagione: rischio sciamatura naturalmente basso.')

    return confidence, low_data, notes


def _summary(level, factors):
    if not factors:
        return f'Rischio sciamatura {level}.'
    drivers = ', '.join(fct['label'] for fct in factors if fct['impact'] > 0)
    if drivers:
        return f'Rischio sciamatura {level}. Fattori principali: {drivers}.'
    return f'Rischio sciamatura {level}.'


def _no_data_result():
    return {
        'target': 'swarm_risk',
        'model': MODEL_VERSION,
        'score': None,
        'level': None,
        'probability': None,
        'confidence': 'nessuna',
        'low_data': True,
        'factors': [],
        'summary': 'Dati insufficienti per stimare il rischio di sciamatura.',
        'notes': ['Nessun controllo registrato per questa colonia.'],
    }
