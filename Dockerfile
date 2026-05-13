# Reconstructed from the eccomerce-backend:latest image layers. Two-stage:
# the builder installs deps into /install (no compilers in the final image),
# the runtime copies that prefix + the source code and runs as the unprivileged
# `app` user. Same layout used by the prior production deploy.

# ---- builder ----
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# ---- runtime ----
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=backend.settings \
    PORT=8000

# Runtime libs only (no compilers). `curl` is used by the HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --home-dir /home/app app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app . .

# Strip CRLF line endings (Windows-edited entrypoint), make executable,
# pre-create the staticfiles target so `collectstatic` doesn't 500.
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh \
    && chmod +x /app/docker-entrypoint.sh \
    && mkdir -p /app/staticfiles \
    && chown -R app:app /app/staticfiles

USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# Shell-form CMD so `$PORT` expands at container start. Render / Fly /
# Cloud Run inject PORT at runtime (usually 10000); locally docker-compose
# leaves PORT=8000 from the ENV above so behaviour is unchanged.
CMD gunicorn backend.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:$PORT \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
