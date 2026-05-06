from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0041_controlloarnia_sostituzione_scatola_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="arnia",
            name="nfc_id",
            field=models.CharField(
                blank=True,
                help_text="ID del tag NFC associato (es. AA:BB:CC:DD)",
                max_length=50,
                null=True,
                unique=True,
            ),
        ),
    ]
