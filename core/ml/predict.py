"""Inference orchestration: colony -> predictions for all available targets.

Single entry point shared by the REST endpoint and any management command, so
the wiring (dataset -> features -> per-target models) lives in one place.
"""

from datetime import date

from core.ml.dataset import build_colonia_dataset
from core.ml.features import colony_feature_frame, select_autumn_snapshot
from core.ml.models import swarm, wintering, production


def predict_colonia(colonia, dataset=None):
    """Run every available predictive target for one colony.

    Returns a JSON-serialisable dict: colony meta + ``predictions`` keyed by
    target. Currently ``swarm_risk`` and ``wintering_risk``; production slots in
    here as its module lands.
    """
    if dataset is None:
        dataset = build_colonia_dataset(colonia)

    rows = colony_feature_frame(dataset)
    n_controls = len(rows)
    latest = rows[-1] if rows else None
    days_since = (
        (date.today() - date.fromisoformat(latest['data'])).days if latest else None
    )

    # Swarm risk: assessed from the most recent control.
    swarm_result = swarm.assess(
        latest, n_controls=n_controls, days_since_last_control=days_since,
    )

    # Wintering risk: assessed from the autumn snapshot (falls back to latest).
    autumn_row, is_autumn = select_autumn_snapshot(rows)
    days_since_autumn = (
        (date.today() - date.fromisoformat(autumn_row['data'])).days
        if autumn_row else None
    )
    wintering_result = wintering.assess(
        autumn_row, is_autumn=is_autumn,
        n_controls=n_controls, days_since_last_control=days_since_autumn,
    )

    # Honey production: seasonal regression over the dataset (no feature row).
    production_result = production.assess(dataset)

    meta = dataset.get('colonia', {})
    return {
        'colonia_id': meta.get('id'),
        'apiario_id': meta.get('apiario_id'),
        'stato': meta.get('stato'),
        'as_of': latest['data'] if latest else None,
        'n_controls': n_controls,
        'predictions': {
            'swarm_risk': swarm_result,
            'wintering_risk': wintering_result,
            'honey_production': production_result,
        },
    }
