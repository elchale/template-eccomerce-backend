#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres to accept connections before doing anything else. Docker
# Compose's `depends_on.condition: service_healthy` covers most cases but the
# DB can still be a few seconds behind; cheap retry loop is enough.
wait_for_postgres() {
    local host="${DB_HOST:-db}"
    local port="${DB_PORT:-5432}"
    local user="${DB_USER:-postgres}"
    local retries=30

    until python - <<PY 2>/dev/null
import os, sys
import psycopg2
try:
    psycopg2.connect(
        host=os.environ.get('DB_HOST', 'db'),
        port=os.environ.get('DB_PORT', '5432'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASS', ''),
        dbname=os.environ.get('DB_NAME', 'postgres'),
        connect_timeout=2,
    ).close()
except Exception as exc:
    sys.exit(1)
PY
    do
        retries=$((retries - 1))
        if [ "$retries" -le 0 ]; then
            echo "postgres at $host:$port not reachable after timeout" >&2
            exit 1
        fi
        echo "waiting for postgres at $host:$port..."
        sleep 2
    done
}

# Decode the base64 GCS service-account JSON when supplied (production), or
# fall back to GCS_CREDENTIALS_PATH if mounted as a file.
materialise_gcs_credentials() {
    if [ -n "${GCS_CREDENTIALS_JSON:-}" ]; then
        local target="/tmp/gcs-credentials.json"
        python -c "import base64, os; open('${target}', 'wb').write(base64.b64decode(os.environ['GCS_CREDENTIALS_JSON']))"
        export GOOGLE_APPLICATION_CREDENTIALS="${target}"
    elif [ -n "${GCS_CREDENTIALS_PATH:-}" ] && [ -f "${GCS_CREDENTIALS_PATH}" ]; then
        export GOOGLE_APPLICATION_CREDENTIALS="${GCS_CREDENTIALS_PATH}"
    fi
}

materialise_gcs_credentials

# Migrations, collectstatic, and wizard only run on the web entrypoint.
# Celery workers reuse the same image but should not race the DB during boot.
case "${1:-}" in
    gunicorn|python|./manage.py)
        wait_for_postgres
        if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
            echo "running migrations..."
            python manage.py migrate --noinput
        fi
        if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
            echo "collecting static files..."
            python manage.py collectstatic --noinput --clear >/dev/null
        fi
        if [ "${RUN_WIZARD:-0}" = "1" ]; then
            echo "running wizard..."
            python wizard.py || echo "wizard exited non-zero (ignored)"
        fi
        ;;
    celery)
        wait_for_postgres
        ;;
esac

exec "$@"
