# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daddy Django is a production-ready Django template for building scalable backend applications with comprehensive authentication, modular settings architecture, and REST API infrastructure. Built on Django 5.2.5 with Python 3.13.7.

## Development Commands

### Initial Setup
```bash
# Copy environment template
cp .env.template .env

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

### Common Management Commands
```bash
# Run migrations
python manage.py migrate

# Create new migrations
python manage.py makemigrations

# Collect static files
python manage.py collectstatic

# Access Django shell
python manage.py shell

# Create new app
python manage.py startapp app_name
```

### Deployment
```bash
# Deploy using Render build script
./build_scripts/render.sh
```

## Architecture

### Settings Structure

Settings are modularized in `backend/settings/` with clear separation of concerns:

- `env.py` - Environment variable loading (must come first)
- `common.py` - Core Django settings, installed apps, middleware
- `auth.py` - Authentication configuration (dj-rest-auth, allauth, JWT)
- `rest_framework.py` - DRF and API documentation (drf-spectacular)
- `databases.py` - PostgreSQL configuration
- `redis.py` - Redis caching configuration
- `celery.py` - Background task queue setup
- `email.py` - SMTP and email template settings
- `cors.py` - CORS headers configuration
- `gcs.py` - Google Cloud Storage integration
- `i18n_l10n.py` - Internationalization and localization
- `logging.py` - Logging configuration
- `warnings.py` - Python warnings filter

Import order matters: `env.py` must be imported first, followed by generic config, internal libraries, then external services.

### App Structure

**core/** - Shared foundation for the entire project
- Abstract base models (`BaseModel`, `UserMixinModel`) - All domain models should inherit from these for consistency
- Shared templates (landing page, email layouts, account pages)
- Custom template tags (language switching, environment variables, domain helpers, math filters)
- Custom middleware for request/response processing
- Core exceptions for application-wide error handling

**users/** - Complete authentication and user management system
- Extended user model via `Profile` with security features (action freezing, IP tracking)
- `LoginHistory` model tracks all login attempts with IP and user agent
- Security features: IP change detection, account action freezing, captcha integration
- Custom adapters in `auth/` directory for third-party services
- Serializers split by domain: `serializers/auth.py` and `serializers/profile.py`
- Asynchronous tasks in `tasks.py` for email notifications
- Cache keys centralized in `cache_keys.py`

**utils/** - Reusable utility functions
- `generic_functions.py` - General-purpose helpers (random string generation, data transformations)
- `text_output.py` - Text formatting and manipulation utilities
- Keep functions stateless and side-effect free when possible

### URL Routing

Main routing in `backend/urls.py`:
- Landing page at root (`/`)
- Admin with OTP protection at `/admin/`
- User auth endpoints extended via `users.urls`

Authentication endpoints (from `users/urls.py`):
- `auth/login/` - JWT authentication with security checks
- `auth/registration/` - New user registration
- `auth/registration/account-confirm-email/` - Email verification
- `resend-email-confirmation/` - Resend verification email
- `auth/password/change/` - Change password (authenticated)
- `auth/password/reset/` - Request password reset
- `auth/password/reset/confirm/` - Complete password reset

See `AUTH_ENDPOINTS.md` for complete API documentation.

### Authentication Flow

Built on `dj-rest-auth` and `allauth` with custom security layers:

1. **Registration**: User registers → Email verification sent → User confirms email → Auto-login with JWT tokens
2. **Login**: User submits credentials → Security checks (IP tracking, captcha if enabled) → `LoginHistory` created → JWT tokens issued
3. **Password Reset**: User requests reset → Email with token sent → Account actions frozen → User sets new password → Tokens refreshed
4. **Account Security**: IP change detection triggers notifications, sensitive operations freeze account temporarily

### Internationalization (i18n) — django-modeltranslation

Content translations for EN/ES/PT are handled by `django-modeltranslation`. The default language is **ES** (Spanish).

**Registered models and fields:**

| App | Model | Translated fields |
|-----|-------|-------------------|
| `products` | `Category` | `name`, `description` |
| `products` | `Product` | `name`, `description` |
| `products` | `VariantType` | `name` |
| `products` | `VariantOption` | `value` |
| `marketing` | `Banner` | `titulo`, `subtitulo`, `texto_cta` |
| `marketing` | `Popup` | `titulo`, `mensaje`, `texto_cta` |
| `marketing` | `Promocion` | `nombre` |
| `coupons` | `Coupon` | `description` |

Each registered field gets `_es`, `_en`, `_pt` columns in the database. The unsuffixed accessor (e.g. `product.name`) transparently returns the active-language value, falling back to `es`.

**Language activation per request:** `LocaleMiddleware` in `MIDDLEWARE` reads the `Accept-Language` header sent by the frontend and activates that language for the lifetime of the request.

**Adding a new language:**
1. Add it to `LANGUAGES` and `MODELTRANSLATION_LANGUAGES` in `settings/i18n_l10n.py`
2. Run `python manage.py makemigrations` (generates migration adding `_code` columns) and commit the result
3. Add a data migration (using `RunPython`) that copies existing values into the new `_code` columns — see `products/migrations/0004_backfill_translations.py` as the reference pattern
4. Run `python manage.py migrate` in deployment — both schema and backfill run automatically

**Admin panel:** All `ModelAdmin` classes for translated models inherit from `modeltranslation.admin.TranslationAdmin`, which adds language tabs automatically in the Django admin.

**Serializers:** Consumer serializers return the active-language value transparently (no change needed). Admin serializers expose all `name_es`, `name_en`, `name_pt` fields so the React admin form can read and write all languages at once. Only the `_es` (default) variants are required; `_en` and `_pt` are optional and fall back to `_es` at read time.

**Translation files** (`locale/`): Django `.po` placeholder files exist at `locale/{es,en,pt}/LC_MESSAGES/django.po`. Populate them via `python manage.py makemessages -a` and compile with `python manage.py compilemessages` to translate DRF validation error messages.

### Model Inheritance Pattern

All models should inherit from abstract base classes in `core/models.py`:

- **BaseModel**: Provides `created` and `updated` timestamp fields
- **UserMixinModel**: Provides `user` ForeignKey relationship

Example:
```python
from core.models import BaseModel, UserMixinModel

