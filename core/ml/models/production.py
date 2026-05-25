"""Honey-production model (per-colony) — target #3, the stated primary goal.

This is a *regression*, not a risk level, and its natural unit is the colony-
harvest / colony-season. With only 1-2 seasons of data a full multi-feature
fit would overfit, so Phase-3 ships a **mechanistic nectar-potential index**
plus a **lightweight ridge calibration** of a single scaling coefficient toward
a regional default, using the colony's own past harvests (pure Python, no new
deps).

    nectar_potential = Σ_flowerings ( intensity × duration × forager_force ×
                                      good_weather_fraction )
    expected_kg      = alpha × nectar_potential

``alpha`` is calibrated per colony with shrinkage toward ``DEFAULT_KG_PER_UNIT``
so a colony with no history borrows the regional prior and one with history is
pulled toward its own yield. The *pooled, cross-colony* global alpha (and, later,
per-plant coefficients via statsmodels/scikit) is computed where all colonies
are visible — the backtest command now, a persisted training step in F4.

Honesty contract: when there is no calibration data the absolute kg is a rough
prior-based estimate, flagged low-confidence with a wide interval; the trustworthy
signal is the *relative* potential and the drivers. The realized ``last_season_kg``
is returned alongside so the user can sanity-check model vs reality.
"""

from datetime import date, datetime, timedelta

MODEL_VERSION = 'production-nectar-index-v1'

# Regional prior: kg of honey per unit of nectar potential, used when the colony
# (or pool) has no calibration data yet. Deliberately rough — see module docstring.
DEFAULT_KG_PER_UNIT = 0.6
# Ridge strength: how strongly alpha is pulled toward the prior. ~half an
# observation's worth of evidence, so 2+ harvests start to dominate.
RIDGE_LAMBDA = 50.0

# Foraging-weather thresholds (per day) from MeteoGiornaliero.
_GOOD_TEMP_MEAN = 12.0   # °C
_MAX_GOOD_PRECIP = 5.0   # mm
_NEUTRAL_WEATHER = 0.6   # assumed good-day fraction when weather is unknown

# Default flowering length when data_fine is missing.
_DEFAULT_FLOWERING_DAYS = 21
# Foragers come from brood reared ~3 weeks earlier; match controls within this.
_FORCE_MATCH_DAYS = 35
_REFERENCE_BROOD_FRAMES = 6.0  # telaini_covata that maps to force = 1.0


def assess(dataset, year=None):
    """Forward estimate of honey production for ``year`` (default: current)."""
    year = year or date.today().year
    covata_points = _covata_points(dataset)
    meteo_by_day = _meteo_by_day(dataset)
    fioriture = dataset.get('fioriture', [])

    # Nectar potential from flowerings overlapping the target year.
    contributions = []  # (pianta, potential)
    for fior in fioriture:
        start = _as_date(fior.get('data_inizio'))
        if start is None:
            continue
        end = _as_date(fior.get('data_fine')) or (start + timedelta(days=_DEFAULT_FLOWERING_DAYS))
        if end.year < year or start.year > year:
            continue
        pot = _flowering_potential(fior, covata_points, meteo_by_day)
        if pot > 0:
            contributions.append((fior.get('pianta') or 'Fioritura', pot))

    total_potential = round(sum(p for _, p in contributions), 2)

    # Calibrate alpha (ridge toward prior) on this colony's realized harvests.
    observations = production_observations(dataset, covata_points, meteo_by_day)
    alpha, n_obs = calibrate_alpha(observations)

    realized = [o['kg'] for o in observations]
    last_season_kg = _last_season_kg(observations)

    notes = []
    weather_known = len(meteo_by_day) > 0
    feeding_kg = _season_feeding(dataset, year)

    if total_potential == 0:
        return _no_potential_result(year, last_season_kg, fioriture)

    expected = round(alpha * total_potential, 1)
    rel = _interval_halfwidth(n_obs)
    kg_low = round(max(0.0, expected * (1 - rel)), 1)
    kg_high = round(expected * (1 + rel), 1)

    confidence, low_data = _confidence(n_obs, weather_known, len(contributions))
    if not weather_known:
        notes.append('Meteo storico assente per il periodo: assunta una stagione media.')
    if feeding_kg > 0:
        notes.append(
            f'Registrati {feeding_kg:.1f} kg di nutrizione: il miele raccolto '
            'va tenuto distinto dalle scorte da sciroppo.'
        )
    if n_obs == 0:
        basis = 'stima preliminare: nessuno storico di raccolto, uso il default regionale'
        notes.append('Senza raccolti passati la stima assoluta è indicativa; '
                     'affidabile soprattutto il confronto tra fioriture/colonie.')
    else:
        basis = f'calibrato su {n_obs} raccolto/i di questa colonia'

    # Drivers: top flowerings by estimated kg contribution.
    factors = [
        {'label': pianta, 'kg': round(alpha * pot, 1)}
        for pianta, pot in sorted(contributions, key=lambda x: -x[1])[:4]
    ]

    return {
        'target': 'honey_production',
        'model': MODEL_VERSION,
        'unit': 'kg',
        'year': year,
        'expected_kg': expected,
        'kg_low': kg_low,
        'kg_high': kg_high,
        'nectar_potential': total_potential,
        'last_season_kg': last_season_kg,
        'feeding_kg': round(feeding_kg, 1),
        'confidence': confidence,
        'low_data': low_data,
        'factors': factors,
        'summary': _summary(expected, kg_low, kg_high, year),
        'notes': notes,
        'basis': basis,
    }


