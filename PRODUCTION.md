# Production Deployment Guide

This guide covers best practices and essential steps for deploying this Django project to production.

## Pre-Deployment Checklist

### 🔒 Security

- [ ] **Set DEBUG=False** in production `.env`
- [ ] **Generate new SECRET_KEY** for production (never use development key)
  ```python
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] **Set ALLOWED_HOSTS** to your domain(s)
  ```env
  ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
  ```
- [ ] **Disable API docs** or restrict to staff only
  ```env
  ENABLE_API_DOCS=False
  ```
- [ ] **Configure CORS** properly (don't use `*` in production)
  ```env
  CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
  ```
- [ ] **Use HTTPS** (set `SECURE_SSL_REDIRECT=True`)
- [ ] **Set secure cookie flags**
  ```python
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  SECURE_HSTS_SECONDS = 31536000
  SECURE_HSTS_INCLUDE_SUBDOMAINS = True
  SECURE_HSTS_PRELOAD = True
  ```

### 🗄️ Database

- [ ] **Use PostgreSQL** (not SQLite)
- [ ] **Enable connection pooling** (`CONN_MAX_AGE`)
- [ ] **Set up database backups** (automated daily backups)
- [ ] **Test database restore** procedure
- [ ] **Run migrations** on production database
  ```bash
  python manage.py migrate --check  # Verify first
  python manage.py migrate
  ```
- [ ] **Create database indexes** for frequently queried fields
- [ ] **Monitor database performance** (slow query log)

### 📦 Static Files

- [ ] **Collect static files**
  ```bash
  python manage.py collectstatic --noinput
  ```
- [ ] **Configure WhiteNoise** (already set up)
- [ ] **Consider CDN** for static files (CloudFlare, AWS CloudFront)
- [ ] **Set up GCS** for media files (user uploads)
  ```env
  GCS_BUCKET_NAME=your-production-bucket
  GCS_PROJECT_ID=your-gcp-project
  ```

### 🔐 Environment Variables

- [ ] **Never commit `.env`** to version control (.gitignore already includes it)
- [ ] **Use environment-specific `.env` files** (`.env.prod`, `.env.staging`)
- [ ] **Store secrets securely** (AWS Secrets Manager, HashiCorp Vault, or platform secrets)
- [ ] **Document all required env vars** in `.env.template`

### 📧 Email

- [ ] **Configure production SMTP** (SendGrid, AWS SES, Mailgun)
- [ ] **Set DEFAULT_FROM_EMAIL** to your verified domain
- [ ] **Test email sending**
  ```bash
  python scripts/email_test.py -t your@email.com --only confirmation
  ```
- [ ] **Set up email monitoring** (delivery rate, bounce rate)
- [ ] **Configure SPF, DKIM, DMARC** records for your domain

### 🚀 Performance

- [ ] **Use Redis** for caching (not in-memory)
  ```bash
  python scripts/redis_check.py
  ```
- [ ] **Enable Celery** for async tasks
- [ ] **Configure Gunicorn** with appropriate worker count
  ```bash
  # Formula: (2 x CPU cores) + 1
  gunicorn --workers 5 --worker-class uvicorn.workers.UvicornWorker backend.asgi:application
  ```
- [ ] **Set up process manager** (Supervisor, systemd)
- [ ] **Enable HTTP/2** on your web server
- [ ] **Configure request/response compression**

### 📊 Monitoring & Logging

- [ ] **Set up error tracking** (Sentry, Rollbar, Bugsnag)
  ```bash
  pip install sentry-sdk
  ```
- [ ] **Configure centralized logging** (CloudWatch, Datadog, ELK stack)
- [ ] **Monitor application metrics** (response times, error rates)
- [ ] **Set up uptime monitoring** (UptimeRobot, Pingdom)
- [ ] **Configure log rotation** (logrotate)
- [ ] **Set up alerts** for critical errors

### 🔄 Backup & Recovery

- [ ] **Automated database backups** (daily, kept for 30 days)
- [ ] **Test backup restoration** regularly
- [ ] **Backup environment variables** securely
- [ ] **Document recovery procedures**
- [ ] **Set up Redis persistence** (RDB or AOF)

---

## Environment Variables for Production

### Required Settings

```env
# Django Core
DJANGO_SECRET_KEY=<generate-new-key-for-production>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DOMAIN=yourdomain.com

# Database (PostgreSQL)
DB_NAME=production_db
DB_USER=prod_user
DB_PASSWORD=<strong-password>
DB_HOST=your-db-host.com
DB_PORT=5432

# Redis
REDIS_HOST=your-redis-host.com
REDIS_PORT=6379
REDIS_PASSWORD=<redis-password>

# Email (Production SMTP)
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=<sendgrid-api-key>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
CORS_ALLOW_CREDENTIALS=True

# API Documentation (disable or restrict)
ENABLE_API_DOCS=False

# Google Cloud Storage (for media files)
GCS_BUCKET_NAME=production-media-bucket
GCS_PROJECT_ID=your-gcp-project-id

