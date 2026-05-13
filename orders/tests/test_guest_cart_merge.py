"""Tests for guest cart merge on login."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='mergeuser', email='merge@test.com', password='pass')


@pytest.fixture
def product(db):
    from products.models import Category, Product
    cat = Category.objects.create(name='Test', slug='test-cat')
    return Product.objects.create(
        name='Test Product',
        slug='test-product',
        sku='TEST001',
        base_price='50.00',
        category=cat,
    )


@pytest.fixture
def product2(db):
    from products.models import Category, Product
    cat = Category.objects.get_or_create(name='Test', slug='test-cat')[0]
    return Product.objects.create(
        name='Test Product 2',
        slug='test-product-2',
        sku='TEST002',
        base_price='30.00',
        category=cat,
    )


@pytest.mark.django_db
class TestCartMerge:
    def test_merge_guest_cart_into_user_cart(self, user, product):
        from orders.models import Cart, CartItem
        from orders.services.cart_merge import merge_session_cart_into_user_cart

        # Create a guest cart
        guest_cart = Cart.objects.create(session_key='test_session_123')
        CartItem.objects.create(cart=guest_cart, product=product, quantity=2)

        # Merge
        merge_session_cart_into_user_cart('test_session_123', user)

        # User should now have a cart with the items
        user_cart = Cart.objects.get(user=user)
        assert user_cart.items.count() == 1
        item = user_cart.items.first()
        assert item.product == product
        assert item.quantity == 2

        # Guest cart should be deleted
        assert not Cart.objects.filter(session_key='test_session_123').exists()

    def test_merge_sums_duplicate_items(self, user, product):
        from orders.models import Cart, CartItem
        from orders.services.cart_merge import merge_session_cart_into_user_cart

        # Create user cart with item
        user_cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=user_cart, product=product, quantity=1)

        # Guest cart also has the same item
        guest_cart = Cart.objects.create(session_key='sess_dupl')
        CartItem.objects.create(cart=guest_cart, product=product, quantity=3)

        merge_session_cart_into_user_cart('sess_dupl', user)

        user_cart.refresh_from_db()
        item = user_cart.items.filter(product=product).first()
        assert item.quantity == 4  # 1 + 3

    def test_merge_no_guest_cart_is_noop(self, user):
        from orders.services.cart_merge import merge_session_cart_into_user_cart
        from orders.models import Cart
        merge_session_cart_into_user_cart('nonexistent_session', user)
        assert not Cart.objects.filter(user=user).exists()

    def test_merge_empty_session_key_is_noop(self, user):
        from orders.services.cart_merge import merge_session_cart_into_user_cart
        from orders.models import Cart
        merge_session_cart_into_user_cart('', user)
        assert not Cart.objects.filter(user=user).exists()

    def test_merge_multiple_products(self, user, product, product2):
        from orders.models import Cart, CartItem
        from orders.services.cart_merge import merge_session_cart_into_user_cart

        guest_cart = Cart.objects.create(session_key='sess_multi')
        CartItem.objects.create(cart=guest_cart, product=product, quantity=1)
        CartItem.objects.create(cart=guest_cart, product=product2, quantity=2)

        merge_session_cart_into_user_cart('sess_multi', user)

        user_cart = Cart.objects.get(user=user)
        assert user_cart.items.count() == 2
