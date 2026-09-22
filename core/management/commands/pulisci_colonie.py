"""
Sistema le colonie rimaste incoerenti con il loro contenitore fisico.

Cosa succedeva prima del fix:
  1. eliminando un'arnia (o un nucleo) la sua colonia restava 'attiva' con
     arnia=NULL: negli elenchi compariva un alveare inesistente e la sua regina
     era contata fra quelle attive nelle statistiche;
  2. spostando un'arnia in un altro apiario, `Colonia.apiario` (denormalizzato)
     restava sul vecchio, dove la colonia compariva come doppione;
  3. né la creazione né lo spostamento di una colonia controllavano che il box
     fosse libero, quindi la stessa arnia poteva ospitare due colonie attive.

Il comando esegue tre passi, in quest'ordine:
  A. chiude come 'eliminata' le colonie attive senza contenitore;
  B. riallinea l'apiario delle colonie attive a quello del loro box;
  C. per ogni box con più colonie attive tiene quella che l'app già mostra
     (data_inizio più recente, poi id più alto — lo stesso criterio di
     `Arnia.colonia_attiva`) e chiude le altre come 'eliminata'.

Nessun record viene cancellato: le colonie chiuse restano consultabili nella
storia del contenitore con i loro controlli, e si possono riaprire dall'admin.

Di default NON scrive nulla: stampa solo cosa farebbe. Per applicare le
modifiche serve `--apply`.

Esempi:
    python manage.py pulisci_colonie
    python manage.py pulisci_colonie --user mario
    python manage.py pulisci_colonie --apply
"""
from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.models import Colonia


class Command(BaseCommand):
    help = (
        "Chiude le colonie orfane o duplicate e riallinea l'apiario delle "
        "colonie al loro contenitore. Dry-run salvo --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help="Applica le modifiche (senza, è solo dry-run).")
        parser.add_argument('--user', type=str, default=None,
                            help="Limita l'intervento alle colonie di questo username.")

    # ------------------------------------------------------------------ entry
    def handle(self, *args, **opts):
        self.apply = opts['apply']
        self.oggi = timezone.localdate()
        self.user_filter = None
        if opts['user']:
            try:
                self.user_filter = User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f"Utente '{opts['user']}' non trovato.")

        intestazione = "APPLICO le modifiche" if self.apply else "DRY-RUN (nessuna scrittura)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Pulizia colonie — {intestazione} ==="))
        if self.user_filter:
            self.stdout.write(f"Filtro utente: {self.user_filter.username}")

        with transaction.atomic():
            orfane = self._step_a_chiudi_orfane()
            riallineate = self._step_b_riallinea_apiario()
            doppioni = self._step_c_chiudi_doppioni()
            if not self.apply:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Riepilogo ==="))
        self.stdout.write(f"  A. colonie senza contenitore chiuse : {orfane}")
        self.stdout.write(f"  B. colonie riallineate all'apiario  : {riallineate}")
        self.stdout.write(f"  C. colonie duplicate chiuse         : {doppioni}")
        if not self.apply:
            self.stdout.write(self.style.WARNING("  Dry-run: rilancia con --apply per scrivere."))

    # ------------------------------------------------------------------ steps
    def _attive(self):
        qs = Colonia.objects.filter(stato='attiva', data_fine__isnull=True).select_related(
            'apiario', 'arnia', 'nucleo', 'utente',
        )
        if self.user_filter:
            qs = qs.filter(utente=self.user_filter)
        return qs

    def _chiudi(self, colonia, motivo):
        colonia.stato = 'eliminata'
        colonia.data_fine = self.oggi
        colonia.motivo_fine = motivo
        colonia.save(update_fields=['stato', 'data_fine', 'motivo_fine'])

    def _descrivi(self, colonia):
        regina = 'con regina' if hasattr(colonia, 'regina') else 'senza regina'
        return (
            f"Colonia #{colonia.id} ({colonia.apiario.nome}, {colonia.utente.username}, "
            f"dal {colonia.data_inizio}, {colonia.controlli.count()} controlli, {regina})"
        )

    def _step_a_chiudi_orfane(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- A) Colonie attive senza contenitore ---"
        ))
        n = 0
        for colonia in self._attive().filter(arnia__isnull=True, nucleo__isnull=True):
            self.stdout.write(f"  • {self._descrivi(colonia)}")
            self._chiudi(colonia, "Contenitore eliminato")
            n += 1
        if n == 0:
            self.stdout.write("  (nessuna)")
        return n

    def _step_b_riallinea_apiario(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- B) Colonie in un apiario diverso da quello del box ---"
        ))
        n = 0
        disallineate = (
            list(self._attive().filter(arnia__isnull=False)
                 .exclude(apiario_id=F('arnia__apiario_id')))
            + list(self._attive().filter(nucleo__isnull=False)
                   .exclude(apiario_id=F('nucleo__apiario_id')))
        )
        for colonia in disallineate:
            box = colonia.arnia or colonia.nucleo
            self.stdout.write(
                f"  • Colonia #{colonia.id}: {colonia.apiario.nome} -> {box.apiario.nome}"
            )
            colonia.apiario = box.apiario
            colonia.save(update_fields=['apiario'])
            n += 1
        if n == 0:
            self.stdout.write("  (nessuna)")
        return n

    def _step_c_chiudi_doppioni(self):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- C) Contenitori con più colonie attive ---"
        ))
        per_box = defaultdict(list)
        for colonia in self._attive().exclude(arnia__isnull=True, nucleo__isnull=True):
            chiave = ('Arnia', colonia.arnia) if colonia.arnia_id else ('Nucleo', colonia.nucleo)
            per_box[chiave].append(colonia)

        n = 0
        for (tipo, box), colonie in per_box.items():
            if len(colonie) < 2:
                continue
            colonie.sort(key=lambda c: (c.data_inizio, c.id), reverse=True)
            tenuta, *doppioni = colonie
            self.stdout.write(f"  {tipo} {box.numero} ({box.apiario.nome}):")
            self.stdout.write(self.style.SUCCESS(f"    tengo  {self._descrivi(tenuta)}"))
            for colonia in doppioni:
                self.stdout.write(self.style.WARNING(f"    chiudo {self._descrivi(colonia)}"))
                self._chiudi(colonia, f"Doppione della colonia #{tenuta.id}")
                n += 1
        if n == 0:
            self.stdout.write("  (nessuno)")
        return n
