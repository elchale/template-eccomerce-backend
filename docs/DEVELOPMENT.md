# Development Guide

This guide covers development workflows, coding standards, and best practices for contributing to this project.

## Getting Started

### Prerequisites

- Python 3.13+
- PostgreSQL 12+
- Redis 6+
- RabbitMQ (optional, for Celery tasks)

### Initial Setup

```bash
# Clone repository
git clone <repository-url>
cd daddy-django

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.template .env
# Edit .env with your configuration

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Accessing the Application

- **Frontend**: http://localhost:8000/
- **Admin Panel**: http://localhost:8000/admin/ (requires OTP)
- **API Docs**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/

## Development Workflow

### Creating a New Feature

1. **Create Feature Branch**
```bash
git checkout -b feature/feature-name
```

2. **Implement Feature**
- Add models, views, serializers
- Write docstrings
- Add tests

3. **Run Tests**
```bash
python manage.py test
```

4. **Commit Changes**
```bash
git add .
git commit -m "Add feature: description"
```

5. **Push and Create PR**
```bash
git push origin feature/feature-name
```

### Adding a New Django App

```bash
# Create app
python manage.py startapp app_name

# Add to INSTALLED_APPS in backend/settings/common.py
INSTALLED_APPS = [
    ...
    'app_name',
]

# Create app structure
mkdir app_name/serializers
mkdir app_name/tests

# Add __init__.py with docstring
# app_name/__init__.py
"""
App Name - Brief description

Purpose:
    What this app does

Features:
    - Feature 1
    - Feature 2

Dependencies:
    - core: For base models
    - users: For authentication
"""

# Inherit from base models
# app_name/models.py
from core.models import BaseModel

class YourModel(BaseModel):
    """Model description with examples"""
    pass
```

## Coding Standards

### Python Style Guide

Follow **PEP 8** with these specifics:

- **Line Length**: 120 characters (Django standard)
- **Indentation**: 4 spaces
- **Imports**: Grouped and sorted
  ```python
  # Standard library
  import os
  from datetime import datetime

  # Django
  from django.conf import settings
  from django.db import models

  # Third-party
  from rest_framework import serializers

  # Local
  from core.models import BaseModel
  from users.models import Profile
  ```

### Naming Conventions

```python
# Models: PascalCase
class UserProfile(BaseModel):
    pass

# Functions/Methods: snake_case
def send_notification_email():
    pass

# Constants: UPPER_SNAKE_CASE
MAX_LOGIN_ATTEMPTS = 5

# Private: prefix with underscore
def _internal_helper():
    pass
```

### Docstring Style

Use **Google Style** docstrings:

```python
def complex_function(param1, param2, optional=None):
    """
    Brief one-line summary.

    More detailed description if needed. Explain what the function
    does, any side effects, and important behavior.

    Args:
        param1 (str): Description of param1
        param2 (int): Description of param2
        optional (bool, optional): Description. Defaults to None.

    Returns:
        dict: Description of return value

    Raises:
        ValueError: When param1 is empty
        TypeError: When param2 is not an integer

    Example:
        >>> result = complex_function("test", 42)
        >>> print(result)
        {'status': 'success'}

    Note:
        Any important notes or warnings

    See Also:
        - related_function(): For related functionality
    """
    pass
