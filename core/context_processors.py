# core/context_processors.py

from django.conf import settings

def meteo_settings(request):
    """Rende disponibili le impostazioni meteo nei template"""
    return {
        'OPENWEATHERMAP_API_KEY': settings.OPENWEATHERMAP_API_KEY,
    }