# core/meteo_utils.py
"""
Servizio meteo unificato basato su Open-Meteo (gratuito, no API key).

Sostituisce la precedente implementazione OpenWeatherMap mantenendo invariata
la signature delle funzioni pubbliche e i modelli `DatiMeteo` / `PrevisioneMeteo`
così da non rompere UI/API esistenti.

Per il dataset giornaliero usato dai modelli ML vedi
`core.meteo_archive_utils` (modello `MeteoGiornaliero`).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta

import requests
from django.core.cache import cache
from django.utils import timezone

from .models import DatiMeteo, PrevisioneMeteo


logger = logging.getLogger(__name__)


FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'

# Cache TTL (secondi) per evitare chiamate ridondanti.
CACHE_TTL_CURRENT = 30 * 60   # 30 minuti per il meteo attuale
CACHE_TTL_FORECAST = 2 * 60 * 60  # 2 ore per le previsioni


# ----------------------------------------------------------------------------
# Mappa codici WMO → descrizione italiana (allineata al frontend)
# ----------------------------------------------------------------------------

def descrizione_da_wmo_code(code: int | None, is_day: bool = True) -> str:
    """Descrizione testuale italiana del codice WMO Open-Meteo."""
    if code is None:
        return 'Non disponibile'
    if code == 0:
        return 'Cielo sereno' if is_day else 'Notte serena'
    if code == 1:
        return 'Prevalentemente sereno'
    if code == 2:
        return 'Parzialmente nuvoloso'
    if code == 3:
        return 'Coperto'
    if code in (45, 48):
        return 'Nebbia'
    if 51 <= code <= 55:
        return 'Pioggerella'
    if 56 <= code <= 57:
        return 'Pioggerella gelata'
    if 61 <= code <= 65:
        return 'Pioggia'
    if 66 <= code <= 67:
        return 'Pioggia gelata'
    if 71 <= code <= 75:
        return 'Neve'
    if code == 77:
        return 'Granuli di neve'
    if 80 <= code <= 82:
        return 'Rovesci di pioggia'
    if 85 <= code <= 86:
        return 'Rovesci di neve'
    if code == 95:
        return 'Temporale'
    if code in (96, 99):
        return 'Temporale con grandine'
    return 'Non disponibile'


def icona_da_wmo_code(code: int | None, is_day: bool = True) -> str:
    """Restituisce un identificatore icona stabile (compatibile col campo
    `icona` esistente, max 20 char). Usiamo il codice WMO come stringa più
    suffisso d/n per consistenza coi vecchi pattern OWM 01d/01n.
    """
    if code is None:
        return ''
    return f"wmo{code:02d}{'d' if is_day else 'n'}"


def emoji_da_wmo_code(code: int | None, is_day: bool = True) -> str:
    """Emoji corrispondente al codice WMO. Usato dai template/server-rendered HTML."""
    if code is None:
        return '❓'
    if code == 0:
        return '☀️' if is_day else '🌙'
    if code == 1:
        return '🌤️' if is_day else '🌙'
    if code == 2:
        return '⛅'
    if code == 3:
        return '☁️'
    if code in (45, 48):
        return '🌫️'
    if 51 <= code <= 57:
        return '🌦️'
    if 61 <= code <= 67:
        return '🌧️'
    if 71 <= code <= 77:
        return '🌨️'
    if 80 <= code <= 82:
        return '🌧️'
    if 85 <= code <= 86:
        return '🌨️'
    if 95 <= code <= 99:
        return '⛈️'
    return '🌡️'


def emoji_da_icona(icona: str | None) -> str:
    """Decodifica il campo `icona` di DatiMeteo/PrevisioneMeteo in emoji.

    Supporta sia il nuovo formato Open-Meteo (`wmoXXd`/`wmoXXn`) sia il
    vecchio formato OpenWeatherMap (`01d`, `02n`, ...) per record storici.
    """
    if not icona:
        return '🌡️'
    s = str(icona).strip().lower()
    if s.startswith('wmo'):
        try:
            code = int(s[3:5])
        except (ValueError, IndexError):
            return '🌡️'
        is_day = not s.endswith('n')
        return emoji_da_wmo_code(code, is_day=is_day)
    # Fallback legacy OWM
    legacy = {
        '01': '☀️', '02': '🌤️', '03': '⛅', '04': '☁️',
        '09': '🌧️', '10': '🌦️', '11': '⛈️', '13': '🌨️', '50': '🌫️',
    }
    is_day = not s.endswith('n')
    base = s[:2]
    icon = legacy.get(base, '🌡️')
    if base == '01' and not is_day:
        return '🌙'
    return icon


def get_wind_direction_text(gradi) -> str:
    """Converte i gradi della direzione del vento in testo (N, NE, E, ecc.)"""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSO', 'SO', 'OSO', 'O', 'ONO', 'NO', 'NNO']
    try:
        index = round(float(gradi) / 22.5) % 16
    except (TypeError, ValueError):
        return ''
    return directions[index]


# ----------------------------------------------------------------------------
# HTTP helper
# ----------------------------------------------------------------------------

def _http_get_json(url: str, params: dict, timeout: int = 15) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=timeout)
    except requests.RequestException as e:
        logger.warning("Open-Meteo request error: %s", e)
        return None
    if r.status_code != 200:
        logger.warning("Open-Meteo HTTP %s: %s", r.status_code, r.text[:200])
        return None
    try:
        return r.json()
    except ValueError as e:
        logger.warning("Open-Meteo JSON decode error: %s", e)
        return None


def _fetch_open_meteo(lat: float, lon: float) -> dict | None:
    """Chiama Open-Meteo forecast per dati current + hourly 5 giorni.
    Unità vento in m/s per retro-compatibilità con i dati storici OpenWeatherMap.
    """
    params = {
        'latitude': lat,
        'longitude': lon,
        'current': ','.join([
            'temperature_2m',
            'relative_humidity_2m',
            'surface_pressure',
            'wind_speed_10m',
            'wind_direction_10m',
            'precipitation',
            'weather_code',
            'is_day',
        ]),
        'hourly': ','.join([
            'temperature_2m',
            'relative_humidity_2m',
            'surface_pressure',
            'wind_speed_10m',
            'wind_direction_10m',
            'precipitation_probability',
            'precipitation',
            'weather_code',
            'is_day',
        ]),
        'forecast_days': 5,
        'wind_speed_unit': 'ms',
        'timezone': 'auto',
    }
    return _http_get_json(FORECAST_URL, params)


# ----------------------------------------------------------------------------
# API pubblica (signature invariate dall'implementazione precedente)
# ----------------------------------------------------------------------------

def aggiorna_dati_meteo(apiario):
    """Recupera i dati meteo attuali per un apiario e li salva in DatiMeteo."""
    if not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
        return None

    cache_key = f"meteo_attuale_{apiario.id}"
    cached = cache.get(cache_key)
    payload = None

    if cached and 'json_data' in cached:
        try:
            payload = json.loads(cached['json_data'])
        except (TypeError, ValueError):
            payload = None

    if payload is None:
        lat = float(apiario.latitudine)
        lon = float(apiario.longitudine)
        payload = _fetch_open_meteo(lat, lon)
        if payload is None:
            return None
        cache.set(cache_key, {
            'json_data': json.dumps(payload),
            'timestamp': timezone.now().timestamp(),
        }, CACHE_TTL_CURRENT)

    cur = payload.get('current') or {}
    weather_code = cur.get('weather_code')
    is_day = bool(cur.get('is_day', 1))

    dati = DatiMeteo(
        apiario=apiario,
        data=timezone.now(),
        temperatura=cur.get('temperature_2m'),
        umidita=cur.get('relative_humidity_2m'),
        pressione=cur.get('surface_pressure'),
        velocita_vento=cur.get('wind_speed_10m'),
        direzione_vento=cur.get('wind_direction_10m'),
        descrizione=descrizione_da_wmo_code(weather_code, is_day=is_day),
        icona=icona_da_wmo_code(weather_code, is_day=is_day),
        pioggia=cur.get('precipitation') or 0,
    )
    dati.save()
    return dati


def aggiorna_previsioni_meteo(apiario):
    """Recupera le previsioni meteo orarie per un apiario e popola PrevisioneMeteo."""
    if not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
        return []

    cache_key = f"previsioni_meteo_{apiario.id}"
    cached = cache.get(cache_key)
    payload = None

    if cached and 'json_data' in cached:
        try:
            payload = json.loads(cached['json_data'])
        except (TypeError, ValueError):
            payload = None

    if payload is None:
        lat = float(apiario.latitudine)
        lon = float(apiario.longitudine)
        payload = _fetch_open_meteo(lat, lon)
        if payload is None:
            return []
        cache.set(cache_key, {
            'json_data': json.dumps(payload),
            'timestamp': timezone.now().timestamp(),
        }, CACHE_TTL_FORECAST)

    return process_forecast_data(apiario, payload)


def process_forecast_data(apiario, payload):
    """Salva le previsioni orarie da Open-Meteo nei prossimi 5 giorni."""
    hourly = payload.get('hourly') or {}
    times = hourly.get('time') or []
    if not times:
        return []

    # Pulisci le previsioni precedenti
    PrevisioneMeteo.objects.filter(apiario=apiario).delete()

    now = timezone.now()
    cutoff = now + timedelta(days=5)
    previsioni = []

    def _get(name, i):
        arr = hourly.get(name)
        if not arr or i >= len(arr):
            return None
        return arr[i]

    for i, t in enumerate(times):
        try:
            naive_dt = datetime.fromisoformat(t)
        except (TypeError, ValueError):
            continue
        data_riferimento = timezone.make_aware(naive_dt) if naive_dt.tzinfo is None else naive_dt
        if data_riferimento > cutoff:
            continue

        temp = _get('temperature_2m', i)
        weather_code = _get('weather_code', i)
        is_day = bool(_get('is_day', i) or 1)

        previsione = PrevisioneMeteo(
            apiario=apiario,
            data_previsione=now,
            data_riferimento=data_riferimento,
            temperatura=temp,
            temperatura_min=temp,  # Open-Meteo hourly non distingue min/max per ora
            temperatura_max=temp,
            umidita=_get('relative_humidity_2m', i),
            pressione=_get('surface_pressure', i),
            velocita_vento=_get('wind_speed_10m', i),
            direzione_vento=_get('wind_direction_10m', i),
            probabilita_pioggia=_get('precipitation_probability', i) or 0,
            descrizione=descrizione_da_wmo_code(weather_code, is_day=is_day),
            icona=icona_da_wmo_code(weather_code, is_day=is_day),
        )
        previsione.save()
        previsioni.append(previsione)

    return previsioni


def ottieni_dati_meteo_correnti(apiario):
    """Ottiene i dati meteo più recenti per un apiario, aggiornandoli se necessario."""
    dati_recenti = DatiMeteo.objects.filter(
        apiario=apiario,
        data__gte=timezone.now() - timedelta(minutes=60),
    ).order_by('-data').first()

    if not dati_recenti:
        dati_recenti = aggiorna_dati_meteo(apiario)

    return dati_recenti


def ottieni_previsioni_meteo(apiario):
    """Ottiene le previsioni meteo per un apiario, aggiornandole se necessario."""
    esistenti = PrevisioneMeteo.objects.filter(
        apiario=apiario,
        data_previsione__gte=timezone.now() - timedelta(hours=3),
    ).exists()

    if not esistenti:
        aggiorna_previsioni_meteo(apiario)

    return PrevisioneMeteo.objects.filter(
        apiario=apiario,
        data_riferimento__gte=timezone.now(),
        data_riferimento__lte=timezone.now() + timedelta(days=5),
    ).order_by('data_riferimento')


def limita_richieste_api(max_richieste: int = 600, per_minuti: int = 1) -> bool:
    """Rate limiter retro-compatibile. Open-Meteo è gratuito con limite ~10k/giorno;
    teniamo un piccolo throttle per evitare burst. Il vecchio limite OWM (60/min)
    non si applica più, quindi alziamo significativamente.
    """
    cache_key = 'open_meteo_api_requests'
    tracker = cache.get(cache_key, {'count': 0, 'reset_time': time.time()})
    now = time.time()
    if now - tracker['reset_time'] > per_minuti * 60:
        tracker = {'count': 0, 'reset_time': now}
    if tracker['count'] >= max_richieste:
        return False
    tracker['count'] += 1
    cache.set(cache_key, tracker, per_minuti * 60)
    return True
