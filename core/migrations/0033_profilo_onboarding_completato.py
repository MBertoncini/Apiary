from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_invasettamento_stato'),
    ]

    operations = [
        migrations.AddField(
            model_name='profilo',
            name='onboarding_completato',
            field=models.BooleanField(default=False),
        ),
    ]
