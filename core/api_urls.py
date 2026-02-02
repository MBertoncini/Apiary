from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .api_views import (
    ApiarioViewSet, ArniaViewSet, ControlloArniaViewSet, ReginaViewSet,
    FiorituraViewSet, TrattamentoSanitarioViewSet, TipoTrattamentoViewSet,
    MelarioViewSet, SmielaturaViewSet, GruppoViewSet, current_user,
    sync_data, inviti_ricevuti, accetta_invito, rifiuta_invito, meteo_by_location,
    PagamentoViewSet, QuotaUtenteViewSet, CustomTokenObtainPairView, CustomTokenRefreshView,
    AttrezzaturaViewSet, SpesaAttrezzaturaViewSet, ManutenzioneAttrezzaturaViewSet
)

# Crea un router e registra i viewsets
router = DefaultRouter()
router.register(r'apiari', ApiarioViewSet, basename='api-apiario')
router.register(r'arnie', ArniaViewSet, basename='api-arnia')
router.register(r'controlli', ControlloArniaViewSet, basename='api-controllo')
router.register(r'regine', ReginaViewSet, basename='api-regina')
router.register(r'fioriture', FiorituraViewSet, basename='api-fioritura')
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
    
    # Endpoint per il meteo
    path('meteo/', meteo_by_location, name='api-meteo'),
]