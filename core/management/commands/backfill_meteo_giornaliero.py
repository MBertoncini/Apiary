# core/management/commands/backfill_meteo_giornaliero.py
"""
Riempie retroattivamente il dataset MeteoGiornaliero per ogni apiario.

Per ogni apiario con coordinate e monitoraggio_meteo abilitato:
  - calcola lo start (data_creazione)
  - calcola l'end (ieri)
  - chiede ad Open-Meteo Archive (ERA5) i giorni mancanti
  - usa Open-Meteo Forecast per coprire gli ultimi 2-5 giorni che ERA5 non
    indicizza ancora

Idempotente: si può rilanciare a piacere; le righe `archive` esistenti non
vengono toccate.

Uso:
  python manage.py backfill_meteo_giornaliero
  python manage.py backfill_meteo_giornaliero --apiario-id 12
  python manage.py backfill_meteo_giornaliero --max-days 365
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from core.models import Apiario
from core.meteo_archive_utils import aggiorna_meteo_apiario


class Command(BaseCommand):
    help = 'Riempie il dataset MeteoGiornaliero per ogni apiario dalla data di creazione a ieri.'

    def add_arguments(self, parser):
        parser.add_argument('--apiario-id', type=int, default=None,
                            help='Limita il backfill a un singolo apiario.')
        parser.add_argument('--max-days', type=int, default=None,
                            help='Limita il backfill agli ultimi N giorni (default: tutto).')

    def handle(self, *args, **options):
        qs = Apiario.objects.filter(
            latitudine__isnull=False,
            longitudine__isnull=False,
            monitoraggio_meteo=True,
        )
        if options['apiario_id']:
            qs = qs.filter(id=options['apiario_id'])

        oggi = date.today()
        ieri = oggi - timedelta(days=1)
        max_days = options.get('max_days')

        total_archive = 0
        total_forecast = 0
        processati = 0

        for apiario in qs:
            start = apiario.data_creazione.date() if apiario.data_creazione else (ieri - timedelta(days=365))
            if max_days:
                start = max(start, oggi - timedelta(days=max_days))
            if start > ieri:
                continue

            self.stdout.write(f"Backfill apiario {apiario.id} ({apiario.nome}): {start} -> {ieri}")
            try:
                result = aggiorna_meteo_apiario(apiario, start, ieri)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  errore: {e}"))
                continue

            self.stdout.write(self.style.SUCCESS(
                f"  archive={result['archive']} forecast={result['forecast']}"
            ))
            total_archive += result['archive']
            total_forecast += result['forecast']
            processati += 1

        self.stdout.write(self.style.SUCCESS(
            f"Backfill completato: {processati} apiari, "
            f"{total_archive} righe archive, {total_forecast} righe forecast."
        ))
