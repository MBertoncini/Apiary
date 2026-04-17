from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_profilo_ai_tier_and_counters'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivationCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=50, unique=True)),
                ('target_tier', models.CharField(
                    choices=[('free', 'Free'), ('apicoltore', 'Apicoltore'), ('professionale', 'Professionale')],
                    default='apicoltore',
                    max_length=20,
                    verbose_name='Tier da attivare',
                )),
                ('max_uses', models.IntegerField(default=1, verbose_name='Utilizzi massimi')),
                ('times_used', models.IntegerField(default=0, verbose_name='Volte utilizzato')),
                ('expires_at', models.DateTimeField(blank=True, null=True, verbose_name='Scadenza')),
                ('note', models.CharField(blank=True, max_length=200, verbose_name='Nota interna')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Codice attivazione AI',
                'verbose_name_plural': 'Codici attivazione AI',
            },
        ),
    ]
