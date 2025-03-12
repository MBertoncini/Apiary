# core/management/commands/aggiorna_meteo.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Apiario, DatiMeteo
from core.meteo_utils import aggiorna_dati_meteo, aggiorna_previsioni_meteo
from datetime import timedelta

class Command(BaseCommand):
    help = 'Aggiorna i dati meteo e le previsioni per tutti gli apiari'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forza l\'aggiornamento anche per apiari con dati recenti',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Inizio aggiornamento dati meteo...'))
        
        # Recupera tutti gli apiari con coordinate valide e monitoraggio abilitato
        apiari = Apiario.objects.filter(
            latitudine__isnull=False,
            longitudine__isnull=False,
            monitoraggio_meteo=True
        )
        
        count_meteo = 0
        count_previsioni = 0
        
        for apiario in apiari:
            # Verifica se l'ultimo aggiornamento è più vecchio di 1 ora (o forza l'aggiornamento)
            ultimo_meteo = DatiMeteo.objects.filter(apiario=apiario).order_by('-data').first()
            
            force_update = options['force']
            need_update = not ultimo_meteo or (timezone.now() - ultimo_meteo.data).total_seconds() > 3600
            
            if force_update or need_update:
                meteo = aggiorna_dati_meteo(apiario)
                if meteo:
                    count_meteo += 1
                
                # Aggiorna anche le previsioni ogni 3 ore
                previsioni = aggiorna_previsioni_meteo(apiario)
                if previsioni:
                    count_previsioni += 1
            
            # Evita di sovraccaricare l'API con troppe richieste consecutive
            if count_meteo > 0 and count_meteo % 10 == 0:
                self.stdout.write(f"Aggiornati {count_meteo} apiari, pausa di 2 secondi...")
                time.sleep(2)
        
        self.stdout.write(self.style.SUCCESS(f'Aggiornati dati meteo per {count_meteo} apiari.'))
        self.stdout.write(self.style.SUCCESS(f'Aggiornate previsioni per {count_previsioni} apiari.'))