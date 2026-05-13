# Architecture Overview

This document explains the architectural decisions and design patterns used in this Django project.

## System Architecture

```
┌─────────────┐
│   Client    │ (Browser, Mobile App)
│  Frontend   │
└──────┬──────┘
       │ HTTPS/JWT
       ▼
┌─────────────────────────────────────┐
│         Django Backend              │
│  ┌──────────────────────────────┐  │
│  │   REST API (DRF)             │  │
│  │   - JWT Authentication       │  │
│  │   - Rate Limiting            │  │
│  │   - CORS Handling            │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │   Business Logic             │  │
│  │   - Users (Auth)             │  │
│  │   - Core (Shared)            │  │
│  │   - Utils (Helpers)          │  │
│  └──────────────────────────────┘  │
└──────┬─────────────┬────────────────┘
       │             │
       ▼             ▼
┌────────────┐  ┌──────────┐
│ PostgreSQL │  │  Redis   │
│  Database  │  │  Cache   │
└────────────┘  └──────────┘
       │
       ▼
┌────────────┐
│  Celery    │
│  Workers   │
└────────────┘
       │
       ▼
┌────────────┐
│ RabbitMQ   │
│   Broker   │
└────────────┘
```

## Core Design Principles

### 1. Modular Settings Architecture

**Decision**: Split settings into specialized modules instead of one monolithic file.

**Location**: `backend/settings/`

**Structure**:
```python
backend/settings/
├── __init__.py           # Imports all modules in correct order
├── env.py                # Environment variable loading (MUST be first)
├── common.py             # Core Django settings
├── auth.py               # Authentication configuration
├── rest_framework.py     # DRF & API settings
├── databases.py          # PostgreSQL configuration
├── redis.py              # Cache configuration
├── celery.py             # Background tasks
├── email.py              # Email/SMTP settings
├── cors.py               # CORS configuration
├── gcs.py                # Google Cloud Storage
├── i18n_l10n.py          # Internationalization
├── logging.py            # Logging configuration
└── warnings.py           # Python warnings
```

**Why?**
- ✅ Easier to find and modify specific settings
- ✅ Better separation of concerns
- ✅ Reduces merge conflicts in teams
- ✅ Clear dependencies (env.py must come first)

**Import Order Matters**:
```python
# backend/settings/__init__.py
from .env import *          # MUST be first (loads environment variables)
from .common import *        # Core settings
from .auth import *          # Uses env() function
from .databases import *     # Uses env() function
```

### 2. Authentication Architecture

**Decision**: JWT tokens stored in HttpOnly cookies + Bearer token support.

**Flow**:
```
User Registration
    ↓
Email Verification (mandatory)
    ↓
Login → Security Checks:
    • Captcha (after failures)
    • Email verified?
    • Account active?
    • Password valid?
    • 2FA (if enabled)
    ↓
JWT Token Generation
    • Access Token (1 day)
    • Refresh Token (5 days)
    ↓
LoginHistory Created
    ↓
IP Change Detection
    ↓
Success Response
```

**Security Layers**:

1. **Email Verification**: Required before first login
2. **Captcha**: Triggered after failed attempts or suspicious IPs
3. **Action Freezing**: Temporary lockout after password reset/change
4. **IP Tracking**: Detect and notify on IP changes
5. **Login History**: Audit trail with device info
6. **Rate Limiting**: 5 requests/minute on auth endpoints

**Why JWT + Cookies?**
- ✅ Stateless (scales horizontally)
- ✅ HttpOnly cookies prevent XSS
- ✅ Secure flag in production prevents MITM
- ✅ Automatic browser handling
- ✅ Mobile-friendly (can use Bearer tokens)

**Trade-offs**:
- ❌ Cannot revoke individual tokens (use short expiry + refresh)
- ❌ Requires CORS configuration
- ✅ But: Better security than localStorage

### 3. Model Inheritance Pattern

**Decision**: Abstract base models for consistency.

**Base Models** (`core/models.py`):

