# Orders App

Shopping cart, checkout, and order management.

## URL Patterns

| Method | URL | Permission | Description |
|--------|-----|-----------|-------------|
| GET | `/api/cart/` | IsAuthenticated | Get cart (auto-create) |
| POST | `/api/cart/items/` | IsAuthenticated | Add item to cart |
| PATCH | `/api/cart/items/<id>/` | IsAuthenticated | Update quantity |
| DELETE | `/api/cart/items/<id>/delete/` | IsAuthenticated | Remove item |
| DELETE | `/api/cart/clear/` | IsAuthenticated | Clear cart |
| POST | `/api/checkout/` | IsAuthenticated | Create order from cart |
| GET | `/api/orders/` | IsAuthenticated | User's orders |
| GET | `/api/orders/<order_number>/` | IsAuthenticated (owner) | Order detail |
| GET | `/api/admin/orders/` | IsAdminUser | All orders |
| GET | `/api/admin/orders/<id>/` | IsAdminUser | Admin order detail |
| PATCH | `/api/admin/orders/<id>/status/` | IsAdminUser | Update order status |
| GET | `/api/admin/dashboard/` | IsAdminUser | Analytics dashboard |
| POST | `/api/payments/izipay/create-token/` | IsAuthenticated | Create Izipay formToken for order |
| POST | `/api/payments/izipay/verify/` | IsAuthenticated | Verify client-side payment callback |
| GET/POST | `/api/payments/izipay/ipn/` | AllowAny + HMAC | IPN webhook (server-to-server) |

## Izipay Payment Integration

### Overview
Orders are paid via Izipay (card / Yape) using the embedded form (Krypton). The payment flow uses an intermediary router (`izipay-router`) that dispatches IPNs by order-number prefix.

### Order Number Format
New orders generate `QLCA-YYYYMMDD-XXXX` via `Order.save()`. The `QLCA` prefix enables the router to dispatch to this service.

### IPN Flow
```
Izipay → izipay-router (HMAC verify + prefix dispatch) → POST /api/payments/izipay/ipn/
```
The backend re-verifies the HMAC (BP1: strict `sha256_hmac` only) then atomically:
1. Updates `order.payment_status = 'paid'`
2. Creates a `Payment` record (status='verified')
3. Auto-confirms order: `pending → confirmed` (BP6)
4. Clears user's cart (ADR D5)
5. Creates `IpnEvent` audit record (BP5)
6. Queues confirmation + admin notification emails

### Payment Models
- `Payment` — verified transactions. Statuses: `verified`, `refunded` only (BP7).
- `IpnEvent` — write-only audit ledger. Every IPN call creates one row. Admin-accessible at `/admin/`.

### Env Vars Required
```
IZIPAY_SHOP_ID=36933364
IZIPAY_MODE=TEST          # or PRODUCTION
IZIPAY_API_KEY_TEST=...
IZIPAY_API_KEY_PROD=...
IZIPAY_HMAC_KEY_TEST=...
IZIPAY_HMAC_KEY_PROD=...
TRUST_PROXY=False         # True when behind Render/Railway/CF
```
