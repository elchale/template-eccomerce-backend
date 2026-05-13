from django.db import models

from core.models import BaseModel


class Promocion(BaseModel):
    class Tipo(models.TextChoices):
        PORCENTAJE = 'porcentaje', 'Porcentaje'
        MONTO_FIJO = 'monto_fijo', 'Monto Fijo'
        COMPRA_X_LLEVA_Y = 'compra_x_lleva_y', 'Compra X Lleva Y'

    nombre = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    valor_descuento = models.DecimalField(max_digits=10, decimal_places=2)
    compra_cantidad = models.PositiveIntegerField(null=True, blank=True)
    lleva_cantidad = models.PositiveIntegerField(null=True, blank=True)
    productos = models.ManyToManyField(
        'products.Product',
        blank=True,
        related_name='promociones',
    )
    categorias = models.ManyToManyField(
        'products.Category',
        blank=True,
        related_name='promociones',
    )
    aplica_a_todo = models.BooleanField(default=False)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    es_flash_sale = models.BooleanField(default=False)
    limite_uso = models.PositiveIntegerField(null=True, blank=True)
    usos_actuales = models.PositiveIntegerField(default=0)
    es_activo = models.BooleanField(default=True)
    prioridad = models.IntegerField(default=0)

    class Meta:
        ordering = ['-prioridad', '-created']
        indexes = [
            models.Index(fields=['es_activo', 'fecha_inicio', 'fecha_fin']),
            models.Index(fields=['slug']),
        ]
        verbose_name = 'Promoción'
        verbose_name_plural = 'Promociones'

    def __str__(self):
        return self.nombre


class Banner(BaseModel):
    class Tipo(models.TextChoices):
        HERO = 'hero', 'Hero'
        ANUNCIO = 'anuncio', 'Anuncio'
        CATEGORIA = 'categoria', 'Categoria'

    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    titulo = models.CharField(max_length=255, blank=True)
    subtitulo = models.CharField(max_length=255, blank=True)
    texto_cta = models.CharField(max_length=100, blank=True)
    enlace_cta = models.URLField(blank=True)
    imagen_url = models.URLField(blank=True)
    imagen_movil_url = models.URLField(blank=True)
    color_fondo = models.CharField(max_length=20, blank=True)
    color_texto = models.CharField(max_length=20, blank=True)
    posicion = models.IntegerField(default=0)
    es_activo = models.BooleanField(default=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['posicion', '-created']
        indexes = [
            models.Index(fields=['tipo', 'es_activo']),
        ]
        verbose_name = 'Banner'
        verbose_name_plural = 'Banners'

    def __str__(self):
        return self.nombre


class Popup(BaseModel):
    class Tipo(models.TextChoices):
        BIENVENIDA = 'bienvenida', 'Bienvenida'
        ABANDONO_CARRITO = 'abandono_carrito', 'Abandono de Carrito'
        INTENCION_SALIDA = 'intencion_salida', 'Intención de Salida'
        SUSCRIPCION = 'suscripcion', 'Suscripción'

    nombre = models.CharField(max_length=255)
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    titulo = models.CharField(max_length=255)
    mensaje = models.TextField()
    imagen_url = models.URLField(blank=True)
    texto_cta = models.CharField(max_length=100, blank=True)
    enlace_cta = models.URLField(blank=True)
    codigo_cupon = models.CharField(max_length=50, blank=True)
    retraso_segundos = models.IntegerField(default=3)
    frecuencia_horas = models.IntegerField(default=24)
    es_activo = models.BooleanField(default=True)
    fecha_inicio = models.DateTimeField(null=True, blank=True)
    fecha_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['tipo', 'es_activo']),
        ]
        verbose_name = 'Popup'
        verbose_name_plural = 'Popups'

    def __str__(self):
        return self.nombre


class SiteTheme(BaseModel):
    THEME_CHOICES = [
        ('classic',  'Clásico'),
        ('dark',     'Oscuro'),
        ('elegant',  'Elegante'),
        ('nature',   'Naturaleza'),
        ('vibrant',  'Vibrante'),
        ('pastel',   'Pastel'),
        ('tech',     'Tecnología'),
        ('minimal',  'Minimalista'),
    ]

    theme_id = models.CharField(max_length=20, choices=THEME_CHOICES, default='classic')
    custom_colors = models.JSONField(default=dict, blank=True)
    # `created` and `updated` provided by BaseModel

    class Meta:
        verbose_name = 'Tema del sitio'
        verbose_name_plural = 'Tema del sitio'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Singleton — never delete
        return

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'theme_id': 'classic', 'custom_colors': {}})
        return obj

    def __str__(self):
        return f'SiteTheme[{self.theme_id}]'


class ConfiguracionTienda(BaseModel):
    clave = models.CharField(max_length=100, unique=True)
    valor = models.TextField()
    descripcion = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['clave']
        indexes = [
            models.Index(fields=['clave']),
        ]
        verbose_name = 'Configuración de Tienda'
        verbose_name_plural = 'Configuraciones de Tienda'

    def __str__(self):
        return self.clave
