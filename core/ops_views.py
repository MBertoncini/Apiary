"""Endpoint di servizio per i bot di gestione (apiary-ops).

Tre endpoint in sola lettura, pensati per essere interrogati dalla sentinella
che gira sul PC di casa:

- ``GET /api/v1/ops/status/``  commit in produzione, stato DB e migrazioni
- ``GET /api/v1/ops/errors/``  righe nuove dell'error log del web server
- ``GET /api/v1/ops/stats/``   statistiche d'uso aggregate (nessun dato personale)

Autenticazione: header ``X-Ops-Token`` uguale alla variabile d'ambiente
``OPS_TOKEN`` (nel ``.env`` di produzione). Se ``OPS_TOKEN`` non è impostata
gli endpoint rispondono 404, come se non esistessero.
"""

import hmac
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db import models as dj_models
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

DEFAULT_ERROR_LOG = '/var/log/cible99.pythonanywhere.com.error.log'
# Quanti byte leggere dalla coda del log: basta per qualche centinaio di righe.
ERROR_LOG_TAIL_BYTES = 256 * 1024
# Le righe dell'error log di PythonAnywhere iniziano con "2026-11-18 10:21:33,512: ".
_TS_RE = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:,\d+)?:')


def _check_token(request):
    expected = os.environ.get('OPS_TOKEN', '')
    if not expected:
        raise Http404()
    received = request.headers.get('X-Ops-Token', '')
    if not hmac.compare_digest(received.encode(), expected.encode()):
        return JsonResponse({'detail': 'token non valido'}, status=403)
    return None


def _git(*args):
    try:
        out = subprocess.run(
            ['git', *args], cwd=settings.BASE_DIR, capture_output=True,
            text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _migrations_info():
    info = {'pending': [], 'conflicts': {}, 'error': None}
    try:
        executor = MigrationExecutor(connection)
        loader = executor.loader
        conflicts = loader.detect_conflicts()
        info['conflicts'] = {app: sorted(names) for app, names in conflicts.items()}
        if not conflicts:
            targets = loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
            info['pending'] = [f'{m.app_label}.{m.name}' for m, _backwards in plan]
    except Exception as exc:  # il DB potrebbe non rispondere: lo riportiamo
        info['error'] = str(exc)[:500]
    return info


@require_GET
def ops_status(request):
    denied = _check_token(request)
    if denied:
        return denied

    db_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        db_ok = False

    return JsonResponse({
        'ok': db_ok,
        'time': timezone.now().isoformat(),
        'commit': _git('rev-parse', 'HEAD'),
        'commit_date': _git('log', '-1', '--format=%cI'),
        'branch': _git('rev-parse', '--abbrev-ref', 'HEAD'),
        'db_ok': db_ok,
        'debug': settings.DEBUG,
        'migrations': _migrations_info() if db_ok else None,
    })


def _parse_since(value):
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


@require_GET
def ops_errors(request):
    """Righe dell'error log successive a ``since`` (formato ``YYYY-MM-DD HH:MM:SS``).

    Le righe senza timestamp (continuazioni di traceback) seguono la riga
    datata che le precede.
    """
    denied = _check_token(request)
    if denied:
        return denied

    path = Path(os.environ.get('OPS_ERROR_LOG', DEFAULT_ERROR_LOG))
    since = _parse_since(request.GET.get('since'))
    try:
        max_lines = max(1, min(int(request.GET.get('max', 300)), 2000))
    except ValueError:
        max_lines = 300

    if not path.exists():
        return JsonResponse({'lines': [], 'last_ts': None, 'missing': str(path)})

    size = path.stat().st_size
    with path.open('rb') as fh:
        if size > ERROR_LOG_TAIL_BYTES:
            fh.seek(size - ERROR_LOG_TAIL_BYTES)
            fh.readline()  # scarta la riga tagliata a metà
        raw = fh.read().decode('utf-8', errors='replace')

    selected = []
    last_ts = None
    keep = since is None
    for line in raw.splitlines():
        match = _TS_RE.match(line)
        if match:
            ts = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
            last_ts = match.group(1)
            keep = since is None or ts > since
        if keep:
            selected.append(line)

    truncated = len(selected) > max_lines
    return JsonResponse({
        'lines': selected[-max_lines:],
        'truncated': truncated,
        'last_ts': last_ts,
        'size': size,
    })


def _creation_field(model):
    for field in model._meta.get_fields():
        if isinstance(field, (dj_models.DateTimeField, dj_models.DateField)) and getattr(field, 'auto_now_add', False):
            return field.name
    return None


def _user_fk(model, user_model):
    for field in model._meta.get_fields():
        if isinstance(field, dj_models.ForeignKey) and field.related_model is user_model:
            return field.name
    return None


@require_GET
def ops_stats(request):
    """Conteggi aggregati per modello: totale, nuovi nel periodo, utenti attivi.

    Nessun dato personale: solo numeri. ``days`` (default 30) definisce il periodo.
    """
    denied = _check_token(request)
    if denied:
        return denied

    try:
        days = max(1, min(int(request.GET.get('days', 30)), 366))
    except ValueError:
        days = 30
    now = timezone.now()
    since = now - timedelta(days=days)
    since_7 = now - timedelta(days=7)

    User = get_user_model()
    users = {
        'totale': User.objects.count(),
        'nuovi_periodo': User.objects.filter(date_joined__gte=since).count(),
        'login_periodo': User.objects.filter(last_login__gte=since).count(),
        'login_7_giorni': User.objects.filter(last_login__gte=since_7).count(),
    }

    per_model = {}
    attivi = set()
    for model in apps.get_app_config('core').get_models():
        entry = {'totale': model.objects.count()}
        created = _creation_field(model)
        if created:
            recent = model.objects.filter(**{f'{created}__gte': since})
            entry['nuovi_periodo'] = recent.count()
            user_fk = _user_fk(model, User)
            if user_fk:
                ids = set(recent.exclude(**{f'{user_fk}__isnull': True})
                          .values_list(user_fk, flat=True).distinct())
                entry['utenti_distinti_periodo'] = len(ids)
                attivi |= ids
        per_model[model.__name__] = entry

    users['attivi_periodo'] = len(attivi)
    return JsonResponse({
        'periodo_giorni': days,
        'generato': now.isoformat(),
        'utenti': users,
        'modelli': per_model,
    })
