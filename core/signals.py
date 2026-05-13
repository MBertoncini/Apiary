# core/signals.py
"""
Signal handlers per il modulo core.

Attualmente: backfill leggero del dataset MeteoGiornaliero quando un Apiario
viene creato con coordinate (o quando le coordinate vengono settate per la
prima volta). Il backfill completo è demandato al cron quotidiano
`aggiorna_meteo_giornaliero` o al management command `backfill_meteo_giornaliero`.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Apiario


logger = logging.getLogger(__name__)

# Numero di giorni di backfill "leggero" eseguito on-create. Il resto verrà
# riempito gradualmente dal cron quotidiano.
ON_CREATE_BACKFILL_DAYS = 30


def _backfill_async(apiario_id: int, days: int) -> None:
    """Esegue il backfill in un thread daemon per non bloccare la response.

    L'import di `aggiorna_meteo_apiario` è ritardato perché tocca cache/HTTP.
    """
    try:
        from .meteo_archive_utils import aggiorna_meteo_apiario
        from .models import Apiario as _Apiario

        apiario = _Apiario.objects.filter(pk=apiario_id).first()
        if not apiario or not apiario.has_coordinates() or not apiario.monitoraggio_meteo:
            return

        oggi = date.today()
        end = oggi - timedelta(days=1)
        start = max(
            end - timedelta(days=days - 1),
            apiario.data_creazione.date() if apiario.data_creazione else end - timedelta(days=days - 1),
        )
        aggiorna_meteo_apiario(apiario, start, end)
    except Exception as e:
        logger.warning("Backfill meteo on-create fallito per apiario %s: %s", apiario_id, e)


@receiver(post_save, sender=Apiario)
def apiario_post_save_backfill_meteo(sender, instance, created, **kwargs):
    """Lancia il backfill leggero quando un apiario diventa "monitorabile".

    Si scatena se:
      - l'apiario è appena stato creato con coordinate e monitoraggio_meteo attivo
      - oppure (best effort) un apiario già esistente diventa monitorabile
        — tracciato in modo grossolano controllando se ci sono già righe
        MeteoGiornaliero; se no, partiamo.
    """
    if not instance.has_coordinates() or not instance.monitoraggio_meteo:
        return

    if not created:
        # Su update: facciamo backfill solo se non ci sono già righe per
        # questo apiario (evita lavoro inutile a ogni save).
        from .models import MeteoGiornaliero
        if MeteoGiornaliero.objects.filter(apiario=instance).exists():
            return

    t = threading.Thread(
        target=_backfill_async,
        args=(instance.pk, ON_CREATE_BACKFILL_DAYS),
        daemon=True,
    )
    t.start()
