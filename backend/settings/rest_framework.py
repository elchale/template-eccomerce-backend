from datetime import timedelta
from .env import env

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
    ),
    'PAGE_SIZE': 10,
    'MAX_PAGINATE_BY': 100,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ),
    'COERCE_DECIMAL_TO_STRING': False,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'dj_rest_auth': '5/minute',
        'email_confirm': '10/min',
        'coupon_validate': '30/minute',
        # Soft-delete confirms the live password; throttle prevents
        # password-grinding via the X-Confirm-Password header.
        'account_delete': '5/minute',
    },
    'EXCEPTION_HANDLER': 'core.exceptions.envelope_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# These are the settings for dj-rest-auth with simplejwt
REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_COOKIE': 'jwt_auth_token',
    'JWT_AUTH_REFRESH_COOKIE': 'jwt_refresh_token',
    'JWT_EXPIRATION_DELTA': timedelta(minutes=15),
    'JWT_AUTH_RETURN_EXPIRATION': True,
    'TOKEN_MODEL': None,
    'JWT_AUTH_HTTPONLY': True,
    'EMAIL_VERIFICATION': True,

    'USER_DETAILS_SERIALIZER': 'users.serializers.auth.UserSerializer',

    # This setting prevents tokens from being issued during registration
    'TOKEN_SERIALIZER': None,
    'LOGIN_SERIALIZER': 'users.serializers.auth.LoginSerializer',
    'REGISTER_SERIALIZER': 'users.serializers.auth.RegisterSerializer',

    'PASSWORD_RESET_SERIALIZER': 'users.serializers.auth.PasswordResetSerializer',
    'PASSWORD_CHANGE_SERIALIZER': 'users.serializers.auth.PasswdChangeSerializer',
    'PASSWORD_RESET_CONFIRM_SERIALIZER': 'users.serializers.auth.PasswordResetConfirmSerializer',

    'JWT_AUTH_SECURE': not env('DEBUG', default=False),
}

OLD_PASSWORD_FIELD_ENABLED = True

# JWT settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'ALGORITHM': 'HS512',
}

# drf-spectacular settings for API documentation
SPECTACULAR_SETTINGS = {
    'TITLE': env('PROJECT_NAME', default='Django API'),
    'DESCRIPTION': 'A comprehensive Django REST API with authentication and security features',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,

    # Authentication
    'SECURITY': [{'bearerAuth': []}],
    'COMPONENT_SPLIT_REQUEST': True,

    # Better schema generation
    'SCHEMA_PATH_PREFIX': r'/api/v[0-9]',
    'SCHEMA_PATH_PREFIX_TRIM': True,
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],  # Control access to schema

    # UI Configuration
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': True,
        'filter': True,
        'tryItOutEnabled': True,
    },

    # Tags for grouping endpoints
    'TAGS': [
        {'name': 'Authentication', 'description': 'User authentication and account management'},
        {'name': 'Users', 'description': 'User profile operations'},
    ],

    # Additional settings
    'CONTACT': {
        'name': 'API Support',
        'email': env('DEFAULT_FROM_EMAIL', default=''),
    },
    'LICENSE': {
        'name': 'Proprietary',
    },
}



