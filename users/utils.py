import random
import json
import uuid
from fuzzywuzzy import fuzz
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model

from users.cache_keys import RUC_CACHE_KEY

User = get_user_model()


def generate_cool_username(separator: str = "", max_length: int = 20) -> str:
    """
    Generate a unique cool username by combining adjectives and nouns.
    Checks that username doesn't exist in database.
    """
    # Word lists for username generation
    adjectives = "swift bold brave bright calm clever cosmic crafty crisp daring deep divine eager elite epic fierce flash fleet flying ghost grand keen laser lunar major mega mighty mystic neon nimble noble prime proud quick rapid royal shadow sharp silent sleek solar solid sonic stark steel storm super titan ultra vital vivid wild wise".split()

    nouns = "ace agent apex arrow atlas atom blade blaze bolt byte champ comet crow cyber delta drake eagle echo edge falcon flux force frost ghost hawk hero hunter jazz knight legend lynx meteor nebula ninja nova omega orbit phoenix pilot pixel prime pulse raven rebel rex rider rover sage scout shadow shark shield spark storm summit thunder tiger titan vector viking viper vision void wave wizard wolf zenith".split()

    for _ in range(30):  # Reduced max attempts for efficiency

        username = random.choice(adjectives).capitalize() + separator + random.choice(nouns).capitalize() + str(random.randint(10**(2-1), 10**2 - 1))

        # Truncate if too long
        if len(username) > max_length:
            username = username[:max_length]

        # Return if unique
        if not User.objects.filter(username__iexact=username).exists():
            return username

    # Fallback - add UUID suffix
    unique_suffix = f"{separator}{str(uuid.uuid4())[:8]}"
    if len(username) + len(unique_suffix) > max_length:
        username = username[:max_length - len(unique_suffix)]

    return username + unique_suffix


class RegisterUserCheck:
    """
    Check if the last emails are similar to the current email
    """
    COUNT_LAST_EMAILS = getattr(settings, 'RUC_COUNT_EMAILS', 5)
    MIN_SCORE = getattr(settings, 'RUC_MIN_SCORE', 85)

    cache = cache

    @classmethod
    def get_cache_key(cls) -> str:
        return RUC_CACHE_KEY

    @classmethod
    def validate_score_email(cls, email: str) -> bool:
        return cls.get_score_email(email) < cls.MIN_SCORE

    @classmethod
    def get_score_email(cls, email: str) -> int:
        recent_emails = cls.get_last_emails()
        if not recent_emails:
            return 0

        # Calculate similarity scores and return the maximum
        return max(fuzz.token_sort_ratio(email, recent_email) for recent_email in recent_emails)

    @classmethod
    def update_last_emails(cls) -> str:
        users = User.objects.order_by('-pk')[:cls.COUNT_LAST_EMAILS]
        username_list = list(users.values_list(
            'username',
            flat=True,
        ))
        cache_username_str = json.dumps(username_list)
        cls.cache.set(cls.get_cache_key(), cache_username_str)

        return cache_username_str

    @classmethod
    def get_last_emails(cls) -> list[str]:
        cached_str = cache.get(cls.get_cache_key())
        if not cached_str:
            cached_str = cls.update_last_emails()

        cached = json.loads(cached_str)
        return cached
