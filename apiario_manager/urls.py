# Aggiorna apiario_manager/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from core.views import homepage
from core.auth_views import login_view, register_view, logout_view, password_reset_confirm_web, forgot_password_view, google_login_web, delete_account_view, delete_data_view
from core.views_nfc import nfc_landing, assetlinks_json, apple_aasa

# Swagger/OpenAPI per documentazione API
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

# Configurazione Swagger
schema_view = get_schema_view(
   openapi.Info(
      title="Apiario Manager API",
      default_version='v1',
      description="API per l'app mobile Apiario Manager",
      terms_of_service="https://www.gestioneapiario.it/terms/",
      contact=openapi.Contact(email="info@gestioneapiario.it"),
      license=openapi.License(name="All Rights Reserved"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path('admin/', admin.site.urls),

    # CKEditor 5 (asset/upload per il rich editor nel pannello admin)
    path('ckeditor5/', include('django_ckeditor_5.urls')),

    # API REST (non localizzate)
    path('api/v1/', include('core.api_urls')),

    # Modulo Statistiche & AI Analytics (non localizzate)
    path('api/stats/', include('statistiche.urls')),

    # Documenti Swagger/OpenAPI
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # NFC deep linking — questi path devono restare FUORI da i18n_patterns
    # perché App Link / Universal Link richiedono URL esatti senza prefisso
    # lingua. assetlinks.json e apple-app-site-association vengono scaricati
    # dall'OS per verificare l'app; /a/<nfc_id>/ è la landing di fallback
    # per browser senza app installata.
    path('.well-known/assetlinks.json', assetlinks_json, name='assetlinks_json'),
    path('.well-known/apple-app-site-association', apple_aasa, name='apple_aasa'),
    path('a/<str:nfc_id>/', nfc_landing, name='nfc_landing'),
    path('a/<str:nfc_id>', nfc_landing),  # senza trailing slash (i tag NFC non lo includono)
]

urlpatterns += i18n_patterns(
    path('', homepage, name='homepage'),  # Homepage come vista principale
    path('app/', include('core.urls')),   # Tutte le altre URL sotto /app/
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('forgot-password/', forgot_password_view, name='forgot_password'),
    path('auth/google/', google_login_web, name='google_login_web'),
    path('reset-password/<uidb64>/<token>/', password_reset_confirm_web, name='password_reset_confirm_web'),
    path('delete-account/', delete_account_view, name='delete_account'),
    path('delete-data/', delete_data_view, name='delete_data'),
)