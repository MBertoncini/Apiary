"""
Ricostruisce le righe di StoriaRegine mancanti per le regine esistenti.

Fino a questo fix l'API usata dall'app creava le regine senza riga di storico
e, alla sostituzione, cancellava la regina: lo storico, che ha una FK CASCADE
verso la regina, spariva con lei. Il risultato erano statistiche su
sostituzioni e durata media delle regine vuote o quasi.

Il comando, per ogni regina ancora agganciata a una colonia:
  - colonia attiva: apre la riga di storico se manca (inizio = data di
    introduzione della regina);
  - colonia chiusa: chiude la riga aperta, o la crea già chiusa, con la data
    di fine della colonia.

Le regine già cancellate dalle vecchie sostituzioni non sono recuperabili:
non ne resta traccia nel database.

Di default NON scrive nulla: stampa solo cosa farebbe. Per applicare le
modifiche serve `--apply`.

Esempi:
    python manage.py ricostruisci_storia_regine
    python manage.py ricostruisci_storia_regine --apply
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Regina, StoriaRegine
from core.storia_regine import apri_storia, chiudi_storia_colonia


class Command(BaseCommand):
    help = (
        "Crea le righe di storico mancanti per le regine esistenti. "
        "Dry-run salvo --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help="Applica le modifiche (senza, è solo dry-run).")

    def handle(self, *args, **opts):
        apply = opts['apply']
        intestazione = "APPLICO le modifiche" if apply else "DRY-RUN (nessuna scrittura)"
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== Ricostruzione storico regine — {intestazione} ==="
        ))

        aperte = chiuse = 0
        with transaction.atomic():
            regine = (Regina.objects.filter(colonia__isnull=False)
                      .select_related('colonia', 'colonia__apiario').order_by('id'))
            for regina in regine:
                colonia = regina.colonia
                storia = StoriaRegine.objects.filter(colonia=colonia, regina=regina)
                etichetta = (f"Regina #{regina.id} — colonia #{colonia.id} "
                             f"({colonia.apiario.nome}, {colonia.get_stato_display()})")
                if colonia.is_attiva():
                    if not storia.filter(data_fine__isnull=True).exists():
                        apri_storia(regina)
                        self.stdout.write(f"  • {etichetta}: apro dal {regina.data_introduzione}")
                        aperte += 1
                elif not storia.exists() or storia.filter(data_fine__isnull=True).exists():
                    chiudi_storia_colonia(colonia)
                    self.stdout.write(f"  • {etichetta}: chiudo al {colonia.data_fine}")
                    chiuse += 1
            if not apply:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Riepilogo ==="))
        self.stdout.write(f"  righe aperte per regine attive : {aperte}")
        self.stdout.write(f"  righe chiuse per colonie chiuse: {chiuse}")
        if not apply:
            self.stdout.write(self.style.WARNING("  Dry-run: rilancia con --apply per scrivere."))
