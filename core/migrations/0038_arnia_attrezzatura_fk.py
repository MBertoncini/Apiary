import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_rimuovi_arnia_legacy_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='arnia',
            name='attrezzatura',
            field=models.ForeignKey(
                blank=True,
                help_text="Attrezzatura collegata (se tracciata nell'inventario)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='arnie',
                to='core.attrezzatura',
            ),
        ),
    ]
