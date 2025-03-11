# core/templatetags/app_filters.py
from django import template

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