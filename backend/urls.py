from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path
from django_otp.admin import OTPAdminSite
from django.views.generic import TemplateView
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

from core.views import healthz, readyz, robots_txt
from core.sitemaps import SITEMAPS
from users.urls import urlpatterns as users_urlpatterns
from coupons.urls import urlpatterns as coupons_urlpatterns
from orders.urls import urlpatterns as orders_urlpatterns
from products.urls import urlpatterns as products_urlpatterns
from marketing.urls import urlpatterns as marketing_urlpatterns

admin.site.__class__ = OTPAdminSite

urlpatterns = [
    path('', TemplateView.as_view(template_name='landing.html', extra_context={'project_name': settings.PROJECT_NAME}), name='landing'),
    path('admin/', admin.site.urls),

    # Probes
    path('healthz/', healthz, name='healthz'),
    path('readyz/', readyz, name='readyz'),

    # SEO
    path('robots.txt', robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='django.contrib.sitemaps.views.sitemap'),
]

# API Documentation (can be disabled in production via settings)
if getattr(settings, 'ENABLE_API_DOCS', settings.DEBUG):
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ]

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns.extend(users_urlpatterns)
urlpatterns.extend(coupons_urlpatterns)
urlpatterns.extend(orders_urlpatterns)
urlpatterns.extend(products_urlpatterns)
urlpatterns.extend(marketing_urlpatterns)
