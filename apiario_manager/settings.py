"""
Django settings for apiario_manager project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cerca il .env nel percorso di produzione, altrimenti usa quello locale
env_path_prod = '/home/Cible99/.env'
if os.path.exists(env_path_prod):
    load_dotenv(dotenv_path=env_path_prod)
else:
    # In locale, si aspetta di trovare il .env nella root del progetto
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-yourkey12345678901234567890')

# Imposta DEBUG in base a una variabile d'ambiente, con un default sicuro
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 't')

# ALLOWED_HOSTS
ALLOWED_HOSTS = ['Cible99.pythonanywhere.com', 'localhost', '127.0.0.1']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'statistiche',
    'crispy_forms',
    'crispy_bootstrap5',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_yasg',
    'anymail',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Configurazione REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Impostazioni JWT
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=3650),
    'ROTATE_REFRESH_TOKENS': True,
}

# Configurazione CORS
CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = 'apiario_manager.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.meteo_settings',
                'core.context_processors.notifiche_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'apiario_manager.wsgi.application'

# Database
if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD'),
            'HOST': os.getenv('DB_HOST'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            }
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'it'
TIME_ZONE = 'Europe/Rome'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('it', 'Italiano'),
    ('en', 'English'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Static files & Media
STATIC_URL = '/static/'
STATIC_ROOT = '/home/Cible99/Apiary/static'
MEDIA_URL = '/media/'
MEDIA_ROOT = '/home/Cible99/Apiary/media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email - Brevo (Sendinblue) transactional email
EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'
ANYMAIL = {
    'BREVO_API_KEY': os.environ.get('BREVO_API_KEY', ''),
}
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Apiario Manager <noreply@gestioneapiario.it>')
FEEDBACK_RECIPIENT_EMAIL = os.environ.get('FEEDBACK_RECIPIENT_EMAIL', 'noreply@gestioneapiario.it')

# Variabili di progetto personalizzate
METEO_DATA_RETENTION_DAYS = 120
OPENWEATHERMAP_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY', '')

# Gemini AI
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# Groq AI (per modulo Statistiche NL Query)
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
STATS_MAX_RESULT_ROWS = int(os.environ.get('STATS_MAX_RESULT_ROWS', 500))
STATS_CACHE_WIDGETS_SECONDS = int(os.environ.get('STATS_CACHE_WIDGETS_SECONDS', 300))

# Cache (locmem in sviluppo, Redis in produzione)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'apiary-stats-cache',
    }
}

# ONNX bee detection model (esportato da best.pt con ultralytics)
ONNX_MODEL_PATH = str(BASE_DIR / 'core' / 'ai_models' / 'best.onnx')

# Configurazione crispy forms
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Configurazione login/logout
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'homepage'