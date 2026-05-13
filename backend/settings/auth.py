from .env import env

SESSION_COOKIE_AGE = 2 * 24 * 60 * 60  # two days

# ---------------------------------------------------------------------------
# Google OAuth credentials (read from environment)
# ---------------------------------------------------------------------------
GOOGLE_OAUTH_CLIENT_ID = env('GOOGLE_OAUTH_CLIENT_ID', default='')
GOOGLE_OAUTH_CLIENT_SECRET = env('GOOGLE_OAUTH_CLIENT_SECRET', default='')

PASSWORD_MIN_LENGTH = 5

ACCOUNT_ADAPTER = 'users.auth.adapters.AccountAdapter'
ACCOUNT_EMAIL_VERIFICATION = 'mandatory' # Change to "optional" if you want to allow users to login without verifying their email
ACCOUNT_SIGNUP_FIELDS = ['email*','password1*', 'password2*']
ACCOUNT_LOGIN_METHODS = ['email']
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_CONFIRMATION_HMAC = False

AUTHENTICATION_BACKENDS = (
    # 'django.contrib.auth.backends.ModelBackend', # NOTE this is the default, it uses username instead of email to authenticate
    'users.auth.backends.CaseInsensitiveModelBackend', # For logging in with case-insensitive email
)

CAPTCHA_ENABLED = False
CAPTCHA_TIMEOUT = 60 * 60
RECAPTCHA_SECRET = env('RECAPTCHA_SECRET', default='')
IP_MASK = env('CAPTCHA_ALLOWED_IP_MASK', default=r'172.\d{1,3}.\d{1,3}.\d{1,3}')
CAPTCHA_ALLOWED_IP_MASK = fr"{IP_MASK}"

# DISALLOW_COUNTRY = ('')

# Custom settings for auth
RUC_COUNT_EMAILS = env('RUC_COUNT_EMAILS', default=5)
RUC_MIN_SCORE = env('RUC_MIN_SCORE', default=85)
ACTIONS_FREEZE_ON_PWD_RESET = env('ACTIONS_FREEZE_ON_PWD_RESET', default=1800)
ACTIONS_FREEZE_ON_PWD_CHANGE = env('ACTIONS_FREEZE_ON_PWD_CHANGE', default=1800)

# ---------------------------------------------------------------------------
# Social account settings (allauth)
# ---------------------------------------------------------------------------
SOCIALACCOUNT_ADAPTER = 'users.auth.social_adapter.CustomSocialAccountAdapter'
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'  # Google already verified the email
SOCIALACCOUNT_AUTO_SIGNUP = True           # Create new user automatically on first Google login

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': GOOGLE_OAUTH_CLIENT_ID,
            'secret': GOOGLE_OAUTH_CLIENT_SECRET,
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    }
}
