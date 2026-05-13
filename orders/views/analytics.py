from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, F, DecimalField
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order, OrderItem

User = get_user_model()


class DashboardView(APIView):
    """GET - Admin dashboard analytics."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        # Total revenue (from delivered/completed orders, excluding cancelled)
        total_revenue = Order.objects.exclude(
            status=Order.Status.CANCELLED
        ).aggregate(
            total=Sum('total')
        )['total'] or Decimal('0.00')

        # Order counts by status
        status_counts = dict(
            Order.objects.values_list('status').annotate(
                count=Count('id')
            ).values_list('status', 'count')
        )
        order_counts = {}
        for choice_value, choice_label in Order.Status.choices:
            order_counts[choice_value] = status_counts.get(choice_value, 0)

        # Top 10 products by revenue.
        # OrderItem snapshots product_name at order time — no FK to Product.
        # We annotate product__id=None so the frontend type is satisfied.
        top_products = list(
            OrderItem.objects.filter(
                order__status__in=[
                    Order.Status.PENDING,
                    Order.Status.CONFIRMED,
                    Order.Status.PROCESSING,
                    Order.Status.SHIPPED,
                    Order.Status.DELIVERED,
                ]
            ).values(
                'product_name'
            ).annotate(
                total_revenue=Sum(
                    F('price') * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                ),
                total_sold=Sum('quantity'),
            ).order_by('-total_revenue')[:10]
        )
        # Rename keys to match frontend AdminDashboardStats type:
        # product__name, product__id, total_sold, total_revenue
        top_products = [
            {
                'product__name': p['product_name'],
                'product__id': None,
                'total_sold': p['total_sold'],
                'total_revenue': p['total_revenue'],
            }
            for p in top_products
        ]

        # Revenue by day (last 30 days)
        revenue_by_day = list(
            Order.objects.filter(
                created__gte=thirty_days_ago
            ).exclude(
                status=Order.Status.CANCELLED
            ).annotate(
                date=TruncDate('created')
            ).values('date').annotate(
                revenue=Sum('total'),
                order_count=Count('id'),
            ).order_by('date')
        )
        # Convert date objects to strings for JSON serialization
        for entry in revenue_by_day:
            entry['date'] = entry['date'].isoformat()
            entry['revenue'] = str(entry['revenue'])

        # Recent orders (last 10)
        recent_orders = list(
            Order.objects.select_related('user').order_by('-created')[:10].values(
                'id',
                'order_number',
                'status',
                'total',
                'created',
                user_email=F('user__email'),
            )
        )
        for order in recent_orders:
            order['total'] = str(order['total'])
            order['created'] = order['created'].isoformat()

        # New customers (last 30 days)
        new_customers_count = User.objects.filter(
            date_joined__gte=thirty_days_ago
        ).count()

        # Convert top_products Decimal to string for serialization
        for product in top_products:
            product['total_revenue'] = str(product['total_revenue'])
            product['total_sold'] = int(product['total_sold']) if product['total_sold'] is not None else 0

        data = {
            'total_revenue': str(total_revenue),
            'order_counts': order_counts,
            'top_products': top_products,
            'revenue_by_day': revenue_by_day,
            'recent_orders': recent_orders,
            'new_customers_count': new_customers_count,
        }

        return Response(data)
