from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_arnia_attrezzatura_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='profilo',
            name='ai_tier',
            field=models.CharField(
                choices=[('free', 'Free'), ('apicoltore', 'Apicoltore'), ('professionale', 'Professionale')],
                default='free',
                max_length=20,
                verbose_name='Piano AI',
            ),
        ),
        migrations.AddField(
            model_name='profilo',
            name='ai_chat_today',
            field=models.IntegerField(default=0, verbose_name='Richieste chat AI oggi'),
        ),
        migrations.AddField(
            model_name='profilo',
            name='ai_voice_today',
            field=models.IntegerField(default=0, verbose_name='Richieste voice AI oggi'),
        ),
    ]