class YourModel(BaseModel):
    # Automatically has created and updated fields
    pass

class UserRelatedModel(UserMixinModel):
    # Automatically has user ForeignKey
    pass
```

### Admin Configuration

Admin is protected with OTP (One-Time Password) via `django-otp`:
- `OTPAdminSite` replaces default admin
- Superuser must use authenticator app for 2FA
- Admin master password configured via `ADMIN_MASTERPASS` env var
- `admin-tools` provides enhanced admin interface with dashboard and theming

### Background Tasks

Celery is configured for asynchronous task processing:
- Celery app defined in `backend/settings/celery.py`
- Tasks should be defined in `tasks.py` within each app
- RabbitMQ or Redis can be used as message broker (configured via `.env`)
- Example: Email notifications in `users/tasks.py`

### Static Files

Static file handling uses WhiteNoise for production:
- Development: `STATIC_URL = '/static/'`, files in `static/`
- Production: `python manage.py collectstatic` gathers files to `staticfiles/`
- WhiteNoise middleware serves static files efficiently without nginx

### Security Features

- **Action Freezing**: `Profile.set_actions_freeze(hours)` temporarily blocks user actions after sensitive operations
- **IP Tracking**: `LoginHistory` records IP and user agent for audit trail
- **Captcha Integration**: Available in `users/captcha.py` for sensitive endpoints
- **Email Verification**: Required for new accounts via allauth
- **JWT Tokens**: Short-lived access tokens with refresh token flow
- **CORS**: Configured in `backend/settings/cors.py` for API access

## Environment Variables

Key environment variables (see `.env.template`):
- `DJANGO_SECRET_KEY` - Django secret key (required)
- `DEBUG` - Debug mode (default: False)
- `DOMAIN` - Host domain
- `DB_*` - PostgreSQL connection details
- `REDIS_*` - Redis connection details
- `AMQP_*` - RabbitMQ/message broker configuration
- `EMAIL_*` - SMTP email configuration
- `GCS_*` - Google Cloud Storage credentials and bucket
- `ADMIN_USER`, `ADMIN_MASTERPASS` - Admin OTP configuration

## Adding New Apps

When creating new Django apps:

1. Create app: `python manage.py startapp app_name`
2. Add to `INSTALLED_APPS` in `backend/settings/common.py`
3. Inherit from `BaseModel` or `UserMixinModel` for consistency
4. Follow existing patterns for serializers, views, and URL routing
5. Create app-level `README.md` documenting purpose and structure
6. Add app URLs to `backend/urls.py` if needed

## Key Dependencies

- **Django 5.2.5** - Web framework
- **DRF 3.16.1** - REST API framework
- **dj-rest-auth 7.0.1** - Authentication endpoints
- **django-allauth 65.11.0** - Account management and social auth
- **djangorestframework-simplejwt 5.5.1** - JWT authentication
- **drf-spectacular 0.28.0** - OpenAPI schema generation
- **celery 5.5.3** - Asynchronous task queue
- **django-redis 6.0.0** - Redis caching backend
- **psycopg2-binary 2.9.10** - PostgreSQL adapter
- **gunicorn 23.0.0** - WSGI HTTP server
- **uvicorn 0.35.0** - ASGI server
- **google-cloud-storage 3.3.0** - GCS integration
- **django-otp 1.6.1** - Two-factor authentication

## Project Patterns

### Custom Template Tags

Located in `core/templatetags/`:
- Load in templates: `{% load tagname %}`
- Examples: `{% change_lang 'es' %}`, `{% get_domain %}`, `{% env 'DEBUG' %}`

### Middleware

Custom middleware in `core/middleware.py`:
- Some middleware commented out by default (access logs, response time tracking)
- Uncomment in `MIDDLEWARE` list in `common.py` to enable

### Exception Handling

Custom exceptions defined in:
- `core/exceptions.py` - Application-wide exceptions
- `users/exceptions.py` - User/auth-specific exceptions

### Caching

Redis caching available:
- Cache keys centralized in `users/cache_keys.py`
- Configure Redis connection in `.env`
- Used for session storage, API throttling, and custom caching

## Database

PostgreSQL is the primary database:
- Connection pooling via `CONN_MAX_AGE`
- Configured in `backend/settings/databases.py`
- Migrations in each app's `migrations/` directory

## Testing

No test framework is configured by default. To add testing:
- Install pytest-django: `pip install pytest-django`
- Create `pytest.ini` configuration
- Add tests in `tests/` directories within each app