```

### Model Documentation

```python
class Profile(BaseModel):
    """
    Extended user profile with security features.

    This model extends Django's built-in User model with additional
    security and profile information.

    Attributes:
        user (User): OneToOne relationship to Django User
        actions_freezed_till (datetime): Timestamp when actions unfreeze

    Methods:
        set_actions_freeze(hours): Freeze user actions temporarily
        is_actions_frozen(): Check if actions are currently frozen

    Example:
        >>> profile = user.profile
        >>> profile.set_actions_freeze(hours=24)
        >>> profile.is_actions_frozen()
        True

    Related Models:
        - User: Django's built-in user model
        - LoginHistory: Tracks user login attempts
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        help_text="Associated user account"
    )
```

### Serializer Documentation

```python
class LoginSerializer(BaseLoginSerializer):
    """
    Handles user authentication with security features.

    Security Checks:
        1. Captcha verification (if required)
        2. Email verification status
        3. Account active status
        4. Password validation
        5. Optional 2FA

    Request Body:
        - email (str): User email address
        - password (str): User password
        - captcha (str, optional): reCAPTCHA token

    Response:
        - access_token (str): JWT access token
        - refresh_token (str): JWT refresh token
        - user (dict): User details

    Side Effects:
        - Creates LoginHistory record
        - Sends email if IP changed
        - Updates captcha cache

    Example:
        POST /auth/login/
        {
            "email": "user@example.com",
            "password": "securepass"
        }
    """
    pass
```

## Database Migrations

### Creating Migrations

```bash
# Create migrations for all apps
python manage.py makemigrations

# Create migration for specific app
python manage.py makemigrations users

# Create empty migration (for data migrations)
python manage.py makemigrations --empty users
```

### Applying Migrations

```bash
# Apply all migrations
python manage.py migrate

# Apply specific migration
python manage.py migrate users 0001

# Show migration status
python manage.py showmigrations

# Rollback migration
python manage.py migrate users 0001  # rolls back to 0001
```

### Migration Best Practices

✅ **DO**:
- Review generated migrations before committing
- Add helpful comments in migrations
- Test migrations on copy of production data
- Make migrations reversible when possible

❌ **DON'T**:
- Edit migrations after they're committed
- Delete migrations
- Skip migrations in production

## Testing

### Running Tests

```bash
# Run all tests
python manage.py test

# Run specific app
python manage.py test users

# Run specific test class
python manage.py test users.tests.TestLogin

# Run with coverage
coverage run --source='.' manage.py test
coverage report
coverage html  # Generate HTML report
```

### Writing Tests

```python
# users/tests/test_auth.py
from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()

class LoginTestCase(TestCase):
    """Test user login functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )

    def test_login_success(self):
        """Test successful login returns tokens"""
        response = self.client.post('/auth/login/', {
            'email': 'test@example.com',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access_token', response.json())

    def test_login_invalid_password(self):
        """Test login fails with wrong password"""
        response = self.client.post('/auth/login/', {
            'email': 'test@example.com',
            'password': 'wrongpass'
        })
        self.assertEqual(response.status_code, 400)

    def tearDown(self):
        """Clean up test data"""
        self.user.delete()
```

## API Development

### Adding New Endpoints

1. **Create Serializer**
```python
# app/serializers.py
class ItemSerializer(serializers.ModelSerializer):
    """Serializer for Item model"""

    class Meta:
        model = Item
        fields = ['id', 'name', 'created']
```

2. **Create View**
```python
# app/views.py
from rest_framework import viewsets
from drf_spectacular.utils import extend_schema

class ItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Item CRUD operations.

    Endpoints:
        - GET /api/items/ - List all items
        - POST /api/items/ - Create item
        - GET /api/items/{id}/ - Retrieve item
        - PUT /api/items/{id}/ - Update item
        - DELETE /api/items/{id}/ - Delete item
    """
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    @extend_schema(
        summary="List all items",
        description="Returns paginated list of items",
        tags=['Items']
    )
    def list(self, request):
        return super().list(request)
```

3. **Add URL**
```python
# app/urls.py
from rest_framework.routers import DefaultRouter
from .views import ItemViewSet

router = DefaultRouter()
router.register('items', ItemViewSet)

urlpatterns = router.urls
```

4. **Include in Main URLs**
```python
# backend/urls.py
from django.urls import path, include

urlpatterns = [
    ...
    path('api/', include('app.urls')),
]
```

5. **Check Swagger**
- Visit http://localhost:8000/api/docs/
- Your endpoints should appear automatically

## Environment Variables

### Adding New Environment Variables

1. **Add to `.env.template`** with description
```env
# Feature flags
ENABLE_FEATURE_X=False  # Enable experimental feature X
```

2. **Load in settings**
```python
# backend/settings/common.py
ENABLE_FEATURE_X = env('ENABLE_FEATURE_X', default=False)
```

3. **Document in README** if user-facing

## Debugging

### Django Debug Toolbar (Optional)

```bash
# Install
pip install django-debug-toolbar

# Add to INSTALLED_APPS (development only)
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']

# Add middleware
if DEBUG:
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']

# Configure
if DEBUG:
    INTERNAL_IPS = ['127.0.0.1']
```

### Logging

```python
import logging
logger = logging.getLogger(__name__)

# Use in code
logger.debug('Debug message')
logger.info('Info message')
logger.warning('Warning message')
logger.error('Error message')
logger.exception('Exception with traceback')
```

### Django Shell

```bash
# Open shell
python manage.py shell

# Use shell_plus if available
python manage.py shell_plus
```

```python
# In shell
from users.models import Profile
from django.contrib.auth import get_user_model

User = get_user_model()

# Query users
users = User.objects.all()
user = User.objects.get(email='test@example.com')

# Check profile
profile = user.profile
print(profile.is_actions_frozen())
```

## Common Tasks

### Reset Database

```bash
# Drop and recreate database (PostgreSQL)
python manage.py dbshell
DROP DATABASE django_template;
CREATE DATABASE django_template;
\q

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Clear Cache

```python
# In Django shell
from django.core.cache import cache
cache.clear()
```

### Generate Secret Key

```python
# In Python shell
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

## Troubleshooting

### Common Issues

**Issue**: Migrations conflict
```bash
# Solution
python manage.py migrate --fake app_name migration_number
python manage.py migrate
```

**Issue**: Port already in use
```bash
# Solution (Linux/Mac)
lsof -i :8000
kill -9 <PID>

# Solution (Windows)
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Issue**: Database connection refused
- Check PostgreSQL is running
- Verify credentials in `.env`
- Check `DB_HOST` and `DB_PORT`

**Issue**: Redis connection error
- Check Redis is running: `redis-cli ping`
- Verify `REDIS_HOST` and `REDIS_PORT`

## Git Workflow

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `hotfix/description` - Urgent production fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation updates

### Commit Messages

Follow conventional commits:

```
feat: add user profile endpoint
fix: resolve login captcha bug
docs: update API documentation
refactor: simplify serializer logic
test: add login tests
chore: update dependencies
```

### Before Committing

```bash
# Check code style
black .
flake8 .

# Run tests
python manage.py test

# Check migrations
python manage.py makemigrations --dry-run --check

# Security check
python manage.py check --deploy
```

## Resources

- [Django Documentation](https://docs.djangoproject.com/)
- [DRF Documentation](https://www.django-rest-framework.org/)
- [PEP 8 Style Guide](https://pep8.org/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
