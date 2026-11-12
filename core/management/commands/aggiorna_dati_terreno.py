"""
Calcola altitudine, pendenza ed esposizione degli apiari dalle coordinate.

I nuovi apiari li ricevono da soli al salvataggio (vedi core/signals.py);
questo comando serve per quelli già esistenti e per ricalcolare a richiesta.

Di default riempie solo gli apiari a cui mancano i dati. Con `--forza`
ricalcola tutti, sovrascrivendo anche i valori inseriti a mano.

Esempi:
    python manage.py aggiorna_dati_terreno
    python manage.py aggiorna_dati_terreno --forza
"""
import time

from django.core.management.base import BaseCommand

from core.ambiente import aggiorna_dati_terreno
from core.models import Apiario


class Command(BaseCommand):
    help = "Ricava altitudine, pendenza ed esposizione degli apiari dalle coordinate."

    def add_arguments(self, parser):
        parser.add_argument('--forza', action='store_true',
                            help="Ricalcola anche gli apiari che hanno già i dati.")

    def handle(self, *args, **options):
        forza = options['forza']
        apiari = Apiario.objects.filter(
            latitudine__isnull=False, longitudine__isnull=False).order_by('id')
        aggiornati = saltati = 0
        for apiario in apiari:
            if aggiorna_dati_terreno(apiario, forza=forza):
                aggiornati += 1
                self.stdout.write(
                    f"  {apiario.nome}: {apiario.altitudine_m} m, "
                    f"pendenza {apiario.pendenza_gradi}°, esposizione {apiario.esposizione}")
                time.sleep(0.3)  # cortesia verso l'API pubblica
            else:
                saltati += 1
        self.stdout.write(self.style.SUCCESS(
            f"Apiari aggiornati: {aggiornati}. Già completi o non calcolabili: {saltati}."))
