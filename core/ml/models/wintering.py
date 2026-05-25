"""Overwintering-survival model — target #2.

Phase-2 mechanistic baseline: scores a colony's risk of *not* surviving winter
from its autumn state. Following beekeeping practice and literature, the
dominant driver is the autumn varroa load (a colony heavily infested in late
summer rears short-lived winter bees and collapses), followed by winter food
stores, autumn population/strength and queen status.

Score is a 0-100 *mortality risk* (higher = worse). As real winter outcomes
accumulate across pooled colonies, a fitted logistic / Cox layer will replace
the hand-tuned weights while keeping the same explanation contract.
"""

MODEL_VERSION = 'wintering-baseline-rules-v1'

# Score -> risk level, evaluated high-to-low.
_LEVELS = [(60, 'critico'), (35, 'alto'), (18, 'medio'), (0, 'basso')]

# A varroa treatment within this many days of the snapshot counts as "recent".
_RECENT_TREATMENT_DAYS = 60


def assess(features, is_autumn=True, n_controls=None, days_since_last_control=None):
    """Score winter-mortality risk from the autumn feature snapshot.

    Parameters
    ----------
    features : dict | None
        Autumn snapshot row from :func:`core.ml.features.select_autumn_snapshot`.
    is_autumn : bool
        Whether the snapshot is an actual autumn control (drives confidence).
    """
    if not features:
        return _no_data_result()

    f = features
    contribs = []  # (italian_label, signed_points)
    notes = []

    # 1 ── Autumn varroa load: the dominant mortality driver. ────────────────
    varroa = f.get('varroa_pct_latest')
    treated_recently = (
        f.get('days_since_treatment') is not None
        and f['days_since_treatment'] <= _RECENT_TREATMENT_DAYS
    )
    if varroa is None:
        notes.append('Carica varroa non misurata di recente: stima meno affidabile.')
    else:
        if varroa > 5:
            pts = 55
        elif varroa > 3:
            pts = 35
        elif varroa > 1:
            pts = 15
        else:
            pts = 0
        if pts:
            contribs.append((f'Varroa autunnale elevata ({varroa:.1f}%)', pts))
        if varroa > 3 and not treated_recently:
            contribs.append(('Varroa alta senza trattamento recente', 15))
        elif varroa > 3 and treated_recently:
            contribs.append(('Trattamento varroa recente', -10))

    # 2 ── Winter food stores (frames + recent supplemental feeding). ────────
    scorte = f.get('telaini_scorte')
    feeding = f.get('feeding_kg_trailing') or 0
    if scorte is not None:
        effective = scorte + min(4, feeding / 3.0)  # ~3 kg syrup ≈ 1 stores frame
        if effective < 2:
            contribs.append(('Scorte invernali molto scarse', 45))
        elif effective < 4:
            contribs.append(('Scorte invernali insufficienti', 28))
        elif effective < 5:
            contribs.append(('Scorte invernali al limite', 14))
    else:
        notes.append('Telaini di scorte non registrati: rischio di fame non valutabile.')

    # 3 ── Colony strength (autumn brood as winter-bee proxy). ───────────────
    covata = f.get('telaini_covata')
    if covata is not None:
        if covata < 2:
            contribs.append(('Colonia molto debole in autunno', 25))
        elif covata < 4:
            contribs.append(('Colonia debole in autunno', 12))

    # 4 ── Queen status. ─────────────────────────────────────────────────────
    if f.get('queen_sospetta_assente') or f.get('presenza_regina') is False:
        contribs.append(('Regina assente o sospetta', 30))
    elif not f.get('uova_fresche') and not f.get('regina_vista'):
        contribs.append(('Deposizione non confermata in autunno', 10))
    age = f.get('queen_age_days')
    if age is not None and age >= 1095:
        contribs.append(('Regina molto anziana (≥3 anni)', 10))

    # 5 ── Health problems. ──────────────────────────────────────────────────
    if f.get('problemi_sanitari'):
        contribs.append(('Problemi sanitari rilevati', 12))

    score = int(round(max(0, min(100, sum(p for _, p in contribs)))))
    level = _level_for(score)
    confidence, low_data, conf_notes = _confidence(f, is_autumn, n_controls, varroa)
    notes.extend(conf_notes)

    factors = [
        {'label': lbl, 'impact': int(round(pts))}
        for lbl, pts in sorted(contribs, key=lambda x: -abs(x[1]))[:4]
    ]

    return {
        'target': 'wintering_risk',
        'model': MODEL_VERSION,
        'score': score,
        'level': level,
        'probability': None,  # populated once a fitted survival layer exists
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


def _confidence(f, is_autumn, n_controls, varroa):
    notes = []
    low_data = False

    if not is_autumn:
        notes.append('Nessun controllo autunnale recente: valutazione indicativa.')
        low_data = True
    if varroa is None:
        low_data = True
    if f.get('telaini_scorte') is None:
        low_data = True
    if n_controls is not None and n_controls < 3:
        low_data = True
        notes.append('Pochi controlli storici: stima poco affidabile.')

    if low_data:
        confidence = 'bassa'
    elif is_autumn and varroa is not None and f.get('telaini_scorte') is not None:
        confidence = 'alta' if (n_controls or 0) >= 5 else 'media'
    else:
        confidence = 'media'

    return confidence, low_data, notes


def _summary(level, factors):
    drivers = ', '.join(fct['label'] for fct in factors if fct['impact'] > 0)
    if drivers:
        return f'Rischio invernamento {level}. Criticità: {drivers}.'
    return f'Rischio invernamento {level}: nessuna criticità rilevata.'


def _no_data_result():
    return {
        'target': 'wintering_risk',
        'model': MODEL_VERSION,
        'score': None,
        'level': None,
        'probability': None,
        'confidence': 'nessuna',
        'low_data': True,
        'factors': [],
        'summary': 'Dati insufficienti per stimare il rischio di invernamento.',
        'notes': ['Nessun controllo registrato per questa colonia.'],
    }
