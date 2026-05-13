# Coupons App

Discount coupon management and validation.

## URL Patterns

| Method | URL | Permission | Description |
|--------|-----|-----------|-------------|
| POST | `/api/coupons/validate/` | IsAuthenticated | Validate coupon code |
| CRUD | `/api/admin/coupons/` | IsAdminUser | Admin coupon management |
