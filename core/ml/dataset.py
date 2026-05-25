"""Single source of truth for a colony's raw ML time series.

``build_colonia_dataset(colonia)`` returns a plain dict of parallel, date-ordered
lists. It is consumed by:

  * the REST endpoint ``ml_dataset_colonia`` (HTTP export for inspection/debug),
  * the feature pipeline (``core.ml.features``) for both inference and training.

Training over many colonies (cross-user pooling) calls this function directly on
ORM objects, avoiding per-colony HTTP round-trips. Extend feature collection HERE,
not in parallel endpoints.
"""

from datetime import date, timedelta

from collections import defaultdict

from core.models import (
    ControlloArnia, PesataMelario, Smielatura, SmielaturaMelario, Alimentazione,
    VarroaCheckpoint, TrattamentoSanitario, MeteoGiornaliero, NomadismoEvent,
    Fioritura, Regina, StoriaRegine,
)

# How many days of daily weather to attach. Kept here so the endpoint and the
# training pipeline stay consistent.
METEO_WINDOW_DAYS = 365


def build_colonia_dataset(colonia, meteo_days=METEO_WINDOW_DAYS):
    """Gather the full raw time series for a single colony.

    Parameters
    ----------
    colonia : core.models.Colonia
        Already-fetched colony instance (caller is responsible for access checks).
    meteo_days : int
        Size of the trailing daily-weather window to include.

    Returns
    -------
    dict
        Parallel date-ordered lists. See module docstring.
    """
    controlli = list(
        ControlloArnia.objects.filter(colonia=colonia).values(
            'id', 'data', 'telaini_covata', 'telaini_scorte',
            'presenza_regina', 'regina_vista', 'uova_fresche',
            'celle_reali', 'numero_celle_reali', 'sciamatura', 'data_sciamatura',
            'problemi_sanitari', 'regina_sostituita', 'sostituzione_scatola',
        ).order_by('data')
    )

    pesate = list(
        PesataMelario.objects.filter(colonia=colonia).values(
            'id', 'data', 'tipo', 'melario_id', 'fioritura_id',
            'smielatura_id', 'peso_lordo_kg', 'tara_kg', 'peso_netto_kg',
        ).order_by('data')
    )

    smielature = list(
        SmielaturaMelario.objects.filter(melario__colonia=colonia)
        .select_related('smielatura')
        .values(
            'smielatura_id', 'smielatura__data', 'smielatura__tipo_miele',
            'kg_miele', 'melario_id',
        ).order_by('smielatura__data')
    )

    # Eventi di raccolto aggregati per smielatura: kg attribuiti a QUESTA colonia
    # + fioriture d'origine (M2M Smielatura.fioriture). È l'unità target del
    # modello produzione miele per-colonia.
    smielature_eventi = _aggrega_smielature(smielature)

    alimentazioni = list(
        Alimentazione.objects.filter(colonia=colonia).values(
            'id', 'data', 'tipo', 'scopo', 'quantita_kg',
        ).order_by('data')
    )

    varroa = list(
        VarroaCheckpoint.objects.filter(colonia=colonia).values(
            'id', 'data_campionamento', 'metodo',
            'percentuale_calcolata', 'caduta_giornaliera', 'confidenza',
            'telaini_covata',
        ).order_by('data_campionamento')
    )

    trattamenti = list(
        TrattamentoSanitario.objects.filter(colonie=colonia)
        .exclude(stato='annullato').values(
            'id', 'data_inizio', 'data_fine', 'data_fine_sospensione',
            'tipo_trattamento_id', 'tipo_trattamento__nome',
            'tipo_trattamento__principio_attivo',
            'blocco_covata_attivo', 'data_inizio_blocco', 'data_fine_blocco',
        ).order_by('data_inizio')
    )

    cutoff = date.today() - timedelta(days=meteo_days)
    meteo = list(
        MeteoGiornaliero.objects.filter(
            apiario=colonia.apiario, data__gte=cutoff,
        ).values(
            'data', 'temp_min', 'temp_max', 'temp_mean',
            'precip_mm', 'precip_hours', 'umidita_media',
            'vento_medio', 'pressione_media',
            'ore_sole', 'radiazione_mj', 'gdd_base10', 'source',
        ).order_by('data')
    )

    nomadismi = list(
        NomadismoEvent.objects.filter(colonia=colonia).values(
            'id', 'data_spostamento',
            'apiario_origine_id', 'apiario_destinazione_id', 'motivo',
        ).order_by('data_spostamento')
    )

    fioriture = list(
        Fioritura.objects.filter(apiario=colonia.apiario).values(
            'id', 'pianta', 'data_inizio', 'data_fine', 'intensita',
            'latitudine', 'longitudine',
        ).order_by('data_inizio')
    )

    # ── Regina: not in the legacy endpoint, but a strong swarm/longevity signal ──
    regina = _regina_snapshot(colonia)
    storia_regine = list(
        StoriaRegine.objects.filter(colonia=colonia).values(
            'id', 'regina_id', 'data_inizio', 'data_fine', 'motivo_fine',
        ).order_by('data_inizio')
    ) if _has_storia_regine_fields() else []

    return {
        'colonia': {
            'id': colonia.id,
            'apiario_id': colonia.apiario_id,
            'apiario_nome': colonia.apiario.nome,
            'data_inizio': colonia.data_inizio,
            'data_fine': colonia.data_fine,
            'stato': colonia.stato,
        },
        'controlli': controlli,
        'pesate_melari': pesate,
        'smielature': smielature,
        'smielature_eventi': smielature_eventi,
        'alimentazioni': alimentazioni,
        'varroa': varroa,
        'trattamenti': trattamenti,
        'meteo_giornaliero': meteo,
        'nomadismi': nomadismi,
        'fioriture': fioriture,
        'regina': regina,
        'storia_regine': storia_regine,
    }


