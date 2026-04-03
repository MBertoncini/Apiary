"""
Migration 0037: FASE 6 cleanup — rimozione FK legacy arnia da Regina, StoriaRegine, Melario.

Presupposti (garantiti dalle migrazioni precedenti):
- 0034: colonne colonia_id già esistono su tutte e tre le tabelle
- 0035: colonia_id già popolata su tutti i record tramite data migration
- 0036: colonia blank=False su ControlloArnia e Regina

Dopo questa migrazione arnia_id viene rimosso da:
  - core_regina
  - core_storiaregine
  - core_melario
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_colonia_fk_notnull'),
    ]

    operations = [
        # ── Regina ────────────────────────────────────────────────────────────
        migrations.RemoveField(
            model_name='regina',
            name='arnia',
        ),

        # ── StoriaRegine ──────────────────────────────────────────────────────
        migrations.RemoveField(
            model_name='storiaregine',
            name='arnia',
        ),

        # ── Melario ───────────────────────────────────────────────────────────
        migrations.RemoveField(
            model_name='melario',
            name='arnia',
        ),

        # ── Aggiorna ordinamento Melario ──────────────────────────────────────
        migrations.AlterModelOptions(
            name='melario',
            options={
                'verbose_name': 'Melario',
                'verbose_name_plural': 'Melari',
                'ordering': ['colonia', 'posizione'],
            },
        ),
    ]
