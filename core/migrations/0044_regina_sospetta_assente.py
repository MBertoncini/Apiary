from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0043_smielatura_kg_trasferiti_invasettamento_venduti"),
    ]

    operations = [
        migrations.AddField(
            model_name="regina",
            name="sospetta_assente",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Segnalata come sospetta assente da 2+ controlli consecutivi "
                    "senza regina e senza uova fresche"
                ),
            ),
        ),
    ]
