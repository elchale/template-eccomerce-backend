"""Tests for review moderation (is_approved flag)."""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='reviewer', email='reviewer@test.com', password='pass')


@pytest.fixture
def admin(db):
    return User.objects.create_superuser(username='admin_rev', email='admin_rev@test.com', password='pass')


@pytest.fixture
def product(db):
    from products.models import Category, Product
    cat = Category.objects.create(name='ModTest', slug='modtest-cat')
    return Product.objects.create(
        name='Review Product',
        slug='review-product',
        sku='REV001',
        base_price='10.00',
        category=cat,
    )


@pytest.fixture
def review(user, product):
    from products.models import Review
    return Review.objects.create(
        user=user,
        product=product,
        rating=4,
        comment='Great product!',
        is_approved=False,
    )


@pytest.fixture
def approved_user(db):
    return User.objects.create_user(username='approved_reviewer', email='approved@test.com', password='pass')


@pytest.fixture
def approved_review(approved_user, product):
    from products.models import Review
    return Review.objects.create(
        user=approved_user,
        product=product,
        rating=5,
        comment='Excellent!',
        is_approved=True,
    )


@pytest.mark.django_db
class TestReviewModeration:
    def test_public_list_only_shows_approved(self, client, review, approved_review, product):
        resp = client.get(f'/api/reviews/?product={product.pk}')
        assert resp.status_code == 200
        ids = [r['id'] for r in resp.data.get('results', resp.data)]
        assert approved_review.pk in ids
        assert review.pk not in ids

    def test_new_review_is_not_approved_by_default(self, db):
        from products.models import Review
        u = User.objects.create_user(username='newrev', email='newrev@test.com', password='pass')
        from products.models import Category, Product
        cat = Category.objects.get_or_create(name='ModTest', slug='modtest-cat')[0]
        p = Product.objects.create(name='New Product', slug='new-prod', sku='NEW001', base_price='5.00', category=cat)
        review = Review.objects.create(user=u, product=p, rating=3)
        assert review.is_approved is False

    def test_admin_can_approve_review(self, admin, review):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.patch(f'/api/admin/reviews/{review.pk}/moderate/', {'is_approved': True}, format='json')
        assert resp.status_code == 200
        review.refresh_from_db()
        assert review.is_approved is True

    def test_admin_can_reject_review(self, admin, approved_review):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=admin)
        resp = client.patch(f'/api/admin/reviews/{approved_review.pk}/moderate/', {'is_approved': False}, format='json')
        assert resp.status_code == 200
        approved_review.refresh_from_db()
        assert approved_review.is_approved is False

    def test_non_admin_cannot_moderate(self, user, review):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.patch(f'/api/admin/reviews/{review.pk}/moderate/', {'is_approved': True}, format='json')
        assert resp.status_code == 403
