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

import math
from collections import defaultdict

from django.db.models import Q

from core.models import (
    Apiario, ControlloArnia, PesataMelario, Smielatura, SmielaturaMelario,
    Alimentazione, VarroaCheckpoint, TrattamentoSanitario, MeteoGiornaliero,
    NomadismoEvent, Fioritura, Regina, StoriaRegine,
)

# Minimum trailing window of daily weather. The window is extended back to the
# colony's start date, so that every past season keeps its weather.
METEO_WINDOW_DAYS = 365

# Flowerings within this distance of an apiary count as reachable forage even
# when they were registered on another apiary (or on none).
FIORITURE_VICINE_KM = 3.0


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

    # Attribution uses the colony snapshot taken when the super was linked to
    # the harvest. Rows created before the snapshot existed fall back to the
    # super's current colony.
    smielature = list(
        SmielaturaMelario.objects.filter(
            Q(colonia=colonia) | Q(colonia__isnull=True, melario__colonia=colonia)
        )
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

    nomadismi = list(
        NomadismoEvent.objects.filter(colonia=colonia).values(
            'id', 'data_spostamento',
            'apiario_origine_id', 'apiario_destinazione_id', 'motivo',
        ).order_by('data_spostamento', 'id')
    )

    # Where the colony actually was, period by period. Weather and flowerings
    # are taken from the apiary of each period, not just the current one.
    cutoff = date.today() - timedelta(days=meteo_days)
    if colonia.data_inizio and colonia.data_inizio < cutoff:
        cutoff = colonia.data_inizio
    permanenze = _permanenze(colonia, nomadismi, cutoff)

    meteo = []
    for p in permanenze:
        filtro = {'apiario_id': p['apiario_id'], 'data__gte': p['dal']}
        if p['al'] is not None:
            filtro['data__lt'] = p['al']
        meteo.extend(
            MeteoGiornaliero.objects.filter(**filtro).values(
                'data', 'apiario_id', 'temp_min', 'temp_max', 'temp_mean',
                'precip_mm', 'precip_hours', 'umidita_media',
                'vento_medio', 'pressione_media',
                'ore_sole', 'radiazione_mj', 'gdd_base10', 'source',
            )
        )
    meteo.sort(key=lambda m: m['data'])

    apiari_ids = {p['apiario_id'] for p in permanenze} | {colonia.apiario_id}
    apiari = {a.id: a for a in Apiario.objects.filter(id__in=apiari_ids)}

    fioriture = list(
        Fioritura.objects.filter(apiario_id__in=apiari_ids).values(
            'id', 'apiario_id', 'pianta', 'data_inizio', 'data_fine', 'intensita',
            'latitudine', 'longitudine',
        ).order_by('data_inizio')
    )
    fioriture_vicine = _fioriture_vicine(
        apiari.values(), escludi_ids={f['id'] for f in fioriture},
        utente_id=colonia.apiario.proprietario_id,
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
        'apiari': [_apiario_ambiente(a) for a in apiari.values()],
        'permanenze': permanenze,
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
        'fioriture_vicine': fioriture_vicine,
        'regina': regina,
        'storia_regine': storia_regine,
    }


def _permanenze(colonia, nomadismi, cutoff):
    """Periods spent in each apiary: ``[{apiario_id, dal, al}]`` (``al`` exclusive,
    None for the current one), clipped to start at ``cutoff``."""
    if not nomadismi:
        return [{'apiario_id': colonia.apiario_id, 'dal': cutoff, 'al': None}]

    periodi = []
    primo = nomadismi[0]
    origine = primo['apiario_origine_id']
    if origine and primo['data_spostamento'] > cutoff:
        periodi.append({'apiario_id': origine, 'dal': cutoff,
                        'al': primo['data_spostamento']})
    for i, ev in enumerate(nomadismi):
        fine = nomadismi[i + 1]['data_spostamento'] if i + 1 < len(nomadismi) else None
        if fine is not None and fine <= cutoff:
            continue
        inizio = max(ev['data_spostamento'], cutoff)
        if fine is not None and fine <= inizio:
            continue
        periodi.append({'apiario_id': ev['apiario_destinazione_id'],
                        'dal': inizio, 'al': fine})
    return periodi


def _apiario_ambiente(apiario):
    """Static site features of an apiary (position, terrain, land cover)."""
    return {
        'id': apiario.id,
        'latitudine': float(apiario.latitudine) if apiario.latitudine is not None else None,
        'longitudine': float(apiario.longitudine) if apiario.longitudine is not None else None,
        'altitudine_m': apiario.altitudine_m,
        'pendenza_gradi': apiario.pendenza_gradi,
        'esposizione': apiario.esposizione or None,
        'copertura_suolo': apiario.copertura_suolo or None,
    }


def _distanza_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _fioriture_vicine(apiari, escludi_ids, utente_id, raggio_km=FIORITURE_VICINE_KM):
    """Flowerings near the colony's apiaries that are not registered on them.

    Only the owner's own flowerings and public (community) ones are used.
    """
    out = {}
    for apiario in apiari:
        if apiario.latitudine is None or apiario.longitudine is None:
            continue
        lat, lon = float(apiario.latitudine), float(apiario.longitudine)
        dlat = raggio_km / 111.0
        dlon = raggio_km / (111.0 * max(0.01, math.cos(math.radians(lat))))
        candidati = Fioritura.objects.filter(
            Q(pubblica=True) | Q(creatore_id=utente_id),
            latitudine__range=(lat - dlat, lat + dlat),
            longitudine__range=(lon - dlon, lon + dlon),
        ).exclude(id__in=escludi_ids).values(
            'id', 'apiario_id', 'pianta', 'data_inizio', 'data_fine', 'intensita',
            'latitudine', 'longitudine', 'raggio',
        )
        for f in candidati:
            d = _distanza_km(lat, lon, float(f['latitudine']), float(f['longitudine']))
            if d > raggio_km:
                continue
            precedente = out.get(f['id'])
            if precedente is None or d < precedente['distanza_km']:
                out[f['id']] = {**f, 'vicino_apiario_id': apiario.id,
                                'distanza_km': round(d, 2)}
    return sorted(out.values(), key=lambda f: f['data_inizio'])


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
