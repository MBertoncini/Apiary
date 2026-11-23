# Aggiunge ControlloArnia.peso_kg: colonna nuova, nullable, nessun dato esistente toccato.
#
# Numerata 0055 e senza un elenco fisso di dipendenze perche' sul server di
# produzione esistono migrazioni create li' e assenti in git (fino a una
# 0054_merge_*). Con una dipendenza solo da 0053 il grafo di produzione avrebbe
# due foglie e il migrate si fermerebbe. Questa migrazione dipende da tutte le
# migrazioni di core con numero inferiore presenti nella cartella: in git
# equivale a dipendere da 0053, in produzione anche dalla 0054_merge_*.
# Le migrazioni future possono dipendere da questa normalmente.

import os
import re
from decimal import Decimal

import django.core.validators
from django.db import migrations, models

_NUMERO = 55
_CARTELLA = os.path.dirname(os.path.abspath(__file__))
_PRECEDENTI = sorted(
    nome[:-3]
    for nome in os.listdir(_CARTELLA)
    if re.match(r"^\d{4}_\w+\.py$", nome) and int(nome[:4]) < _NUMERO
)


class Migration(migrations.Migration):
    dependencies = [("core", nome) for nome in _PRECEDENTI]

    operations = [
        migrations.AddField(
            model_name="controlloarnia",
            name="peso_kg",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Peso dell'arnia in kg",
                max_digits=6,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
