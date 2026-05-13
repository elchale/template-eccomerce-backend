from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from marketing.models import Banner, Popup, Promocion


class Command(BaseCommand):
    help = 'Seeds sample banners, popups, and promotions for dev/demo environments.'

    def handle(self, *args, **options):
        now = timezone.now()
        start = now - timedelta(days=1)
        end = now + timedelta(days=30)

        banners = [
            {
                'nombre': 'Hero principal',
                'tipo': Banner.Tipo.HERO,
                'titulo': 'Nueva colección de temporada',
                'subtitulo': 'Descubre piezas seleccionadas con descuentos hasta 40%',
                'texto_cta': 'Comprar ahora',
                'enlace_cta': '/search',
                'imagen_url': 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1920&q=85',
                'imagen_movil_url': 'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=900&q=85',
                'color_fondo': '#0f172a',
                'color_texto': '#ffffff',
                'posicion': 0,
            },
            {
                'nombre': 'Anuncio envío gratis',
                'tipo': Banner.Tipo.ANUNCIO,
                'titulo': 'Envío gratis en pedidos sobre S/ 200',
                'subtitulo': 'En todo el territorio nacional',
                'texto_cta': 'Ver más',
                'enlace_cta': '/search',
                'imagen_url': 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1600&q=85',
                'imagen_movil_url': 'https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=800&q=85',
                'color_fondo': '#0ea5e9',
                'color_texto': '#ffffff',
                'posicion': 0,
            },
            {
                'nombre': 'Categoría — Moda',
                'tipo': Banner.Tipo.CATEGORIA,
                'titulo': 'Moda femenina',
                'subtitulo': 'Piezas atemporales para el día a día',
                'texto_cta': 'Explorar',
                'enlace_cta': '/shop/category/womens',
                'imagen_url': 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=1600&q=85',
                'imagen_movil_url': 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&q=85',
                'color_fondo': '#f3f4f6',
                'color_texto': '#111827',
                'posicion': 1,
            },
        ]

        banners_created = 0
        for data in banners:
            _, created = Banner.objects.update_or_create(
                nombre=data['nombre'],
                defaults={
                    **data,
                    'es_activo': True,
                    'fecha_inicio': start,
                    'fecha_fin': end,
                },
            )
            if created:
                banners_created += 1

        popups = [
            {
                'nombre': 'Bienvenida — 10% descuento',
                'tipo': Popup.Tipo.BIENVENIDA,
                'titulo': '¡Bienvenido!',
                'mensaje': 'Usa el código BIENVENIDO10 y obtén 10% de descuento en tu primera compra.',
                'imagen_url': 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=600&q=80',
                'texto_cta': 'Comprar ahora',
                'enlace_cta': '/search',
                'codigo_cupon': 'BIENVENIDO10',
                'retraso_segundos': 5,
                'frecuencia_horas': 24,
            },
            {
                'nombre': 'Suscripción — newsletter',
                'tipo': Popup.Tipo.SUSCRIPCION,
                'titulo': 'Recibe nuestras ofertas',
                'mensaje': 'Suscríbete al boletín y sé el primero en enterarte de nuevos lanzamientos.',
                'imagen_url': '',
                'texto_cta': 'Suscribirme',
                'enlace_cta': '',
                'codigo_cupon': '',
                'retraso_segundos': 20,
                'frecuencia_horas': 72,
            },
        ]

        popups_created = 0
        for data in popups:
            _, created = Popup.objects.update_or_create(
                nombre=data['nombre'],
                defaults={
                    **data,
                    'es_activo': True,
                    'fecha_inicio': start,
                    'fecha_fin': end,
                },
            )
            if created:
                popups_created += 1

        promociones = [
            {
                'nombre': 'Descuento de temporada 20%',
                'slug': 'descuento-temporada-20',
                'tipo': Promocion.Tipo.PORCENTAJE,
                'valor_descuento': 20,
                'aplica_a_todo': True,
                'es_flash_sale': False,
                'prioridad': 10,
            },
            {
                'nombre': 'Flash Sale — S/ 30 de descuento',
                'slug': 'flash-sale-30-soles',
                'tipo': Promocion.Tipo.MONTO_FIJO,
                'valor_descuento': 30,
                'aplica_a_todo': True,
                'es_flash_sale': True,
                'prioridad': 20,
            },
            {
                'nombre': 'Compra 2 lleva 3',
                'slug': 'compra-2-lleva-3',
                'tipo': Promocion.Tipo.COMPRA_X_LLEVA_Y,
                'valor_descuento': 0,
                'compra_cantidad': 2,
                'lleva_cantidad': 3,
                'aplica_a_todo': True,
                'es_flash_sale': False,
                'prioridad': 5,
            },
        ]

        promos_created = 0
        for data in promociones:
            _, created = Promocion.objects.update_or_create(
                slug=data['slug'],
                defaults={
                    **data,
                    'es_activo': True,
                    'fecha_inicio': start,
                    'fecha_fin': end,
                },
            )
            if created:
                promos_created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Marketing seed complete: '
            f'{banners_created} banners created ({len(banners)} total), '
            f'{popups_created} popups created ({len(popups)} total), '
            f'{promos_created} promociones created ({len(promociones)} total).'
        ))
