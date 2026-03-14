from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_merge_20260311_0950'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemAiQuota',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requests_today', models.IntegerField(default=0)),
                ('reset_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Quota AI di sistema',
            },
        ),
        migrations.AddField(
            model_name='profilo',
            name='ai_requests_today',
            field=models.IntegerField(default=0, verbose_name='Richieste AI oggi (chiave personale)'),
        ),
        migrations.AddField(
            model_name='profilo',
            name='ai_requests_reset_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Reset contatore AI personale'),
        ),
    ]
