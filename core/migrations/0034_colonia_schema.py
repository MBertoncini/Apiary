"""
Migration 0034 – FASE 1b (schema only)

Aggiunge:
  • tabella core_colonia (nuovo modello Colonia)
  • colonna colonia (FK nullable) su ControlloNucleo
  • colonne colonia (FK nullable) e modifica arnia (SET_NULL) su ControlloArnia
  • colonna colonia (OneToOne nullable) + arnia → SET_NULL su Regina
  • colonne colonia (FK nullable) + arnia → SET_NULL su StoriaRegine
  • colonne colonia (FK nullable) + arnia → SET_NULL su Melario
  • M2M colonie su TrattamentoSanitario

Nessun dato viene modificato: questa migration è REVERSIBILE con migrate 0033.
La migration 0035 (data migration) e 0036 (NOT NULL) la seguono.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_profilo_onboarding_completato'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── 1. Crea tabella core_colonia ─────────────────────────────────────
        migrations.CreateModel(
            name='Colonia',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data_inizio', models.DateField(
                    help_text='Data in cui la colonia è stata insediata nel contenitore attuale'
                )),
                ('data_fine', models.DateField(
                    blank=True, null=True,
                    help_text='Data di fine del ciclo (null = ancora attiva)'
                )),
                ('stato', models.CharField(
                    choices=[
                        ('attiva',    'Attiva'),
                        ('inattiva',  'Temporaneamente inattiva'),
                        ('morta',     'Colonia morta'),
                        ('venduta',   'Ceduta / Venduta'),
                        ('sciamata',  'Sciamata e non recuperata'),
                        ('unita',     'Unita ad altra colonia'),
                        ('nucleo',    'Ridotta a nucleo'),
                        ('eliminata', 'Eliminata'),
                    ],
                    default='attiva', max_length=20
                )),
                ('motivo_fine', models.TextField(
                    blank=True, null=True,
                    help_text='Descrizione del motivo di fine ciclo'
                )),
                ('note_fine', models.TextField(blank=True, null=True)),
                ('note',      models.TextField(blank=True, null=True)),
                ('data_creazione', models.DateTimeField(auto_now_add=True)),

                # FK al contenitore fisico (mutualmente esclusivi)
                ('arnia', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='colonie',
                    to='core.arnia',
                    help_text='Arnia (box completo) in cui vive attualmente la colonia'
                )),
                ('nucleo', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='colonie',
                    to='core.nucleo',
                    help_text='Nucleo in cui vive attualmente la colonia'
                )),

                # Denormalizzato
                ('apiario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='colonie',
                    to='core.apiario',
                )),
                ('utente', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='colonie',
                    to=settings.AUTH_USER_MODEL,
                )),

                # Genealogia (self-ref, aggiunta dopo la creazione della tabella)
                ('colonia_origine', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='colonie_figlie',
                    to='core.colonia',
                    help_text='Colonia da cui questa proviene'
                )),
                ('colonia_successore', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='colonie_assorbite',
                    to='core.colonia',
                    help_text='Colonia in cui è confluita questa (in caso di unione)'
                )),
            ],
            options={
                'verbose_name': 'Colonia',
                'verbose_name_plural': 'Colonie',
                'ordering': ['-data_inizio'],
            },
        ),

        # ── 2. ControlloNucleo: aggiungi colonia (nullable) ──────────────────
        migrations.AddField(
            model_name='controllonucleo',
            name='colonia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='controlli_nucleo',
                to='core.colonia',
                help_text='Colonia ispezionata'
            ),
        ),

        # ── 3. ControlloArnia: aggiungi colonia (nullable) ───────────────────
        #       arnia diventa SET_NULL/nullable (era CASCADE NOT NULL)
        migrations.AddField(
            model_name='controlloarnia',
            name='colonia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='controlli',
                to='core.colonia',
                help_text='Colonia ispezionata (dato biologico principale)'
            ),
        ),
        migrations.AlterField(
            model_name='controlloarnia',
            name='arnia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='controlli',
                to='core.arnia',
                help_text='Arnia (posizione fisica) al momento del controllo'
            ),
        ),

        # ── 4. Regina: aggiungi colonia (OneToOne nullable) ──────────────────
        #       arnia diventa SET_NULL/nullable (era CASCADE NOT NULL)
        migrations.AddField(
            model_name='regina',
            name='colonia',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='regina',
                to='core.colonia',
                help_text='Colonia di cui è regina'
            ),
        ),
        migrations.AlterField(
            model_name='regina',
            name='arnia',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='regina',
                to='core.arnia',
            ),
        ),

        # ── 5. StoriaRegine: aggiungi colonia (nullable) ─────────────────────
        #       arnia diventa SET_NULL/nullable (era CASCADE NOT NULL)
        migrations.AddField(
            model_name='storiaregine',
            name='colonia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='storia_regine',
                to='core.colonia',
                help_text='Colonia in cui la regina ha operato'
            ),
        ),
        migrations.AlterField(
            model_name='storiaregine',
            name='arnia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='storia_regine',
                to='core.arnia',
            ),
        ),

        # ── 6. Melario: aggiungi colonia (nullable) ──────────────────────────
        #       arnia diventa SET_NULL/nullable (era CASCADE NOT NULL)
        migrations.AddField(
            model_name='melario',
            name='colonia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='melari',
                to='core.colonia',
                help_text='Colonia su cui è posizionato il melario'
            ),
        ),
        migrations.AlterField(
            model_name='melario',
            name='arnia',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='melari',
                to='core.arnia',
            ),
        ),

        # ── 7. TrattamentoSanitario: aggiungi M2M colonie ────────────────────
        migrations.AddField(
            model_name='trattamentosanitario',
            name='colonie',
            field=models.ManyToManyField(
                blank=True,
                related_name='trattamenti',
                to='core.colonia',
                help_text='Colonie specifiche trattate (vuoto = tutto l\'apiario)'
            ),
        ),
    ]
