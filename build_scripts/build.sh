#!/usr/bin/env bash
set -o errexit

python -m pip install --upgrade pip
pip install -r requirements.txt

# NOTE: `migrate` and `wizard.py` deliberately do NOT run here. The Nixpacks
# BUILD phase has no access to the Railway service's runtime env vars (DB_*),
# so migrating here silently no-ops against the real database. They run in
# start.sh instead (runtime), mirroring jobkiwi's working setup.
python manage.py collectstatic --noinput
