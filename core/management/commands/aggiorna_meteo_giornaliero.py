# core/management/commands/aggiorna_meteo_giornaliero.py
"""
Cron giornaliero: aggiorna il dataset MeteoGiornaliero degli ultimi 7 giorni
per ogni apiario.

I giorni più vecchi vengono letti da Open-Meteo Archive (ERA5), gli ultimi
2-5 da Forecast. Nei run successivi le righe `forecast` vengono sovrascritte
dalle versioni `archive`, quindi nel tempo il dataset converge a ERA5.

Eseguire su PythonAnywhere come scheduled task quotidiana (ore 04:00 UTC
suggerito):
  python manage.py aggiorna_meteo_giornaliero
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from core.models import Apiario
from core.meteo_archive_utils import aggiorna_meteo_apiario


class Command(BaseCommand):
    help = 'Aggiorna gli ultimi 7 giorni del dataset MeteoGiornaliero per tutti gli apiari attivi.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7,
                            help='Numero di giorni indietro da aggiornare (default: 7).')

    def handle(self, *args, **options):
        days = max(1, int(options['days']))
        oggi = date.today()
        start = oggi - timedelta(days=days)
        end = oggi - timedelta(days=1)

        qs = Apiario.objects.filter(
            latitudine__isnull=False,
            longitudine__isnull=False,
            monitoraggio_meteo=True,
        )

        total_archive = 0
        total_forecast = 0
        processati = 0

        for apiario in qs:
            try:
                result = aggiorna_meteo_apiario(apiario, start, end)
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"Apiario {apiario.id} ({apiario.nome}): errore {e}"
                ))
                continue
            total_archive += result['archive']
            total_forecast += result['forecast']
            processati += 1

        self.stdout.write(self.style.SUCCESS(
            f"Meteo giornaliero aggiornato per {processati} apiari "
            f"(range {start} -> {end}): archive={total_archive}, forecast={total_forecast}."
        ))
