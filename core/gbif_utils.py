# core/gbif_utils.py
"""
GBIF (Global Biodiversity Information Facility) API utilities.
Fornisce dati su specie vegetali mellifere per supportare:
  - Analisi flora locale vicina agli apiari (raggio 3 km)
  - Pianificazione nomadismo (tile layer densità per specie)
Tutti i risultati sono cachati 7 giorni (dati storici, stabili).
"""
import math
import requests
from django.core.cache import cache

# ── Preset miele: specie target per nomadismo ─────────────────────────────────
PRESET_MIELE = {
    'acacia': {
        'nome': 'Acacia (Robinia)',
        'pianta': 'Robinia pseudoacacia',
        'taxonKey': 5352251,
        'emoji': '🌸',
        'colore': '#FFF9C4',
        'colore_bordo': '#F5C518',
        'colore_tile': '#yellow',
        'descrizione': 'Miele pregiato, chiaro e delicato. Fioritura: aprile–maggio.',
        'periodo': 'Apr–Mag',
        'regioni': 'Toscana, Umbria, Lazio, colline appenniniche',
    },
    'castagno': {
        'nome': 'Castagno',
        'pianta': 'Castanea sativa',
        'taxonKey': 5333294,
        'emoji': '🌰',
        'colore': '#EFEBE9',
        'colore_bordo': '#795548',
        'descrizione': 'Miele scuro, tannico e aromatico. Fioritura: giugno–luglio.',
        'periodo': 'Giu–Lug',
        'regioni': 'Appennino, Prealpi, Appennino calabro-lucano',
    },
    'tiglio': {
        'nome': 'Tiglio',
        'pianta': 'Tilia',
        'taxonKey': 3152041,
        'emoji': '🍃',
        'colore': '#C8E6C9',
        'colore_bordo': '#388E3C',
        'descrizione': 'Miele profumato, lievemente mentolato. Fioritura: giugno.',
        'periodo': 'Giu',
        'regioni': 'Valli alpine, Pianura Padana, parchi urbani',
    },
    'lavanda': {
        'nome': 'Lavanda',
        'pianta': 'Lavandula',
        'taxonKey': 2927302,
        'emoji': '💜',
        'colore': '#E1BEE7',
        'colore_bordo': '#7B1FA2',
        'descrizione': 'Miele aromatico e floreale. Fioritura: lug–ago.',
        'periodo': 'Lug–Ago',
        'regioni': 'Provenza (FR), Alta Valle Pesio, Valchiusella',
    },
    'sulla': {
        'nome': 'Sulla',
        'pianta': 'Hedysarum coronarium',
        'taxonKey': 2960919,
        'emoji': '🌺',
        'colore': '#FFCDD2',
        'colore_bordo': '#C62828',
        'descrizione': 'Miele chiaro, tipico del Sud Italia. Fioritura: apr–mag.',
        'periodo': 'Apr–Mag',
        'regioni': 'Sicilia, Calabria, Sardegna, Puglia',
    },
    'corbezzolo': {
        'nome': 'Corbezzolo',
        'pianta': 'Arbutus unedo',
        'taxonKey': 2882803,
        'emoji': '🍓',
        'colore': '#FFCCBC',
        'colore_bordo': '#BF360C',
        'descrizione': 'Miele amaro, unico. Fioritura: ott–nov.',
        'periodo': 'Ott–Nov',
        'regioni': 'Sardegna, Maremma, coste tirreniche',
    },
    'eucalipto': {
        'nome': 'Eucalipto',
        'pianta': 'Eucalyptus',
        'taxonKey': 7493935,
        'emoji': '🌿',
        'colore': '#B2DFDB',
        'colore_bordo': '#00695C',
        'descrizione': 'Miele balsamico e scuro. Fioritura: gen–mar.',
        'periodo': 'Gen–Mar',
        'regioni': 'Sardegna, Sicilia, Calabria ionica',
    },
    'girasole': {
        'nome': 'Girasole',
        'pianta': 'Helianthus annuus',
        'taxonKey': 9206251,
        'emoji': '🌻',
        'colore': '#FFF9C4',
        'colore_bordo': '#F9A825',
        'descrizione': 'Miele chiaro, cristallizza rapidamente. Fioritura: lug–ago.',
        'periodo': 'Lug–Ago',
        'regioni': 'Pianura Padana, Toscana, Marche, Puglia',
    },
    'trifoglio': {
        'nome': 'Trifoglio',
        'pianta': 'Trifolium',
        'taxonKey': 2973363,
        'emoji': '🍀',
        'colore': '#DCEDC8',
        'colore_bordo': '#558B2F',
        'descrizione': 'Miele millefiori delicato. Fioritura: mag–set.',
        'periodo': 'Mag–Set',
        'regioni': 'Prati, pascoli, tutta Italia',
    },
    'agrumi': {
        'nome': 'Agrumi',
        'pianta': 'Citrus',
        'taxonKey': 3190155,
        'emoji': '🍊',
        'colore': '#FFE0B2',
        'colore_bordo': '#E65100',
        'descrizione': "Miele d'arancio, profumato. Fioritura: mar–apr.",
        'periodo': 'Mar–Apr',
        'regioni': 'Sicilia, Calabria, Campania, Puglia',
    },
}

