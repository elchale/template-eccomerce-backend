#!/usr/bin/env bash
set -o errexit

if [ -n "${GCS_CREDENTIALS_JSON:-}" ]; then
    python -c "import base64, os; open('/tmp/gcs-credentials.json', 'wb').write(base64.b64decode(os.environ['GCS_CREDENTIALS_JSON']))"
    export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcs-credentials.json
fi

# Run migrations at startup (runtime). Railway only exposes the service env
# vars (DB_*, etc.) at run time, NOT during the Nixpacks build phase, so this
# is the only reliable place to migrate. Idempotent — a no-op once applied.
python manage.py migrate --noinput
python wizard.py

exec gunicorn backend.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
