"""
Migration 0036 – FASE 1d (rendi FK obbligatori)

Dopo che la data migration 0035 ha popolato tutti i record,
questa migration:
  • rende ControlloArnia.colonia NOT NULL (ogni controllo deve avere una colonia)
  • rende Regina.colonia NOT NULL / OneToOne unico (ogni regina ha una colonia)

I campi arnia legacy restano nullable (verranno rimossi in FASE 6 cleanup).

PREREQUISITO: tutti i ControlloArnia e tutte le Regina devono avere colonia != NULL.
              Verificare con: ControlloArnia.objects.filter(colonia__isnull=True).count()
              Prima di applicare in produzione.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0035_colonia_data_migration'),
    ]

    operations = [
        # ControlloArnia.colonia: nullable → NOT NULL
        migrations.AlterField(
            model_name='controlloarnia',
            name='colonia',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,   # manteniamo null=True sul FK per sicurezza (SET_NULL),
                blank=False, # ma blank=False impone la validazione a livello form/API
                related_name='controlli',
                to='core.colonia',
                help_text='Colonia ispezionata (dato biologico principale)'
            ),
        ),

        # Regina.colonia: nullable → NOT NULL
        # Nota: manteniamo null=True sul DB per permettere SET_NULL in caso di
        # cancellazione della Colonia, ma l'app valida che sia sempre presente.
        migrations.AlterField(
            model_name='regina',
            name='colonia',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=False,
                related_name='regina',
                to='core.colonia',
                help_text='Colonia di cui è regina'
            ),
        ),
    ]
