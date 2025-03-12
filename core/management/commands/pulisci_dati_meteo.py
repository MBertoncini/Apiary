# core/management/commands/pulisci_dati_meteo.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from core.models import DatiMeteo, PrevisioneMeteo
from datetime import timedelta

class Command(BaseCommand):
    help = 'Pulisce i dati meteo vecchi per risparmiare spazio'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=settings.METEO_DATA_RETENTION_DAYS,
            help='Numero di giorni per cui mantenere i dati (default da settings)'
        )

    def handle(self, *args, **options):
        days = options['days']
        data_limite = timezone.now() - timedelta(days=days)
        
        # Elimina dati meteo vecchi
        dati_meteo_vecchi = DatiMeteo.objects.filter(data__lt=data_limite)
        count_dati = dati_meteo_vecchi.count()
        dati_meteo_vecchi.delete()
        
        # Elimina previsioni vecchie
        previsioni_vecchie = PrevisioneMeteo.objects.filter(data_previsione__lt=data_limite)
        count_previsioni = previsioni_vecchie.count()
        previsioni_vecchie.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Eliminati {count_dati} dati meteo e {count_previsioni} previsioni più vecchi di {days} giorni')
        )