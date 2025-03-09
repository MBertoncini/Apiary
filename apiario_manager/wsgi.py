"""
WSGI config for apiario_manager project.


import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiario_manager.settings')

application = get_wsgi_application()
"""


#Il seguente per PythonAnywhere
import os
import sys

# Aggiungi la directory del progetto al path di sistema
path = '/home/yourusername/apiario_manager'
if path not in sys.path:
    sys.path.append(path)

# Imposta il file di settings di Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'apiario_manager.settings'

# Attiva il virtualenv
activate_this = '/home/yourusername/.virtualenvs/apiario_venv/bin/activate_this.py'
with open(activate_this) as file_:
    exec(file_.read(), dict(__file__=activate_this))

# Importa la funzione get_wsgi_application da Django
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()