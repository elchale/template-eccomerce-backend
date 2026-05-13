from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from products.models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    VariantOption,
    VariantType,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ['image_url', 'alt_text', 'sort_order', 'is_primary']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ['sku', 'price', 'stock', 'is_active']


@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'sort_order', 'created']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'slug', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['sort_order', 'name']


@admin.register(Product)
class ProductAdmin(TranslationAdmin):
    list_display = [
        'name',
        'slug',
        'category',
        'base_price',
        'stock',
        'is_active',
        'is_featured',
        'average_rating',
        'review_count',
        'created',
    ]
    list_filter = ['is_active', 'is_featured', 'category']
    search_fields = ['name', 'slug', 'sku', 'description']
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline, ProductVariantInline]
    ordering = ['-created']


@admin.register(VariantType)
class VariantTypeAdmin(TranslationAdmin):
    list_display = ['name', 'created']
    search_fields = ['name']


@admin.register(VariantOption)
class VariantOptionAdmin(TranslationAdmin):
    list_display = ['variant_type', 'value', 'created']
    list_filter = ['variant_type']
    search_fields = ['value', 'variant_type__name']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = [
        'product',
        'user',
        'rating',
        'title',
        'is_verified_purchase',
        'created',
    ]
    list_filter = ['rating', 'is_verified_purchase', 'created']
    search_fields = ['product__name', 'user__email', 'title', 'comment']
    readonly_fields = ['user', 'product', 'is_verified_purchase']
    ordering = ['-created']
