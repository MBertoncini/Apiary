from django.db import models
from django.contrib.auth.models import User


class DashboardConfig(models.Model):
    """Configurazione dashboard personalizzata per ogni utente."""
    utente = models.OneToOneField(User, on_delete=models.CASCADE, related_name='dashboard_config')
    widget_config = models.JSONField(default=list)
    # Struttura widget_config:
    # [
    #   {
    #     'widget_id': 'salute_arnie',
    #     'posizione': 1,
    #     'visibile': True,
    #     'parametri': {'periodo_giorni': 90, 'apiario_id': None}
    #   },
    # ]
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configurazione Dashboard'
        verbose_name_plural = 'Configurazioni Dashboard'

    def __str__(self):
        return f'Dashboard di {self.utente.username}'
