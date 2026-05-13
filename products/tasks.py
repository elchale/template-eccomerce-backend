from celery import shared_task
from django.db.models import Avg, Count


@shared_task
def update_product_rating(product_id):
    """
    Recalculate the average_rating and review_count for a product
    based on its reviews.
    """
    from products.models import Product

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return

    stats = product.reviews.aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id'),
    )

    product.average_rating = stats['avg_rating'] or 0
    product.review_count = stats['total_reviews'] or 0
    product.save(update_fields=['average_rating', 'review_count', 'updated'])
