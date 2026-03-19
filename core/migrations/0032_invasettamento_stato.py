from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_cantina_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='invasettamento',
            name='stato',
            field=models.CharField(
                choices=[('disponibile', 'Disponibile'), ('venduto', 'Venduto')],
                default='disponibile',
                max_length=20,
            ),
        ),
    ]
