"""Order state machine.

Encodes allowed transitions and performs them atomically:
  1. Validates the transition (raises InvalidTransition → 400)
  2. Writes an OrderStatusHistory row
  3. Enqueues send_order_status_changed.delay()

Izipay refund side-effects remain in the view layer — the machine only
handles pure state transitions.
"""
import logging

from django.db import transaction

logger = logging.getLogger(__name__)

# Mapping: current_status → set of allowed next statuses
_TRANSITIONS: dict[str, set[str]] = {
    'pending':   {'confirmed', 'cancelled'},
    'confirmed': {'shipped', 'cancelled', 'refunded'},
    'shipped':   {'delivered', 'refunded'},
    'delivered': {'refunded'},
    'cancelled': set(),   # terminal
    'refunded':  set(),   # terminal
    # Legacy — keep compatibility with existing PROCESSING status
    'processing': {'shipped', 'cancelled', 'refunded'},
}


class OrderStateMachine:

    @staticmethod
    def transition(order, new_status: str, *, user=None, note: str = '') -> None:
        """Transition *order* to *new_status* atomically.

        Raises
        ------
        InvalidTransition
            When the transition is not allowed.
        """
        from orders.exceptions import InvalidTransition
        from orders.models import OrderStatusHistory

        old_status = order.status
        allowed = _TRANSITIONS.get(old_status, set())

        if new_status not in allowed:
            raise InvalidTransition(
                f"Cannot transition order from '{old_status}' to '{new_status}'."
            )

        with transaction.atomic():
            order.status = new_status
            order.save(update_fields=['status', 'updated'])

            OrderStatusHistory.objects.create(
                order=order,
                old_status=old_status,
                new_status=new_status,
                note=note,
                changed_by=user,
            )

        # Enqueue email notification outside the atomic block
        try:
            from orders.tasks import send_order_status_changed
            send_order_status_changed.delay(order.id, old_status, new_status)
        except Exception as exc:
            logger.warning(
                'Could not enqueue status-change email for order %s: %s',
                order.order_number, exc,
            )
