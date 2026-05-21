"""Schema ML per modelli predittivi per-colonia.

Aggiunge:
- PesataMelario: pesate (lordo/tara/netto) di un melario per evento.
- Alimentazione: somministrazioni di nutrimento per-colonia.
- NomadismoEvent: storico spostamenti apiario di una colonia.
- SmielaturaMelario.kg_miele: attribuzione kg miele al singolo melario.
- Smielatura.fioriture (M2M): collega il raccolto alle fioriture di origine.
- AnalisiTelaino.colonia: FK opzionale alla colonia presente al momento.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0048_varroacheckpoint"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── SmielaturaMelario: kg attribuiti al singolo melario ─────────────
        migrations.AddField(
            model_name="smielaturamelario",
            name="kg_miele",
            field=models.DecimalField(
                max_digits=7, decimal_places=2, null=True, blank=True,
                help_text="Kg di miele attribuiti a questo melario (per analisi per-colonia)",
            ),
        ),
        # ── Smielatura ↔ Fioritura (M2M) ─────────────────────────────────────
        migrations.AddField(
            model_name="smielatura",
            name="fioriture",
            field=models.ManyToManyField(
                related_name="smielature", blank=True, to="core.fioritura",
                help_text="Fioriture da cui proviene principalmente il raccolto (per modelli predittivi)",
            ),
        ),
        # ── AnalisiTelaino.colonia FK opzionale ──────────────────────────────
        migrations.AddField(
            model_name="analisitelaino",
            name="colonia",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name="analisi_telaini",
                to="core.colonia",
                help_text="Colonia presente nell'arnia al momento dell'analisi (dato biologico)",
            ),
        ),
        # ── PesataMelario ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="PesataMelario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField()),
                (
                    "tipo",
                    models.CharField(
                        max_length=20,
                        default="rimozione",
                        choices=[
                            ("posizionamento", "Posizionamento"),
                            ("intermedia",     "Pesata intermedia"),
                            ("rimozione",      "Rimozione dal nido"),
                            ("smielatura",     "Pre-smielatura"),
                        ],
                    ),
                ),
                (
                    "peso_lordo_kg",
                    models.DecimalField(
                        max_digits=6, decimal_places=2,
                        help_text="Peso lordo misurato (melario + favi + miele) in kg",
                    ),
                ),
                (
                    "tara_kg",
                    models.DecimalField(
                        max_digits=6, decimal_places=2, null=True, blank=True,
                        help_text="Tara del melario vuoto in kg (favi inclusi se costruiti)",
                    ),
                ),
                (
                    "peso_netto_kg",
                    models.DecimalField(
                        max_digits=6, decimal_places=2, null=True, blank=True,
                        help_text="Peso netto miele in kg (auto-calcolato come lordo - tara se entrambi disponibili)",
                    ),
                ),
                ("note", models.TextField(blank=True, null=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                (
                    "melario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pesate", to="core.melario",
                    ),
                ),
                (
                    "colonia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True, blank=True,
                        related_name="pesate_melari", to="core.colonia",
                        help_text="Colonia produttrice al momento della pesata",
                    ),
                ),
                (
                    "fioritura",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True, blank=True,
                        related_name="pesate_melari", to="core.fioritura",
                        help_text="Fioritura principale a cui il melario è stato esposto",
                    ),
                ),
                (
                    "smielatura",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True, blank=True,
                        related_name="pesate_melari", to="core.smielatura",
                        help_text="Smielatura a cui questa pesata è collegata (se applicabile)",
                    ),
                ),
                (
                    "utente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pesate_melari",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Pesata Melario",
                "verbose_name_plural": "Pesate Melari",
                "ordering": ["-data", "-id"],
                "indexes": [
                    models.Index(fields=["melario", "data"], name="core_pesata_melario_05d247_idx"),
                    models.Index(fields=["colonia", "data"], name="core_pesata_colonia_c8b1e0_idx"),
                    models.Index(fields=["fioritura"], name="core_pesata_fioritu_3f4928_idx"),
                ],
            },
        ),
        # ── Alimentazione ────────────────────────────────────────────────────
        migrations.CreateModel(
            name="Alimentazione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField()),
                (
                    "tipo",
                    models.CharField(
                        max_length=20,
                        default="sciroppo_1_1",
                        choices=[
                            ("sciroppo_1_1",     "Sciroppo 1:1 (stimolante)"),
                            ("sciroppo_2_1",     "Sciroppo 2:1 (invernale)"),
                            ("candito",          "Candito"),
                            ("candito_proteico", "Candito proteico"),
                            ("polline",          "Polline / sostituti"),
                            ("miele",            "Miele"),
                            ("altro",            "Altro"),
                        ],
                    ),
                ),
                (
                    "scopo",
                    models.CharField(
                        max_length=20, blank=True, default="",
                        choices=[
                            ("stimolante",   "Stimolante primaverile"),
                            ("sostentamento","Sostentamento estivo"),
                            ("invernale",    "Riserve invernali"),
                            ("emergenza",    "Emergenza (fame)"),
                            ("introduzione", "Introduzione regina / sciame"),
                            ("altro",        "Altro"),
                        ],
                    ),
                ),
                (
                    "quantita_kg",
                    models.DecimalField(
                        max_digits=6, decimal_places=2,
                        help_text="Quantità somministrata in kg (per liquidi: assumere densità ~1.3 kg/l per sciroppo 2:1)",
                    ),
                ),
                ("note", models.TextField(blank=True, null=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                (
                    "colonia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alimentazioni", to="core.colonia",
                        help_text="Colonia a cui è stata somministrata l'alimentazione",
                    ),
                ),
                (
                    "utente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alimentazioni",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Alimentazione",
                "verbose_name_plural": "Alimentazioni",
                "ordering": ["-data", "-id"],
                "indexes": [
                    models.Index(fields=["colonia", "data"], name="core_alimen_colonia_74522c_idx"),
                ],
            },
        ),
        # ── NomadismoEvent ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="NomadismoEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_spostamento", models.DateField()),
                (
                    "motivo",
                    models.CharField(
                        max_length=100, blank=True,
                        help_text="Motivo dello spostamento (es. fioritura acacia, svernamento, divisione)",
                    ),
                ),
                ("note", models.TextField(blank=True, null=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                (
                    "colonia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="spostamenti", to="core.colonia",
                    ),
                ),
                (
                    "apiario_origine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True, blank=True,
                        related_name="nomadismo_partenze", to="core.apiario",
                        help_text="Apiario di partenza (null per primo insediamento)",
                    ),
                ),
                (
                    "apiario_destinazione",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nomadismo_arrivi", to="core.apiario",
                        help_text="Apiario di arrivo",
                    ),
                ),
                (
                    "utente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nomadismi",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Spostamento di nomadismo",
                "verbose_name_plural": "Spostamenti di nomadismo",
                "ordering": ["-data_spostamento", "-id"],
                "indexes": [
                    models.Index(fields=["colonia", "data_spostamento"], name="core_nomadi_colonia_abc0ec_idx"),
                ],
            },
        ),
    ]
