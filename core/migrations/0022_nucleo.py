from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_apiariomaplayout'),
    ]

    operations = [
        migrations.CreateModel(
            name='Nucleo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.IntegerField()),
                ('colore_hex', models.CharField(
                    default='#8B6914',
                    help_text='Colore identificativo del nucleo',
                    max_length=7,
                )),
                ('data_installazione', models.DateField()),
                ('note', models.TextField(blank=True, null=True)),
                ('attiva', models.BooleanField(default=True)),
                ('data_conversione', models.DateField(blank=True, null=True)),
                ('data_creazione', models.DateTimeField(auto_now_add=True)),
                ('apiario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='nuclei',
                    to='core.apiario',
                )),
                ('arnia', models.OneToOneField(
                    blank=True,
                    help_text='Arnia creata dalla conversione di questo nucleo',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='nucleo_originale',
                    to='core.arnia',
                )),
            ],
            options={
                'verbose_name': 'Nucleo',
                'verbose_name_plural': 'Nuclei',
                'ordering': ['apiario', 'numero'],
            },
        ),
    ]
