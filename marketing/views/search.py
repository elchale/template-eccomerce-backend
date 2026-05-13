from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from marketing.cache_keys import SEARCH_SUGGESTIONS_CACHE_KEY
from products.models import Product


class SearchSuggestionsView(APIView):
    """
    GET ?q=<query> - Returns top 5 active products whose name contains the query.
    Minimum 2 characters required. Results are cached for 1 minute.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if len(q) < 2:
            return Response([])

        cache_key = f"{SEARCH_SUGGESTIONS_CACHE_KEY}:{q.lower()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        products = (
            Product.objects
            .filter(is_active=True, name__icontains=q)
            .select_related('category')
            .prefetch_related('images')
            .order_by('-average_rating', '-review_count')[:5]
        )

        results = []
        for product in products:
            images = list(product.images.all())
            primary = next((img for img in images if img.is_primary), None)
            image_url = primary.image_url if primary else (images[0].image_url if images else '')

            results.append({
                'id': product.id,
                'name': product.name,
                'slug': product.slug,
                'base_price': str(product.base_price),
                'image_url': image_url,
            })

        cache.set(cache_key, results, 60)
        return Response(results)
