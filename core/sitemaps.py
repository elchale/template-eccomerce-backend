"""Django sitemaps for the storefront.

Mounted at /sitemap.xml by backend/urls.py.  URLs are built against
FRONTEND_DOMAIN so the sitemap references the React SPA, not the API server.
"""
from django.conf import settings
from django.contrib.sitemaps import Sitemap


class ProductSitemap(Sitemap):
    changefreq = 'daily'
    priority = 0.8

    def items(self):
        from products.models import Product
        return Product.objects.filter(is_active=True).only('slug', 'updated')

    def location(self, obj):
        return f'{settings.FRONTEND_DOMAIN}/products/{obj.slug}'

    def lastmod(self, obj):
        return obj.updated


class CategorySitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        from products.models import Category
        return Category.objects.filter(is_active=True).only('slug', 'updated')

    def location(self, obj):
        return f'{settings.FRONTEND_DOMAIN}/category/{obj.slug}'

    def lastmod(self, obj):
        return obj.updated


class StaticPagesSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return [
            '/',
            '/shop/',
            '/privacy/',
            '/terms/',
            '/cookies/',
        ]

    def location(self, item):
        return f'{settings.FRONTEND_DOMAIN}{item}'


SITEMAPS = {
    'products': ProductSitemap,
    'categories': CategorySitemap,
    'static': StaticPagesSitemap,
}
