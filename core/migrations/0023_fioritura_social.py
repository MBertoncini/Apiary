from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_nucleo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='fioritura',
            name='pubblica',
            field=models.BooleanField(default=False, help_text='Visibile a tutta la community di apicoltori'),
        ),
        migrations.AddField(
            model_name='fioritura',
            name='intensita',
            field=models.IntegerField(
                blank=True,
                choices=[(1, 'Scarsa'), (2, 'Discreta'), (3, 'Buona'), (4, 'Ottima'), (5, 'Eccezionale')],
                help_text='Intensità/qualità della fioritura stimata dal creatore',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='fioritura',
            name='pianta_tipo',
            field=models.CharField(
                blank=True,
                choices=[
                    ('spontanea', 'Spontanea'),
                    ('coltivata', 'Coltivata'),
                    ('alberata', 'Alberata'),
                    ('arborea', 'Arborea'),
                    ('arbustiva', 'Arbustiva'),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name='FiorituraConferma',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateTimeField(auto_now_add=True)),
                ('intensita', models.IntegerField(
                    blank=True,
                    choices=[(1, 'Scarsa'), (2, 'Discreta'), (3, 'Buona'), (4, 'Ottima'), (5, 'Eccezionale')],
                    null=True,
                )),
                ('nota', models.TextField(blank=True, null=True)),
                ('fioritura', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conferme', to='core.fioritura')),
                ('utente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='conferme_fioriture', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Conferma Fioritura',
                'verbose_name_plural': 'Conferme Fioriture',
                'ordering': ['-data'],
                'unique_together': {('fioritura', 'utente')},
            },
        ),
    ]
