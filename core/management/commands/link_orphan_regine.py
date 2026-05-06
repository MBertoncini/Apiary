"""
Ricollega le regine orfane (colonia=null) all'arnia/colonia corretta.

Le regine create dalla vecchia versione del client Flutter (prima del fix del
serializer) sono state salvate con `colonia=null` perché il client inviava
solo `arnia` e il serializer lo ignorava silenziosamente. Il risultato sono
record che nessun utente vede tramite gli endpoint `/api/v1/regine/` o
`/api/v1/arnie/{id}/regina/`.

Questo comando applica un'euristica basata sui controlli arnia:
  - Cerca i ControlloArnia con `data == regina.data_introduzione` e
    `presenza_regina=True`.
  - Se c'è una sola arnia candidata → la collega (creando la Colonia attiva
    se manca).
  - Se ci sono più candidati → registra il caso come ambiguo.
  - Se non ci sono candidati → registra come irrisolvibile.

Esempi:
    python manage.py link_orphan_regine --dry-run
    python manage.py link_orphan_regine
    python manage.py link_orphan_regine --delete-unlinkable
    python manage.py link_orphan_regine --user michele
"""
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Arnia, Colonia, ControlloArnia, Regina


class Command(BaseCommand):
    help = "Ricollega le regine orfane (colonia=null) all'arnia/colonia corretta usando i controlli come euristica."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Non scrive sul database, mostra solo cosa farebbe.",
        )
        parser.add_argument(
            '--delete-unlinkable',
            action='store_true',
            help="Elimina le regine orfane per cui non si trova alcuna arnia candidata.",
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help="Limita l'operazione alle regine la cui arnia candidata appartiene a questo username.",
        )
        parser.add_argument(
            '--window-days',
            type=int,
            default=2,
            help="Tolleranza in giorni per matchare data_introduzione contro la data del controllo (default 2).",
        )

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        delete_unlinkable = opts['delete_unlinkable']
        username = opts['user']
        window = timedelta(days=opts['window_days'])

        orphans = Regina.objects.filter(colonia__isnull=True).order_by('id')
        total = orphans.count()
        self.stdout.write(self.style.NOTICE(f"Regine orfane trovate: {total}"))
        if total == 0:
            return

        user_filter = None
        if username:
            try:
                user_filter = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Utente '{username}' non trovato."))
                return

        linked = 0
        ambiguous = 0
        unlinkable = 0
        deleted = 0

        for regina in orphans:
            data_intro = regina.data_introduzione
            if not data_intro:
                self._log_unlinkable(regina, "nessuna data_introduzione")
                unlinkable += 1
                continue

            # Cerca controlli con presenza_regina e data ravvicinata.
            qs = ControlloArnia.objects.filter(
                presenza_regina=True,
                data__gte=data_intro - window,
                data__lte=data_intro + window,
                arnia__isnull=False,
            )
            if user_filter is not None:
                qs = qs.filter(arnia__apiario__proprietario=user_filter)

            arnia_ids = (
                qs.values_list('arnia_id', flat=True).distinct()
            )
            arnia_ids = list(arnia_ids)

            if len(arnia_ids) == 0:
                self._log_unlinkable(regina, f"nessun controllo candidato vicino al {data_intro}")
                unlinkable += 1
                if delete_unlinkable and not dry:
                    regina.delete()
                    deleted += 1
                continue

            if len(arnia_ids) > 1:
                self._log_ambiguous(regina, arnia_ids)
                ambiguous += 1
                continue

            # Match unico → collega
            arnia = Arnia.objects.get(id=arnia_ids[0])
            colonia = self._get_or_create_active_colonia(arnia, data_intro, dry=dry)
            self.stdout.write(self.style.SUCCESS(
                f"  ↪ Regina #{regina.id} → Arnia {arnia.numero} (apiario '{arnia.apiario.nome}'), "
                f"colonia #{colonia.id if colonia else '?'}{' [DRY]' if dry else ''}"
            ))
            if not dry and colonia is not None:
                regina.colonia = colonia
                regina.save(update_fields=['colonia'])
            linked += 1

        self.stdout.write("")
        self.stdout.write(self.style.NOTICE(
            f"Riepilogo: collegate={linked}, ambigue={ambiguous}, irrisolvibili={unlinkable}"
            + (f", eliminate={deleted}" if delete_unlinkable else "")
            + (" [dry-run, nessuna modifica scritta]" if dry else "")
        ))

    # ------------------------------------------------------------------ helpers
    def _log_unlinkable(self, regina, reason):
        self.stdout.write(self.style.WARNING(
            f"  ✗ Regina #{regina.id} (intro {regina.data_introduzione}, razza {regina.razza}): {reason}"
        ))

    def _log_ambiguous(self, regina, arnia_ids):
        arnie = Arnia.objects.filter(id__in=arnia_ids).select_related('apiario')
        labels = ", ".join(f"arnia {a.numero} ({a.apiario.nome})" for a in arnie)
        self.stdout.write(self.style.WARNING(
            f"  ? Regina #{regina.id} (intro {regina.data_introduzione}): {len(arnia_ids)} candidati → {labels}"
        ))

    def _get_or_create_active_colonia(self, arnia, data_intro, dry=False):
        colonia = Colonia.objects.filter(
            arnia=arnia, stato='attiva', data_fine__isnull=True
        ).first()
        if colonia is not None:
            return colonia
        if dry:
            return None
        return Colonia.objects.create(
            arnia=arnia,
            apiario=arnia.apiario,
            utente=arnia.apiario.proprietario,
            data_inizio=data_intro or timezone.now().date(),
            stato='attiva',
        )
