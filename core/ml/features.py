"""Feature engineering: raw colony dataset -> tidy observation grid.

The observation unit is a *control event* (one ``ControlloArnia``), which is the
moment a beekeeper actually observed the colony. Each row carries only causal
features (nothing from the future of that date) so the same rows are valid for
both inference (use the latest row) and honest backtesting.

Forward-looking labels (e.g. "did this colony swarm within N weeks?") are added
separately by :func:`attach_swarm_labels`, never mixed into the features.

Weekly resampling for the production model can be layered on top later; each row
already carries its ISO ``(year, week)`` bucket.
"""

from datetime import date, datetime, timedelta

# Trailing window over which we accumulate growing-degree-days as a phenology proxy.
GDD_WINDOW_DAYS = 21
# Northern-hemisphere swarm season (Italy). Used as a soft seasonal prior.
SWARM_SEASON_MONTHS = (4, 5, 6)
# Autumn window used to assess winter readiness (Northern hemisphere).
AUTUMN_MONTHS = (9, 10, 11)
# Trailing window over which we sum supplemental feeding (kg) as a stores proxy.
FEEDING_WINDOW_DAYS = 60


def _as_date(v):
    """Coerce ORM dates / ISO strings / datetimes to a plain ``date``."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return datetime.fromisoformat(str(v)[:10]).date()


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def colony_feature_frame(dataset):
    """Build the causal observation grid for one colony.

    Parameters
    ----------
    dataset : dict
        Output of :func:`core.ml.dataset.build_colonia_dataset`.

    Returns
    -------
    list[dict]
        One row per control event, date-ordered. Empty if no controls.
    """
    controlli = sorted(dataset.get('controlli', []), key=lambda c: _as_date(c['data']))
    if not controlli:
        return []

    gdd_by_day = _gdd_by_day(dataset.get('meteo_giornaliero', []))
    varroa_points = _varroa_points(dataset.get('varroa', []))
    treatment_intervals = _treatment_intervals(dataset.get('trattamenti', []))
    feeding_points = _feeding_points(dataset.get('alimentazioni', []))
    regina = dataset.get('regina') or {}
    q_birth = _as_date(regina.get('data_nascita'))
    q_intro = _as_date(regina.get('data_introduzione'))
    q_tendenza = regina.get('tendenza_sciamatura')
    q_sospetta = bool(regina.get('sospetta_assente'))

    rows = []
    prev = None
    for c in controlli:
        d = _as_date(c['data'])
        covata = _to_float(c.get('telaini_covata'))
        scorte = _to_float(c.get('telaini_scorte'))

        # Brood trend vs previous control (frames/day), causal.
        covata_delta = None
        covata_rate_day = None
        days_since_prev = None
        if prev is not None:
            pd = _as_date(prev['data'])
            days_since_prev = (d - pd).days
            pc = _to_float(prev.get('telaini_covata'))
            if covata is not None and pc is not None:
                covata_delta = covata - pc
                if days_since_prev and days_since_prev > 0:
                    covata_rate_day = covata_delta / days_since_prev

        # Queen age at the time of this control.
        queen_age_days = (d - q_birth).days if q_birth else None
        queen_days_in_colony = (d - q_intro).days if q_intro else None

        rows.append({
            'controllo_id': c.get('id'),
            'data': d.isoformat(),
            'iso_year': d.isocalendar()[0],
            'iso_week': d.isocalendar()[1],
            'month': d.month,
            'in_swarm_season': d.month in SWARM_SEASON_MONTHS,

            # ── Brood / stores ──────────────────────────────────────────────
            'telaini_covata': covata,
            'telaini_scorte': scorte,
            'covata_delta': covata_delta,
            'covata_rate_day': covata_rate_day,
            'days_since_prev_control': days_since_prev,

            # ── Queen / swarm signals (point-in-time) ───────────────────────
            'celle_reali': bool(c.get('celle_reali')),
            'numero_celle_reali': int(c.get('numero_celle_reali') or 0),
            'presenza_regina': c.get('presenza_regina'),
            'regina_vista': bool(c.get('regina_vista')),
            'uova_fresche': bool(c.get('uova_fresche')),
            'regina_sostituita': bool(c.get('regina_sostituita')),
            'problemi_sanitari': bool(c.get('problemi_sanitari')),
            'queen_age_days': queen_age_days,
            'queen_days_in_colony': queen_days_in_colony,
            'queen_tendenza_sciamatura': q_tendenza,
            'queen_sospetta_assente': q_sospetta,

            # ── Environment / health context ────────────────────────────────
            'gdd_trailing': _trailing_gdd(gdd_by_day, d, GDD_WINDOW_DAYS),
            'varroa_pct_latest': _latest_on_or_before(varroa_points, d),
            'under_treatment': _is_within_any(treatment_intervals, d),
            'days_since_treatment': _days_since_last_treatment(treatment_intervals, d),
            'feeding_kg_trailing': _trailing_sum(feeding_points, d, FEEDING_WINDOW_DAYS),

            # Raw swarm flag for THIS control (used by label builder, not as feature).
            '_sciamatura': bool(c.get('sciamatura')) or bool(c.get('data_sciamatura')),
        })
        prev = c

    return rows


def latest_features(dataset, as_of=None):
    """Return the most recent feature row at/at-before ``as_of`` (default: latest)."""
    rows = colony_feature_frame(dataset)
    if not rows:
        return None
    if as_of is None:
        return rows[-1]
    cutoff = _as_date(as_of)
    eligible = [r for r in rows if _as_date(r['data']) <= cutoff]
    return eligible[-1] if eligible else None


def attach_swarm_labels(rows, horizon_days=28):
    """Add a forward-looking ``swarm_within_horizon`` label to each row.

    For backtesting ONLY. A row is positive if any later control within
    ``horizon_days`` recorded a swarming event. Rows whose horizon extends past
    the last observation are marked ``label_censored=True`` (incomplete follow-up).
    """
    if not rows:
        return rows
    last_date = _as_date(rows[-1]['data'])
    swarm_dates = [_as_date(r['data']) for r in rows if r.get('_sciamatura')]
    for r in rows:
        d = _as_date(r['data'])
        window_end = d + timedelta(days=horizon_days)
        positive = any(d < sd <= window_end for sd in swarm_dates)
        censored = (not positive) and (window_end > last_date)
        r['swarm_within_horizon'] = positive
        r['label_censored'] = censored
    return rows


def select_autumn_snapshot(rows, ref_date=None):
    """Pick the colony's autumn state used to assess winter-survival risk.

    Returns ``(row, is_autumn)``. Prefers the latest control in the autumn
    window (months 9-11); falls back to the latest available row with
    ``is_autumn=False`` so the model can still answer (at lower confidence).
    """
    if not rows:
        return None, False
    candidates = rows
    if ref_date is not None:
        cutoff = _as_date(ref_date)
        candidates = [r for r in rows if _as_date(r['data']) <= cutoff]
        if not candidates:
            return None, False
    autumn = [r for r in candidates if r['month'] in AUTUMN_MONTHS]
    if autumn:
        return autumn[-1], True
    return candidates[-1], False


def wintering_label(dataset, snapshot_date, window_days=180):
    """Backtest label for the winter following ``snapshot_date``.

    Returns ``(died, censored)``:
      * ``died=True``  — colony recorded dead (stato 'morta') with ``data_fine``
        inside the window.
      * ``died=False, censored=False`` — a later control proves it survived past
        the window, or the colony is still active and the window has elapsed.
      * ``censored=True`` — insufficient follow-up to decide; exclude from metrics.
    """
    snap = _as_date(snapshot_date)
    window_end = snap + timedelta(days=window_days)
    meta = dataset.get('colonia', {})
    stato = meta.get('stato')
    data_fine = _as_date(meta.get('data_fine'))

    later_controls = [
        _as_date(c['data']) for c in dataset.get('controlli', [])
        if _as_date(c['data']) is not None and _as_date(c['data']) > snap
    ]
    seen_after_window = any(d > window_end for d in later_controls)

    if stato == 'morta' and data_fine is not None and snap < data_fine <= window_end:
        return True, False
    if seen_after_window:
        return False, False
    if stato == 'attiva' and data_fine is None and date.today() > window_end:
        return False, False
    return False, True


# ── Internal helpers ─────────────────────────────────────────────────────────

def _feeding_points(alimentazioni):
    pts = []
    for a in alimentazioni:
        d = _as_date(a.get('data'))
        kg = _to_float(a.get('quantita_kg'))
        if d is not None and kg is not None:
            pts.append((d, kg))
    pts.sort(key=lambda x: x[0])
    return pts


def _trailing_sum(points, end_date, window_days):
    if not points:
        return 0.0
    start = end_date - timedelta(days=window_days)
    return round(sum(kg for d, kg in points if start < d <= end_date), 2)

def _gdd_by_day(meteo):
    out = {}
    for m in meteo:
        d = _as_date(m.get('data'))
        gdd = _to_float(m.get('gdd_base10'))
        if d is not None and gdd is not None:
            out[d] = gdd
    return out


def _trailing_gdd(gdd_by_day, end_date, window_days):
    if not gdd_by_day:
        return None
    start = end_date - timedelta(days=window_days)
    total = sum(g for d, g in gdd_by_day.items() if start < d <= end_date)
    return round(total, 1)


def _varroa_points(varroa):
    pts = []
    for v in varroa:
        d = _as_date(v.get('data_campionamento'))
        pct = _to_float(v.get('percentuale_calcolata'))
        if d is not None and pct is not None:
            pts.append((d, pct))
    pts.sort(key=lambda x: x[0])
    return pts


def _latest_on_or_before(points, ref_date):
    val = None
    for d, pct in points:
        if d <= ref_date:
            val = pct
        else:
            break
    return val


def _treatment_intervals(trattamenti):
    intervals = []
    for t in trattamenti:
        start = _as_date(t.get('data_inizio'))
        end = _as_date(t.get('data_fine')) or _as_date(t.get('data_fine_sospensione')) or start
        if start is not None:
            intervals.append((start, end or start))
    intervals.sort(key=lambda x: x[0])
    return intervals


def _is_within_any(intervals, ref_date):
    return any(s <= ref_date <= e for s, e in intervals)


def _days_since_last_treatment(intervals, ref_date):
    ended = [e for s, e in intervals if e <= ref_date]
    if not ended:
        return None
    return (ref_date - max(ended)).days
