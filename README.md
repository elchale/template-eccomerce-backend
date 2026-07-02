<div align="center">
  <img src="static/images/logo.svg" alt="Logo" width="96" height="96">

  <h1>E-commerce Template — Backend</h1>

  <p><strong>Production-ready Django REST API for an e-commerce storefront. JWT auth, multi-language catalog, GCS uploads, payment integration, Docker-first deployment.</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.13-3776ab?logo=python&logoColor=fff" alt="Python">
    <img src="https://img.shields.io/badge/Django-5.2-092e20?logo=django&logoColor=fff" alt="Django">
    <img src="https://img.shields.io/badge/DRF-3.16-a30000" alt="DRF">
    <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&logoColor=fff" alt="Postgres">
    <img src="https://img.shields.io/badge/Redis-7-dc382d?logo=redis&logoColor=fff" alt="Redis">
    <img src="https://img.shields.io/badge/Celery-5.5-37814a?logo=celery&logoColor=fff" alt="Celery">
    <img src="https://img.shields.io/badge/Docker-ready-2496ed?logo=docker&logoColor=fff" alt="Docker">
    <img src="https://img.shields.io/badge/License-MIT-blue" alt="MIT">
  </p>
</div>

---

> **Note** — this repository is a **single-commit snapshot** of a working Django + DRF e-commerce backend. The full pre-snapshot history (feature branches, ADRs, code reviews) lived in a private monorepo and is not preserved here on purpose. Treat this as a clean starting point.

