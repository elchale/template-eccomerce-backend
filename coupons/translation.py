from modeltranslation.translator import register, TranslationOptions

from .models import Coupon


@register(Coupon)
class CouponTranslationOptions(TranslationOptions):
    fields = ('description',)
