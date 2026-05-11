"""Through table SmielaturaMelario con stato_origine + StoricoPosizioneMelario.

- Riusa la tabella `core_smielatura_melari` già auto-generata (SeparateDatabaseAndState):
  a livello DB aggiunge solo le colonne `stato_origine` e `data_link`; a livello
  state la M2M `Smielatura.melari` passa attraverso `SmielaturaMelario`.
- Per le righe legacy `stato_origine` viene popolato con 'rimosso' (default DB),
  così la semantica vecchia ("delete smielatura → melari a rimosso") è preservata
  per le smielature preesistenti.
- Crea `StoricoPosizioneMelario` e per ogni Melario esistente apre una riga
  "attiva" (data_fine=NULL) con motivo='seed_legacy'.
"""

from django.db import migrations, models
import django.db.models.deletion


def _seed_storico_melari(apps, schema_editor):
    """Crea una riga di storico attiva per ogni Melario già presente."""
    Melario = apps.get_model('core', 'Melario')
    StoricoPosizioneMelario = apps.get_model('core', 'StoricoPosizioneMelario')
    from django.utils import timezone
    oggi = timezone.now().date()
    rows = []
    for m in Melario.objects.all().iterator():
        rows.append(StoricoPosizioneMelario(
            melario_id=m.pk,
            colonia_id=m.colonia_id,
            posizione=m.posizione,
            stato=m.stato,
            data_inizio=m.data_posizionamento or oggi,
            data_fine=None,
            motivo='seed_legacy',
        ))
    if rows:
        StoricoPosizioneMelario.objects.bulk_create(rows, batch_size=200)


def _seed_storico_reverse(apps, schema_editor):
    StoricoPosizioneMelario = apps.get_model('core', 'StoricoPosizioneMelario')
    StoricoPosizioneMelario.objects.filter(motivo='seed_legacy').delete()


STATO_CHOICES = [
    ('posizionato', 'Posizionato'),
    ('rimosso', 'Rimosso'),
    ('in_smielatura', 'In Smielatura'),
    ('smielato', 'Smielato'),
]

MOTIVO_CHOICES = [
    ('posizionamento', 'Posizionamento iniziale'),
    ('riposizionamento', 'Riposizionamento'),
    ('shift_posizione', 'Spostamento di posizione'),
    ('cambio_colonia', 'Spostato su altra colonia'),
    ('cambio_stato', 'Cambio stato'),
    ('rimosso', 'Rimosso dalla colonia'),
    ('smielatura', 'Linkato a smielatura'),
    ('ripristino_smielatura', 'Ripristino da smielatura'),
    ('seed_legacy', 'Inizializzazione dato preesistente'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0044_regina_sospetta_assente'),
    ]

    operations = [
        # ── 1) StoricoPosizioneMelario ──────────────────────────────────────
        migrations.CreateModel(
            name='StoricoPosizioneMelario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('posizione', models.IntegerField(blank=True, help_text='Posizione occupata (NULL se non posizionato)', null=True)),
                ('stato', models.CharField(choices=STATO_CHOICES, help_text='Stato del melario in questo intervallo', max_length=20)),
                ('data_inizio', models.DateField()),
                ('data_fine', models.DateField(blank=True, help_text='NULL se il periodo è quello corrente', null=True)),
                ('motivo', models.CharField(blank=True, choices=MOTIVO_CHOICES, help_text='Evento che ha aperto questa riga', max_length=30)),
                ('note', models.CharField(blank=True, max_length=200)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('colonia', models.ForeignKey(blank=True, help_text='Colonia su cui il melario era posizionato in questo intervallo (NULL se non posizionato)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='storico_melari', to='core.colonia')),
                ('melario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='storico_posizioni', to='core.melario')),
            ],
            options={
                'verbose_name': 'Storico posizione melario',
                'verbose_name_plural': 'Storico posizioni melari',
                'ordering': ['melario_id', '-data_inizio', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='storicoposizionemelario',
            index=models.Index(fields=['melario', 'data_fine'], name='core_storic_melario_e2a87c_idx'),
        ),
        migrations.AddIndex(
            model_name='storicoposizionemelario',
            index=models.Index(fields=['colonia', 'posizione', 'data_fine'], name='core_storic_colonia_74d64a_idx'),
        ),

        # ── 2) Through table riusata ────────────────────────────────────────
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_smielatura_melari "
                        "ADD COLUMN stato_origine VARCHAR(20) NOT NULL DEFAULT 'rimosso';"
                    ),
                    reverse_sql=(
                        "ALTER TABLE core_smielatura_melari DROP COLUMN stato_origine;"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE core_smielatura_melari "
                        "ADD COLUMN data_link DATETIME NULL;"
                    ),
                    reverse_sql=(
                        "ALTER TABLE core_smielatura_melari DROP COLUMN data_link;"
                    ),
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='SmielaturaMelario',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('stato_origine', models.CharField(blank=True, choices=STATO_CHOICES, default='', help_text='Stato che il melario aveva prima del link; usato per il ripristino', max_length=20)),
                        ('data_link', models.DateTimeField(auto_now_add=True, blank=True, null=True)),
                        ('melario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.melario')),
                        ('smielatura', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.smielatura')),
                    ],
                    options={
                        'verbose_name': 'Link Smielatura-Melario',
                        'verbose_name_plural': 'Link Smielatura-Melario',
                        'db_table': 'core_smielatura_melari',
                        'unique_together': {('smielatura', 'melario')},
                    },
                ),
                migrations.AlterField(
                    model_name='smielatura',
                    name='melari',
                    field=models.ManyToManyField(related_name='smielature', through='core.SmielaturaMelario', to='core.melario'),
                ),
            ],
        ),

        # ── 3) Seed storico per Melari esistenti ────────────────────────────
        migrations.RunPython(_seed_storico_melari, _seed_storico_reverse),
    ]
