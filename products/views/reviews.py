"""Review views — public listing + admin moderation."""
from rest_framework import generics, status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from products.models import Review
from products.serializers.reviews import ReviewCreateSerializer, ReviewSerializer
from products.tasks import update_product_rating


class ProductReviewListView(generics.ListAPIView):
    """Public listing of *approved* reviews for a product (filtered by ?product=<id> or slug path)."""

    permission_classes = [AllowAny]
    serializer_class = ReviewSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        qs = Review.objects.filter(is_approved=True).select_related('user')
        # Support both slug-path and ?product query param
        if 'slug' in self.kwargs:
            qs = qs.filter(product__slug=self.kwargs['slug'])
        elif 'product' in self.request.query_params:
            qs = qs.filter(product_id=self.request.query_params['product'])
        return qs.order_by('-created')


class ReviewCreateView(generics.CreateAPIView):
    """Authenticated users can create a review.

    New reviews default to is_approved=False until moderated.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ReviewCreateSerializer

    def perform_create(self, serializer):
        review = serializer.save()
        update_product_rating.delay(review.product_id)


class ReviewUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    """Authenticated users can update or delete their own reviews."""

    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user).select_related('user')

    def perform_update(self, serializer):
        review = serializer.save()
        update_product_rating.delay(review.product_id)

    def perform_destroy(self, instance):
        product_id = instance.product_id
        instance.delete()
        update_product_rating.delay(product_id)


class AdminReviewListView(generics.ListAPIView):
    """Admin: list ALL reviews (including unapproved)."""

    permission_classes = [IsAdminUser]
    serializer_class = ReviewSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        qs = Review.objects.select_related('user', 'product').order_by('-created')
        is_approved = self.request.query_params.get('is_approved')
        if is_approved is not None:
            qs = qs.filter(is_approved=is_approved.lower() == 'true')
        return qs


class AdminReviewModerateView(APIView):
    """Admin: PATCH /api/admin/reviews/<pk>/moderate/ — flip is_approved."""

    permission_classes = [IsAdminUser]

    def patch(self, request, pk):
        try:
            review = Review.objects.select_related('product').get(pk=pk)
        except Review.DoesNotExist:
            return Response(
                {'message': 'Review not found.', 'type': 'not_found', 'field_errors': {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_approved = request.data.get('is_approved')
        if is_approved is None:
            return Response(
                {'message': '`is_approved` field is required.', 'type': 'validation_error', 'field_errors': {'is_approved': ['This field is required.']}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        review.is_approved = bool(is_approved)
        review.save(update_fields=['is_approved', 'updated'])

        update_product_rating.delay(review.product_id)

        return Response(ReviewSerializer(review).data, status=status.HTTP_200_OK)
