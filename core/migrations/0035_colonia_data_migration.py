"""
Migration 0035 – FASE 1c (data migration)

Crea i record Colonia a partire dai dati esistenti di Arnia e Nucleo,
poi popola tutti i FK colonia sui modelli correlati.

LOGICA DI MIGRAZIONE:

Arnie:
  • arnia.attiva=True  → Colonia stato='attiva', data_fine=None
  • arnia.attiva=False → Colonia stato='eliminata', data_fine=data_installazione
    (non abbiamo info precisa sulla data di fine, usiamo data_installazione
     come placeholder conservativo — l'utente potrà correggere manualmente)

Nuclei (solo quelli NON già convertiti in arnia):
  • nucleo.attiva=True  → Colonia stato='attiva', data_fine=None
  • nucleo.attiva=False → Colonia stato='eliminata', data_fine=data_installazione

Nuclei già convertiti in arnia:
  • La Colonia esiste già (creata dalla riga Arnia corrispondente).
    Aggiorniamo colonia.nucleo per tracciare la provenienza storica
    (la colonia è partita da un nucleo ed è poi cresciuta in un'arnia).

FK correlati:
  • ControlloArnia.colonia  ← mappa tramite ControlloArnia.arnia_id → colonia
  • ControlloNucleo.colonia ← mappa tramite ControlloNucleo.nucleo_id → colonia
  • Regina.colonia          ← mappa tramite Regina.arnia_id → colonia
  • StoriaRegine.colonia    ← mappa tramite StoriaRegine.arnia_id → colonia
  • Melario.colonia         ← mappa tramite Melario.arnia_id → colonia
  • TrattamentoSanitario.colonie (M2M) ← espande TrattamentoSanitario.arnie (M2M)

ROLLBACK (reverse):
  • Cancella tutti i record Colonia creati da questa migration.
  • I FK/M2M vengono azzerati automaticamente (SET_NULL) dalla migration 0034.
  • I dati originali (Arnia, ControlloArnia, ecc.) restano INTATTI.
"""

from django.db import migrations
from django.utils import timezone


