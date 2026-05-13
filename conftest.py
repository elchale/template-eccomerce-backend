"""
Root pytest configuration for the backend.
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_cache_for_db_tests(request):
    """
    Clear Django's cache before and after every test that accesses the database.
    This prevents cache_page / cache.set from leaking responses between tests.
    """
    if request.node.get_closest_marker('django_db') is None:
        yield
        return

    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()
