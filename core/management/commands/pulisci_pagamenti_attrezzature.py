"""
Ripulisce i doppioni e i residui lasciati dalla vecchia gestione delle spese
attrezzatura, in cui ogni costo poteva finire fino a tre volte nelle uscite del
bilancio economico.

Cosa succedeva prima del fix:
  1. `AttrezzaturaViewSet.perform_create` registrava la SpesaAttrezzatura;
  2. l'app Flutter (fino alla build 19) ne registrava una seconda identica;
  3. l'app creava anche un Pagamento scollegato da tutto.
Il bilancio somma SpesaAttrezzatura + Pagamento, quindi un'arnia da 100 € pesava
300 €. Cancellando l'attrezzatura le spese sparivano in cascata ma il Pagamento
restava: un'uscita fantasma che nessuna schermata permetteva di ricondurre alla
sua origine.

Il comando esegue tre passi, in quest'ordine:
  A. elimina le SpesaAttrezzatura duplicate (stessa attrezzatura, tipo, importo,
     data e utente), tenendo la più vecchia;
  B. collega i Pagamento superstiti alla loro SpesaAttrezzatura (match su
     importo, data e pagante): da lì in poi il bilancio smette di contarli due
     volte e la cancellazione della spesa se li porta dietro;
  C. elimina i Pagamento automatici rimasti orfani, cioè quelli la cui spesa (o
     la cui attrezzatura) non esiste più.

Di default NON scrive nulla: stampa solo cosa farebbe. Per applicare le
modifiche serve `--apply`.

Esempi:
    python manage.py pulisci_pagamenti_attrezzature
    python manage.py pulisci_pagamenti_attrezzature --user mario
    python manage.py pulisci_pagamenti_attrezzature --apply
"""
from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from core.models import Pagamento, SpesaAttrezzatura
from core.signals import descrizione_pagamento_spesa

# Prefissi delle descrizioni generate automaticamente dai client/view vecchi.
# Solo i pagamenti che iniziano così sono considerati "automatici": tutto il
# resto è roba scritta a mano dall'utente e non va toccata.
PREFISSI_AUTO = (
    'Acquisto attrezzatura:',
    'Manutenzione attrezzatura:',
    'Spesa attrezzatura (',
)


