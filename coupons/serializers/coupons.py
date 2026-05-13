from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from coupons.models import Coupon


class CouponSerializer(serializers.ModelSerializer):
    # Per-language translation fields
    description_es = serializers.CharField(allow_blank=True, required=False, default='')
    description_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    description_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Coupon
        fields = [
            'id',
            'code',
            'description',
            'description_es',
            'description_en',
            'description_pt',
            'discount_type',
            'discount_value',
            'min_purchase_amount',
            'max_discount_amount',
            'usage_limit',
            'times_used',
            'is_active',
            'valid_from',
            'valid_until',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'times_used', 'created', 'updated']

    def validate(self, attrs):
        valid_from = attrs.get('valid_from', getattr(self.instance, 'valid_from', None))
        valid_until = attrs.get('valid_until', getattr(self.instance, 'valid_until', None))

        if valid_from and valid_until and valid_from >= valid_until:
            raise serializers.ValidationError(
                {'valid_until': _('valid_until must be after valid_from.')}
            )

        discount_type = attrs.get(
            'discount_type',
            getattr(self.instance, 'discount_type', None),
        )
        discount_value = attrs.get(
            'discount_value',
            getattr(self.instance, 'discount_value', None),
        )

        if discount_type == Coupon.DiscountType.PERCENTAGE and discount_value is not None:
            if discount_value <= 0 or discount_value > 100:
                raise serializers.ValidationError(
                    {'discount_value': _('Percentage discount must be between 0 and 100.')}
                )

        if discount_value is not None and discount_value <= 0:
            raise serializers.ValidationError(
                {'discount_value': _('Discount value must be greater than zero.')}
            )

        return attrs


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    cart_subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)

    def validate_cart_subtotal(self, value):
        if value <= 0:
            raise serializers.ValidationError(_('Cart subtotal must be greater than zero.'))
        return value

    def validate(self, attrs):
        code = attrs['code'].strip().upper()
        cart_subtotal = attrs['cart_subtotal']
        now = timezone.now()

        try:
            coupon = Coupon.objects.get(code__iexact=code)
        except Coupon.DoesNotExist:
            raise serializers.ValidationError(
                {'code': _('Coupon not found.')}
            )

        if not coupon.is_active:
            raise serializers.ValidationError(
                {'code': _('This coupon is no longer active.')}
            )

        if now < coupon.valid_from:
            raise serializers.ValidationError(
                {'code': _('This coupon is not yet valid.')}
            )

        if now > coupon.valid_until:
            raise serializers.ValidationError(
                {'code': _('This coupon has expired.')}
            )

        if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
            raise serializers.ValidationError(
                {'code': _('This coupon has reached its usage limit.')}
            )

        if cart_subtotal < coupon.min_purchase_amount:
            raise serializers.ValidationError(
                {'cart_subtotal': _(
                    'Minimum purchase amount of %(amount)s is required for this coupon.'
                ) % {'amount': coupon.min_purchase_amount}}
            )

        # Calculate the discount amount
        if coupon.discount_type == Coupon.DiscountType.PERCENTAGE:
            discount_amount = (cart_subtotal * coupon.discount_value) / Decimal('100')
        else:
            discount_amount = coupon.discount_value

        # Cap discount at max_discount_amount if set
        if coupon.max_discount_amount is not None:
            discount_amount = min(discount_amount, coupon.max_discount_amount)

        # Discount cannot exceed cart subtotal
        discount_amount = min(discount_amount, cart_subtotal)

        attrs['coupon'] = coupon
        attrs['discount_amount'] = discount_amount.quantize(Decimal('0.01'))
        return attrs

    def to_representation(self, validated_data):
        coupon = validated_data['coupon']
        return {
            'coupon_id': coupon.id,
            'code': coupon.code,
            'description': coupon.description,
            'discount_type': coupon.discount_type,
            'discount_value': str(coupon.discount_value),
            'discount_amount': str(validated_data['discount_amount']),
        }