# ── Famiglie botaniche mellifere (per classificare le specie GBIF) ────────────
FAMIGLIE_MELLIFERE = {
    'Lamiaceae',    # lavanda, timo, rosmarino, salvia, origano
    'Fabaceae',     # robinia, trifoglio, sulla, meliloto
    'Rosaceae',     # melo, ciliegio, pero, lampone
    'Apiaceae',     # finocchio selvatico, angelica, carota selvatica
    'Boraginaceae', # borragine, facelia, viperina
    'Asteraceae',   # girasole, fiordaliso, tarassaco
    'Fagaceae',     # castagno, quercia
    'Ericaceae',    # corbezzolo, erica, mirtillo
    'Myrtaceae',    # eucalipto
    'Rutaceae',     # agrumi
    'Malvaceae',    # tiglio, malva
    'Brassicaceae', # colza, senape, rafano
    'Lythraceae',   # lagerstroemia
    'Salicaceae',   # salice (fonte di propoli e polline)
    'Polygonaceae', # poligono, grano saraceno
}


def get_specie_mellifere_vicine(lat, lng, raggio_km=5):
    """
    Recupera le specie vegetali presenti entro raggio_km dal punto (lat, lng)
    interrogando l'API GBIF occurrence/search.

    Restituisce una lista di dict ordinata: prima le specie mellifere (per count
    decrescente), poi le altre piante.

    Ogni dict:
      {taxonKey, nomeLatino, famiglia, count, mellifera, gbif_url}

    Cache: 7 giorni (i dati GBIF sono storici e stabili).
    """
    lat = round(float(lat), 4)
    lng = round(float(lng), 4)
    cache_key = f'gbif_specie_{lat}_{lng}_{raggio_km}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    delta_lat = raggio_km / 111.0
    delta_lng = raggio_km / (111.0 * math.cos(math.radians(lat))) if lat != 90 else raggio_km / 111.0

    params = {
        'decimalLatitude': f'{lat - delta_lat:.4f},{lat + delta_lat:.4f}',
        'decimalLongitude': f'{lng - delta_lng:.4f},{lng + delta_lng:.4f}',
        'kingdomKey': 6,            # Plantae
        'hasCoordinate': 'true',
        'hasGeospatialIssue': 'false',
        'year': '2010,2025',
        'limit': 300,
    }

    try:
        resp = requests.get(
            'https://api.gbif.org/v1/occurrence/search',
            params=params,
            timeout=12,
            headers={'User-Agent': 'ApiaryApp/1.0 (beekeeping management; contact: admin@apiary.it)'},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    species_dict = {}
    for occ in data.get('results', []):
        sp_key = occ.get('speciesKey')
        sp_name = occ.get('species') or ''
        if not sp_name:
            # fallback: usa le prime due parole del nome scientifico
            sn = occ.get('scientificName', '')
            parts = sn.split()
            sp_name = ' '.join(parts[:2]) if len(parts) >= 2 else sn
        family = occ.get('family', '')
        if not sp_name or not sp_key:
            continue
        if sp_key not in species_dict:
            species_dict[sp_key] = {
                'taxonKey': sp_key,
                'nomeLatino': sp_name,
                'famiglia': family,
                'count': 0,
                'mellifera': family in FAMIGLIE_MELLIFERE,
                'gbif_url': f'https://www.gbif.org/species/{sp_key}',
            }
        species_dict[sp_key]['count'] += 1

    result = sorted(
        species_dict.values(),
        key=lambda x: (-int(x['mellifera']), -x['count'])
    )
    cache.set(cache_key, result, 60 * 60 * 24 * 7)
    return result


def gbif_tile_url(taxon_key, style='classic.poly'):
    """
    Restituisce il template URL dei tile GBIF per Leaflet per una specie/taxon.
    Usabile direttamente come tileLayer in Leaflet.js.
    """
    return (
        f'https://api.gbif.org/v2/map/occurrence/density/{{z}}/{{x}}/{{y}}@1x.png'
        f'?taxonKey={taxon_key}&style={style}&bin=hex'
    )
