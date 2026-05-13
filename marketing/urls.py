from django.urls import include, path
from rest_framework.routers import DefaultRouter

from marketing.views.banners import ActiveBannerListView, AdminBannerViewSet
from marketing.views.configuracion import AdminConfiguracionView, ConfiguracionView
from marketing.views.popups import ActivePopupListView, AdminPopupViewSet
from marketing.views.promociones import ActivePromocionListView, AdminPromocionViewSet
from marketing.views.search import SearchSuggestionsView
from marketing.views.theme import AdminThemeResetView, AdminThemeView, PublicThemeView

# Admin routers
admin_router = DefaultRouter()
admin_router.register(r'promociones', AdminPromocionViewSet, basename='admin-promocion')
admin_router.register(r'banners', AdminBannerViewSet, basename='admin-banner')
admin_router.register(r'popups', AdminPopupViewSet, basename='admin-popup')

urlpatterns = [
    # Public endpoints
    path('api/marketing/promociones/activas/', ActivePromocionListView.as_view(), name='active-promociones'),
    path('api/marketing/banners/activos/', ActiveBannerListView.as_view(), name='active-banners'),
    path('api/marketing/popups/activos/', ActivePopupListView.as_view(), name='active-popups'),
    path('api/marketing/configuracion/', ConfiguracionView.as_view(), name='configuracion'),
    path('api/marketing/theme/', PublicThemeView.as_view(), name='public-theme'),
    path('api/products/search-suggestions/', SearchSuggestionsView.as_view(), name='search-suggestions'),

    # Admin endpoints (router-based)
    path('api/admin/marketing/', include(admin_router.urls)),

    # Admin config & theme
    path('api/admin/marketing/configuracion/', AdminConfiguracionView.as_view(), name='admin-configuracion'),
    path('api/admin/marketing/theme/', AdminThemeView.as_view(), name='admin-theme'),
    path('api/admin/marketing/theme/reset/', AdminThemeResetView.as_view(), name='admin-theme-reset'),
]