# ── Shared building blocks (also used by the backtest) ───────────────────────

def production_observations(dataset, covata_points=None, meteo_by_day=None):
    """Realized harvests with their nectar potential, for calibration/backtest.

    One entry per harvest event with attributed kg > 0:
    ``{date, kg, potential}``. The potential uses the harvest's linked flowerings
    (``Smielatura.fioriture``); if none were tagged, it falls back to flowerings
    active in the weeks before the harvest.
    """
    covata_points = covata_points if covata_points is not None else _covata_points(dataset)
    meteo_by_day = meteo_by_day if meteo_by_day is not None else _meteo_by_day(dataset)
    fioriture_by_id = {f['id']: f for f in dataset.get('fioriture', [])}

    obs = []
    for ev in dataset.get('smielature_eventi', []):
        kg = ev.get('kg_colonia') or 0.0
        h_date = _as_date(ev.get('data'))
        if kg <= 0 or h_date is None:
            continue
        linked = [fioriture_by_id[i] for i in ev.get('fioriture', []) if i in fioriture_by_id]
        if not linked:
            linked = _flowerings_before(dataset.get('fioriture', []), h_date, days=42)
        potential = sum(
            _flowering_potential(f, covata_points, meteo_by_day) for f in linked
        )
        if potential > 0:
            obs.append({'date': h_date, 'kg': float(kg), 'potential': round(potential, 3)})
    return obs


def calibrate_alpha(observations, prior=DEFAULT_KG_PER_UNIT, lam=RIDGE_LAMBDA):
    """Ridge estimate of alpha = kg / potential, shrunk toward ``prior``.

    Minimises Σ(kg - α·p)² + λ(α - prior)²  →
        α = (Σ p·kg + λ·prior) / (Σ p² + λ)
    With zero observations this returns ``prior`` exactly.
    """
    sp2 = sum(o['potential'] ** 2 for o in observations)
    spk = sum(o['potential'] * o['kg'] for o in observations)
    alpha = (spk + lam * prior) / (sp2 + lam)
    return alpha, len(observations)


