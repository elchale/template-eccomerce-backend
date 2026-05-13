# Pre-Launch Checklist

Quick reference checklist before deploying to production. For detailed instructions, see [PRODUCTION.md](PRODUCTION.md).

## ⚠️ Critical (Must Do)

- [ ] Set `DEBUG=False` in production `.env`
- [ ] Generate new `DJANGO_SECRET_KEY` for production
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] Set `ALLOWED_HOSTS` to your domain
- [ ] Configure production database (PostgreSQL)
- [ ] Set up Redis for caching
- [ ] Configure production SMTP (SendGrid, AWS SES, Mailgun)
- [ ] Enable HTTPS (`SECURE_SSL_REDIRECT=True`)
- [ ] Set secure cookie flags (`SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`)
- [ ] Configure CORS properly (no `*` in production)
- [ ] Set up database backups (automated daily)
- [ ] Collect static files (`python manage.py collectstatic`)
- [ ] Run migrations (`python manage.py migrate`)

## 🔒 Security

- [ ] Run security check: `python manage.py check --deploy`
- [ ] Disable or restrict API docs (`ENABLE_API_DOCS=False`)
- [ ] Set up error tracking (Sentry)
- [ ] Enable HSTS headers
- [ ] Configure rate limiting
- [ ] Review `.gitignore` (ensure no secrets committed)
- [ ] Set up OTP for admin panel
- [ ] Generate strong passwords for all services

## 🧪 Testing

- [ ] Test Redis connection: `python scripts/redis_check.py`
- [ ] Test email delivery: `python scripts/email_test.py -t your@email.com`
- [ ] Test registration flow
- [ ] Test login flow
- [ ] Test password reset flow
- [ ] Test admin panel access
- [ ] Verify API endpoints work
- [ ] Test file uploads (if applicable)

## 📊 Monitoring

- [ ] Set up error tracking (Sentry, Rollbar)
- [ ] Configure logging (centralized logs)
- [ ] Set up uptime monitoring (UptimeRobot, Pingdom)
- [ ] Configure performance monitoring
- [ ] Set up alerts for critical errors
- [ ] Create health check endpoint

## 🚀 Performance

- [ ] Configure Gunicorn with appropriate workers
- [ ] Enable Redis caching
- [ ] Set up Celery for async tasks
- [ ] Configure connection pooling
- [ ] Enable HTTP/2
- [ ] Set up CDN for static files (optional)

## 📝 Documentation

- [ ] Update `.env.template` with all required variables
- [ ] Document deployment process
- [ ] Create rollback procedure
- [ ] Document monitoring setup
- [ ] Update README with production notes

## ✅ Post-Launch (First 24 Hours)

- [ ] Monitor error logs every hour
- [ ] Check response times
- [ ] Verify email delivery
- [ ] Test all critical user flows
- [ ] Monitor database performance
- [ ] Check Redis hit rates
- [ ] Review server resources (CPU, memory, disk)
- [ ] Verify backups are running

## 📞 Emergency Contacts

- [ ] Database admin contact
- [ ] DevOps team contact
- [ ] Domain registrar support
- [ ] Hosting provider support
- [ ] Email service provider support

---

## Quick Commands

```bash
# Security check
python manage.py check --deploy

# Test Redis
python scripts/redis_check.py

# Test emails
python scripts/email_test.py --dry-run

# Collect static files
python manage.py collectstatic --noinput

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

---

**See [PRODUCTION.md](PRODUCTION.md) for comprehensive deployment guide.**
