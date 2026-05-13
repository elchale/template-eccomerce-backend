import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from products.models import (
    Category,
    Product,
    ProductImage,
    VariantType,
    VariantOption,
    ProductVariant,
    Review,
)
from coupons.models import Coupon

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with premium e-commerce data for a Shopify-style marketplace'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush',
            action='store_true',
            help='Delete existing seed data before creating new data',
        )

    def handle(self, *args, **options):
        if options['flush']:
            self.stdout.write('Flushing existing data...')
            Review.objects.all().delete()
            ProductVariant.objects.all().delete()
            ProductImage.objects.all().delete()
            Product.objects.all().delete()
            VariantOption.objects.all().delete()
            VariantType.objects.all().delete()
            Category.objects.all().delete()
            Coupon.objects.all().delete()
            self.stdout.write(self.style.WARNING('Flushed all product/category/coupon data'))

        self.stdout.write('Seeding premium e-commerce data...')

        # ─── Categories ───────────────────────────────────────────
        electronics = Category.objects.create(
            name='Electronics', slug='electronics',
            description='The latest tech, gadgets, and devices to power your digital life.',
            image_url='https://images.unsplash.com/photo-1498049794561-7780e7231661?w=800&q=80',
            sort_order=1,
        )
        phones = Category.objects.create(
            name='Phones & Tablets', slug='phones-tablets',
            description='Smartphones, tablets, and mobile accessories.',
            image_url='https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=800&q=80',
            parent=electronics, sort_order=1,
        )
        laptops = Category.objects.create(
            name='Laptops & Computers', slug='laptops-computers',
            description='Laptops, desktops, and computer peripherals.',
            image_url='https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=800&q=80',
            parent=electronics, sort_order=2,
        )
        audio = Category.objects.create(
            name='Audio', slug='audio',
            description='Headphones, speakers, and audio equipment.',
            image_url='https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&q=80',
            parent=electronics, sort_order=3,
        )

        clothing = Category.objects.create(
            name='Clothing', slug='clothing',
            description='Fashion-forward apparel for every occasion.',
            image_url='https://images.unsplash.com/photo-1445205170230-053b83016050?w=800&q=80',
            sort_order=2,
        )
        men = Category.objects.create(
            name="Men's", slug='mens',
            description="Men's clothing, shoes, and accessories.",
            image_url='https://images.unsplash.com/photo-1617137968427-85924c800a22?w=800&q=80',
            parent=clothing, sort_order=1,
        )
        women = Category.objects.create(
            name="Women's", slug='womens',
            description="Women's clothing, shoes, and accessories.",
            image_url='https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&q=80',
            parent=clothing, sort_order=2,
        )

        home_living = Category.objects.create(
            name='Home & Living', slug='home-living',
            description='Furniture, decor, and everything to make your house a home.',
            image_url='https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=800&q=80',
            sort_order=3,
        )
        kitchen = Category.objects.create(
            name='Kitchen', slug='kitchen',
            description='Cookware, appliances, and kitchen essentials.',
            image_url='https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=800&q=80',
            parent=home_living, sort_order=1,
        )

        sports = Category.objects.create(
            name='Sports & Outdoors', slug='sports-outdoors',
            description='Gear up for every adventure, indoors and out.',
            image_url='https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=800&q=80',
            sort_order=4,
        )

        beauty = Category.objects.create(
            name='Beauty & Personal Care', slug='beauty',
            description='Skincare, cosmetics, and personal wellness.',
            image_url='https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=800&q=80',
            sort_order=5,
        )

        self.stdout.write(self.style.SUCCESS(f'  Created {Category.objects.count()} categories'))

        # ─── Variant Types ────────────────────────────────────────
        size_type = VariantType.objects.create(name='Size')
        color_type = VariantType.objects.create(name='Color')
        storage_type = VariantType.objects.create(name='Storage')
        material_type = VariantType.objects.create(name='Material')

        sizes = {}
        for s in ['XS', 'S', 'M', 'L', 'XL', 'XXL']:
            sizes[s] = VariantOption.objects.create(variant_type=size_type, value=s)

        colors = {}
        for c in ['Black', 'White', 'Navy', 'Charcoal', 'Sand', 'Olive', 'Burgundy', 'Midnight Blue', 'Stone', 'Forest Green']:
            colors[c] = VariantOption.objects.create(variant_type=color_type, value=c)

        storages = {}
        for st in ['64GB', '128GB', '256GB', '512GB', '1TB']:
            storages[st] = VariantOption.objects.create(variant_type=storage_type, value=st)

        materials = {}
        for m in ['Cotton', 'Linen', 'Wool', 'Leather']:
            materials[m] = VariantOption.objects.create(variant_type=material_type, value=m)

        # ─── Products ─────────────────────────────────────────────
        products_data = [
            # ── Electronics / Phones ──
            {
                'name': 'iPhone 15 Pro Max',
                'slug': 'iphone-15-pro-max',
                'description': 'The most powerful iPhone ever. Featuring the A17 Pro chip, a 48MP camera system with 5x optical zoom, titanium design, and all-day battery life. The Super Retina XDR display with ProMotion delivers an incredibly smooth visual experience.',
                'category': phones,
                'base_price': '1199.00',
                'compare_at_price': '1299.00',
                'sku': 'IPHONE-15PM',
                'stock': 85,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=800&q=80', 'iPhone 15 Pro Max front view'),
                    ('https://images.unsplash.com/photo-1592899677977-9c10ca588bbd?w=800&q=80', 'iPhone side angle'),
                    ('https://images.unsplash.com/photo-1591337676887-a217a6c6bff3?w=800&q=80', 'iPhone camera detail'),
                ],
                'variants': [
                    {'sku': 'IPHONE-15PM-256-BLK', 'price': '1199.00', 'stock': 30, 'options': [storages['256GB'], colors['Black']]},
                    {'sku': 'IPHONE-15PM-256-WHT', 'price': '1199.00', 'stock': 25, 'options': [storages['256GB'], colors['White']]},
                    {'sku': 'IPHONE-15PM-512-BLK', 'price': '1399.00', 'stock': 15, 'options': [storages['512GB'], colors['Black']]},
                    {'sku': 'IPHONE-15PM-1TB-BLK', 'price': '1599.00', 'stock': 10, 'options': [storages['1TB'], colors['Black']]},
                ],
            },
            {
                'name': 'Samsung Galaxy S24 Ultra',
                'slug': 'samsung-galaxy-s24-ultra',
                'description': 'Galaxy AI is here. The Samsung Galaxy S24 Ultra features a built-in S Pen, a stunning 6.8" QHD+ display, and a 200MP camera. Titanium frame with Gorilla Armor for ultimate durability.',
                'category': phones,
                'base_price': '1099.00',
                'compare_at_price': None,
                'sku': 'GALAXY-S24U',
                'stock': 60,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1610945415295-d9bbf067e59c?w=800&q=80', 'Samsung Galaxy S24 Ultra'),
                    ('https://images.unsplash.com/photo-1585060544812-6b45742d762f?w=800&q=80', 'Samsung Galaxy back view'),
                ],
                'variants': [
                    {'sku': 'S24U-256-BLK', 'price': '1099.00', 'stock': 20, 'options': [storages['256GB'], colors['Black']]},
                    {'sku': 'S24U-512-BLK', 'price': '1299.00', 'stock': 15, 'options': [storages['512GB'], colors['Black']]},
                    {'sku': 'S24U-256-SAND', 'price': '1099.00', 'stock': 15, 'options': [storages['256GB'], colors['Sand']]},
                ],
            },

            # ── Electronics / Laptops ──
            {
                'name': 'MacBook Pro 16" M3 Max',
                'slug': 'macbook-pro-16-m3-max',
                'description': 'The most advanced Mac laptop for demanding workflows. The M3 Max chip delivers extraordinary performance for video editing, 3D rendering, and software development. Up to 22 hours of battery life with a stunning Liquid Retina XDR display.',
                'category': laptops,
                'base_price': '2499.00',
                'compare_at_price': None,
                'sku': 'MBP-16-M3MAX',
                'stock': 25,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=800&q=80', 'MacBook Pro 16 open'),
                    ('https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=800&q=80', 'MacBook Pro closed angle'),
                    ('https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=800&q=80', 'MacBook Pro workspace'),
                ],
                'variants': [
                    {'sku': 'MBP-16-512', 'price': '2499.00', 'stock': 10, 'options': [storages['512GB']]},
                    {'sku': 'MBP-16-1TB', 'price': '2899.00', 'stock': 10, 'options': [storages['1TB']]},
                ],
            },

            # ── Electronics / Audio ──
            {
                'name': 'Sony WH-1000XM5 Headphones',
                'slug': 'sony-wh-1000xm5',
                'description': 'Industry-leading noise cancellation meets premium sound. The WH-1000XM5 features Auto NC Optimizer, Speak-to-Chat, and up to 30 hours of battery life. Ultra-comfortable design with soft-fit leather ear pads.',
                'category': audio,
                'base_price': '349.99',
                'compare_at_price': '399.99',
                'sku': 'SONY-XM5',
                'stock': 120,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&q=80', 'Sony headphones product shot'),
                    ('https://images.unsplash.com/photo-1583394838336-acd977736f90?w=800&q=80', 'Headphones on stand'),
                ],
                'variants': [
                    {'sku': 'XM5-BLK', 'price': '349.99', 'stock': 50, 'options': [colors['Black']]},
                    {'sku': 'XM5-WHT', 'price': '349.99', 'stock': 40, 'options': [colors['White']]},
                    {'sku': 'XM5-MBL', 'price': '349.99', 'stock': 30, 'options': [colors['Midnight Blue']]},
                ],
            },
            {
                'name': 'AirPods Pro (2nd Gen)',
                'slug': 'airpods-pro-2',
                'description': 'Rebuilt from the sound up. AirPods Pro feature Active Noise Cancellation, Adaptive Transparency, and Personalized Spatial Audio. The H2 chip delivers smarter noise cancellation and immersive sound. Up to 6 hours of listening time.',
                'category': audio,
                'base_price': '249.00',
                'compare_at_price': None,
                'sku': 'AIRPODS-PRO2',
                'stock': 200,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1606220945770-b5b6c2c55bf1?w=800&q=80', 'AirPods Pro in case'),
                    ('https://images.unsplash.com/photo-1588423771073-b8903fde1c68?w=800&q=80', 'AirPods Pro detail'),
                ],
                'variants': [],
            },

            # ── Electronics / Watches ──
            {
                'name': 'Apple Watch Ultra 2',
                'slug': 'apple-watch-ultra-2',
                'description': 'The most rugged and capable Apple Watch ever. Built for exploration with precision dual-frequency GPS, up to 36 hours of battery life, and a 49mm titanium case. Water resistant to 100m with depth gauge and water temperature sensor.',
                'category': electronics,
                'base_price': '799.00',
                'compare_at_price': '849.00',
                'sku': 'WATCH-ULTRA2',
                'stock': 45,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1546868871-af0de0ae72be?w=800&q=80', 'Apple Watch Ultra on wrist'),
                    ('https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=800&q=80', 'Smart watch product shot'),
                ],
                'variants': [],
            },

            # ── Men's Clothing ──
            {
                'name': 'Merino Wool Crew Neck Sweater',
                'slug': 'merino-wool-crew-neck',
                'description': 'Luxuriously soft 100% extra-fine merino wool sweater. Naturally temperature-regulating and breathable. Features ribbed cuffs and hem for a clean, tailored look. Machine washable on gentle cycle.',
                'category': men,
                'base_price': '98.00',
                'compare_at_price': '128.00',
                'sku': 'MERINO-CREW',
                'stock': 180,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1614975059251-992f11792571?w=800&q=80', 'Merino wool sweater navy'),
                    ('https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=800&q=80', 'Sweater detail texture'),
                ],
                'variants': [
                    {'sku': 'MERINO-S-NVY', 'price': '98.00', 'stock': 25, 'options': [sizes['S'], colors['Navy']]},
                    {'sku': 'MERINO-M-NVY', 'price': '98.00', 'stock': 35, 'options': [sizes['M'], colors['Navy']]},
                    {'sku': 'MERINO-L-NVY', 'price': '98.00', 'stock': 30, 'options': [sizes['L'], colors['Navy']]},
                    {'sku': 'MERINO-M-CHR', 'price': '98.00', 'stock': 30, 'options': [sizes['M'], colors['Charcoal']]},
                    {'sku': 'MERINO-L-CHR', 'price': '98.00', 'stock': 25, 'options': [sizes['L'], colors['Charcoal']]},
                    {'sku': 'MERINO-M-OLV', 'price': '98.00', 'stock': 20, 'options': [sizes['M'], colors['Olive']]},
                ],
            },
            {
                'name': 'Classic Fit Oxford Shirt',
                'slug': 'classic-fit-oxford-shirt',
                'description': 'The perfect everyday shirt. Made from premium long-staple cotton with a soft, textured Oxford weave. Button-down collar, back box pleat, and a slightly relaxed fit for effortless style.',
                'category': men,
                'base_price': '68.00',
                'compare_at_price': None,
                'sku': 'OXFORD-SHIRT',
                'stock': 250,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=800&q=80', 'Oxford shirt white'),
                    ('https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=800&q=80', 'Oxford shirt folded'),
                ],
                'variants': [
                    {'sku': 'OXFORD-S-WHT', 'price': '68.00', 'stock': 40, 'options': [sizes['S'], colors['White']]},
                    {'sku': 'OXFORD-M-WHT', 'price': '68.00', 'stock': 50, 'options': [sizes['M'], colors['White']]},
                    {'sku': 'OXFORD-L-WHT', 'price': '68.00', 'stock': 45, 'options': [sizes['L'], colors['White']]},
                    {'sku': 'OXFORD-M-NVY', 'price': '68.00', 'stock': 40, 'options': [sizes['M'], colors['Navy']]},
                    {'sku': 'OXFORD-L-NVY', 'price': '68.00', 'stock': 35, 'options': [sizes['L'], colors['Navy']]},
                ],
            },
            {
                'name': 'Leather Chelsea Boots',
                'slug': 'leather-chelsea-boots',
                'description': 'Handcrafted Italian leather Chelsea boots with Goodyear welt construction. Pull-on style with elastic side panels and a leather-lined interior. Dainite rubber sole for all-weather traction. Will age beautifully over time.',
                'category': men,
                'base_price': '285.00',
                'compare_at_price': '350.00',
                'sku': 'CHELSEA-BOOT',
                'stock': 60,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1638247025967-b4e38f787b76?w=800&q=80', 'Chelsea boots pair'),
                    ('https://images.unsplash.com/photo-1608256246200-53e635b5b65f?w=800&q=80', 'Chelsea boots side view'),
                ],
                'variants': [
                    {'sku': 'CHELSEA-BLK-M', 'price': '285.00', 'stock': 20, 'options': [colors['Black']]},
                    {'sku': 'CHELSEA-BRG-M', 'price': '285.00', 'stock': 20, 'options': [colors['Burgundy']]},
                    {'sku': 'CHELSEA-SND-M', 'price': '285.00', 'stock': 15, 'options': [colors['Sand']]},
                ],
            },

            # ── Women's Clothing ──
            {
                'name': 'Cashmere Blend Wrap Coat',
                'slug': 'cashmere-blend-wrap-coat',
                'description': 'Elegant wrap coat crafted from a luxurious cashmere-wool blend. Features a wide lapel collar, self-tie belt, and side pockets. Fully lined in silk for a smooth, comfortable fit. A timeless investment piece.',
                'category': women,
                'base_price': '395.00',
                'compare_at_price': '495.00',
                'sku': 'WRAP-COAT',
                'stock': 40,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1539533018447-63fcce2678e3?w=800&q=80', 'Cashmere wrap coat'),
                    ('https://images.unsplash.com/photo-1548624313-0396c75e4b1a?w=800&q=80', 'Wrap coat detail'),
                ],
                'variants': [
                    {'sku': 'COAT-S-STN', 'price': '395.00', 'stock': 10, 'options': [sizes['S'], colors['Stone']]},
                    {'sku': 'COAT-M-STN', 'price': '395.00', 'stock': 12, 'options': [sizes['M'], colors['Stone']]},
                    {'sku': 'COAT-L-BLK', 'price': '395.00', 'stock': 10, 'options': [sizes['L'], colors['Black']]},
                    {'sku': 'COAT-M-BLK', 'price': '395.00', 'stock': 8, 'options': [sizes['M'], colors['Black']]},
                ],
            },
            {
                'name': 'Silk Midi Slip Dress',
                'slug': 'silk-midi-slip-dress',
                'description': 'Effortlessly elegant. This bias-cut midi dress is crafted from 100% mulberry silk with a subtle sheen. Adjustable spaghetti straps, cowl neckline, and a delicate lace trim at the hem. Perfect layered or worn alone.',
                'category': women,
                'base_price': '175.00',
                'compare_at_price': '220.00',
                'sku': 'SILK-SLIP',
                'stock': 75,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=800&q=80', 'Silk slip dress'),
                    ('https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=800&q=80', 'Dress detail'),
                ],
                'variants': [
                    {'sku': 'SLIP-XS-BLK', 'price': '175.00', 'stock': 12, 'options': [sizes['XS'], colors['Black']]},
                    {'sku': 'SLIP-S-BLK', 'price': '175.00', 'stock': 18, 'options': [sizes['S'], colors['Black']]},
                    {'sku': 'SLIP-M-BLK', 'price': '175.00', 'stock': 20, 'options': [sizes['M'], colors['Black']]},
                    {'sku': 'SLIP-S-SND', 'price': '175.00', 'stock': 15, 'options': [sizes['S'], colors['Sand']]},
                ],
            },

            # ── Home & Living ──
            {
                'name': 'Handwoven Linen Throw Blanket',
                'slug': 'handwoven-linen-throw',
                'description': 'Artisan-crafted throw blanket made from 100% European flax linen. Pre-washed for a beautifully soft, lived-in texture. Finished with hand-twisted fringe. Gets softer with every wash. 140cm x 200cm.',
                'category': home_living,
                'base_price': '129.00',
                'compare_at_price': None,
                'sku': 'LINEN-THROW',
                'stock': 95,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=800&q=80', 'Linen throw on sofa'),
                    ('https://images.unsplash.com/photo-1616627561950-9f746e330187?w=800&q=80', 'Throw blanket texture'),
                ],
                'variants': [
                    {'sku': 'THROW-STN', 'price': '129.00', 'stock': 30, 'options': [colors['Stone']]},
                    {'sku': 'THROW-CHR', 'price': '129.00', 'stock': 25, 'options': [colors['Charcoal']]},
                    {'sku': 'THROW-OLV', 'price': '129.00', 'stock': 20, 'options': [colors['Olive']]},
                    {'sku': 'THROW-WHT', 'price': '129.00', 'stock': 20, 'options': [colors['White']]},
                ],
            },
            {
                'name': 'Ceramic Pour-Over Coffee Set',
                'slug': 'ceramic-pour-over-coffee-set',
                'description': 'Elevate your morning ritual. This handmade ceramic pour-over set includes a dripper, carafe (600ml), and two matching cups. Matte glaze finish with a clean, minimalist silhouette. Dishwasher safe.',
                'category': kitchen,
                'base_price': '84.00',
                'compare_at_price': '99.00',
                'sku': 'COFFEE-SET',
                'stock': 70,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&q=80', 'Pour-over coffee set'),
                    ('https://images.unsplash.com/photo-1514432324607-a09d9b4aefda?w=800&q=80', 'Coffee set detail'),
                ],
                'variants': [
                    {'sku': 'COFFEE-WHT', 'price': '84.00', 'stock': 30, 'options': [colors['White']]},
                    {'sku': 'COFFEE-BLK', 'price': '84.00', 'stock': 25, 'options': [colors['Black']]},
                    {'sku': 'COFFEE-STN', 'price': '84.00', 'stock': 15, 'options': [colors['Stone']]},
                ],
            },

            # ── Sports & Outdoors ──
            {
                'name': 'Premium Yoga Mat Pro',
                'slug': 'premium-yoga-mat-pro',
                'description': 'Studio-grade 6mm yoga mat with a natural rubber base and microfiber suede top. The more you sweat, the better the grip. Alignment markers for proper form. Includes cotton carrying strap. 183cm x 68cm.',
                'category': sports,
                'base_price': '89.00',
                'compare_at_price': None,
                'sku': 'YOGA-MAT-PRO',
                'stock': 130,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1601925260368-ae2f83cf8b7f?w=800&q=80', 'Yoga mat rolled'),
                    ('https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80', 'Yoga mat in use'),
                ],
                'variants': [
                    {'sku': 'YOGA-BLK', 'price': '89.00', 'stock': 40, 'options': [colors['Black']]},
                    {'sku': 'YOGA-OLV', 'price': '89.00', 'stock': 35, 'options': [colors['Olive']]},
                    {'sku': 'YOGA-SND', 'price': '89.00', 'stock': 30, 'options': [colors['Sand']]},
                    {'sku': 'YOGA-MBL', 'price': '89.00', 'stock': 25, 'options': [colors['Midnight Blue']]},
                ],
            },
            {
                'name': 'Trail Running Shoes',
                'slug': 'trail-running-shoes',
                'description': 'Built for the trail. Vibram Megagrip outsole, responsive Floatride Energy foam midsole, and a protective rock plate. Breathable mesh upper with reinforced toe cap. Reflective details for low-light visibility.',
                'category': sports,
                'base_price': '159.00',
                'compare_at_price': '189.00',
                'sku': 'TRAIL-SHOE',
                'stock': 90,
                'is_featured': True,
                'images': [
                    ('https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=800&q=80', 'Trail running shoe side'),
                    ('https://images.unsplash.com/photo-1606107557195-0e29a4b5b4aa?w=800&q=80', 'Running shoes pair'),
                ],
                'variants': [
                    {'sku': 'TRAIL-BLK', 'price': '159.00', 'stock': 30, 'options': [colors['Black']]},
                    {'sku': 'TRAIL-FGR', 'price': '159.00', 'stock': 30, 'options': [colors['Forest Green']]},
                    {'sku': 'TRAIL-NVY', 'price': '159.00', 'stock': 30, 'options': [colors['Navy']]},
                ],
            },

            # ── Beauty ──
            {
                'name': 'Botanical Face Serum',
                'slug': 'botanical-face-serum',
                'description': 'A potent blend of plant-derived actives for radiant, healthy skin. Contains hyaluronic acid, vitamin C, niacinamide, and bakuchiol. Lightweight, fast-absorbing formula suitable for all skin types. 30ml glass dropper bottle.',
                'category': beauty,
                'base_price': '62.00',
                'compare_at_price': '78.00',
                'sku': 'FACE-SERUM',
                'stock': 150,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1620916566398-39f1143ab7be?w=800&q=80', 'Face serum bottle'),
                    ('https://images.unsplash.com/photo-1608248597279-f99d160bfcbc?w=800&q=80', 'Serum dropper close-up'),
                ],
                'variants': [],
            },

            # ── Extra Electronics ──
            {
                'name': 'Minimalist Desk Lamp',
                'slug': 'minimalist-desk-lamp',
                'description': 'Sleek LED desk lamp with wireless charging base. 5 color temperatures, 7 brightness levels, and a built-in 30/60-minute timer. Adjustable arm with 180-degree rotation. USB-C port for device charging.',
                'category': home_living,
                'base_price': '79.00',
                'compare_at_price': None,
                'sku': 'DESK-LAMP',
                'stock': 110,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1507473885765-e6ed057ab6fe?w=800&q=80', 'Desk lamp on table'),
                    ('https://images.unsplash.com/photo-1513506003901-1e6a229e2d15?w=800&q=80', 'Desk lamp workspace'),
                ],
                'variants': [
                    {'sku': 'LAMP-BLK', 'price': '79.00', 'stock': 40, 'options': [colors['Black']]},
                    {'sku': 'LAMP-WHT', 'price': '79.00', 'stock': 40, 'options': [colors['White']]},
                    {'sku': 'LAMP-SND', 'price': '79.00', 'stock': 30, 'options': [colors['Sand']]},
                ],
            },
            {
                'name': 'Canvas Weekender Bag',
                'slug': 'canvas-weekender-bag',
                'description': 'The perfect bag for short trips. Waxed canvas body with full-grain leather handles and trim. Brass hardware, padded laptop sleeve (fits 15"), and a separate shoe compartment. Water-resistant and built to last.',
                'category': men,
                'base_price': '195.00',
                'compare_at_price': '245.00',
                'sku': 'WEEKENDER',
                'stock': 55,
                'is_featured': False,
                'images': [
                    ('https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=800&q=80', 'Canvas weekender bag'),
                    ('https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=800&q=80', 'Bag detail leather'),
                ],
                'variants': [
                    {'sku': 'BAG-OLV', 'price': '195.00', 'stock': 20, 'options': [colors['Olive']]},
                    {'sku': 'BAG-CHR', 'price': '195.00', 'stock': 20, 'options': [colors['Charcoal']]},
                    {'sku': 'BAG-SND', 'price': '195.00', 'stock': 15, 'options': [colors['Sand']]},
                ],
            },
        ]

        created_products = []
        for pdata in products_data:
            images = pdata.pop('images')
            variants = pdata.pop('variants')
            product = Product.objects.create(**pdata)
            created_products.append(product)

            for i, img_data in enumerate(images):
                img_url, alt = img_data
                ProductImage.objects.create(
                    product=product,
                    image_url=img_url,
                    alt_text=alt,
                    sort_order=i,
                    is_primary=(i == 0),
                )

            for vdata in variants:
                options = vdata.pop('options')
                variant = ProductVariant.objects.create(product=product, **vdata)
                variant.options.set(options)

        self.stdout.write(self.style.SUCCESS(f'  Created {Product.objects.count()} products'))

        # ─── Reviews ──────────────────────────────────────────────
        test_users = list(User.objects.all()[:5])
        if len(test_users) < 3:
            for i in range(3 - len(test_users)):
                u = User.objects.create_user(
                    username=f'shopper{i+1}',
                    email=f'shopper{i+1}@example.com',
                    password='testpass123',
                    first_name=['Alex', 'Jordan', 'Morgan'][i],
                    last_name=['Chen', 'Rivera', 'Kim'][i],
                )
                test_users.append(u)

        review_pool = [
            ('Absolutely love it', "This exceeded all my expectations. The quality is outstanding and it looks even better in person. Would purchase again without hesitation.", 5),
            ('Excellent quality', "Arrived quickly and well-packaged. The materials feel premium and the construction is solid. Very happy with this purchase.", 5),
            ('Great everyday piece', "Perfect for daily use. Comfortable, well-made, and exactly as described. The value for the price is excellent.", 4),
            ('Solid purchase', "Good quality overall. Minor details could be improved but I'm satisfied. Would recommend to friends.", 4),
            ('Beautiful design', "The design is even more stunning in person. Clearly a lot of thought went into every detail. Feels like a premium product.", 5),
            ('Worth the investment', "Was hesitant about the price but this is genuinely worth it. The quality speaks for itself.", 4),
            ('Impressive', "Sleek, functional, and well-built. Exactly what I was looking for. Fast shipping too.", 5),
            ('Good but not perfect', "Really nice product overall. One small issue with sizing but customer service helped resolve it quickly.", 3),
        ]

        for product in created_products:
            num_reviews = random.randint(1, min(4, len(test_users)))
            selected_users = random.sample(test_users, num_reviews)
            for user in selected_users:
                title, comment, rating = random.choice(review_pool)
                try:
                    Review.objects.create(
                        user=user,
                        product=product,
                        rating=rating,
                        title=title,
                        comment=comment,
                        is_verified_purchase=random.choice([True, True, True, False]),
                    )
                except Exception:
                    pass  # Skip if duplicate user/product combo

            # Update product rating
            reviews = product.reviews.all()
            if reviews.exists():
                from django.db.models import Avg, Count
                stats = reviews.aggregate(avg=Avg('rating'), cnt=Count('id'))
                product.average_rating = round(Decimal(str(stats['avg'])), 2)
                product.review_count = stats['cnt']
                product.save()

        self.stdout.write(self.style.SUCCESS(f'  Created {Review.objects.count()} reviews'))

        # ─── Coupons ──────────────────────────────────────────────
        now = timezone.now()
        coupons = [
            {
                'code': 'WELCOME15',
                'description': '15% off your first order',
                'discount_type': 'percentage',
                'discount_value': 15,
                'min_purchase_amount': 50,
                'max_discount_amount': 150,
                'usage_limit': 500,
                'is_active': True,
                'valid_from': now,
                'valid_until': now + timezone.timedelta(days=180),
            },
            {
                'code': 'SAVE30',
                'description': '$30 off orders over $150',
                'discount_type': 'fixed',
                'discount_value': 30,
                'min_purchase_amount': 150,
                'is_active': True,
                'valid_from': now,
                'valid_until': now + timezone.timedelta(days=60),
            },
            {
                'code': 'FLASH20',
                'description': '20% off everything — limited time',
                'discount_type': 'percentage',
                'discount_value': 20,
                'min_purchase_amount': 0,
                'max_discount_amount': 200,
                'usage_limit': 100,
                'is_active': True,
                'valid_from': now,
                'valid_until': now + timezone.timedelta(days=7),
            },
            {
                'code': 'FREESHIP',
                'description': 'Free shipping on orders over $75',
                'discount_type': 'fixed',
                'discount_value': 10,
                'min_purchase_amount': 75,
                'is_active': True,
                'valid_from': now,
                'valid_until': now + timezone.timedelta(days=90),
            },
        ]
        for c in coupons:
            Coupon.objects.create(**c)

        self.stdout.write(self.style.SUCCESS(f'  Created {Coupon.objects.count()} coupons'))
        self.stdout.write(self.style.SUCCESS('\nSeed complete! Your marketplace is ready.'))
        self.stdout.write(f'  Categories: {Category.objects.count()}')
        self.stdout.write(f'  Products:   {Product.objects.count()}')
        self.stdout.write(f'  Variants:   {ProductVariant.objects.count()}')
        self.stdout.write(f'  Images:     {ProductImage.objects.count()}')
        self.stdout.write(f'  Reviews:    {Review.objects.count()}')
        self.stdout.write(f'  Coupons:    {Coupon.objects.count()}')
