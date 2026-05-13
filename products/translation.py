from modeltranslation.translator import register, TranslationOptions

from .models import Category, Product, VariantOption, VariantType


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(VariantType)
class VariantTypeTranslationOptions(TranslationOptions):
    fields = ('name',)


@register(VariantOption)
class VariantOptionTranslationOptions(TranslationOptions):
    fields = ('value',)
