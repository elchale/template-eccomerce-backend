import os
from kombu import Queue
from django.conf import settings
from celery import Celery

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

backend_url = f"redis://:{settings.REDIS['pwd']}@{settings.REDIS['host']}:{settings.REDIS['port']}" \
    if settings.REDIS['pwd'] else \
    f"redis://{settings.REDIS['host']}:{settings.REDIS['port']}"

app = Celery(
    'core',
    backend=backend_url,
    broker=settings.BROKER_URL,
    include=[
        # Tasks from all apps
    ]
)

# Configure Celery using settings from Django settings.py
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.worker_log_format = "[%(asctime)s: %(processName)s %(levelname)s] %(name)s %(message)s"

app.conf.beat_schedule = {}
app.conf.task_routes = {}
app.conf.task_default_queue = 'default'

app.conf.task_queues = (
    Queue('default'),
)


if False:
    app.conf.beat_schedule.update({
        'task_name': {
            'task': 'task_path',
            'schedule': 60.0,
            'options': {
                'queue': 'queue_name',
            }
        },
    })
    app.conf.task_queues += (Queue('queue_name'),)


# Load task modules from all registered Django apps
app.autodiscover_tasks()
