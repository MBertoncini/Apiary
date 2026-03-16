from django.contrib import admin
from .models import (
    Apiario, Arnia, ControlloArnia, Regina, StoriaRegine,
    Fioritura, FiorituraConferma,
    TrattamentoSanitario, TipoTrattamento,
    Melario, Smielatura, Gruppo, MembroGruppo, InvitoGruppo,
    Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura,
    Invasettamento, Cliente, Vendita, DettaglioVendita,
    AnalisiTelaino, Nucleo, ControlloNucleo,
)


@admin.register(Fioritura)
class FiorituraAdmin(admin.ModelAdmin):
    list_display = ['pianta', 'apiario', 'data_inizio', 'data_fine', 'pubblica', 'intensita', 'creatore']
    list_filter = ['pubblica', 'intensita', 'pianta_tipo']
    search_fields = ['pianta', 'apiario__nome', 'creatore__username']
    readonly_fields = ['data_creazione', 'data_modifica', 'creatore']


@admin.register(FiorituraConferma)
class FiorituraConfermaAdmin(admin.ModelAdmin):
    list_display = ['fioritura', 'utente', 'intensita', 'data']
    list_filter = ['intensita']
    search_fields = ['fioritura__pianta', 'utente__username']
    readonly_fields = ['data']


@admin.register(Arnia)
class ArniaAdmin(admin.ModelAdmin):
    list_display = ['numero', 'apiario', 'tipo_arnia', 'colore', 'attiva', 'data_installazione']
    list_filter = ['tipo_arnia', 'attiva', 'colore']
    search_fields = ['numero', 'apiario__nome', 'note']


# Registrazioni semplici per il resto dei model
for model in [
    Apiario, ControlloArnia, Regina, StoriaRegine,
    TrattamentoSanitario, TipoTrattamento,
    Melario, Smielatura, Gruppo, MembroGruppo, InvitoGruppo,
    Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura,
    Invasettamento, Cliente, Vendita, DettaglioVendita,
    AnalisiTelaino, Nucleo, ControlloNucleo,
]:
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