# Sentry (Error Tracking)
SENTRY_DSN=<your-sentry-dsn>
SENTRY_ENVIRONMENT=production

# Admin OTP
ADMIN_USER=admin@yourdomain.com
ADMIN_MASTERPASS=<secure-master-password>
```

---

## Deployment Platforms

### Render.com (Recommended)

Uses included `build_scripts/render.sh`:

1. **Create Web Service**
   - Build Command: `./build_scripts/render.sh`
   - Start Command: `gunicorn backend.wsgi:application`

2. **Add PostgreSQL Database**
   - Render provides `DATABASE_URL` automatically

3. **Add Redis Instance**
   - Set `REDIS_URL` in environment variables

4. **Set Environment Variables**
   - Add all production env vars in Render dashboard

5. **Enable Auto-Deploy**
   - Connected to your GitHub repository

### AWS (EC2 + RDS + ElastiCache)

```bash
# Install dependencies
sudo apt update
sudo apt install python3-pip python3-venv nginx supervisor

# Clone repository
git clone <your-repo>
cd <project>

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up Gunicorn with Supervisor
sudo nano /etc/supervisor/conf.d/django.conf
# [program:django]
# command=/path/to/venv/bin/gunicorn backend.wsgi:application
# directory=/path/to/project
# user=ubuntu
# autostart=true
# autorestart=true
# redirect_stderr=true

# Configure Nginx
sudo nano /etc/nginx/sites-available/django
# Proxy to Gunicorn on localhost:8000

# Enable and start services
sudo supervisorctl reread
sudo supervisorctl update
sudo systemctl restart nginx
```

### Docker (Optional)

Create `Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Run Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "backend.wsgi:application"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/dbname
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=dbname
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

---

## Post-Deployment Steps

### 1. Create Superuser

```bash
python manage.py createsuperuser
```

### 2. Test Admin Panel

- Visit `https://yourdomain.com/admin/`
- Set up OTP (use authenticator app)
- Verify admin access works

### 3. Test Authentication Flow

```bash
# Test registration
curl -X POST https://yourdomain.com/auth/registration/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password1":"pass","password2":"pass"}'

# Test login
curl -X POST https://yourdomain.com/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"pass"}'
```

### 4. Verify Email Delivery

```bash
# From production server
python scripts/email_test.py -t your@email.com --only confirmation
```

### 5. Test Redis Connectivity

```bash
# From production server
python scripts/redis_check.py
```

### 6. Monitor Initial Traffic

- Check error logs for any issues
- Monitor response times
- Verify database connections
- Check Redis hit rates

### 7. Set Up Health Checks

Create `core/views.py`:

```python
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def health_check(request):
    """Health check endpoint for load balancers"""
    return JsonResponse({"status": "healthy"})
```

Add to `backend/urls.py`:

```python
urlpatterns = [
    path('health/', health_check, name='health_check'),
    ...
]
```

---

## Security Hardening

### 1. Enable Security Middleware

Already configured in `backend/settings/common.py`:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',  # ✓
    'whitenoise.middleware.WhiteNoiseMiddleware',     # ✓
    ...
]
```

### 2. Security Headers

Add to production settings:

```python
# backend/settings/common.py (only if DEBUG=False)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
```

### 3. Rate Limiting

Already configured in `backend/settings/rest_framework.py`:

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',      # Adjust for production
        'user': '1000/hour',     # Adjust for production
    }
}
```

### 4. Database Security

```python
# Use SSL for database connections
DATABASES = {
    'default': {
        ...
        'OPTIONS': {
            'sslmode': 'require',
        }
    }
}
```

### 5. Restrict Admin Access

```python
# Only allow admin from specific IPs (optional)
ADMIN_IP_WHITELIST = ['203.0.113.0/24']  # Your office IP range
```

---

## Performance Optimization

### 1. Database Query Optimization

```python
# Use select_related for ForeignKey
users = User.objects.select_related('profile').all()

# Use prefetch_related for Many-to-Many
users = User.objects.prefetch_related('groups').all()

# Add database indexes
class Meta:
    indexes = [
        models.Index(fields=['email', 'created']),
    ]
```

### 2. Caching Strategy

```python
# Cache expensive queries
from django.core.cache import cache

def get_user_profile(user_id):
    cache_key = f'user_profile_{user_id}'
    profile = cache.get(cache_key)

    if profile is None:
        profile = UserProfile.objects.get(user_id=user_id)
        cache.set(cache_key, profile, timeout=3600)

    return profile
```

### 3. Gunicorn Configuration

Create `gunicorn.conf.py`:

```python
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'sync'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = '/var/log/gunicorn/access.log'
errorlog = '/var/log/gunicorn/error.log'
loglevel = 'info'

# Process naming
proc_name = 'django_app'

# Server mechanics
daemon = False
pidfile = '/var/run/gunicorn.pid'
user = 'www-data'
group = 'www-data'
tmp_upload_dir = None

# SSL (if terminating SSL at Gunicorn)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'
```

Run with:

```bash
gunicorn -c gunicorn.conf.py backend.wsgi:application
```

### 4. Enable Redis Persistence

