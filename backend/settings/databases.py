# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

from .env import env

_db_name = env('DB_NAME')
# Allow overriding the test DB name via env var.
# Set TEST_DB_NAME to the same value as DB_NAME when targeting a cloud DB
# (e.g. Neon) that does not permit CREATE / DROP DATABASE.
_test_db_name = env('TEST_DB_NAME', default=f'test_{_db_name}')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': _db_name,
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASS'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default=5432),
        'CONN_MAX_AGE': env('DB_CONN_MAX_AGE', default=10),
        # Neon/PgBouncer does not support server-side cursors; disable them
        # so Django's test-db serialization (and QuerySet.iterator) work correctly.
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'TEST': {
            'NAME': _test_db_name,
        },
    }
}
