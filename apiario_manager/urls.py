# Aggiorna apiario_manager/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core.views import homepage  # Importa la vista homepage
from core.auth_views import register_view, logout_view  # Importa la vista register

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
    path('admin/', admin.site.urls),
    path('', homepage, name='homepage'),  # Homepage come vista principale
    path('app/', include('core.urls')),   # Tutte le altre URL sotto /app/
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),  # Usa la tua vista personalizzata invece di LogoutView
    path('register/', register_view, name='register'),  # Aggiunge la URL per la registrazione
    
    # Aggiungi le API REST
    path('api/v1/', include('core.api_urls')),
    
    # Documenti Swagger/OpenAPI
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
]