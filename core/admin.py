from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html

from .admin_stats import build_admin_stats
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
    AdminBroadcast, Notifica,
)

# CKEditor 5 widget per il pannello broadcast (import safe: se la lib non è
# installata, fall back su Textarea senza rompere il caricamento dell'admin).
try:
    from django_ckeditor_5.widgets import CKEditor5Widget
    _RICH_WIDGET = CKEditor5Widget(config_name='broadcast')
except Exception:  # pragma: no cover
    _RICH_WIDGET = forms.Textarea(attrs={'rows': 12, 'cols': 80})


# ── Admin index esteso con statistiche ───────────────────────────────────────
_original_admin_index = admin.site.__class__.index


def _admin_index_with_stats(self, request, extra_context=None):
    extra_context = dict(extra_context or {})
    try:
        extra_context['app_stats'] = build_admin_stats()
    except Exception:
        extra_context['app_stats'] = None
    return _original_admin_index(self, request, extra_context=extra_context)


admin.site.__class__.index = _admin_index_with_stats
admin.site.index_template = 'admin/custom_index.html'


# ── User admin con last_login visibile in changelist ─────────────────────────
User = get_user_model()
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdminWithActivity(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name',
                    'is_staff', 'date_joined', 'last_login')
    list_filter = UserAdmin.list_filter + ('date_joined', 'last_login')
    ordering = ('-last_login',)


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


# ── Comunicazioni Broadcast (Centro notifiche admin) ────────────────────────

class AdminBroadcastForm(forms.ModelForm):
    """Form admin con CKEditor 5 per il corpo della broadcast."""

    class Meta:
        model = AdminBroadcast
        fields = '__all__'
        widgets = {
            'body_html': _RICH_WIDGET,
        }


@admin.register(AdminBroadcast)
class AdminBroadcastAdmin(admin.ModelAdmin):
    form = AdminBroadcastForm
    list_display = ['titolo', 'pubblicata_badge', 'priorita',
                    'data_creazione', 'data_pubblicazione', 'destinatari_count']
    list_filter = ['pubblicata', 'priorita']
    search_fields = ['titolo', 'body_html']
    readonly_fields = ['data_creazione', 'data_pubblicazione',
                       'destinatari_count', 'creata_da']
    fieldsets = (
        ('Contenuto', {
            'fields': ('titolo', 'body_html', 'immagine_url'),
            'description': (
                "Scrivi il messaggio. Usa la barra dell'editor per formattazione, "
                "link, elenchi. <b>Immagine</b>: incolla l'URL pubblico di "
                "un'immagine (https://...) opzionale come banner."
            ),
        }),
        ('Azione al tap', {
            'fields': ('link_route', 'link_param'),
            'description': (
                "Quando l'utente tocca la notifica, l'app apre la schermata "
                "scelta. <code>link_param</code> serve solo per alcune rotte "
                "(es. id dell'arnia)."
            ),
        }),
        ('Pubblicazione', {
            'fields': ('pubblicata', 'priorita',
                       'data_pubblicazione', 'destinatari_count'),
            'description': (
                "⚠️ Quando salvi con <b>Pubblicata</b> spuntato, la notifica "
                "viene inviata a tutti gli utenti attivi e <b>non è più "
                "modificabile</b>."
            ),
        }),
        ('Audit', {
            'fields': ('creata_da', 'data_creazione'),
            'classes': ('collapse',),
        }),
    )

    def pubblicata_badge(self, obj):
        if obj.pubblicata and obj.data_pubblicazione:
            return format_html('<span style="color:#080">✓ inviata</span>')
        if obj.pubblicata:
            return format_html('<span style="color:#a60">in invio…</span>')
        return format_html('<span style="color:#888">bozza</span>')
    pubblicata_badge.short_description = 'Stato'

    def save_model(self, request, obj, form, change):
        if not obj.creata_da_id:
            obj.creata_da = request.user
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        # Una volta pubblicata, blocca tutto tranne i campi audit (che sono
        # già readonly). Evita di modificare titolo/body dopo l'invio.
        if obj and obj.data_pubblicazione is not None:
            ro.extend(['titolo', 'body_html', 'immagine_url', 'link_route',
                       'link_param', 'priorita', 'pubblicata'])
        return ro


@admin.register(Notifica)
class NotificaAdmin(admin.ModelAdmin):
    list_display = ['utente', 'tipo', 'titolo', 'letta',
                    'priorita', 'data_creazione']
    list_filter = ['tipo', 'letta', 'priorita']
    search_fields = ['titolo', 'messaggio',
                     'utente__username', 'utente__email']
    readonly_fields = ['data_creazione', 'broadcast', 'mittente']
    raw_id_fields = ['utente']


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
