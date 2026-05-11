"""Melario.numero_progressivo: counter per-utente stabile e visibile in UI.

L'`id` SQL è globale e crea numeri non sequenziali per l'utente. Si aggiunge
un campo `numero_progressivo` (1..N nell'ordine di creazione) per utente
proprietario dell'apiario su cui poggia la colonia del melario.

Backfill: per ogni proprietario, assegna 1..N ai melari esistenti ordinati per
`id` ascendente (proxy di "ordine di creazione" più stabile possibile).
"""

from django.db import migrations, models


def _backfill_numero_progressivo(apps, schema_editor):
    Melario = apps.get_model('core', 'Melario')
    # Gruppo per proprietario: melario.colonia.apiario.proprietario_id
    qs = (
        Melario.objects
        .filter(colonia__apiario__proprietario_id__isnull=False)
        .values_list('id', 'colonia__apiario__proprietario_id')
        .order_by('colonia__apiario__proprietario_id', 'id')
    )
    counters = {}
    updates = []
    for melario_id, proprietario_id in qs:
        counters[proprietario_id] = counters.get(proprietario_id, 0) + 1
        updates.append((melario_id, counters[proprietario_id]))
    for melario_id, n in updates:
        Melario.objects.filter(pk=melario_id).update(numero_progressivo=n)


def _backfill_reverse(apps, schema_editor):
    Melario = apps.get_model('core', 'Melario')
    Melario.objects.update(numero_progressivo=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_smielatura_through_e_storico_melario'),
    ]

    operations = [
        migrations.AddField(
            model_name='melario',
            name='numero_progressivo',
            field=models.IntegerField(
                blank=True, db_index=True, null=True,
                help_text=(
                    "Numero progressivo per-utente (1..N nell'ordine di creazione). "
                    "Indipendente dal pk SQL globale. Auto-assegnato al create."
                ),
            ),
        ),
        migrations.RunPython(_backfill_numero_progressivo, _backfill_reverse),
    ]
