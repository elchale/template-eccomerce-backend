from django.urls import include, path
from rest_framework.routers import DefaultRouter

from products.views.categories import (
    AdminCategoryViewSet,
    CategoryDetailView,
    CategoryListView,
)
from products.views.products import (
    AdminProductImageView,
    AdminProductVariantViewSet,
    AdminProductViewSet,
    AdminVariantTypeViewSet,
    ProductDetailView,
    ProductListView,
)
from products.views.reviews import (
    AdminReviewListView,
    AdminReviewModerateView,
    ProductReviewListView,
    ReviewCreateView,
    ReviewUpdateDeleteView,
)
from products.views.wishlist import WishlistListView, WishlistToggleView

# Admin routers
admin_router = DefaultRouter()
admin_router.register(r'products', AdminProductViewSet, basename='admin-product')
admin_router.register(r'categories', AdminCategoryViewSet, basename='admin-category')
admin_router.register(r'variant-types', AdminVariantTypeViewSet, basename='admin-variant-type')

# Nested variant router for admin products
variant_router = DefaultRouter()
variant_router.register(r'variants', AdminProductVariantViewSet, basename='admin-product-variant')

urlpatterns = [
    # Public product endpoints
    path('api/products/', ProductListView.as_view(), name='product-list'),
    path('api/products/<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),

    # Public category endpoints
    path('api/categories/', CategoryListView.as_view(), name='category-list'),
    path('api/categories/<slug:slug>/', CategoryDetailView.as_view(), name='category-detail'),

    # Product reviews
    path('api/products/<slug:slug>/reviews/', ProductReviewListView.as_view(), name='product-review-list'),
    # GET /api/reviews/?product=<id> for public listing; POST for create
    path('api/reviews/', ProductReviewListView.as_view(), name='review-list'),
    path('api/reviews/create/', ReviewCreateView.as_view(), name='review-create'),
    path('api/reviews/<int:pk>/', ReviewUpdateDeleteView.as_view(), name='review-update-delete'),

    # Wishlist
    path('api/wishlist/', WishlistListView.as_view(), name='wishlist-list'),
    path('api/wishlist/toggle/', WishlistToggleView.as_view(), name='wishlist-toggle'),

    # Admin review moderation
    path('api/admin/reviews/', AdminReviewListView.as_view(), name='admin-review-list'),
    path('api/admin/reviews/<int:pk>/moderate/', AdminReviewModerateView.as_view(), name='admin-review-moderate'),

    # Admin endpoints (router-based)
    path('api/admin/', include(admin_router.urls)),

    # Admin product images
    path(
        'api/admin/products/<int:product_id>/images/',
        AdminProductImageView.as_view(),
        name='admin-product-images',
    ),

    # Admin product variants (nested under product)
    path(
        'api/admin/products/<int:product_id>/',
        include(
            (variant_router.urls, 'admin-product-variants'),
        ),
    ),
]
