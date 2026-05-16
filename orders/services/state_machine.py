"""Order state machine.

Encodes allowed transitions and performs them atomically:
  1. Validates the transition (raises InvalidTransition → 400)
  2. Writes an OrderStatusHistory row
  3. Dispatches send_order_status_changed via dispatch_order_email (on_commit)

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

        # Dispatch email notification via dispatch_order_email (commit-deferred,
        # non-blocking, with EmailLog tracking).
        try:
            from orders.tasks import send_order_status_changed
            import orders.email_dispatch as _ed

            _ed.dispatch_order_email(
                send_order_status_changed,
                order.id,
                old_status,
                new_status,
                changed_by_id=user.id if user else None,
                order_id=order.id,
                email_type='customer_status_update',
            )
        except Exception as exc:
            logger.warning(
                'OrderStateMachine: could not dispatch status-change email for order %s: %s',
                order.order_number, exc,
            )
