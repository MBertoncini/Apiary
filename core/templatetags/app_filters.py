# core/templatetags/app_filters.py
from django import template

from ..meteo_utils import emoji_da_icona

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Restituisce un elemento da un dizionario usando la chiave specificata.
    Utile nei template per accedere a un dizionario con chiavi variabili.
    """
    key = str(key)  # Assicura che la chiave sia una stringa
    if key in dictionary:
        return dictionary[key]
    return None


@register.filter
def meteo_emoji(icona):
    """Converte il codice icona di DatiMeteo/PrevisioneMeteo in emoji.

    Sostituisce le vecchie `<img src="https://openweathermap.org/img/wn/...">`
    ora che il backend usa Open-Meteo (codici WMO interni).
    """
    return emoji_da_icona(icona)