def crea_colonie_e_popola_fk(apps, schema_editor):
    Arnia                = apps.get_model('core', 'Arnia')
    Nucleo               = apps.get_model('core', 'Nucleo')
    Colonia              = apps.get_model('core', 'Colonia')
    ControlloArnia       = apps.get_model('core', 'ControlloArnia')
    ControlloNucleo      = apps.get_model('core', 'ControlloNucleo')
    Regina               = apps.get_model('core', 'Regina')
    StoriaRegine         = apps.get_model('core', 'StoriaRegine')
    Melario              = apps.get_model('core', 'Melario')
    TrattamentoSanitario = apps.get_model('core', 'TrattamentoSanitario')

    today = timezone.now().date()

    # ── STEP 1: Crea una Colonia per ogni Arnia ──────────────────────────────
    # Dizionario arnia_id → Colonia per uso nei passi successivi
    arnia_to_colonia = {}

    for arnia in Arnia.objects.select_related('apiario', 'apiario__proprietario').all():
        if arnia.attiva:
            stato     = 'attiva'
            data_fine = None
        else:
            # L'arnia non è attiva: segnaliamo 'eliminata'.
            # data_fine = data_installazione è il massimo che possiamo dedurre;
            # se l'arnia non ha mai avuto colonie significative va bene così.
            stato     = 'eliminata'
            data_fine = arnia.data_installazione  # placeholder conservativo

        colonia = Colonia(
            arnia    = arnia,
            nucleo   = None,
            apiario  = arnia.apiario,
            utente   = arnia.apiario.proprietario,
            data_inizio = arnia.data_installazione,
            data_fine   = data_fine,
            stato       = stato,
            note        = 'Migrata automaticamente da Arnia (migration 0035)',
        )
        colonia.save()
        arnia_to_colonia[arnia.id] = colonia

    # ── STEP 2: Crea una Colonia per ogni Nucleo NON convertito ─────────────
    # Un nucleo convertito (nucleo.arnia_id is not None) ha la sua Colonia
    # già creata nello step 1 tramite l'Arnia di destinazione.
    # In quel caso colleghiamo solo la provenienza storica (colonia.nucleo).
    nucleo_to_colonia = {}

    for nucleo in Nucleo.objects.select_related(
        'apiario', 'apiario__proprietario', 'arnia'
    ).all():
        if nucleo.arnia_id is not None:
            # Nucleo già convertito → la colonia è quella dell'arnia di destinazione
            colonia_esistente = arnia_to_colonia.get(nucleo.arnia_id)
            if colonia_esistente:
                # Segna che questa colonia è partita da un nucleo
                # (non sovrascriviamo arnia, solo aggiungiamo il riferimento nucleo
                #  nelle note per ora — il campo nucleo sulla Colonia è il
                #  "contenitore attuale", che qui è l'arnia)
                colonia_esistente.note = (
                    (colonia_esistente.note or '') +
                    f'\nProveniente da Nucleo {nucleo.numero} (convertito il {nucleo.data_conversione})'
                ).strip()
                colonia_esistente.save(update_fields=['note'])
                nucleo_to_colonia[nucleo.id] = colonia_esistente
        else:
            # Nucleo non convertito → crea Colonia dedicata
            if nucleo.attiva:
                stato     = 'attiva'
                data_fine = None
            else:
                stato     = 'eliminata'
                data_fine = nucleo.data_installazione

            colonia = Colonia(
                arnia    = None,
                nucleo   = nucleo,
                apiario  = nucleo.apiario,
                utente   = nucleo.apiario.proprietario,
                data_inizio = nucleo.data_installazione,
                data_fine   = data_fine,
                stato       = stato,
                note        = 'Migrata automaticamente da Nucleo (migration 0035)',
            )
            colonia.save()
            nucleo_to_colonia[nucleo.id] = colonia

    # ── STEP 3: Popola ControlloArnia.colonia ────────────────────────────────
    # Aggiornamento in bulk usando update() per evitare N query
    for arnia_id, colonia in arnia_to_colonia.items():
        ControlloArnia.objects.filter(arnia_id=arnia_id).update(colonia=colonia)

    # ── STEP 4: Popola ControlloNucleo.colonia ───────────────────────────────
    for nucleo_id, colonia in nucleo_to_colonia.items():
        ControlloNucleo.objects.filter(nucleo_id=nucleo_id).update(colonia=colonia)

    # ── STEP 5: Popola Regina.colonia ────────────────────────────────────────
    for regina in Regina.objects.filter(arnia_id__isnull=False):
        colonia = arnia_to_colonia.get(regina.arnia_id)
        if colonia:
            regina.colonia = colonia
            regina.save(update_fields=['colonia'])

    # ── STEP 6: Popola StoriaRegine.colonia ──────────────────────────────────
    for storia in StoriaRegine.objects.filter(arnia_id__isnull=False):
        colonia = arnia_to_colonia.get(storia.arnia_id)
        if colonia:
            storia.colonia = colonia
            storia.save(update_fields=['colonia'])

    # ── STEP 7: Popola Melario.colonia ───────────────────────────────────────
    for melario in Melario.objects.filter(arnia_id__isnull=False):
        colonia = arnia_to_colonia.get(melario.arnia_id)
        if colonia:
            melario.colonia = colonia
            melario.save(update_fields=['colonia'])

    # ── STEP 8: Popola TrattamentoSanitario.colonie (M2M) ────────────────────
    for trattamento in TrattamentoSanitario.objects.prefetch_related('arnie').all():
        colonie_da_aggiungere = []
        for arnia in trattamento.arnie.all():
            colonia = arnia_to_colonia.get(arnia.id)
            if colonia:
                colonie_da_aggiungere.append(colonia)
        if colonie_da_aggiungere:
            trattamento.colonie.set(colonie_da_aggiungere)


def cancella_colonie_migrate(apps, schema_editor):
    """
    Rollback: rimuove i record Colonia creati da questa migration.
    I FK su ControlloArnia, Regina, ecc. tornano NULL automaticamente (SET_NULL).
    I dati originali (Arnia, ControlloArnia, Regina, ecc.) restano INTATTI.
    """
    Colonia = apps.get_model('core', 'Colonia')
    Colonia.objects.filter(note__contains='migration 0035').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_colonia_schema'),
    ]

    operations = [
        migrations.RunPython(
            crea_colonie_e_popola_fk,
            reverse_code=cancella_colonie_migrate,
        ),
    ]