```python
class BaseModel(models.Model):
    """Provides timestamp tracking for all models"""
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class UserMixinModel(models.Model):
    """Provides user relationship for all user-owned models"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        abstract = True
```

**Usage**:
```python
# Every app model should inherit from these
class Profile(BaseModel):  # Gets created/updated automatically
    user = models.OneToOneField(User, ...)

class LoginHistory(UserMixinModel):  # Gets user FK automatically
    ip = models.GenericIPAddressField(...)
```

**Why?**
- ✅ Consistent timestamp tracking across all models
- ✅ DRY (Don't Repeat Yourself)
- ✅ Easy to add audit fields later
- ✅ Query optimization (can filter by created/updated globally)

### 4. App Organization

**Three-Tier App Structure**:

```
┌─────────────────────────────────────┐
│           core/                     │
│  Abstract models, shared templates  │
│  Middleware, exceptions, tags       │
│  (Foundation for all apps)          │
└─────────────────────────────────────┘
           │
           ├─────────────────┐
           ▼                 ▼
┌──────────────────┐  ┌──────────────┐
│     users/       │  │    utils/    │
│  Authentication  │  │   Helpers    │
│  User profiles   │  │  Text utils  │
│  Login history   │  │  Generic fn  │
└──────────────────┘  └──────────────┘
```

**Core App** (`core/`):
- Purpose: Shared foundation
- Contains: Abstract models, base templates, middleware, custom exceptions
- Used by: All other apps

**Users App** (`users/`):
- Purpose: Authentication & user management
- Contains: Profile, LoginHistory models, auth serializers, security features
- Dependencies: core, utils

**Utils App** (`utils/`):
- Purpose: Reusable utilities
- Contains: Text processing, generic functions, helpers
- Dependencies: None (stateless)

**Why This Structure?**
- ✅ Clear separation of concerns
- ✅ Reusable components (core as foundation)
- ✅ Easy to add new domain apps
- ✅ Testable in isolation

### 5. Serializer Organization

**Decision**: Split serializers by domain concern.

**Structure**:
```
users/serializers/
├── __init__.py
├── auth.py        # Authentication: Login, Register, Password Reset
└── profile.py     # User profile management
```

**Why?**
- ✅ Large serializers files become unmanageable
- ✅ Clear domain boundaries
- ✅ Easier to find and modify
- ✅ Better for code reviews

### 6. Background Task Processing

**Decision**: Celery + RabbitMQ for async tasks.

**Use Cases**:
- Email notifications (IP change, failed login)
- Heavy computations
- Third-party API calls
- Scheduled tasks

**Example**:
```python
# users/tasks.py
@shared_task
def notify_user_ip_changed(user_id, new_ip, device, os, browser):
    """Send email notification when user logs in from new IP"""
    user = User.objects.get(id=user_id)
    send_mail(
        subject=f'New login from {device}',
        message=f'IP: {new_ip}, OS: {os}, Browser: {browser}',
        recipient_list=[user.email],
    )

# users/serializers/auth.py
if ip not in ip_history:
    notify_user_ip_changed.apply_async((user.id, ip, device, os, browser))
```

**Why Celery?**
- ✅ Non-blocking (API responds immediately)
- ✅ Retry logic built-in
- ✅ Monitoring with Flower
- ✅ Scheduled tasks (periodic tasks)

**Production Considerations**:
- Use JSON serialization (not pickle - security risk)
- Monitor task queue length
- Set appropriate timeouts
- Handle failures gracefully

### 7. Caching Strategy

**Decision**: Redis for session storage and API caching.

**Cache Usage**:
1. **Session Storage**: Django sessions
2. **Rate Limiting**: DRF throttling counters
3. **Captcha State**: Track failed attempts
4. **Email Verification Tokens**: Temporary token storage

**Example**:
```python
# Cache email verification token
cache.set(f'email_verify_{token}', user_id, timeout=1800)  # 30 min

# Check captcha state
attempts = cache.get(f'captcha_attempts_{email}')
```

**Why Redis?**
- ✅ Fast (in-memory)
- ✅ Supports expiration (TTL)
- ✅ Atomic operations
- ✅ Pub/Sub for real-time features

### 8. Security-First Design

**Layered Security**:

1. **Network Layer**: HTTPS, HSTS, secure cookies
2. **Application Layer**: JWT, CSRF protection, rate limiting
3. **Data Layer**: Encrypted passwords, hashed tokens
4. **Monitoring Layer**: Login history, access logs

**Key Security Features**:

| Feature | Implementation | Purpose |
|---------|---------------|---------|
| Action Freezing | `Profile.actions_freezed_till` | Prevent abuse after pwd reset |
| IP Tracking | `LoginHistory.ip` | Detect account takeover |
| Captcha | `CaptchaProcessor` | Prevent brute force |
| Rate Limiting | DRF throttling | Prevent API abuse |
| Email Verification | django-allauth | Prevent fake accounts |
| HttpOnly Cookies | JWT settings | Prevent XSS |
| CORS | django-cors-headers | Controlled access |

## Data Flow Examples

### User Registration Flow

```
POST /auth/registration/
    ↓
RegisterSerializer.validate()
    • Check DISABLE_REGISTRATION
    • Verify captcha
    • Check email uniqueness
    ↓
RegisterSerializer.save()
    • Create User (with atomic transaction)
    • Create Profile (via signal)
    • Send verification email
    ↓
EmailAddress.send_confirmation()
    • Generate confirmation key
    • Send email (via Celery)
    ↓
Response: 200 OK
    • "Verification email sent"
    • No tokens (email not verified)
```

### Login Flow with IP Change

```
POST /auth/login/
    ↓
LoginSerializer.validate()
    • Check captcha
    • Validate credentials
    • Check email verified
    • Check account active
    ↓
Create LoginHistory record
    ↓
Check IP history
    • Query LoginHistory.objects.filter(user=user)
    • Compare current IP with history
    ↓
If IP changed:
    • Send notification email (async via Celery)
    ↓
Generate JWT tokens
    ↓
Response: 200 OK
    • access_token
    • refresh_token
    • user object
```

## Performance Considerations

### Database Optimization

1. **Connection Pooling**: `CONN_MAX_AGE = 10` (reuse connections)
2. **Indexes**: On frequently queried fields (user, email, created)
3. **Select Related**: Use `select_related()` for ForeignKeys
4. **Prefetch**: Use `prefetch_related()` for Many-to-Many

### Caching Strategy

- Session data: Redis
- Captcha state: Redis (short TTL)
- Static files: WhiteNoise (in production)

### Async Tasks

- Email sending: Celery
- Expensive operations: Celery
- Scheduled jobs: Celery Beat

## Scalability

### Horizontal Scaling

✅ **Stateless Design**: JWT tokens allow multiple app servers
✅ **Shared Cache**: Redis for session/state
✅ **Shared Database**: PostgreSQL with connection pooling
✅ **Background Workers**: Celery workers can scale independently

### Bottlenecks to Monitor

⚠️ **Database**: Use read replicas if needed
⚠️ **Redis**: Can become single point of failure (use Redis Cluster)
⚠️ **Celery**: Monitor queue length, scale workers as needed

## Future Considerations

### Potential Improvements

1. **Database Read Replicas**: For read-heavy operations
2. **CDN Integration**: For static files and media
3. **WebSocket Support**: Already configured (channels + channels_redis)
4. **API Versioning**: Add `/api/v1/` prefix
5. **GraphQL**: Consider for complex data fetching needs

### Migration Paths

- **Microservices**: Can extract `users` app to separate service
- **Event-Driven**: Can add event bus (Kafka/RabbitMQ)
- **Multi-Tenancy**: Can add tenant isolation with django-tenants

## References

- [Django Best Practices](https://docs.djangoproject.com/en/stable/misc/design-philosophies/)
- [DRF Best Practices](https://www.django-rest-framework.org/topics/best-practices/)
- [12-Factor App](https://12factor.net/)