def _regina_snapshot(colonia):
    """Current queen summary: age (days) and user-rated swarming tendency."""
    regina = Regina.objects.filter(colonia=colonia).first()
    if regina is None:
        return None
    eta_giorni = regina.get_eta_giorni()
    return {
        'id': regina.id,
        'data_nascita': regina.data_nascita,
        'data_introduzione': regina.data_introduzione,
        'origine': regina.origine,
        'razza': regina.razza,
        'eta_giorni': eta_giorni,
        'tendenza_sciamatura': regina.tendenza_sciamatura,  # 1-5 user rating, may be None
        'sospetta_assente': regina.sospetta_assente,
    }


def _has_storia_regine_fields():
    """StoriaRegine field names vary across migrations; guard the optional query."""
    field_names = {f.name for f in StoriaRegine._meta.get_fields()}
    return {'data_inizio'}.issubset(field_names)


def _aggrega_smielature(smielature_per_melario):
    """Aggrega le righe per-melario in eventi di raccolto (uno per smielatura).

    Somma ``kg_miele`` attribuiti ai melari della colonia e allega le fioriture
    d'origine (M2M ``Smielatura.fioriture``). ``kg_miele`` può essere None se
    l'utente non l'ha attribuito: in quel caso ``kg_attribuiti_completi`` è False
    e il consumatore decide se stimarlo dalle pesate.
    """
    grouped = defaultdict(lambda: {
        'data': None, 'tipo_miele': None, 'kg': 0.0,
        'n_melari': 0, 'n_kg_mancanti': 0,
    })
    for r in smielature_per_melario:
        g = grouped[r['smielatura_id']]
        g['data'] = r['smielatura__data']
        g['tipo_miele'] = r['smielatura__tipo_miele']
        g['n_melari'] += 1
        kg = r['kg_miele']
        if kg is None:
            g['n_kg_mancanti'] += 1
        else:
            g['kg'] += float(kg)

    if not grouped:
        return []

    fioriture_per_smielatura = {
        sm.id: list(sm.fioriture.values_list('id', flat=True))
        for sm in Smielatura.objects.filter(id__in=grouped.keys())
        .prefetch_related('fioriture')
    }

    eventi = []
    for sid, g in grouped.items():
        eventi.append({
            'smielatura_id': sid,
            'data': g['data'],
            'tipo_miele': g['tipo_miele'],
            'kg_colonia': round(g['kg'], 2),
            'n_melari': g['n_melari'],
            'kg_attribuiti_completi': g['n_kg_mancanti'] == 0,
            'fioriture': fioriture_per_smielatura.get(sid, []),
        })
    eventi.sort(key=lambda e: (e['data'] or date.min))
    return eventi
