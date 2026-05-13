import environ
from pathlib import Path

# For building paths use: BASE_DIR / 'subdir'
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
    EMAIL_CONFIRMATION_EXPIRE_DAYS=None,
    EMAIL_CONFIRMATION_COOLDOWN=None,
)

environ.Env.read_env(str(BASE_DIR / '.env'))
