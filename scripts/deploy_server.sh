#!/bin/bash
# Deploy su PythonAnywhere: backup DB, git pull, migrate, reload.
#
# Uso (da una console Bash di PythonAnywhere):
#   bash ~/Apiary/scripts/deploy_server.sh            # deploy se ci sono commit nuovi
#   bash ~/Apiary/scripts/deploy_server.sh --force    # rifà migrate e reload comunque
#   bash ~/Apiary/scripts/deploy_server.sh --check    # mostra solo cosa arriverebbe
#
# L'ultima riga stampata è sempre DEPLOY_OK <commit>, DEPLOY_NIENTE <commit>
# oppure DEPLOY_FAIL <motivo>: la legge la sentinella di apiary-ops.
#
# Variabili sovrascrivibili: WSGI_FILE, BACKUP_DIR, BACKUP_KEEP.

set -uo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WSGI_FILE="${WSGI_FILE:-/var/www/cible99_pythonanywhere_com_wsgi.py}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-3}"
MODE="${1:-}"
# La sentinella passa OPS_RUN per riconoscere l'esito di questa esecuzione
# nell'output della console (che contiene anche quello dei deploy precedenti).
RUN_TAG="${OPS_RUN:+[run $OPS_RUN]}"

fail() { echo "ERRORE: $1"; echo "DEPLOY_FAIL $1 $RUN_TAG"; exit 1; }

cd "$APP_DIR" || fail "cartella $APP_DIR non trovata"

# Virtualenv: usa quello già attivo, altrimenti l'unico in ~/.virtualenvs
if [ -z "${VIRTUAL_ENV:-}" ]; then
    venvs=("$HOME"/.virtualenvs/*/bin/activate)
    if [ "${#venvs[@]}" -eq 1 ] && [ -f "${venvs[0]}" ]; then
        # shellcheck disable=SC1090
        source "${venvs[0]}"
    else
        fail "virtualenv non attivo e non individuabile in ~/.virtualenvs"
    fi
fi

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short --untracked-files=no
    fail "file tracciati modificati sul server: sistemare a mano prima del deploy"
fi

PREV="$(git rev-parse HEAD)"
git fetch --quiet origin main || fail "git fetch non riuscito"
NEW="$(git rev-parse origin/main)"

echo "In produzione: $PREV"
echo "Su origin/main: $NEW"

if [ "$PREV" = "$NEW" ] && [ "$MODE" != "--force" ]; then
    echo "Nessun commit nuovo."
    echo "DEPLOY_NIENTE $PREV $RUN_TAG"
    exit 0
fi

echo "--- Commit in arrivo ---"
git log --oneline "$PREV..$NEW"
echo "--- File cambiati ---"
git diff --stat "$PREV" "$NEW" | tail -n 30

if [ "$MODE" = "--check" ]; then
    echo "DEPLOY_NIENTE $PREV (solo controllo) $RUN_TAG"
    exit 0
fi

# 1. Backup del database (compresso, si tengono gli ultimi $BACKUP_KEEP)
# Le credenziali si leggono dai settings di Django (che caricano ~/Apiary/.env):
# la console Bash non ha le variabili del file WSGI e senza host mysqldump
# proverebbe il socket locale, che su PythonAnywhere non esiste.
# Vanno in un file temporaneo leggibile solo dall'utente, cosi' la password
# non compare tra gli argomenti dei processi.
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/apiary_$(date +%Y%m%d_%H%M%S).sql.gz"
echo "--- Backup in $BACKUP_FILE ---"
DB_CNF="$(umask 077 && mktemp)" || fail "file temporaneo per il backup non creato"
trap 'rm -f "$DB_CNF"' EXIT
DB_INFO="$(DB_CNF="$DB_CNF" python - 2>&1 <<'PY'
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiario_manager.settings')
django.setup()
from django.conf import settings
db = settings.DATABASES['default']
if 'mysql' not in db['ENGINE'] or not db.get('HOST'):
    raise SystemExit('database non MySQL o host mancante nei settings')
pw = (db.get('PASSWORD') or '').replace('\\', '\\\\').replace('"', '\\"')
with open(os.environ['DB_CNF'], 'w') as f:
    f.write('[client]\nuser=%s\npassword="%s"\nhost=%s\nport=%s\n' % (
        db['USER'], pw, db['HOST'], db.get('PORT') or 3306))
print(db['NAME'])
PY
)" || fail "credenziali del database non leggibili dai settings: $(echo "$DB_INFO" | tail -n 1)"
DB_NAME="$(echo "$DB_INFO" | tail -n 1)"
if ! mysqldump --defaults-extra-file="$DB_CNF" --single-transaction --set-gtid-purged=OFF \
        --no-tablespaces --column-statistics=0 "$DB_NAME" | gzip > "$BACKUP_FILE"; then
    rm -f "$BACKUP_FILE"
    fail "backup del database non riuscito, deploy annullato"
fi
rm -f "$DB_CNF"
ls -1t "$BACKUP_DIR"/apiary_*.sql.gz 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" | xargs -r rm -f
du -h "$BACKUP_FILE" | cut -f1 | sed 's/^/Dimensione backup: /'

# 2. Codice
git merge --ff-only --quiet "$NEW" || fail "git merge --ff-only non riuscito"

rollback() {
    echo "Ripristino il codice a $PREV"
    git reset --hard --quiet "$PREV"
    fail "$1 (codice ripristinato, sito non ricaricato)"
}

# 3. Dipendenze, solo se requirements.txt è cambiato
if ! git diff --quiet "$PREV" "$NEW" -- requirements.txt; then
    echo "--- requirements.txt cambiato: pip install ---"
    pip install --no-cache-dir -q -r requirements.txt || rollback "pip install non riuscito"
fi

# 4. Controlli e migrazioni
python manage.py check || rollback "manage.py check non riuscito"
echo "--- Piano migrazioni ---"
if ! python manage.py migrate --plan; then
    rollback "piano migrazioni non valido (probabile conflitto con migrazioni create sul server)"
fi
python manage.py migrate --noinput || fail "migrate non riuscito DOPO il pull: controllare a mano, backup in $BACKUP_FILE"

# 5. Reload del web server
touch "$WSGI_FILE" || fail "touch di $WSGI_FILE non riuscito"
echo "Sito ricaricato."
echo "DEPLOY_OK $NEW $RUN_TAG"
