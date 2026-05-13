from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent

LANGUAGE_CODE = 'es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ('es', 'Español'),
    ('en', 'English'),
    ('pt', 'Português'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

MODELTRANSLATION_DEFAULT_LANGUAGE = 'es'
MODELTRANSLATION_LANGUAGES = ('es', 'en', 'pt')
MODELTRANSLATION_FALLBACK_LANGUAGES = {'default': ('es',)}