This template is paired with **[template-eccomerce-frontend](https://github.com/elchale/template-eccomerce-frontend)** (React + Vite). They are designed to be deployed independently — frontend on Vercel/Cloudflare Pages/Netlify, backend on any container host (Render, Fly, Railway, Cloud Run, etc.).

---

## What you get

A **full storefront API** with all the moving parts wired:

- **Auth** — JWT access tokens + refresh tokens (rotating, blacklist-on-rotation), allauth-compatible registration with email verification, password reset with action freezing, Google OAuth, login history with IP + user-agent tracking, IP-change detection, optional reCAPTCHA.
- **Catalog** — `Category`, `Product`, `ProductVariant` with arbitrary attribute axes (`VariantType` / `VariantOption`), reviews, wishlist, full-text search via PostgreSQL.
- **i18n** — `django-modeltranslation` for ES / EN / PT on every customer-facing string. `Accept-Language` header switches the response transparently; admin endpoints return all locales so the React form can edit them side-by-side.
- **Cart + Checkout** — server-side cart per user, idempotent checkout, address persistence, currency-aware totals.
- **Orders** — order lifecycle with state transitions, line-item snapshots (so price/translation changes don't rewrite history), order-detail audit fields.
- **Coupons** — discount codes with expiry, min-spend, max-redemption, per-user limits.
- **Marketing** — banners (announcements + hero), promotions, popups, theme + custom-colors config — all cached for 10 minutes, invalidated on admin write.
- **GCS uploads** — product images, marketing banners, user avatars uploaded to Google Cloud Storage via a thin wrapper in `core/utils/gcs.py`. **Never** uses Django's `FileField` / `ImageField`; URL only is stored in `URLField`.
- **Admin panel** — `OTPAdminSite` (TOTP 2FA required) with django-admin-tools dashboard, modeltranslation tabs on every translated model.
- **API docs** — `drf-spectacular` → OpenAPI 3.1 at `/api/schema/`, Swagger UI at `/api/docs/`, ReDoc at `/api/redoc/`. Gated by `ENABLE_API_DOCS` in production.
- **Background tasks** — Celery + RabbitMQ for emails, image processing, and search indexing. `USE_CELERY=False` falls back to `CELERY_TASK_ALWAYS_EAGER` for dev / single-process deploys.
- **Caching** — Redis via `django-redis` for sessions, query caching, marketing config, and DRF throttle counters.
- **WebSockets** — Django Channels + `channels_redis` for real-time order status updates.
- **Payments** — Izipay (Lyra) integration. The frontend renders the embedded form; this backend creates form tokens and verifies IPN signatures.
- **Observability** — Sentry SDK auto-enabled when `SENTRY_DSN` is set, no-op when empty (no overhead in dev).
- **Request correlation** — `RequestIdMiddleware` issues an `X-Request-Id` per request (or echoes the one the frontend sent), surfaced in logs and exposed back to the SPA via CORS.

## Tech stack

| Layer            | Choice                                                          |
| ---------------- | --------------------------------------------------------------- |
| Framework        | Django 5.2 + DRF 3.16                                           |
| Python           | 3.13 (typed `from __future__ import annotations` not required) |
| Database         | PostgreSQL 15 (with `pg_trgm` for fuzzy search)                 |
| Cache + sessions | Redis 7 via `django-redis`                                      |
| Queue            | Celery 5.5 + RabbitMQ (or Redis broker)                         |
| Realtime         | Django Channels + `channels_redis`                              |
| Auth             | `dj-rest-auth` + `django-allauth` + `djangorestframework-simplejwt` |
| 2FA              | `django-otp` (TOTP) on admin                                    |
| i18n             | `django-modeltranslation` (ES default, EN + PT)                 |
| Storage          | Google Cloud Storage (`google-cloud-storage`)                   |
| API docs         | `drf-spectacular` (OpenAPI 3.1)                                 |
| WSGI / ASGI      | Gunicorn + Uvicorn worker                                       |
| Static files     | WhiteNoise (no nginx required)                                  |
| Lint             | Ruff                                                            |
| Tests            | pytest + pytest-django                                          |
| Security audit   | Bandit + pip-audit                                              |

## Project layout

```
backend/                  Django project config
├── settings/             modular settings (env → common → auth → db → cache → …)
├── urls.py               root URL conf
├── asgi.py / wsgi.py
└── celery.py
core/                     shared foundation
├── models.py             BaseModel, UserMixinModel (abstract bases)
├── middleware.py         RequestIdMiddleware
├── exceptions.py
├── utils/gcs.py          GCS upload helper (everywhere instead of FileField)
├── templates/            base_layout.html + email layouts
└── templatetags/         site_config, change_lang, env, get_domain
users/                    auth + profiles
├── models.py             Profile, LoginHistory
├── views/                login / register / password / account_delete
├── serializers/auth.py + serializers/profile.py
├── adapters/             allauth custom adapters
├── tasks.py              Celery email tasks
├── captcha.py            optional reCAPTCHA hook
└── cache_keys.py         centralized cache keys
products/                 catalog
├── models.py             Category, Product, ProductVariant, VariantType, VariantOption, Review, Wishlist
└── translation.py        modeltranslation registrations
orders/                   cart + checkout + orders
├── models.py             Cart, CartItem, Order, OrderItem
└── views/                checkout, order_detail, …
coupons/                  discount codes
marketing/                banners / popups / promos / theme / site config
utils/                    pure helpers (stateless)
scripts/                  CLI utilities (delete_user, redis_check, email_test)
locale/                   .po translation catalogs
static/                   logo + admin overrides
```

## Quick start (Docker — recommended)

The fastest path is the included `docker-compose.yml` — it boots Postgres, Redis, RabbitMQ, the web service, the Celery worker, and Celery beat.

```bash
git clone https://github.com/elchale/template-eccomerce-backend.git
cd template-eccomerce-backend
cp .env.template .env             # then edit DB / SECRET_KEY / GCS / SMTP

docker compose up --build         # web on http://localhost:8000
```

The bundled `Dockerfile` is a two-stage build: a `python:3.13-slim` builder installs deps into `/install` (so the runtime stage has no compilers or `build-essential`), and the runtime stage copies that prefix plus the source. The container runs as a non-root user. `CMD` uses shell form so `$PORT` expands at start (Render, Fly, Cloud Run, and Heroku inject `PORT` dynamically).

## Quick start (local — no Docker)

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env               # then edit

createdb ecommerce                  # or use any Postgres you have running
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_ecommerce     # categories, products, variants, reviews
python manage.py runserver
```

Visit:

- **API root**         http://localhost:8000/
- **Swagger UI**       http://localhost:8000/api/docs/
- **ReDoc**            http://localhost:8000/api/redoc/
- **OpenAPI JSON**     http://localhost:8000/api/schema/
- **Admin (OTP)**      http://localhost:8000/admin/  *(scan TOTP QR with Google Authenticator on first login)*

## Environment variables

See `.env.template` for the full list with comments. Required:

| Variable                | Required           | Notes                                                                    |
| ----------------------- | ------------------ | ------------------------------------------------------------------------ |
| `DJANGO_SECRET_KEY`     | yes                | Generate with `python -c 'import secrets; print(secrets.token_urlsafe(64))'` |
| `DEBUG`                 | yes                | `False` in production                                                    |
| `DOMAIN`                | yes                | Host the API serves on (e.g. `api.example.com`)                          |
| `FRONTEND_DOMAIN`       | yes                | Origin of the SPA — used for CORS + email links                          |
| `ADDITIONAL_CORS_ORIGINS` | optional         | Comma-separated extra origins (e.g. preview deploys)                     |
| `DB_*`                  | yes                | `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE` |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASS` | yes  | Redis connection                                                         |
| `USE_CELERY`            | yes                | `False` in dev to skip RabbitMQ requirement (tasks run eagerly)          |
| `AMQP_*`                | only if `USE_CELERY=True` | RabbitMQ connection                                              |
| `EMAIL_*`               | yes                | SMTP host/port/user/pass + `DEFAULT_FROM_EMAIL`                          |
| `GCS_BUCKET_NAME`, `GCS_PROJECT_ID` | yes    | GCS bucket details                                                       |
| `GCS_CREDENTIALS_PATH` *or* `GCS_CREDENTIALS_JSON` | yes for prod uploads | Path to service-account JSON, or base64-encoded JSON for container envs |
| `ADMIN_USER`, `ADMIN_MASTERPASS` | yes       | Master credentials for the OTP admin site                                |
| `SENTRY_DSN`            | optional           | Empty = Sentry disabled (no-op)                                          |
| `IZIPAY_*`              | only if using Izipay | Shop ID + API key + HMAC key, TEST and PROD                            |
| `ENABLE_API_DOCS`       | optional (default False) | Set `True` to expose Swagger / ReDoc / schema in production         |

## Common commands

```bash
python manage.py runserver              # dev server
python manage.py migrate
python manage.py makemigrations
python manage.py createsuperuser
python manage.py shell
python manage.py collectstatic --no-input

python manage.py seed_ecommerce         # seed sample products + reviews
python manage.py seed_site_config       # seed configuracion-tienda defaults
python manage.py makemessages -a        # gather i18n strings
python manage.py compilemessages

pytest                                  # all tests
pytest path/to/test.py                  # single file
pytest -k "test_name"                   # by name match

ruff check .                            # lint
bandit -r . -x ./venv,./tests --severity-level medium  # security scan
pip-audit -r requirements.txt           # dependency CVE check
```

## URL structure

| Prefix              | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `/auth/*`           | login, register, password reset, token refresh       |
| `/api/products/`    | product catalog, variants                            |
| `/api/categories/`  | category tree                                        |
| `/api/reviews/`     | product reviews                                      |
| `/api/wishlist/`    | per-user wishlist                                    |
| `/api/cart/`        | cart + cart items                                    |
| `/api/checkout/`    | checkout finalize                                    |
| `/api/orders/`      | order list + detail                                  |
| `/api/coupons/`     | coupon validation                                    |
| `/api/marketing/`   | banners, popups, promotions, theme, site config     |
| `/api/admin/*`      | admin CRUD (gated by `is_staff`)                     |
| `/api/schema/`      | OpenAPI 3.1 schema                                   |
| `/api/docs/`        | Swagger UI (gated by `ENABLE_API_DOCS`)              |
| `/api/redoc/`       | ReDoc (gated by `ENABLE_API_DOCS`)                   |
| `/admin/`           | Django admin (TOTP required)                         |
| `/healthz/`         | health check (returns `{"status": "ok"}`)            |

## Architecture highlights

### Modular settings

`backend/settings/` is split into single-concern files. `__init__.py` imports them in a deliberate order — `env.py` first (loads `.env`), then generic config, then internal libs (auth, DRF), then external services (DB, Redis, Celery, email, GCS). This keeps each file under 100 lines and lets you swap one concern at a time.

### Abstract base models

Every domain model inherits from `core.models.BaseModel` (gives `created`, `updated` timestamps) or `core.models.UserMixinModel` (adds a `user` FK). This means timestamp behaviour, indexes, and serializer fields are consistent across the codebase without copy-paste.

### Account deletion that actually invalidates tokens

`users/views/account_delete.py` calls `BlacklistedToken.objects.get_or_create(token=outstanding)` for every outstanding refresh token of the deleted user. Without this, refresh tokens stay valid for up to 7 days after the account is deleted — a real GDPR / security concern. The view is also throttled at 5 attempts/minute via `ScopedRateThrottle` so it can't be hammered.

### Marketing config cache

The marketing app exposes a `ConfiguracionTienda` key/value store edited from the admin and read by both API consumers and Django email templates (via the `{% site_config %}` template tag). Cache invalidation is shared between both paths — admin save → both API responses and rendered emails see the new value within the same request.

### Email templates that survive iPhone dark mode

`core/templates/base_layout.html` uses the **gradient-anti-dark-mode** technique: `linear-gradient(to right, #COLOR, #COLOR) !important` for backgrounds, plus double-span text wrappers with `gmail-blend-difference` and `mso-color-alt`. iPhone's forced dark inversion cannot rewrite gradient colors, so brand emails keep their light theme. Reference template at `core/templates/accounts/test_email.html`.

### CORS that actually works with the SPA

`CORS_ALLOW_HEADERS` extends `corsheaders.defaults.default_headers` with `accept-language` (drives `LocaleMiddleware`) and `x-request-id` (distributed tracing correlation). Both are exposed back via `CORS_EXPOSE_HEADERS` so the frontend can read the request-id off the response and log it alongside error toasts. Missing these breaks CORS preflight in Chrome with `net::ERR_FAILED`.

### Healthcheck + `$PORT`

`/healthz/` returns `{"status":"ok"}` synchronously with no DB hit. The `Dockerfile` uses **shell-form** `CMD` so `$PORT` expands at container start — Render, Fly, Cloud Run, and Heroku all inject `PORT` at runtime (usually 10000), and the same image runs locally on 8000 via `docker compose` because the `ENV PORT=8000` default kicks in when nothing's injected.

## Testing

```bash
pytest                              # run all tests
pytest -k checkout                  # by name match
pytest --create-db                  # recreate test DB (after model changes)
pytest --cov=. --cov-report=term-missing
```

`conftest.py` includes a `_reset_cache_for_db_tests` fixture that flushes the Redis cache between tests, so cache state never bleeds across test files.

## CI

`.github/workflows/ci.yml` runs on every push and PR:

| Job          | Blocks merge? |
| ------------ | ------------- |
| ruff         | yes           |
| pytest       | yes (with real Postgres + Redis service containers) |
| bandit + pip-audit | no (informational — transient CVE advisories shouldn't block) |

CI matches the production Python version (3.13) exactly — no multi-version matrix that drifts from what actually ships.

## Production deployment

The bundled `Dockerfile` runs on any container host. Tested deployment paths:

- **Render** — pick "Docker" runtime, point at this repo, set the health-check path to `/healthz/`, paste the env vars from `.env.template`. Render injects `PORT`.
- **Fly.io** — `fly launch` from this directory; the existing Dockerfile is detected.
- **Google Cloud Run** — `gcloud run deploy --source .`; Cloud Run injects `PORT=8080`.
- **Railway** — works with the included Dockerfile out of the box.

For non-Docker hosts (e.g. classic Heroku Python buildpack), see `build_scripts/render.sh` for the install + migrate + collectstatic sequence.

Detailed production guidance: see [PRODUCTION.md](PRODUCTION.md) and [PRE_LAUNCH_CHECKLIST.md](PRE_LAUNCH_CHECKLIST.md).

## Documentation

- [docs/API.md](docs/API.md) — endpoint inventory + auth flow
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — settings, app boundaries, model relationships
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — local workflow, coding standards, contribution guide
- [docs/API_DOCS_SECURITY.md](docs/API_DOCS_SECURITY.md) — how Swagger / ReDoc are gated in production
- [PRODUCTION.md](PRODUCTION.md) — production deployment + hardening guide
- [PRE_LAUNCH_CHECKLIST.md](PRE_LAUNCH_CHECKLIST.md) — go-live checklist

## License

MIT — use this as a starting point for any project, commercial or otherwise.

## Maintained by

This template is built and maintained by **[Qolca](https://www.qolca.org)** — a software & AI automation studio in Lima, Peru. We use it as the foundation for client storefronts.

- Don't want to self-host? We run it for you: **[managed store from $10/month](https://www.qolca.org/solutions/self-hosted-ecommerce-template)** ([español](https://www.qolca.org/es/soluciones/plantilla-ecommerce-autohospedada) · [português](https://www.qolca.org/pt/solucoes/modelo-ecommerce-auto-hospedado))
- More automation guides on the [Qolca blog](https://www.qolca.org/blog)
