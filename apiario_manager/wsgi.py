"""
WSGI config for apiario_manager project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiario_manager.settings')

application = get_wsgi_application()