import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0050_add_admin_broadcast"),
    ]

    operations = [
        migrations.AddField(
            model_name="pagamento",
            name="spesa_attrezzatura",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Spesa attrezzatura che ha generato automaticamente questo pagamento. "
                    "Se valorizzato, l'importo è già contato nelle uscite come SpesaAttrezzatura "
                    "e il pagamento viene escluso dal bilancio economico (resta però valido per "
                    "le quote di gruppo). Cancellando la spesa il pagamento sparisce con lei."
                ),
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pagamenti",
                to="core.spesaattrezzatura",
            ),
        ),
    ]
