"""Shared pricing helpers for active marketing promotions.

Single source of truth for resolving the active :class:`marketing.Promocion`
that applies to a product and computing the discounted unit price. Used by both
the product display serializers (``variant=None`` → product-page behaviour) and
the cart/checkout flow (variant-aware).
"""
from decimal import Decimal

from django.utils import timezone

CENTS = Decimal('0.01')


def get_active_promo_for_product(product, active_promos=None):
    """
    Return the highest-priority active Promocion that applies to this product
    (via product M2M, category M2M, or ``aplica_a_todo``).
    Returns ``None`` if no active promotion applies.

    Active = ``es_activo AND fecha_inicio <= now <= fecha_fin``.
    Precedence: product-link > category-link > store-wide, then ``-prioridad``.

    If ``active_promos`` is provided (a prefetched list already sorted by
    ``-prioridad`` and filtered to currently-active promos), the match is
    resolved in-memory to avoid N+1 queries. Otherwise the DB is queried.
    """
    if active_promos is not None:
        # In-memory lookup using prefetched promos (avoids N+1).
        product_id = product.pk
        category_id = product.category_id

        best_product_promo = None
        best_category_promo = None
        best_global_promo = None

        for promo in active_promos:
            if not best_product_promo:
                promo_product_ids = {p.pk for p in promo.productos.all()}
                if product_id in promo_product_ids:
                    best_product_promo = promo

            if not best_category_promo and category_id:
                promo_category_ids = {c.pk for c in promo.categorias.all()}
                if category_id in promo_category_ids:
                    best_category_promo = promo

            if not best_global_promo and promo.aplica_a_todo:
                best_global_promo = promo

            if best_product_promo and best_category_promo and best_global_promo:
                break

        return best_product_promo or best_category_promo or best_global_promo

    # Fallback: DB queries (used when prefetched promos are not available).
    try:
        from marketing.models import Promocion
    except ImportError:
        return None

    now = timezone.now()
    base_qs = Promocion.objects.filter(
        es_activo=True,
        fecha_inicio__lte=now,
        fecha_fin__gte=now,
    ).order_by('-prioridad')

    promo = base_qs.filter(productos=product).first()
    if promo:
        return promo

    if product.category_id:
        promo = base_qs.filter(categorias=product.category_id).first()
        if promo:
            return promo

    return base_qs.filter(aplica_a_todo=True).first()


def effective_unit_price(product, variant, promo):
    """
    Return the discounted unit price to charge for one unit of
    ``(product, variant)`` under ``promo`` as a Decimal quantized to ``0.01``.

    Base price is ``variant.price`` when a variant is supplied, else
    ``product.base_price``. The promo is applied to that base:

    - PORCENTAJE  → ``max(base - base * valor / 100, 0)``
    - MONTO_FIJO  → ``max(base - valor, 0)``
    - COMPRA_X_LLEVA_Y / no promo → ``base`` (no per-unit reduction)

    The display path passes ``variant=None`` so product-page pricing is
    unchanged.
    """
    base = variant.price if variant is not None else product.base_price
    base = Decimal(base)

    if promo is None:
        return base.quantize(CENTS)

    from marketing.models import Promocion

    tipo = promo.tipo
    if tipo == Promocion.Tipo.PORCENTAJE:
        discount = (base * promo.valor_descuento / Decimal('100')).quantize(CENTS)
        price = max(base - discount, Decimal('0.00'))
    elif tipo == Promocion.Tipo.MONTO_FIJO:
        price = max(base - promo.valor_descuento, Decimal('0.00'))
    else:
        # COMPRA_X_LLEVA_Y doesn't reduce the per-unit price directly.
        price = base

    return price.quantize(CENTS)
