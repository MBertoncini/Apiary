from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_vendita_canale_pagamento_acquirente_dettaglio_categoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='gruppo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='clienti',
                to='core.gruppo',
            ),
        ),
        migrations.AddField(
            model_name='vendita',
            name='gruppo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='vendite',
                to='core.gruppo',
            ),
        ),
    ]
