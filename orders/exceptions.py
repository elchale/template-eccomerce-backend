"""Orders domain exceptions."""
from core.exceptions import BaseError


class InvalidTransition(BaseError):
    """Raised when an order state transition is not allowed."""
    default_detail = 'Invalid order status transition.'
