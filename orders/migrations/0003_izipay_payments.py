# Generated migration for Izipay payments integration (ADR §6)
# Adds payment fields to Order, creates Payment and IpnEvent models.
# RunPython backfills uuid for existing rows.

import uuid

import django.db.models.deletion
from django.db import migrations, models


def backfill_order_uuids(apps, schema_editor):
    """Assign a unique uuid4 to every existing Order row."""
    Order = apps.get_model('orders', 'Order')
    for order in Order.objects.filter(uuid__isnull=True):
        order.uuid = uuid.uuid4()
        order.save(update_fields=['uuid'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_alter_orderitem_options_order_order_user_created_idx_and_more'),
    ]

    operations = [
        # Step 1: Add uuid as non-unique, nullable first so we can backfill
        migrations.AddField(
            model_name='order',
            name='uuid',
            field=models.UUIDField(
                null=True,
                blank=True,
                editable=False,
            ),
        ),

        # Step 2: Backfill existing rows with uuid4 values
        migrations.RunPython(backfill_order_uuids, noop),

        # Step 3: Make uuid unique and non-nullable
        migrations.AlterField(
            model_name='order',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
            ),
        ),

        # Step 4: Add payment fields to Order
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.CharField(
                choices=[
                    ('unpaid', 'Sin pagar'),
                    ('paid', 'Pagado'),
                    ('refunded', 'Reembolsado'),
                ],
                db_index=True,
                default='unpaid',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='order',
            name='izipay_transaction_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='order',
            name='izipay_form_token_created_at',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # Step 5: Allow order_number to be blank (model.save() generates it)
        migrations.AlterField(
            model_name='order',
            name='order_number',
            field=models.CharField(blank=True, max_length=50, unique=True),
        ),

        # Step 6: Create Payment model
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('method', models.CharField(
                    choices=[
                        ('izipay', 'Izipay (tarjeta)'),
                        ('yape', 'Yape (vía Izipay)'),
                        ('transfer', 'Transferencia'),
                    ],
                    max_length=20,
                )),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(
                    choices=[
                        ('verified', 'Verificado'),
                        ('refunded', 'Reembolsado'),
                    ],
                    default='verified',
                    max_length=20,
                )),
                ('transaction_id', models.CharField(db_index=True, max_length=100)),
                ('raw_response', models.JSONField(default=dict)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payments',
                    to='orders.order',
                )),
            ],
            options={
                'verbose_name': 'Payment',
                'verbose_name_plural': 'Payments',
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(
                fields=['order', '-created'],
                name='payment_order_created_idx',
            ),
        ),

        # Step 7: Create IpnEvent model
        migrations.CreateModel(
            name='IpnEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('source_ip', models.CharField(max_length=45)),
                ('kr_hash_prefix', models.CharField(max_length=8)),
                ('order_number', models.CharField(db_index=True, max_length=50)),
                ('order_status', models.CharField(blank=True, max_length=20)),
                ('processed_outcome', models.CharField(
                    choices=[
                        ('paid', 'Paid'),
                        ('refunded', 'Refunded'),
                        ('cancelled', 'Cancelled'),
                        ('unpaid', 'Unpaid'),
                        ('duplicate', 'Duplicate'),
                        ('no_order', 'No Order'),
                        ('bad_amount', 'Bad Amount'),
                        ('bad_signature', 'Bad Signature'),
                        ('no_op', 'No Operation'),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ('raw_body', models.TextField()),
                ('error_detail', models.TextField(blank=True)),
            ],
            options={
                'verbose_name': 'IPN Event',
                'verbose_name_plural': 'IPN Events',
                'ordering': ['-created'],
            },
        ),
        migrations.AddIndex(
            model_name='ipnevent',
            index=models.Index(
                fields=['order_number', '-created'],
                name='ipnevent_order_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='ipnevent',
            index=models.Index(
                fields=['processed_outcome', '-created'],
                name='ipnevent_outcome_created_idx',
            ),
        ),
    ]
