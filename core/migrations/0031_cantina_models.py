from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0030_pagamento_destinatario'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Make Invasettamento.smielatura nullable
        migrations.AlterField(
            model_name='invasettamento',
            name='smielatura',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invasettamenti',
                to='core.smielatura',
            ),
        ),

        # 2. Create PreferenzaMaturazione
        migrations.CreateModel(
            name='PreferenzaMaturazione',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_miele', models.CharField(max_length=100)),
                ('giorni_maturazione', models.IntegerField(default=21)),
                ('utente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='preferenze_maturazione',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Preferenza Maturazione',
                'verbose_name_plural': 'Preferenze Maturazione',
                'ordering': ['tipo_miele'],
                'unique_together': {('utente', 'tipo_miele')},
            },
        ),

        # 3. Create Maturatore
        migrations.CreateModel(
            name='Maturatore',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100)),
                ('capacita_kg', models.DecimalField(decimal_places=2, help_text='Capacità in kg', max_digits=7)),
                ('kg_attuali', models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ('tipo_miele', models.CharField(max_length=100)),
                ('data_inizio', models.DateField()),
                ('giorni_maturazione', models.IntegerField(default=21)),
                ('stato', models.CharField(
                    choices=[('in_maturazione', 'In Maturazione'), ('pronto', 'Pronto'), ('svuotato', 'Svuotato')],
                    default='in_maturazione', max_length=20,
                )),
                ('note', models.TextField(blank=True, null=True)),
                ('data_registrazione', models.DateTimeField(auto_now_add=True)),
                ('smielatura', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='maturatori',
                    to='core.smielatura',
                )),
                ('utente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='maturatori',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Maturatore',
                'verbose_name_plural': 'Maturatori',
                'ordering': ['-data_inizio'],
            },
        ),

        # 4. Create ContenitoreStoccaggio
        migrations.CreateModel(
            name='ContenitoreStoccaggio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(blank=True, max_length=100)),
                ('tipo', models.CharField(
                    choices=[('secchio', 'Secchio'), ('bidone', 'Bidone inox'), ('fusto', 'Fusto'), ('altro', 'Altro')],
                    default='secchio', max_length=20,
                )),
                ('capacita_kg', models.DecimalField(decimal_places=2, max_digits=7)),
                ('kg_attuali', models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ('tipo_miele', models.CharField(max_length=100)),
                ('data_riempimento', models.DateField()),
                ('stato', models.CharField(
                    choices=[('pieno', 'Pieno'), ('parziale', 'Parziale'), ('vuoto', 'Vuoto')],
                    default='pieno', max_length=20,
                )),
                ('note', models.TextField(blank=True, null=True)),
                ('data_registrazione', models.DateTimeField(auto_now_add=True)),
                ('maturatore', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='contenitori',
                    to='core.maturatore',
                )),
                ('utente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contenitori_stoccaggio',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Contenitore Stoccaggio',
                'verbose_name_plural': 'Contenitori Stoccaggio',
                'ordering': ['-data_riempimento'],
            },
        ),

        # 5. Add contenitore FK to Invasettamento
        migrations.AddField(
            model_name='invasettamento',
            name='contenitore',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='invasettamenti',
                to='core.contenitorestoccaggio',
            ),
        ),
    ]
