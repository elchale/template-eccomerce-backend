# API Documentation Security

This guide explains how to control access to your API documentation in different environments.

## Overview

The API documentation (Swagger UI, ReDoc) is automatically generated from your code using `drf-spectacular`. By default:

- **Development** (`DEBUG=True`): API docs are **enabled** and **publicly accessible**
- **Production** (`DEBUG=False`): API docs are **disabled** by default

## Configuration Options

### Option 1: Completely Disable in Production (Recommended)

This is the **most secure** option - API docs are not available at all in production.

**Configuration:**
```env
# .env (Production)
DEBUG=False
ENABLE_API_DOCS=False  # This is the default
```

**Result:**
- `/api/docs/` → 404 Not Found
- `/api/redoc/` → 404 Not Found
- `/api/schema/` → 404 Not Found

**Use Case:**
- Public-facing APIs where you don't want to expose endpoint structure
- Maximum security
- No overhead from documentation endpoints

---

### Option 2: Enable for Authenticated Staff Users Only

Enable API docs in production, but require staff/admin authentication.

**Step 1: Update Settings**

Edit `backend/settings/rest_framework.py`:

```python
# Change SERVE_PERMISSIONS based on environment
SPECTACULAR_SETTINGS = {
    ...
    'SERVE_PERMISSIONS': [
        'rest_framework.permissions.IsAdminUser' if not DEBUG
        else 'rest_framework.permissions.AllowAny'
    ],
    ...
}
```

**Step 2: Enable API Docs**
```env
# .env (Production)
DEBUG=False
ENABLE_API_DOCS=True  # Enable docs
```

**Result:**
- `/api/docs/` → Requires staff user login
- `/api/redoc/` → Requires staff user login
- `/api/schema/` → Requires staff user login

**Use Case:**
- Internal APIs used by your team
- Sharing docs with trusted partners
- Development/staging environments

---

### Option 3: Enable for Specific IP Addresses

Restrict API docs to specific IP addresses (e.g., your office, VPN).

**Step 1: Create Custom Permission**

Create `core/permissions.py`:

```python
from rest_framework.permissions import BasePermission

class IsInternalIP(BasePermission):
    """
    Allow access only from whitelisted IPs.
    """
    ALLOWED_IPS = [
        '192.168.1.0/24',  # Office network
        '10.0.0.0/8',      # VPN
        '127.0.0.1',       # Localhost
    ]

    def has_permission(self, request, view):
        from ipaddress import ip_address, ip_network

        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        client_ip = ip_address(ip)

        # Check if IP is in allowed ranges
        for allowed in self.ALLOWED_IPS:
            if '/' in allowed:  # CIDR notation
                if client_ip in ip_network(allowed):
                    return True
            elif str(client_ip) == allowed:
                return True

        return False
```

**Step 2: Update Settings**

```python
# backend/settings/rest_framework.py
from .env import env

SPECTACULAR_SETTINGS = {
    ...
    'SERVE_PERMISSIONS': [
        'core.permissions.IsInternalIP' if not env('DEBUG', default=False)
        else 'rest_framework.permissions.AllowAny'
    ],
    ...
}
```

**Step 3: Enable API Docs**
```env
# .env (Production)
DEBUG=False
ENABLE_API_DOCS=True
```

**Result:**
- `/api/docs/` → Only accessible from whitelisted IPs
- Other IPs → 403 Forbidden

**Use Case:**
- Office/company network access only
- CI/CD pipelines need access
- Staging environments

---

### Option 4: API Key Authentication

Require an API key to access documentation.

**Step 1: Create Custom Permission**

```python
# core/permissions.py
from rest_framework.permissions import BasePermission
from django.conf import settings

class HasAPIKey(BasePermission):
    """
    Require X-API-Key header to access.
    """
    def has_permission(self, request, view):
        api_key = request.headers.get('X-API-Key')
        valid_keys = getattr(settings, 'API_DOC_KEYS', [])
        return api_key in valid_keys
```

**Step 2: Add Setting**

```python
# backend/settings/common.py
API_DOC_KEYS = env.list('API_DOC_KEYS', default=[])
```

**Step 3: Configure Environment**

```env
# .env (Production)
DEBUG=False
ENABLE_API_DOCS=True
API_DOC_KEYS=secret-key-1,secret-key-2
```

**Step 4: Update Spectacular Settings**

```python
# backend/settings/rest_framework.py
SPECTACULAR_SETTINGS = {
    ...
    'SERVE_PERMISSIONS': [
        'core.permissions.HasAPIKey' if not env('DEBUG', default=False)
        else 'rest_framework.permissions.AllowAny'
    ],
    ...
}
```

**Usage:**
```bash
curl -H "X-API-Key: secret-key-1" https://yourdomain.com/api/docs/
```

