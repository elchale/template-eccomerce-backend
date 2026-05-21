# Add Culqi payment fields alongside the existing Izipay fields.
#
# Culqi becomes the active gateway; the Izipay fields are retained for the
# dormant Izipay code path. Additive only — nothing is removed.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0005_emaillog'),
    ]

    operations = [
        # Culqi identifiers on Order — chr_… charge id (synchronous card/Yape)
        # and ord_… order id (alternative payment methods).
        migrations.AddField(
            model_name='order',
            name='culqi_charge_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='culqi_order_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        # Gateway-agnostic audit ledger — record which gateway each IPN /
        # webhook event came from. Existing rows are all Izipay (default).
        migrations.AddField(
            model_name='ipnevent',
            name='gateway',
            field=models.CharField(
                choices=[('culqi', 'Culqi'), ('izipay', 'Izipay')],
                db_index=True,
                default='izipay',
                max_length=20,
            ),
        ),
        # Add 'culqi' to the Payment method choices (choices-only — no schema
        # change, but keep the migration state in sync with the model).
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.CharField(
                choices=[
                    ('culqi', 'Culqi (tarjeta/Yape)'),
                    ('izipay', 'Izipay (tarjeta)'),
                    ('yape', 'Yape'),
                    ('transfer', 'Transferencia'),
                ],
                max_length=20,
            ),
        ),
    ]
