# core/context_processors.py

from django.conf import settings

def meteo_settings(request):
    """Rende disponibili le impostazioni meteo nei template"""
    return {
        'OPENWEATHERMAP_API_KEY': settings.OPENWEATHERMAP_API_KEY,
        'GEMINI_AVAILABLE': bool(getattr(settings, 'GEMINI_API_KEY', '')),
    }

def notifiche_context(request):
    """Rende disponibile il conteggio notifiche non lette in tutti i template"""
    if not request.user.is_authenticated:
        return {'notifiche_non_lette': 0, 'notifiche_recenti': []}
    from .models import Notifica
    non_lette = Notifica.objects.filter(utente=request.user, letta=False).count()
    recenti = Notifica.objects.filter(utente=request.user).order_by('-data_creazione')[:8]
    return {
        'notifiche_non_lette': non_lette,
        'notifiche_recenti': recenti,
    }