# Aggiorna apiario_manager/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core.views import homepage  # Importa la vista homepage
from core.auth_views import register_view, logout_view  # Importa la vista register

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', homepage, name='homepage'),  # Homepage come vista principale
    path('app/', include('core.urls')),   # Tutte le altre URL sotto /app/
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),  # Usa la tua vista personalizzata invece di LogoutView
    path('register/', register_view, name='register'),  # Aggiunge la URL per la registrazione
]

# Aggiungi queste configurazioni al file urls.py del progetto (apiario_manager/urls.py)

from django.conf import settings
from django.conf.urls.static import static

# Aggiungi questa riga in fondo al file, dopo urlpatterns
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)