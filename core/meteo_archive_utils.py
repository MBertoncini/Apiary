# core/meteo_archive_utils.py
"""
Client Open-Meteo per aggregati giornalieri (dataset ML).

Open-Meteo è gratuito e non richiede API key. Due endpoint:

  * Archive (ERA5):  https://archive-api.open-meteo.com/v1/archive
      Copre da 1940 a ~5 giorni fa. Affidabile, reanalysis.

  * Forecast:        https://api.open-meteo.com/v1/forecast
      Con past_days=N restituisce gli ultimi N giorni. Usato per il
      gap recente che Archive non copre ancora.

Il flusso è: per ogni apiario chiediamo i giorni mancanti tra
data_creazione e ieri, prendendo i giorni "vecchi" dall'Archive e gli
ultimi giorni dal Forecast (etichettati `source='forecast'`). Al run
successivo, quegli stessi giorni vengono richiesti di nuovo all'Archive
e sovrascritti come `source='archive'`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import requests
from django.core.cache import cache
from django.db import transaction

from .models import Apiario, MeteoGiornaliero


logger = logging.getLogger(__name__)


ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'

# Lag tipico di ERA5 (Open-Meteo dichiara ~5gg).
ARCHIVE_LAG_DAYS = 5

# Variabili daily richieste (sia ad Archive che a Forecast).
DAILY_VARS = [
    'temperature_2m_max',
    'temperature_2m_min',
    'temperature_2m_mean',
    'precipitation_sum',
    'precipitation_hours',
    'wind_speed_10m_max',
    'wind_gusts_10m_max',
    'relative_humidity_2m_mean',
    'surface_pressure_mean',
    'sunshine_duration',
    'shortwave_radiation_sum',
    'weather_code',
]

# Open-Meteo: 10k chiamate/giorno gratuito; teniamo un piccolo throttle.
_RATE_LIMIT_KEY = 'open_meteo_throttle'
_MIN_INTERVAL_SECONDS = 0.2


def _throttle() -> None:
    last = cache.get(_RATE_LIMIT_KEY)
    now = time.monotonic()
    if last is not None:
        delta = now - last
        if delta < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - delta)
    cache.set(_RATE_LIMIT_KEY, time.monotonic(), 60)


def _http_get(url: str, params: dict, timeout: int = 30) -> dict | None:
    _throttle()
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
        logger.warning("Open-Meteo JSON error: %s", e)
        return None


@dataclass
class DailyRow:
    data: date
    temp_min: float | None
    temp_max: float | None
    temp_mean: float | None
    precip_mm: float | None
    precip_hours: float | None
    umidita_media: float | None
    vento_medio: float | None
    vento_raffica_max: float | None
    pressione_media: float | None
    ore_sole: float | None
    radiazione_mj: float | None
    weather_code_dominante: int | None


def _parse_daily(payload: dict) -> list[DailyRow]:
    """Trasforma la risposta `daily` Open-Meteo in lista di DailyRow."""
    daily = payload.get('daily') or {}
    times = daily.get('time') or []
    if not times:
        return []

    def _get(name: str, i: int):
        arr = daily.get(name)
        if not arr or i >= len(arr):
            return None
        return arr[i]

    rows: list[DailyRow] = []
    for i, t in enumerate(times):
        try:
            d = date.fromisoformat(t)
        except (TypeError, ValueError):
            continue
        sunshine_s = _get('sunshine_duration', i)
        rows.append(DailyRow(
            data=d,
            temp_min=_get('temperature_2m_min', i),
            temp_max=_get('temperature_2m_max', i),
            temp_mean=_get('temperature_2m_mean', i),
            precip_mm=_get('precipitation_sum', i),
            precip_hours=_get('precipitation_hours', i),
            umidita_media=_get('relative_humidity_2m_mean', i),
            # wind_speed_10m_max è il massimo della giornata: lo usiamo come
            # proxy di "vento medio rappresentativo" finché non aggiungiamo
            # un secondo campo `vento_max`. Per il modello ML basta avere
            # una sola variabile vento coerente nel tempo.
            vento_medio=_get('wind_speed_10m_max', i),
            vento_raffica_max=_get('wind_gusts_10m_max', i),
            pressione_media=_get('surface_pressure_mean', i),
            ore_sole=(sunshine_s / 3600.0) if sunshine_s is not None else None,
            radiazione_mj=_get('shortwave_radiation_sum', i),
            weather_code_dominante=_get('weather_code', i),
        ))
    return rows


def calcola_gdd(tmin: float | None, tmax: float | None, base: float = 10.0) -> float | None:
    """Growing Degree Days: max(0, (Tmin+Tmax)/2 - base). None se input mancanti."""
    if tmin is None or tmax is None:
        return None
    return max(0.0, (tmin + tmax) / 2.0 - base)


def fetch_meteo_archive(
    lat: float,
    lon: float,
    start: date,
    end: date,
    timezone_str: str = 'auto',
) -> list[DailyRow]:
    """Recupera daily ERA5 da Open-Meteo Archive (estremi inclusi)."""
    if start > end:
        return []
    params = {
        'latitude': lat,
        'longitude': lon,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'daily': ','.join(DAILY_VARS),
        'timezone': timezone_str,
    }
    payload = _http_get(ARCHIVE_URL, params)
    if not payload:
        return []
    return _parse_daily(payload)


def fetch_meteo_forecast_recent(
    lat: float,
    lon: float,
    past_days: int = ARCHIVE_LAG_DAYS,
    timezone_str: str = 'auto',
) -> list[DailyRow]:
    """Recupera gli ultimi N giorni da Open-Meteo Forecast.

    Usato per coprire il gap di ~5 giorni che ERA5 non ha ancora indicizzato.
    `forecast_days=1` perché ci servono solo i giorni passati + oggi.
    """
    past_days = max(1, min(past_days, 92))
    params = {
        'latitude': lat,
        'longitude': lon,
        'daily': ','.join(DAILY_VARS),
        'past_days': past_days,
        'forecast_days': 1,
        'timezone': timezone_str,
    }
    payload = _http_get(FORECAST_URL, params)
    if not payload:
        return []
    return _parse_daily(payload)


@transaction.atomic
def upsert_meteo_giornaliero(
    apiario: Apiario,
    rows: Iterable[DailyRow],
    source: str,
) -> int:
    """Upsert idempotente. Restituisce numero di righe scritte/aggiornate.

    Regola: una riga `archive` non viene mai sovrascritta da `forecast`.
    Una riga `forecast` viene sovrascritta da `archive`.
    """
    written = 0
    for row in rows:
        gdd = calcola_gdd(row.temp_min, row.temp_max)
        existing = MeteoGiornaliero.objects.filter(apiario=apiario, data=row.data).first()
        if existing and existing.source == MeteoGiornaliero.SOURCE_ARCHIVE \
                and source == MeteoGiornaliero.SOURCE_FORECAST:
            continue
        defaults = {
            'temp_min': row.temp_min,
            'temp_max': row.temp_max,
            'temp_mean': row.temp_mean,
            'precip_mm': row.precip_mm,
            'precip_hours': row.precip_hours,
            'umidita_media': row.umidita_media,
            'vento_medio': row.vento_medio,
            'vento_raffica_max': row.vento_raffica_max,
            'pressione_media': row.pressione_media,
            'ore_sole': row.ore_sole,
            'radiazione_mj': row.radiazione_mj,
            'gdd_base10': gdd,
            'weather_code_dominante': row.weather_code_dominante,
            'source': source,
        }
        MeteoGiornaliero.objects.update_or_create(
            apiario=apiario, data=row.data, defaults=defaults,
        )
        written += 1
    return written


def trova_giorni_mancanti(apiario: Apiario, start: date, end: date) -> set[date]:
    """Date in [start, end] senza MeteoGiornaliero `archive` (le `forecast` si rifanno)."""
    if start > end:
        return set()
    qs = MeteoGiornaliero.objects.filter(
        apiario=apiario,
        data__gte=start,
        data__lte=end,
        source=MeteoGiornaliero.SOURCE_ARCHIVE,
    ).values_list('data', flat=True)
    presenti = set(qs)
    giorni = {start + timedelta(days=i) for i in range((end - start).days + 1)}
    return giorni - presenti


def aggiorna_meteo_apiario(apiario: Apiario, start: date, end: date) -> dict:
    """Riempie i buchi tra start ed end per un singolo apiario.

    - Per i giorni fino a `oggi - ARCHIVE_LAG_DAYS` usa Archive (ERA5).
    - Per i restanti giorni recenti usa Forecast (etichettati `forecast`).
    Idempotente: ri-eseguibile a piacere; archivia non viene mai sovrascritto
    da un forecast successivo.

    Restituisce dizionario con conteggi: {archive: N, forecast: N}.
    """
    if not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
        return {'archive': 0, 'forecast': 0, 'skipped': True}

    lat = float(apiario.latitudine)
    lon = float(apiario.longitudine)

    oggi = date.today()
    archive_max = oggi - timedelta(days=ARCHIVE_LAG_DAYS)
    end = min(end, oggi)

    archive_written = 0
    forecast_written = 0

    # Fase 1: Archive per i giorni vecchi
    archive_end = min(end, archive_max)
    if start <= archive_end:
        mancanti = trova_giorni_mancanti(apiario, start, archive_end)
        if mancanti:
            mancanti_sorted = sorted(mancanti)
            fetch_start = mancanti_sorted[0]
            fetch_end = mancanti_sorted[-1]
            rows = fetch_meteo_archive(lat, lon, fetch_start, fetch_end)
            rows = [r for r in rows if r.data in mancanti]
            archive_written = upsert_meteo_giornaliero(
                apiario, rows, MeteoGiornaliero.SOURCE_ARCHIVE,
            )

    # Fase 2: Forecast per i giorni recenti che Archive non copre
    if end > archive_max:
        past_days = (end - archive_max).days + ARCHIVE_LAG_DAYS
        rows = fetch_meteo_forecast_recent(lat, lon, past_days=past_days)
        rows = [r for r in rows if start <= r.data <= end]
        forecast_written = upsert_meteo_giornaliero(
            apiario, rows, MeteoGiornaliero.SOURCE_FORECAST,
        )

    return {'archive': archive_written, 'forecast': forecast_written, 'skipped': False}
