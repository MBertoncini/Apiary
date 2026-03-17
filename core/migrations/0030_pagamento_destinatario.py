from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0029_arnia_tipo_arnia'),
    ]

    operations = [
        migrations.AddField(
            model_name='pagamento',
            name='destinatario',
            field=models.ForeignKey(
                blank=True,
                help_text='Membro che riceve il pagamento (usato per saldare bilanci tra membri)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='pagamenti_ricevuti',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
