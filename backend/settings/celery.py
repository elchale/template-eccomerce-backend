"""Celery / broker settings.

When USE_CELERY=False (local dev without a broker), tasks run synchronously
via CELERY_TASK_ALWAYS_EAGER so the application stays fully functional without
RabbitMQ.  Set USE_CELERY=True in production or when you need real async.
"""
from .env import env

# Optional Celery — tasks run eagerly when False (broker-less local dev)
USE_CELERY = env('USE_CELERY', default=True)

# Celery serialisation
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'
CELERY_ACCEPT_CONTENT = [
    'json',
    'pickle',
]

# RabbitMQ broker settings
AMQP_IS_EXTERNAL = env('AMQP_IS_EXTERNAL', default=True)
AMQP_USER = env('AMQP_USER', default='guest')
AMQP_PASS = env('AMQP_PASS', default='guest')
AMQP_HOST = env('AMQP_HOST', default='localhost')
AMQP_PORT = env('AMQP_PORT', default='5672')

# Construct the broker URL
BROKER_URL = f"{'amqps' if AMQP_IS_EXTERNAL else 'amqp'}://{AMQP_USER}:{AMQP_PASS}@{AMQP_HOST}:{AMQP_PORT}/{AMQP_USER if AMQP_IS_EXTERNAL else '/'}"

# Bound the broker connection attempt so a dead/slow broker fails fast
# instead of blocking the web thread (e.g. the IPN on_commit callback).
# _run_via_celery in orders/email_dispatch.py also passes connect_timeout
# and transport_options={'max_retries': 0} per-call for belt-and-suspenders.
CELERY_BROKER_CONNECTION_TIMEOUT = 2  # seconds
CELERY_BROKER_CONNECTION_RETRY = False  # do not retry on connection failure at dispatch time

if not USE_CELERY:
    # Tasks run synchronously in the web process — no broker required.
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
