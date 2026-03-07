from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_trattamentosanitario_metodo_applicazione'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApiarioMapLayout',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('layout_json', models.TextField(
                    default='{}',
                    help_text='JSON con posizioni arnie e elementi decorativi (nuclei, alberi, vialetti)'
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('apiario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='map_layout',
                    to='core.apiario',
                )),
            ],
            options={
                'verbose_name': 'Layout Mappa Apiario',
                'verbose_name_plural': 'Layout Mappe Apiari',
            },
        ),
    ]
