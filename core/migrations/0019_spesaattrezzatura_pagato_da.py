from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0018_cliente_gruppo_vendita_gruppo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='spesaattrezzatura',
            name='pagato_da',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='spese_pagate',
                to=settings.AUTH_USER_MODEL,
                help_text='Membro del gruppo che ha effettivamente pagato',
            ),
        ),
    ]
