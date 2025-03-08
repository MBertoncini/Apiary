# Aggiorna apiario_manager/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from core.views import homepage  # Importa la vista homepage

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', homepage, name='homepage'),  # Homepage come vista principale
    path('app/', include('core.urls')),   # Tutte le altre URL sotto /app/
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='homepage'), name='logout'),  # Reindirizza alla homepage dopo il logout
    path('register/', auth_views.LoginView.as_view(template_name='auth/register.html'), name='register'),
]