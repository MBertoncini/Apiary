from django.contrib import admin
from .models import (
    Apiario, Arnia, Colonia, ControlloArnia, Regina, StoriaRegine,
    Fioritura, FiorituraConferma,
    TrattamentoSanitario, TipoTrattamento,
    Melario, Smielatura, Gruppo, MembroGruppo, InvitoGruppo,
    Pagamento, QuotaUtente,
    Attrezzatura, SpesaAttrezzatura, ManutenzioneAttrezzatura,
    Invasettamento, Cliente, Vendita, DettaglioVendita,
    AnalisiTelaino, Nucleo, ControlloNucleo,
    Profilo, AI_TIER_LIMITS, ActivationCode,
)


@admin.register(Profilo)
class ProfiloAdmin(admin.ModelAdmin):
    list_display = ['utente', 'ai_tier', 'chat_usage', 'voice_usage',
                    'total_usage', 'ai_requests_reset_at']
    list_filter = ['ai_tier']
    search_fields = ['utente__username', 'utente__email']
    list_editable = ['ai_tier']
    readonly_fields = ['utente', 'ai_requests_reset_at', 'chat_usage', 'voice_usage', 'total_usage']
    fieldsets = (
        (None, {
            'fields': ('utente', 'immagine', 'data_nascita', 'bio',
                       'onboarding_completato'),
        }),
        ('API Keys', {
            'fields': ('gemini_api_key',),
        }),
        ('Piano AI & Utilizzo', {
            'fields': ('ai_tier', 'chat_usage', 'voice_usage',
                       'total_usage', 'ai_requests_reset_at'),
            'description': (
                'Limiti giornalieri per tier — '
                f'Base: {AI_TIER_LIMITS["free"]}, '
                f'Sostenitore: {AI_TIER_LIMITS["apicoltore"]}, '
                f'Tester Avanzato: {AI_TIER_LIMITS["professionale"]}'
            ),
        }),
    )

    def chat_usage(self, obj):
        limit = AI_TIER_LIMITS.get(obj.ai_tier, AI_TIER_LIMITS['free'])['chat']
        return f"{obj.ai_chat_today} / {limit}"
    chat_usage.short_description = 'Chat (oggi/max)'

    def voice_usage(self, obj):
        limit = AI_TIER_LIMITS.get(obj.ai_tier, AI_TIER_LIMITS['free'])['voice']
        return f"{obj.ai_voice_today} / {limit}"
    voice_usage.short_description = 'Voice (oggi/max)'

    def total_usage(self, obj):
        limit = AI_TIER_LIMITS.get(obj.ai_tier, AI_TIER_LIMITS['free'])['total']
        return f"{obj.ai_requests_today} / {limit}"
    total_usage.short_description = 'Totale (oggi/max)'

    actions = ['reset_ai_counters', 'set_tier_free', 'set_tier_apicoltore',
               'set_tier_professionale']

    @admin.action(description='Reset contatori AI a zero')
    def reset_ai_counters(self, request, queryset):
        queryset.update(ai_chat_today=0, ai_voice_today=0, ai_requests_today=0)
        self.message_user(request, f'{queryset.count()} profili resettati.')

    @admin.action(description='Imposta tier → Base (Test)')
    def set_tier_free(self, request, queryset):
        queryset.update(ai_tier='free')
        self.message_user(request, f'{queryset.count()} profili impostati a Base (Test).')

    @admin.action(description='Imposta tier → Sostenitore')
    def set_tier_apicoltore(self, request, queryset):
        queryset.update(ai_tier='apicoltore')
        self.message_user(request, f'{queryset.count()} profili impostati a Sostenitore.')

    @admin.action(description='Imposta tier → Tester Avanzato')
    def set_tier_professionale(self, request, queryset):
        queryset.update(ai_tier='professionale')
        self.message_user(request, f'{queryset.count()} profili impostati a Tester Avanzato.')


@admin.register(ActivationCode)
class ActivationCodeAdmin(admin.ModelAdmin):
    list_display = ['code', 'target_tier', 'times_used', 'max_uses', 'expires_at', 'is_valid_display', 'note']
    list_filter = ['target_tier']
    search_fields = ['code', 'note']
    readonly_fields = ['times_used', 'created_at']

    def is_valid_display(self, obj):
        return obj.is_valid
    is_valid_display.boolean = True
    is_valid_display.short_description = 'Valido'


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


@admin.register(Colonia)
class ColoniaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'apiario', 'contenitore_display', 'stato',
        'data_inizio', 'data_fine', 'utente',
    ]
    list_filter  = ['stato', 'apiario']
    search_fields = ['apiario__nome', 'note', 'arnia__numero', 'nucleo__numero']
    readonly_fields = ['data_creazione']
    raw_id_fields   = ['arnia', 'nucleo', 'colonia_origine', 'colonia_successore']

    def contenitore_display(self, obj):
        return obj.contenitore_display()
    contenitore_display.short_description = 'Contenitore'


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