**Use Case:**
- Share with external developers
- CI/CD tools that need schema access
- Third-party integrations

---

## Testing Security

### Test in Development

```bash
# Start server
python manage.py runserver

# Should work (DEBUG=True, docs enabled by default)
curl http://localhost:8000/api/docs/
```

### Test Production Security

```bash
# Simulate production
DEBUG=False ENABLE_API_DOCS=False python manage.py runserver

# Should return 404
curl http://localhost:8000/api/docs/
```

### Test Staff-Only Access

```bash
# Enable docs with staff requirement
DEBUG=False ENABLE_API_DOCS=True python manage.py runserver

# Without authentication -> 403 Forbidden
curl http://localhost:8000/api/schema/

# With staff user -> 200 OK
curl -u staff@example.com:password http://localhost:8000/api/schema/
```

---

## Recommended Setup by Environment

### Local Development
```env
DEBUG=True
ENABLE_API_DOCS=True
# No restrictions - easy development
```

### Staging/Testing
```env
DEBUG=False
ENABLE_API_DOCS=True
# Option 2 or 3: Staff-only or IP-restricted
```

### Production (Public API)
```env
DEBUG=False
ENABLE_API_DOCS=False
# Completely disabled
```

### Production (Internal API)
```env
DEBUG=False
ENABLE_API_DOCS=True
# Option 2: Staff-only access
# OR
# Option 3: IP-restricted
```

---

## Alternative: Separate Documentation Site

For public APIs, consider hosting static documentation separately:

1. **Generate OpenAPI Schema**
```bash
python manage.py spectacular --file openapi.json
```

2. **Host Static Docs**
- Use [ReDoc](https://github.com/Redocly/redoc) static HTML
- Host on GitHub Pages, Netlify, or S3
- Update docs as part of deployment

3. **Keep Production API Private**
```env
ENABLE_API_DOCS=False  # No docs on production API
```

**Benefits:**
- No performance overhead on API server
- Can customize documentation
- Better SEO for docs
- Separate scaling for docs vs API

---

## Security Checklist

Before deploying to production:

- [ ] Set `DEBUG=False`
- [ ] Set `ENABLE_API_DOCS=False` (or implement access control)
- [ ] If enabled, test that authentication works
- [ ] Test that unauthorized access is blocked
- [ ] Review what endpoints are exposed
- [ ] Check if any sensitive data appears in schema
- [ ] Consider rate limiting for `/api/schema/` endpoint
- [ ] Monitor access logs for documentation endpoints

---

## Monitoring

### Track Documentation Access

Add logging to track who accesses API docs:

```python
# core/middleware.py
import logging

logger = logging.getLogger(__name__)

class APIDocsAccessMiddleware:
    """Log access to API documentation"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/docs') or \
           request.path.startswith('/api/schema'):
            logger.warning(
                f'API Docs Access: {request.path} from '
                f'{request.META.get("REMOTE_ADDR")} '
                f'User: {request.user}'
            )

        return self.get_response(request)
```

Add to `MIDDLEWARE` in production:
```python
if not DEBUG:
    MIDDLEWARE += ['core.middleware.APIDocsAccessMiddleware']
```

---

## FAQ

**Q: Can I have different docs for internal vs external users?**

A: Yes! Create two schema views with different permissions:

```python
# backend/urls.py
urlpatterns = [
    # Public docs (filtered endpoints)
    path('api/docs/public/', SpectacularSwaggerView.as_view(
        url_name='public-schema'
    )),

    # Internal docs (all endpoints)
    path('api/docs/internal/', SpectacularSwaggerView.as_view(
        url_name='internal-schema'
    )),
]
```

**Q: Does disabling docs affect API functionality?**

A: No! Disabling documentation only removes the UI endpoints (`/api/docs/`, etc.). Your actual API endpoints continue to work normally.

**Q: Can users still discover endpoints if docs are disabled?**

A: Users can potentially discover endpoints through:
- Error messages
- CORS headers
- Brute force
- Previous documentation
- Consider: security through obscurity is not real security

**Q: How do I share docs with external developers?**

A: Options:
1. Generate static schema and share file
2. Use API key authentication (Option 4)
3. Create separate documentation site
4. Use API management platform (e.g., Postman, Stoplight)

---

## Summary

| Method | Security Level | Use Case |
|--------|---------------|----------|
| Disabled | 🔒🔒🔒 Highest | Public APIs |
| Staff-Only | 🔒🔒 High | Internal APIs |
| IP-Restricted | 🔒🔒 High | Office/VPN access |
| API Key | 🔒 Medium | Partner integrations |
| Public | ⚠️ Low | Open APIs |

**Default Recommendation**: Disable in production (`ENABLE_API_DOCS=False`)