class Command(BaseCommand):
    help = (
        "Elimina le spese attrezzatura duplicate e i pagamenti fantasma che "
        "gonfiavano il bilancio economico. Dry-run salvo --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help="Applica le modifiche (senza, è solo dry-run).")
        parser.add_argument('--user', type=str, default=None,
                            help="Limita l'intervento ai dati di questo username.")
        parser.add_argument('--anno', type=int, default=None,
                            help="Limita l'intervento a un anno specifico (campo data).")

    # ------------------------------------------------------------------ entry
    def handle(self, *args, **opts):
        self.apply = opts['apply']
        self.anno = opts['anno']
        # In dry-run tiene traccia dei pagamenti che il passo B *avrebbe*
        # ricollegato, così il passo C non li riconta come fantasma.
        self._simulati_collegati = set()
        self.user_filter = None
        if opts['user']:
            try:
                self.user_filter = User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f"Utente '{opts['user']}' non trovato.")

        intestazione = "APPLICO le modifiche" if self.apply else "DRY-RUN (nessuna scrittura)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"=== Pulizia pagamenti attrezzature — {intestazione} ==="))
        if self.user_filter:
            self.stdout.write(f"Filtro utente: {self.user_filter.username}")
        if self.anno:
            self.stdout.write(f"Filtro anno: {self.anno}")

        if self.apply:
            with transaction.atomic():
                duplicati = self._step_a_dedupe_spese()
                collegati = self._step_b_collega_pagamenti()
                orfani = self._step_c_elimina_orfani()
        else:
            duplicati = self._step_a_dedupe_spese()
            collegati = self._step_b_collega_pagamenti()
            orfani = self._step_c_elimina_orfani()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Riepilogo ==="))
        self.stdout.write(f"  A. spese duplicate eliminate : {duplicati['spese']} (€ {duplicati['importo']:.2f})")
        self.stdout.write(f"  B. pagamenti ricollegati     : {collegati['pagamenti']} (€ {collegati['importo']:.2f})")
        self.stdout.write(f"  C. pagamenti fantasma rimossi: {orfani['pagamenti']} (€ {orfani['importo']:.2f})")
        totale = duplicati['importo'] + collegati['importo'] + orfani['importo']
        self.stdout.write(self.style.SUCCESS(
            f"  Uscite tolte dal bilancio: € {totale:.2f}"
        ))
        if not self.apply:
            self.stdout.write(self.style.WARNING(
                "\nDry-run: nessuna modifica scritta. Rilancia con --apply per applicare."
            ))

    # ------------------------------------------------------------------ passi
    def _step_a_dedupe_spese(self):
        """Elimina le SpesaAttrezzatura identiche create due volte alla creazione
        dell'attrezzatura (una dal backend, una dal client vecchio)."""
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- A) SpesaAttrezzatura duplicate ---"
        ))

        qs = SpesaAttrezzatura.objects.filter(attrezzatura__isnull=False)
        if self.user_filter:
            qs = qs.filter(utente=self.user_filter)
        if self.anno:
            qs = qs.filter(data__year=self.anno)

        gruppi = defaultdict(list)
        for spesa in qs.select_related('attrezzatura').order_by('id'):
            chiave = (spesa.attrezzatura_id, spesa.tipo, spesa.importo,
                      spesa.data, spesa.utente_id)
            gruppi[chiave].append(spesa)

        eliminate, importo_tot = 0, 0.0
        for spese in gruppi.values():
            if len(spese) < 2:
                continue
            tenuta, doppioni = spese[0], spese[1:]
            nome = tenuta.attrezzatura.nome if tenuta.attrezzatura else '—'
            self.stdout.write(
                f"  • '{nome}' {tenuta.data} € {tenuta.importo} ({tenuta.get_tipo_display()}): "
                f"tengo #{tenuta.id}, elimino {', '.join('#%d' % s.id for s in doppioni)}"
            )
            for doppione in doppioni:
                eliminate += 1
                importo_tot += float(doppione.importo)
                if self.apply:
                    doppione.delete()

        if eliminate == 0:
            self.stdout.write("  (nessun duplicato)")
        return {'spese': eliminate, 'importo': importo_tot}

    def _step_b_collega_pagamenti(self):
        """Aggancia i Pagamento automatici superstiti alla loro spesa.

        Due passate: prima il match esatto sul pagante, poi — solo per le spese
        di gruppo — il match a pagante diverso. Il client vecchio infatti
        scriveva il "pagato da" scelto nella UI *solo* sul Pagamento e mai sulla
        spesa: senza la seconda passata quei pagamenti sembrerebbero fantasma e
        finirebbero cancellati, perdendo la traccia di chi ha sborsato i soldi.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- B) Pagamenti automatici da ricollegare alla spesa ---"
        ))

        collegati, importo_tot = 0, 0.0
        # Spese ancora senza pagamento collegato, per pagante/importo/data e,
        # per la seconda passata, per solo gruppo/importo/data.
        per_pagante = defaultdict(list)
        per_gruppo = defaultdict(list)
        spese_qs = SpesaAttrezzatura.objects.filter(pagamenti__isnull=True)
        if self.user_filter:
            spese_qs = spese_qs.filter(
                Q(utente=self.user_filter) | Q(pagato_da=self.user_filter)
            )
        if self.anno:
            spese_qs = spese_qs.filter(data__year=self.anno)
        for spesa in spese_qs.select_related('attrezzatura').order_by('id'):
            pagante_id = spesa.pagato_da_id or spesa.utente_id
            per_pagante[(pagante_id, spesa.importo, spesa.data)].append(spesa)
            if spesa.gruppo_id:
                per_gruppo[(spesa.gruppo_id, spesa.importo, spesa.data)].append(spesa)

        def _consuma(indice, chiave):
            """Preleva una spesa libera dall'indice, saltando quelle già prese."""
            for candidata in indice.get(chiave, []):
                if candidata.id in presi:
                    continue
                presi.add(candidata.id)
                return candidata
            return None

        presi = set()
        for pagamento in self._pagamenti_automatici_orfani():
            spesa = _consuma(per_pagante,
                             (pagamento.utente_id, pagamento.importo, pagamento.data))
            pagante_diverso = False
            if spesa is None and pagamento.gruppo_id:
                # Seconda passata: stessa spesa di gruppo, pagante diverso.
                spesa = _consuma(per_gruppo,
                                 (pagamento.gruppo_id, pagamento.importo, pagamento.data))
                pagante_diverso = spesa is not None
            if spesa is None:
                continue

            nota = ''
            if pagante_diverso:
                registrata_da = spesa.utente.username if spesa.utente_id else '—'
                nota = (f"  [pagante {pagamento.utente.username} != "
                        f"registrata da {registrata_da} -> imposto pagato_da]")
            self.stdout.write(
                f"  • Pagamento #{pagamento.id} '{pagamento.descrizione}' "
                f"-> SpesaAttrezzatura #{spesa.id}{nota}"
            )
            collegati += 1
            importo_tot += float(pagamento.importo)
            if self.apply:
                pagamento.spesa_attrezzatura = spesa
                pagamento.descrizione = descrizione_pagamento_spesa(spesa)
                pagamento.save(update_fields=['spesa_attrezzatura', 'descrizione'])
                if pagante_diverso and not spesa.pagato_da_id:
                    # Recupera sulla spesa l'informazione che il client vecchio
                    # aveva scritto solo sul pagamento.
                    spesa.pagato_da_id = pagamento.utente_id
                    spesa.save(update_fields=['pagato_da'])
            else:
                self._simulati_collegati.add(pagamento.id)

        if collegati == 0:
            self.stdout.write("  (nessun pagamento da ricollegare)")
        return {'pagamenti': collegati, 'importo': importo_tot}

    def _step_c_elimina_orfani(self):
        """Elimina i Pagamento automatici la cui spesa/attrezzatura non esiste più.

        È l'unico passo che cancella un dato non ricostruibile, quindi per ogni
        candidato stampiamo anche se esiste una spesa di pari importo e data che
        il passo B non ha potuto agganciare: se compare, conviene guardarla
        prima di dare --apply.
        """
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n--- C) Pagamenti fantasma (spesa inesistente) ---"
        ))

        eliminati, importo_tot = 0, 0.0
        for pagamento in self._pagamenti_automatici_orfani():
            self.stdout.write(
                f"  • Pagamento #{pagamento.id} {pagamento.data} € {pagamento.importo} "
                f"'{pagamento.descrizione}' (utente {pagamento.utente.username})"
            )
            simili = SpesaAttrezzatura.objects.filter(
                importo=pagamento.importo, data=pagamento.data
            ).select_related('attrezzatura', 'utente')[:3]
            for spesa in simili:
                nome = spesa.attrezzatura.nome if spesa.attrezzatura_id else '—'
                self.stdout.write(self.style.WARNING(
                    f"      ATTENZIONE: esiste la spesa #{spesa.id} '{nome}' "
                    f"di {spesa.utente.username} con stesso importo e data — "
                    f"verifica prima di cancellare"
                ))
            eliminati += 1
            importo_tot += float(pagamento.importo)
            if self.apply:
                pagamento.delete()

        if eliminati == 0:
            self.stdout.write("  (nessun pagamento fantasma)")
        return {'pagamenti': eliminati, 'importo': importo_tot}

    # ------------------------------------------------------------------ utils
    def _pagamenti_automatici_orfani(self):
        """Pagamenti non collegati a una spesa la cui descrizione è una di quelle
        generate automaticamente. In dry-run il passo B non scrive, quindi il
        passo C rivede gli stessi record: li filtriamo per non contarli due
        volte nel riepilogo."""
        qs = Pagamento.objects.filter(
            spesa_attrezzatura__isnull=True,
            destinatario__isnull=True,
        ).select_related('utente')
        if self.user_filter:
            qs = qs.filter(utente=self.user_filter)
        if self.anno:
            qs = qs.filter(data__year=self.anno)

        automatici = [p for p in qs.order_by('id')
                      if (p.descrizione or '').startswith(PREFISSI_AUTO)]

        if not self.apply and self._simulati_collegati:
            # Simula l'effetto del passo B: i pagamenti che *sarebbero* stati
            # ricollegati non vanno riproposti come fantasma nel passo C.
            automatici = [p for p in automatici if p.id not in self._simulati_collegati]
        return automatici
