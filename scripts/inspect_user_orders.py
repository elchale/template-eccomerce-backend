"""Read-only inspection of a single user's orders + payments + IPN events.

Usage:
    python scripts/inspect_user_orders.py <email>

Loads `.env.prod` (override=True) before booting Django so it hits the
Railway production database. Strictly read — no writes, no migrations.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env.prod', override=True)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, str(BASE_DIR))

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

from orders.models import IpnEvent, Order, OrderStatusHistory, Payment  # noqa: E402

User = get_user_model()


def main(email: str) -> None:
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        print(f'No user with email={email!r}')
        return

    print(f'User: id={user.id} email={user.email} username={user.username}')
    print(f'      date_joined={user.date_joined}')

    orders = list(Order.objects.filter(user=user).order_by('-created'))
    print(f'\nOrders ({len(orders)}):')
    for o in orders:
        print(
            f'  - {o.order_number}  status={o.status}  payment_status={o.payment_status}  '
            f'total={o.total} {o.currency_code}  created={o.created.isoformat()}'
        )
        print(
            f'      izipay_tx_id={o.izipay_transaction_id!r}  '
            f'token_created_at={o.izipay_form_token_created_at}'
        )

    # Payments
    payments = list(Payment.objects.filter(order__user=user).order_by('-created'))
    print(f'\nPayments ({len(payments)}):')
    for p in payments:
        print(
            f'  - order={p.order.order_number}  method={p.method}  status={p.status}  '
            f'amount={p.amount}  tx_id={p.transaction_id}  created={p.created.isoformat()}'
        )

    # Status history for this user's orders
    history = list(
        OrderStatusHistory.objects.filter(order__user=user).order_by('-created')[:30]
    )
    print(f'\nOrderStatusHistory (last {len(history)}):')
    for h in history:
        print(
            f'  - {h.order.order_number}  {h.old_status} -> {h.new_status}  '
            f'by={h.changed_by_id}  at={h.created.isoformat()}  note={h.note[:120]!r}'
        )

    # IPN events for this user's orders
    order_numbers = [o.order_number for o in orders]
    if order_numbers:
        events = list(
            IpnEvent.objects.filter(order_number__in=order_numbers).order_by('-created')
        )
        print(f'\nIpnEvents ({len(events)}):')
        for e in events:
            print(
                f'  - order={e.order_number}  outcome={e.processed_outcome}  '
                f'order_status={e.order_status}  source_ip={e.source_ip}  '
                f'kr_hash_prefix={e.kr_hash_prefix}  created={e.created.isoformat()}'
            )
            if e.error_detail:
                print(f'      error_detail={e.error_detail[:200]!r}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: python scripts/inspect_user_orders.py <email>')
        sys.exit(1)
    main(sys.argv[1])