```conf
# redis.conf
save 900 1      # Save after 900s if 1 key changed
save 300 10     # Save after 300s if 10 keys changed
save 60 10000   # Save after 60s if 10000 keys changed
```

---

## Monitoring & Alerting

### 1. Set Up Sentry

```bash
pip install sentry-sdk
```

```python
# backend/settings/common.py
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

if not DEBUG:
    sentry_sdk.init(
        dsn=env('SENTRY_DSN'),
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=env('SENTRY_ENVIRONMENT', default='production'),
    )
```

### 2. Application Metrics

Track key metrics:
- Request rate (requests per second)
- Response time (p50, p95, p99)
- Error rate (5xx responses)
- Database query time
- Redis hit/miss rate
- Celery queue length

### 3. Set Up Alerts

Configure alerts for:
- Error rate > 1%
- Response time p95 > 1000ms
- Database connections > 80% of max
- Redis memory > 80% of max
- Celery queue length > 1000
- Disk space > 80%

---

## Maintenance Tasks

### Daily

- [ ] Monitor error logs
- [ ] Check application metrics
- [ ] Review security alerts

### Weekly

- [ ] Review slow database queries
- [ ] Check disk space usage
- [ ] Review failed Celery tasks
- [ ] Check SSL certificate expiry (90 days notice)

### Monthly

- [ ] Update dependencies (security patches)
  ```bash
  pip list --outdated
  pip install --upgrade <package>
  ```
- [ ] Review access logs for suspicious activity
- [ ] Test database backup restoration
- [ ] Review and optimize database indexes
- [ ] Clean up old data (expired sessions, old logs)

### Quarterly

- [ ] Security audit
- [ ] Performance review
- [ ] Dependency updates (major versions)
- [ ] Review and update documentation

---

## Rollback Procedure

If deployment fails:

1. **Immediate Rollback**
   ```bash
   git revert HEAD
   git push origin main
   ```

2. **Database Rollback** (if migrations were run)
   ```bash
   python manage.py migrate app_name previous_migration
   ```

3. **Restore from Backup** (last resort)
   ```bash
   pg_restore -d database_name backup_file.dump
   ```

4. **Clear Cache**
   ```bash
   python manage.py shell
   >>> from django.core.cache import cache
   >>> cache.clear()
   ```

---

## Scaling Considerations

### Horizontal Scaling

- **Multiple app servers** behind load balancer
- **Stateless architecture** (JWT tokens, no server-side sessions)
- **Shared Redis** instance for all app servers
- **Shared PostgreSQL** with connection pooling

### Vertical Scaling

- Increase Gunicorn workers
- Upgrade database instance
- Increase Redis memory
- Add more Celery workers

### Database Scaling

- **Read replicas** for read-heavy workloads
- **Connection pooling** (PgBouncer)
- **Query optimization** (indexes, select_related, prefetch_related)

### Caching Scaling

- **Redis Cluster** for high availability
- **CDN** for static files
- **Application-level caching** for expensive operations

---

## Security Checklist

- [ ] Run Django's security check
  ```bash
  python manage.py check --deploy
  ```
- [ ] Scan for vulnerabilities
  ```bash
  pip install safety
  safety check
  ```
- [ ] Review OWASP Top 10
- [ ] Enable HTTPS only
- [ ] Set secure cookie flags
- [ ] Configure CSP headers
- [ ] Enable HSTS
- [ ] Disable DEBUG mode
- [ ] Rotate secrets regularly
- [ ] Implement rate limiting
- [ ] Set up WAF (Web Application Firewall)
- [ ] Regular security audits

---

## Final Pre-Launch Commands

```bash
# 1. Run all checks
python manage.py check --deploy

# 2. Run security checks
pip install safety
safety check

# 3. Test migrations (dry run)
python manage.py migrate --check

# 4. Verify static files
python manage.py collectstatic --noinput --dry-run

# 5. Test email
python scripts/email_test.py --dry-run

# 6. Test Redis
python scripts/redis_check.py

# 7. Run tests (if you have them)
python manage.py test

# 8. Create superuser
python manage.py createsuperuser
```

---

## Support & Resources

- **Django Deployment Checklist**: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- **Django Security**: https://docs.djangoproject.com/en/stable/topics/security/
- **Gunicorn Documentation**: https://docs.gunicorn.org/
- **Nginx Configuration**: https://www.nginx.com/resources/wiki/

---

## Post-Launch Monitoring

First 24 hours after launch:

- [ ] Monitor error rates every hour
- [ ] Check response times
- [ ] Verify email delivery
- [ ] Monitor database performance
- [ ] Check Redis hit rates
- [ ] Review access logs
- [ ] Test all critical user flows
- [ ] Monitor server resources (CPU, memory, disk)

First week:

- [ ] Daily review of metrics
- [ ] Identify and fix performance bottlenecks
- [ ] Address any user-reported issues
- [ ] Optimize slow queries
- [ ] Fine-tune caching strategy

---

**Good luck with your production deployment! 🚀**

Remember: Start small, monitor closely, and scale as needed. Always have a rollback plan ready.
