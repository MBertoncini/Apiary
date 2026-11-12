"""Dati ambientali di una postazione ricavati dalle coordinate.

Altitudine, pendenza ed esposizione del versante si ottengono dal modello
digitale del terreno esposto dall'API Elevation di Open-Meteo (stesso
fornitore del meteo, nessuna chiave). Si interrogano cinque punti: il centro
e quattro vicini a nord, est, sud, ovest; dalla differenza di quota si ricava
il gradiente.
"""

import logging
import math

import requests

logger = logging.getLogger(__name__)

ELEVATION_URL = 'https://api.open-meteo.com/v1/elevation'

# Distanza dei punti vicini dal centro. Il modello del terreno ha una
# risoluzione di circa 90 m: un passo più corto leggerebbe lo stesso pixel.
PASSO_M = 100.0

# Sotto questa pendenza il versante non ha un'esposizione significativa.
PENDENZA_PIANO_GRADI = 2.0

_SETTORI = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO']


def esposizione_da_gradiente(dz_est, dz_nord):
    """Pendenza (gradi) ed esposizione dal gradiente di quota (m/m).

    L'esposizione è la direzione verso cui il terreno scende, cioè quella a
    cui il versante è rivolto.
    """
    pendenza = math.degrees(math.atan(math.hypot(dz_est, dz_nord)))
    if pendenza < PENDENZA_PIANO_GRADI:
        return pendenza, 'piano'
    azimut = math.degrees(math.atan2(-dz_est, -dz_nord)) % 360
    return pendenza, _SETTORI[int((azimut + 22.5) // 45) % 8]


def calcola_dati_terreno(latitudine, longitudine, timeout=10):
    """Restituisce {'altitudine_m', 'pendenza_gradi', 'esposizione'} o None."""
    lat, lon = float(latitudine), float(longitudine)
    dlat = PASSO_M / 111320.0
    dlon = PASSO_M / (111320.0 * max(0.01, math.cos(math.radians(lat))))
    # Ordine: centro, nord, est, sud, ovest.
    lats = [lat, lat + dlat, lat, lat - dlat, lat]
    lons = [lon, lon, lon + dlon, lon, lon - dlon]
    try:
        r = requests.get(
            ELEVATION_URL,
            params={
                'latitude': ','.join(f'{v:.6f}' for v in lats),
                'longitude': ','.join(f'{v:.6f}' for v in lons),
            },
            timeout=timeout,
        )
        r.raise_for_status()
        quote = r.json().get('elevation') or []
    except Exception as e:
        logger.warning("Elevation API non raggiungibile: %s", e)
        return None
    if len(quote) != 5 or any(q is None for q in quote):
        return None

    centro, nord, est, sud, ovest = (float(q) for q in quote)
    dz_est = (est - ovest) / (2 * PASSO_M)
    dz_nord = (nord - sud) / (2 * PASSO_M)
    pendenza, esposizione = esposizione_da_gradiente(dz_est, dz_nord)
    return {
        'altitudine_m': round(centro, 1),
        'pendenza_gradi': round(pendenza, 1),
        'esposizione': esposizione,
    }


def aggiorna_dati_terreno(apiario, forza=False):
    """Calcola e salva i dati del terreno di un apiario. True se aggiornato.

    Senza `forza` non sovrascrive valori già presenti (anche inseriti a mano).
    """
    from .models import Apiario

    if not apiario.has_coordinates():
        return False
    if not forza and apiario.altitudine_m is not None and apiario.esposizione:
        return False
    dati = calcola_dati_terreno(apiario.latitudine, apiario.longitudine)
    if not dati:
        return False
    # .update() evita di ritriggerare i signal post_save dell'apiario.
    Apiario.objects.filter(pk=apiario.pk).update(**dati)
    for campo, valore in dati.items():
        setattr(apiario, campo, valore)
    return True