def _flowering_potential(fior, covata_points, meteo_by_day):
    start = _as_date(fior.get('data_inizio'))
    if start is None:
        return 0.0
    end = _as_date(fior.get('data_fine')) or (start + timedelta(days=_DEFAULT_FLOWERING_DAYS))
    duration = max(1, (end - start).days)
    intensity = _intensity_weight(fior.get('intensita'))
    force = _force_at(covata_points, start + timedelta(days=duration // 2))
    weather = _good_weather_fraction(meteo_by_day, start, end)
    return intensity * duration * force * weather


# ── Helpers ──────────────────────────────────────────────────────────────────

def _intensity_weight(intensita):
    # Fioritura.intensita is 1 (Scarsa) .. 5 (Eccezionale); None -> moderate.
    if intensita is None:
        return 0.5
    return {1: 0.2, 2: 0.4, 3: 0.6, 4: 0.8, 5: 1.0}.get(int(intensita), 0.5)


def _force_at(covata_points, ref_date):
    if not covata_points:
        return 1.0
    best = min(covata_points, key=lambda p: abs((p[0] - ref_date).days))
    if abs((best[0] - ref_date).days) > _FORCE_MATCH_DAYS:
        return 1.0
    return max(0.3, min(2.0, best[1] / _REFERENCE_BROOD_FRAMES))


def _good_weather_fraction(meteo_by_day, start, end):
    if not meteo_by_day:
        return _NEUTRAL_WEATHER
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    known = [meteo_by_day[d] for d in days if d in meteo_by_day]
    if not known:
        return _NEUTRAL_WEATHER
    good = sum(
        1 for m in known
        if (m.get('temp_mean') is None or m['temp_mean'] >= _GOOD_TEMP_MEAN)
        and (m.get('precip_mm') or 0) < _MAX_GOOD_PRECIP
    )
    return good / len(known)


def _covata_points(dataset):
    pts = []
    for c in dataset.get('controlli', []):
        d = _as_date(c.get('data'))
        cov = c.get('telaini_covata')
        if d is not None and cov is not None:
            pts.append((d, float(cov)))
    pts.sort(key=lambda x: x[0])
    return pts


def _meteo_by_day(dataset):
    out = {}
    for m in dataset.get('meteo_giornaliero', []):
        d = _as_date(m.get('data'))
        if d is not None:
            out[d] = m
    return out


def _flowerings_before(fioriture, ref_date, days=42):
    window_start = ref_date - timedelta(days=days)
    out = []
    for f in fioriture:
        start = _as_date(f.get('data_inizio'))
        if start is None:
            continue
        end = _as_date(f.get('data_fine')) or (start + timedelta(days=_DEFAULT_FLOWERING_DAYS))
        if start <= ref_date and end >= window_start:
            out.append(f)
    return out


def _season_feeding(dataset, year):
    total = 0.0
    for a in dataset.get('alimentazioni', []):
        d = _as_date(a.get('data'))
        kg = a.get('quantita_kg')
        if d is not None and d.year == year and kg is not None:
            total += float(kg)
    return total


def _last_season_kg(observations):
    if not observations:
        return None
    last_year = max(o['date'].year for o in observations)
    return round(sum(o['kg'] for o in observations if o['date'].year == last_year), 1)


def _interval_halfwidth(n_obs):
    # Wide when uncalibrated, tightening as harvests accumulate.
    return {0: 0.5, 1: 0.4}.get(n_obs, 0.3)


def _confidence(n_obs, weather_known, n_flowerings):
    if n_obs == 0:
        return 'bassa', True
    if n_obs >= 2 and weather_known and n_flowerings > 0:
        return 'media', False
    return 'bassa', n_obs < 1


def _summary(expected, kg_low, kg_high, year):
    return (f'Produzione attesa {year}: ~{expected:.0f} kg '
            f'(indicativamente {kg_low:.0f}-{kg_high:.0f} kg).')


def _no_potential_result(year, last_season_kg, fioriture):
    note = ('Nessuna fioritura registrata per il periodo: senza fioriture '
            'georeferenziate non posso stimare il potenziale nettarifero.')
    if fioriture:
        note = ('Nessuna fioritura attiva nel periodo stimato: la produzione '
                'attesa dipende dalle fioriture della stagione.')
    return {
        'target': 'honey_production',
        'model': MODEL_VERSION,
        'unit': 'kg',
        'year': year,
        'expected_kg': None,
        'kg_low': None,
        'kg_high': None,
        'nectar_potential': 0.0,
        'last_season_kg': last_season_kg,
        'feeding_kg': None,
        'confidence': 'nessuna',
        'low_data': True,
        'factors': [],
        'summary': 'Potenziale produttivo non stimabile per il periodo.',
        'notes': [note],
        'basis': 'nessuna fioritura utilizzabile',
    }


def _as_date(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)[:10]).date()
