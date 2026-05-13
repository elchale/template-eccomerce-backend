from modeltranslation.translator import register, TranslationOptions

from .models import Banner, Popup, Promocion


@register(Promocion)
class PromocionTranslationOptions(TranslationOptions):
    fields = ('nombre',)


@register(Banner)
class BannerTranslationOptions(TranslationOptions):
    fields = ('titulo', 'subtitulo', 'texto_cta')


@register(Popup)
class PopupTranslationOptions(TranslationOptions):
    fields = ('titulo', 'mensaje', 'texto_cta')
