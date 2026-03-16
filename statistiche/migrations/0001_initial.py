from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DashboardConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('widget_config', models.JSONField(default=list)),
                ('aggiornato_il', models.DateTimeField(auto_now=True)),
                ('utente', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='dashboard_config',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Configurazione Dashboard',
                'verbose_name_plural': 'Configurazioni Dashboard',
            },
        ),
    ]
