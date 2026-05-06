"""
Ricollega le regine orfane (colonia=null) all'arnia/colonia corretta.

Le regine create dalla vecchia versione del client Flutter (prima del fix del
serializer) sono state salvate con `colonia=null` perché il client inviava
solo `arnia` e il serializer lo ignorava silenziosamente. Il risultato sono
record che nessun utente vede tramite gli endpoint `/api/v1/regine/` o
`/api/v1/arnie/{id}/regina/`.

Modalità d'uso:
  --list                   solo elenco delle regine orfane (nessuna modifica)
  --auto-only [--dry-run]  euristica automatica, salta i casi ambigui
  --interactive [--dry-run] (default) chiede all'utente per i casi ambigui
  --link R:A               collegamento manuale Regina R → Arnia A
  --delete R               cancella la regina orfana R
  --delete-unlinkable      cancella le orfane senza candidati

Esempi:
    python manage.py link_orphan_regine --list
    python manage.py link_orphan_regine --auto-only --dry-run
    python manage.py link_orphan_regine                       # interattivo
    python manage.py link_orphan_regine --link 8:5 --link 12:3
    python manage.py link_orphan_regine --delete 14
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Arnia, Colonia, ControlloArnia, Regina


class Command(BaseCommand):
    help = (
        "Ricollega le regine orfane (colonia=null) all'arnia/colonia corretta "
        "usando i controlli come euristica, con fallback interattivo o manuale."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Non scrive sul database, mostra solo cosa farebbe.")
        parser.add_argument('--list', action='store_true', dest='just_list',
                            help="Mostra solo l'elenco delle regine orfane.")
        parser.add_argument('--auto-only', action='store_true',
                            help="Euristica automatica, salta i casi ambigui (no input).")
        parser.add_argument('--interactive', action='store_true',
                            help="Forza la modalità interattiva (è il default).")
        parser.add_argument('--link', action='append', default=[],
                            metavar='REGINA_ID:ARNIA_ID',
                            help="Collega manualmente: ripetibile (es. --link 8:5 --link 12:3).")
        parser.add_argument('--delete', action='append', default=[], type=int,
                            metavar='REGINA_ID',
                            help="Cancella una regina orfana specifica (ripetibile).")
        parser.add_argument('--delete-unlinkable', action='store_true',
                            help="Elimina le orfane senza candidati possibili.")
        parser.add_argument('--user', type=str, default=None,
                            help="Limita ai candidati la cui arnia appartiene a questo username.")
        parser.add_argument('--window-days', type=int, default=2,
                            help="Tolleranza in giorni per matchare data_introduzione (default 2).")

    # ------------------------------------------------------------------ entry
    def handle(self, *args, **opts):
        self.dry = opts['dry_run']
        self.window = timedelta(days=opts['window_days'])
        self.user_filter = None
        if opts['user']:
            try:
                self.user_filter = User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f"Utente '{opts['user']}' non trovato.")

        if opts['delete']:
            return self._do_delete(opts['delete'])

        if opts['link']:
            return self._do_manual_link(opts['link'])

        if opts['just_list']:
            return self._do_list()

        # Modalità default: euristica + (interattivo se non --auto-only)
        return self._do_auto(
            interactive=not opts['auto_only'],
            delete_unlinkable=opts['delete_unlinkable'],
        )

    # ------------------------------------------------------------------ ops
    def _do_list(self):
        orphans = self._orphans()
        self.stdout.write(self.style.NOTICE(f"Regine orfane trovate: {orphans.count()}"))
        for r in orphans:
            self.stdout.write(self._format_regina(r))
        return

    def _do_delete(self, regina_ids):
        for rid in regina_ids:
            try:
                r = Regina.objects.get(id=rid)
            except Regina.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Regina #{rid} non esiste."))
                continue
            if r.colonia_id is not None:
                self.stderr.write(self.style.WARNING(
                    f"Regina #{rid} ha già colonia #{r.colonia_id}: salto (usa il pannello admin)."
                ))
                continue
            tag = ' [DRY]' if self.dry else ''
            self.stdout.write(self.style.SUCCESS(f"✗ Cancello Regina #{rid}{tag}"))
            if not self.dry:
                r.delete()

    def _do_manual_link(self, pairs):
        for raw in pairs:
            try:
                rid, aid = (int(x) for x in raw.split(':'))
            except ValueError:
                raise CommandError(f"Formato --link non valido: '{raw}' (atteso REGINA_ID:ARNIA_ID).")
            try:
                regina = Regina.objects.get(id=rid)
                arnia  = Arnia.objects.get(id=aid)
            except (Regina.DoesNotExist, Arnia.DoesNotExist) as e:
                raise CommandError(f"--link {raw}: {e}")
            self._link(regina, arnia)

    def _do_auto(self, interactive, delete_unlinkable):
        orphans = self._orphans()
        total = orphans.count()
        self.stdout.write(self.style.NOTICE(f"Regine orfane trovate: {total}"))
        if total == 0:
            return

        linked = ambiguous = unlinkable = deleted = skipped = 0

        for regina in orphans:
            candidates = self._candidates_for(regina)

            if not candidates:
                self._log_unlinkable(regina, f"nessun candidato vicino al {regina.data_introduzione}")
                unlinkable += 1
                if delete_unlinkable and not self.dry:
                    regina.delete()
                    deleted += 1
                continue

            if len(candidates) == 1:
                arnia = candidates[0]
                self._link(regina, arnia)
                linked += 1
                continue

            # Multipli → ambiguo
            if not interactive:
                self._log_ambiguous(regina, candidates)
                ambiguous += 1
                continue

            choice = self._prompt_choice(regina, candidates)
            if choice is None:
                skipped += 1
                continue
            if choice == 'DELETE':
                tag = ' [DRY]' if self.dry else ''
                self.stdout.write(self.style.SUCCESS(f"✗ Cancello Regina #{regina.id}{tag}"))
                if not self.dry:
                    regina.delete()
                    deleted += 1
                continue
            self._link(regina, choice)
            linked += 1

        self.stdout.write("")
        msg = (
            f"Riepilogo: collegate={linked}, ambigue={ambiguous}, "
            f"irrisolvibili={unlinkable}, saltate={skipped}, eliminate={deleted}"
        )
        if self.dry:
            msg += " [dry-run, nessuna modifica scritta]"
        self.stdout.write(self.style.NOTICE(msg))

    # ------------------------------------------------------------------ core
    def _orphans(self):
        return Regina.objects.filter(colonia__isnull=True).order_by('id')

    def _candidates_for(self, regina):
        """Restituisce le arnie candidate per `regina`, già filtrate.

        Filtri applicati (in ordine di restrizione):
        1. Controllo con presenza_regina=True su data ≈ data_introduzione.
        2. Arnia non già "occupata" da una regina propriamente collegata.
        3. (se restano >1) Solo arnie il cui *primo* controllo con
           presenza_regina=True cade nella finestra: corrisponde al momento in
           cui maybeAutoCreate vedeva 404 e creava la scheda regina.
        """
        d = regina.data_introduzione
        if not d:
            return []

        qs = ControlloArnia.objects.filter(
            presenza_regina=True,
            data__gte=d - self.window,
            data__lte=d + self.window,
            arnia__isnull=False,
        )
        if self.user_filter is not None:
            qs = qs.filter(arnia__apiario__proprietario=self.user_filter)

        arnia_ids = list(qs.values_list('arnia_id', flat=True).distinct())
        if not arnia_ids:
            return []

        # Filtro 2: arnie senza altra regina già correttamente collegata.
        already_linked = set(Regina.objects
                             .filter(colonia__arnia_id__in=arnia_ids,
                                     colonia__stato='attiva',
                                     colonia__data_fine__isnull=True)
                             .exclude(id=regina.id)
                             .values_list('colonia__arnia_id', flat=True))
        kept_after_2 = [a for a in arnia_ids if a not in already_linked]
        # Fallback: se il filtro 2 elimina tutto, è probabile che la regina
        # vada a sostituirne una già esistente (caso "sostituzione regina"):
        # in quel caso non possiamo escludere le arnie già collegate, quindi
        # ripristiniamo l'elenco originale e lasciamo decidere all'utente.
        if kept_after_2:
            arnia_ids = kept_after_2
        if len(arnia_ids) <= 1:
            return list(Arnia.objects.filter(id__in=arnia_ids).select_related('apiario'))

        # Filtro 3: per ciascuna arnia, controllo che il PRIMO ControlloArnia
        # con presenza_regina=True per quell'arnia cada nella finestra. Se cade
        # prima, allora la regina sarebbe già stata auto-creata in passato.
        kept = []
        for aid in arnia_ids:
            first = (ControlloArnia.objects
                     .filter(arnia_id=aid, presenza_regina=True)
                     .order_by('data', 'id')
                     .first())
            if first is None:
                continue
            if first.data >= d - self.window and first.data <= d + self.window:
                kept.append(aid)

        # Se il filtro 3 toglie tutto, non lo applichiamo (meglio ambiguo che vuoto)
        if kept:
            arnia_ids = kept

        return list(Arnia.objects.filter(id__in=arnia_ids).select_related('apiario'))

    def _link(self, regina, arnia):
        d = regina.data_introduzione
        colonia = self._get_or_create_active_colonia(arnia, d)
        tag = ' [DRY]' if self.dry else ''
        self.stdout.write(self.style.SUCCESS(
            f"  ↪ Regina #{regina.id} → Arnia {arnia.numero} (apiario '{arnia.apiario.nome}'), "
            f"colonia #{colonia.id if colonia else '?'}{tag}"
        ))
        if not self.dry and colonia is not None:
            regina.colonia = colonia
            regina.save(update_fields=['colonia'])

    def _get_or_create_active_colonia(self, arnia, data_intro):
        colonia = Colonia.objects.filter(
            arnia=arnia, stato='attiva', data_fine__isnull=True
        ).first()
        if colonia is not None:
            return colonia
        if self.dry:
            return None
        return Colonia.objects.create(
            arnia=arnia,
            apiario=arnia.apiario,
            utente=arnia.apiario.proprietario,
            data_inizio=data_intro or timezone.now().date(),
            stato='attiva',
        )

    # ------------------------------------------------------------------ ux
    def _format_regina(self, r):
        bits = [f"#{r.id}", f"intro {r.data_introduzione}", f"razza {r.razza}",
                f"origine {r.origine}"]
        if r.codice_marcatura:
            bits.append(f"cod. {r.codice_marcatura}")
        if r.colore_marcatura and r.colore_marcatura != 'non_marcata':
            bits.append(f"colore {r.colore_marcatura}")
        if r.note:
            note = r.note.strip().replace('\n', ' ')
            if len(note) > 60:
                note = note[:57] + '…'
            bits.append(f"note: {note}")
        return "  • " + " | ".join(bits)

    def _log_unlinkable(self, regina, reason):
        self.stdout.write(self.style.WARNING(
            f"  ✗ Regina #{regina.id} (intro {regina.data_introduzione}, razza {regina.razza}): {reason}"
        ))

    def _log_ambiguous(self, regina, candidates):
        labels = ", ".join(f"arnia {a.numero} ({a.apiario.nome})" for a in candidates)
        self.stdout.write(self.style.WARNING(
            f"  ? Regina #{regina.id} (intro {regina.data_introduzione}): "
            f"{len(candidates)} candidati → {labels}"
        ))

    def _prompt_choice(self, regina, candidates):
        """Mostra i candidati e chiede una scelta. Ritorna Arnia, 'DELETE' o None (skip)."""
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            f"Regina #{regina.id} è ambigua (intro {regina.data_introduzione}, razza {regina.razza})"
        ))
        for i, a in enumerate(candidates, 1):
            self.stdout.write(f"  [{i}] arnia {a.numero} (apiario '{a.apiario.nome}')  id={a.id}")
        self.stdout.write("  [s] skip   [d] delete   [a:<id>] collega ad arnia con quell'id")
        try:
            raw = input("Scelta: ").strip().lower()
        except EOFError:
            return None
        if not raw or raw in ('s', 'skip'):
            return None
        if raw in ('d', 'delete', 'del'):
            return 'DELETE'
        if raw.startswith('a:'):
            try:
                aid = int(raw.split(':', 1)[1])
                return Arnia.objects.get(id=aid)
            except (ValueError, Arnia.DoesNotExist):
                self.stderr.write(self.style.ERROR(f"Arnia id non valido: '{raw}'."))
                return None
        try:
            idx = int(raw)
            if 1 <= idx <= len(candidates):
                return candidates[idx - 1]
        except ValueError:
            pass
        self.stderr.write(self.style.ERROR(f"Input non valido: '{raw}'. Salto."))
        return None
