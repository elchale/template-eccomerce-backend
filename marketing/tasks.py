import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def deactivate_expired_promociones():
    """
    Celery task: set es_activo=False on promotions whose fecha_fin has passed.

    Note: the public views already filter by date range, so expired promotions
    are never exposed publicly. This task is cleanup-only to keep the DB tidy
    and make admin listings accurate.
    """
    from marketing.models import Promocion

    now = timezone.now()
    updated_count = Promocion.objects.filter(
        es_activo=True,
        fecha_fin__lt=now,
    ).update(es_activo=False)

    if updated_count:
        logger.info(
            f'deactivate_expired_promociones: deactivated {updated_count} expired promotion(s).'
        )
    else:
        logger.debug('deactivate_expired_promociones: no expired promotions found.')

    return updated_count
