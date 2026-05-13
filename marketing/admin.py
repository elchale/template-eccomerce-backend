from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from marketing.models import Banner, ConfiguracionTienda, Popup, Promocion, SiteTheme


@admin.register(Promocion)
class PromocionAdmin(TranslationAdmin):
    list_display = [
        'nombre', 'tipo', 'valor_descuento', 'es_activo',
        'es_flash_sale', 'fecha_inicio', 'fecha_fin', 'prioridad',
    ]
    list_filter = ['tipo', 'es_activo', 'es_flash_sale', 'aplica_a_todo']
    search_fields = ['nombre', 'slug']
    prepopulated_fields = {'slug': ('nombre',)}
    filter_horizontal = ['productos', 'categorias']
    readonly_fields = ['usos_actuales', 'created', 'updated']
    date_hierarchy = 'fecha_inicio'


@admin.register(Banner)
class BannerAdmin(TranslationAdmin):
    list_display = [
        'nombre', 'tipo', 'posicion', 'es_activo', 'fecha_inicio', 'fecha_fin',
    ]
    list_filter = ['tipo', 'es_activo']
    search_fields = ['nombre', 'titulo']
    readonly_fields = ['created', 'updated']


@admin.register(Popup)
class PopupAdmin(TranslationAdmin):
    list_display = [
        'nombre', 'tipo', 'es_activo', 'retraso_segundos',
        'frecuencia_horas', 'fecha_inicio', 'fecha_fin',
    ]
    list_filter = ['tipo', 'es_activo']
    search_fields = ['nombre', 'titulo']
    readonly_fields = ['created', 'updated']


@admin.register(ConfiguracionTienda)
class ConfiguracionTiendaAdmin(admin.ModelAdmin):
    list_display = ['clave', 'valor', 'descripcion', 'updated']
    search_fields = ['clave', 'descripcion']
    readonly_fields = ['created', 'updated']


@admin.register(SiteTheme)
class SiteThemeAdmin(admin.ModelAdmin):
    list_display = ['theme_id', 'updated']
    readonly_fields = ['created', 'updated']
