from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_spesaattrezzatura_pagato_da'),
    ]

    operations = [
        migrations.AddField(
            model_name='trattamentosanitario',
            name='metodo_applicazione',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=20,
                choices=[
                    ('strisce', 'Strisce'),
                    ('gocciolato', 'Gocciolato'),
                    ('sublimato', 'Sublimato'),
                    ('altro', 'Altro'),
                ],
                help_text='Metodo di applicazione del trattamento',
            ),
        ),
    ]
