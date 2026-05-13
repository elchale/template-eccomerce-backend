from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from coupons.models import Coupon


@admin.register(Coupon)
class CouponAdmin(TranslationAdmin):
    list_display = (
        'code',
        'discount_type',
        'discount_value',
        'is_active',
        'times_used',
        'valid_from',
        'valid_until',
    )
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code', 'description')
    readonly_fields = ('times_used', 'created', 'updated')
    ordering = ('-created',)
