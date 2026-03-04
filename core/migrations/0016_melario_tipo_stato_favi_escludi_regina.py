from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_analisitelaino'),
    ]

    operations = [
        migrations.AddField(
            model_name='melario',
            name='tipo_melario',
            field=models.CharField(
                choices=[('standard', 'Standard (Dadan)'), ('tre_quarti', '3/4'), ('meta', '1/2')],
                default='standard',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='melario',
            name='stato_favi',
            field=models.CharField(
                choices=[('costruiti', 'Già costruiti'), ('fogli_cerei', 'Fogli cerei')],
                default='costruiti',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='melario',
            name='escludi_regina',
            field=models.BooleanField(
                default=True,
                help_text='Indica se è presente un escludiregina',
            ),
        ),
    ]
