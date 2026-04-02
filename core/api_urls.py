from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .api_views import (
    ApiarioViewSet, ArniaViewSet, ColoniaViewSet, ControlloArniaViewSet,
    ReginaViewSet, StoriaRegineViewSet, FiorituraViewSet, FiorituraConfermaViewSet,
    TrattamentoSanitarioViewSet,
    TipoTrattamentoViewSet, MelarioViewSet, SmielaturaViewSet, GruppoViewSet,
    current_user, sync_data, inviti_ricevuti, accetta_invito, rifiuta_invito,
    meteo_by_location, PagamentoViewSet, QuotaUtenteViewSet,
    CustomTokenObtainPairView, CustomTokenRefreshView,
    AttrezzaturaViewSet, SpesaAttrezzaturaViewSet, ManutenzioneAttrezzaturaViewSet,
    InvasettamentoViewSet, ClienteViewSet, VenditaViewSet,
    AnalisiTelainoViewSet, NucleoViewSet, register_user, chat_ai_api, ai_quota,
    password_reset_request, password_reset_confirm,
    PreferenzaMaturazionViewSet, MatutatoreViewSet, ContenitoreStoccaggioViewSet,
)

# Crea un router e registra i viewsets
router = DefaultRouter()
router.register(r'apiari', ApiarioViewSet, basename='api-apiario')
router.register(r'arnie', ArniaViewSet, basename='api-arnia')
router.register(r'colonie', ColoniaViewSet, basename='api-colonia')
router.register(r'controlli', ControlloArniaViewSet, basename='api-controllo')
router.register(r'regine', ReginaViewSet, basename='api-regina')
router.register(r'storia-regine', StoriaRegineViewSet, basename='api-storia-regina')
router.register(r'fioriture', FiorituraViewSet, basename='api-fioritura')
router.register(r'fioriture-conferme', FiorituraConfermaViewSet, basename='api-fioritura-conferma')
router.register(r'trattamenti', TrattamentoSanitarioViewSet, basename='api-trattamento')
router.register(r'tipi-trattamento', TipoTrattamentoViewSet, basename='api-tipo-trattamento')
router.register(r'melari', MelarioViewSet, basename='api-melario')
router.register(r'smielature', SmielaturaViewSet, basename='api-smielatura')
router.register(r'gruppi', GruppoViewSet, basename='api-gruppo')
router.register(r'pagamenti', PagamentoViewSet, basename='api-pagamento')
router.register(r'quote', QuotaUtenteViewSet, basename='api-quota')
router.register(r'attrezzature', AttrezzaturaViewSet, basename='api-attrezzatura')
router.register(r'spese-attrezzatura', SpesaAttrezzaturaViewSet, basename='api-spesa-attrezzatura')
router.register(r'manutenzioni', ManutenzioneAttrezzaturaViewSet, basename='api-manutenzione')
router.register(r'invasettamenti', InvasettamentoViewSet, basename='api-invasettamento')
router.register(r'clienti', ClienteViewSet, basename='api-cliente')
router.register(r'vendite', VenditaViewSet, basename='api-vendita')
router.register(r'analisi-telaini', AnalisiTelainoViewSet, basename='api-analisi-telaino')
router.register(r'nuclei', NucleoViewSet, basename='api-nucleo')
router.register(r'maturatori', MatutatoreViewSet, basename='api-maturatore')
router.register(r'contenitori-stoccaggio', ContenitoreStoccaggioViewSet, basename='api-contenitore')
router.register(r'preferenze-maturazione', PreferenzaMaturazionViewSet, basename='api-preferenza-maturazione')

# URLs per le API
urlpatterns = [
    # Include URLs router generati automaticamente
    path('', include(router.urls)),
    
    # URLs per autenticazione con JWT
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    
    # Endpoint per la sincronizzazione
    path('sync/', sync_data, name='api-sync'),

    # Endpoint per gli inviti
    path('inviti/ricevuti/', inviti_ricevuti, name='api-inviti-ricevuti'),
    path('inviti/accetta/<uuid:token>/', accetta_invito, name='api-attiva-invito'),
    path('inviti/rifiuta/<uuid:token>/', rifiuta_invito, name='api-rifiuta-invito'),
    
    # Endpoint per il profilo utente
    path('users/me/', current_user, name='api-current-user'),
    
    # Endpoint AI chat (JWT-compatible, per app mobile)
    path('ai/chat/', chat_ai_api, name='api-ai-chat'),
    path('ai/quota/', ai_quota, name='api-ai-quota'),

    # Endpoint per il meteo
    path('meteo/', meteo_by_location, name='api-meteo'),

    # Endpoint registrazione utente (app mobile)
    path('register/', register_user, name='api-register'),

    # Endpoint reset password (app mobile)
    path('password-reset/', password_reset_request, name='api-password-reset'),
    path('password-reset/confirm/', password_reset_confirm, name='api-password-reset-confirm'),
]