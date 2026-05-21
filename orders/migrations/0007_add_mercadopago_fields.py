# Add Mercado Pago payment fields alongside the existing Culqi + Izipay fields.
#
# Mercado Pago becomes the active gateway; the Culqi and Izipay fields are
# retained for the dormant gateway paths. Additive only — nothing is removed.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_add_culqi_fields'),
    ]

    operations = [
        # MP payment id (numeric string) on Order — the canonical handle for
        # refunds and for webhook ↔ order correlation.
        migrations.AddField(
            model_name='order',
            name='mp_payment_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=100),
        ),
        # Add 'mercadopago' to the IpnEvent gateway choices (choices-only — no
        # schema change, but keep the migration state in sync with the model).
        migrations.AlterField(
            model_name='ipnevent',
            name='gateway',
            field=models.CharField(
                choices=[
                    ('mercadopago', 'Mercado Pago'),
                    ('culqi', 'Culqi'),
                    ('izipay', 'Izipay'),
                ],
                db_index=True,
                default='izipay',
                max_length=20,
            ),
        ),
        # Add 'mercadopago' to the Payment method choices (choices-only — no
        # schema change, but keep the migration state in sync with the model).
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.CharField(
                choices=[
                    ('mercadopago', 'Mercado Pago'),
                    ('culqi', 'Culqi (tarjeta/Yape)'),
                    ('izipay', 'Izipay (tarjeta)'),
                    ('yape', 'Yape'),
                    ('transfer', 'Transferencia'),
                ],
                max_length=20,
            ),
        ),
    ]
