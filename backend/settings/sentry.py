"""Optional Sentry integration.

Init is a no-op when SENTRY_DSN is empty — safe for local dev without a DSN.
The entire init block is wrapped in try/except so a misconfigured DSN or SDK
version mismatch never prevents Django from starting.
"""
import logging

from .env import env

SENTRY_DSN = env('SENTRY_DSN', default='')
SENTRY_ENVIRONMENT = env('SENTRY_ENVIRONMENT', default='local')
SENTRY_TRACES_SAMPLE_RATE = env('SENTRY_TRACES_SAMPLE_RATE', default=0.05)

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            traces_sample_rate=float(SENTRY_TRACES_SAMPLE_RATE),
            integrations=[
                DjangoIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            send_default_pii=False,
        )
    except Exception as exc:  # pragma: no cover
        import logging as _logging
        _logging.getLogger(__name__).warning('Sentry init failed: %s', exc)
