# Generated by Django 5.1.7 on 2025-03-08 15:36

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_apiario_condiviso_con_gruppo_apiario_proprietario_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagamento',
            name='gruppo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pagamenti', to='core.gruppo'),
        ),
        migrations.AddField(
            model_name='quotautente',
            name='gruppo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quote', to='core.gruppo'),
        ),
    ]
