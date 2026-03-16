from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_systemaiquota_profilo_ai_quota'),
    ]

    operations = [
        migrations.AddField(
            model_name='arnia',
            name='tipo_arnia',
            field=models.CharField(
                choices=[
                    ('dadant', 'Dadant-Blatt'),
                    ('langstroth', 'Langstroth'),
                    ('top_bar', 'Top Bar (Kenyana)'),
                    ('warre', 'Warré'),
                    ('osservazione', 'Arnia da Osservazione'),
                    ('pappa_reale', 'Arnia Pappa Reale / Allevamento Regine'),
                    ('nucleo_legno', 'Nucleo in Legno'),
                    ('nucleo_polistirolo', 'Nucleo in Polistirolo'),
                    ('portasciami', 'Portasciami / Prendisciame'),
                    ('apidea', 'Apidea / Kieler'),
                    ('mini_plus', 'Mini-Plus'),
                ],
                default='dadant',
                help_text="Modello / tipo costruttivo dell'arnia",
                max_length=25,
            ),
        ),
    ]
