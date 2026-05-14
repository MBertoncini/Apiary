import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_meteogiornaliero"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add efficacy fields to TipoTrattamento
        migrations.AddField(
            model_name="tipotrattamento",
            name="efficacia_foretica",
            field=models.FloatField(
                default=0.9,
                help_text="Frazione di varroa foretiche uccise (0-1). Es: ossalico ≈ 0.95, formico ≈ 0.80",
            ),
        ),
        migrations.AddField(
            model_name="tipotrattamento",
            name="efficacia_in_covata",
            field=models.FloatField(
                default=0.0,
                help_text="Frazione di varroa in covata uccise (0-1). Es: formico ≈ 0.60, calore ≈ 0.90",
            ),
        ),
        # Create VarroaCheckpoint model
        migrations.CreateModel(
            name="VarroaCheckpoint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "data_campionamento",
                    models.DateField(),
                ),
                (
                    "metodo",
                    models.CharField(
                        choices=[
                            ("lavaggio_alcolico", "Lavaggio alcolico"),
                            ("caduta_naturale",   "Caduta naturale (fondo)"),
                            ("sugar_shake",       "Zucchero a velo (sugar shake)"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "api_campionate",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        help_text="Numero di api nel campione (lavaggio alcolico / sugar shake)",
                    ),
                ),
                (
                    "acari_contati",
                    models.PositiveIntegerField(
                        help_text="Acari Varroa contati nel campione o nel periodo di rilevazione",
                    ),
                ),
                (
                    "giorni_misurazione",
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        help_text="Giorni di rilevazione con fondo (solo caduta naturale)",
                    ),
                ),
                (
                    "telaini_covata",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Telaini di covata al campionamento (per calibrazione modello)",
                    ),
                ),
                (
                    "percentuale_calcolata",
                    models.FloatField(
                        help_text="% infestazione stimata calcolata automaticamente",
                    ),
                ),
                (
                    "caduta_giornaliera",
                    models.FloatField(
                        blank=True,
                        null=True,
                        help_text="Acari/giorno (calcolato solo per caduta naturale)",
                    ),
                ),
                (
                    "confidenza",
                    models.FloatField(
                        default=1.0,
                        help_text="Affidabilità: 0.95 lavaggio, 0.75 sugar shake, 0.50 caduta naturale",
                    ),
                ),
                ("note", models.TextField(blank=True, null=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                (
                    "colonia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="varroa_checkpoints",
                        to="core.colonia",
                    ),
                ),
                (
                    "utente",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Checkpoint Varroa",
                "verbose_name_plural": "Checkpoint Varroa",
                "ordering": ["-data_campionamento"],
                "indexes": [
                    models.Index(
                        fields=["colonia", "data_campionamento"],
                        name="idx_varroa_cp_colonia_data",
                    )
                ],
            },
        ),
    ]
