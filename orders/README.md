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
| POST | `/api/admin/orders/<id>/refund/` | IsAdminUser | Refund order (Culqi if charged via Culqi, else Izipay) |
| GET | `/api/admin/dashboard/` | IsAdminUser | Analytics dashboard |
| GET | `/api/admin/email-logs/` | IsAdminUser | List EmailLog records (filterable by status/email_type) |
| POST | `/api/admin/email-logs/<id>/retry/` | IsAdminUser | Retry a failed/stale email |
| POST | `/api/payments/culqi/charge/` | IsAuthenticated | Charge a Culqi card/Yape token (synchronous) |
| POST | `/api/payments/culqi/order/` | IsAuthenticated | Create a Culqi Order for alt payment methods |
| POST | `/api/payments/culqi/webhook-<secret>/` | AllowAny | Culqi webhook (server-to-server, always 200) |
| POST | `/api/payments/izipay/create-token/` | IsAuthenticated | Create Izipay formToken for order (dormant) |
| POST | `/api/payments/izipay/verify/` | IsAuthenticated | Verify client-side payment callback (dormant) |
| GET/POST | `/api/payments/izipay/ipn/` | AllowAny + HMAC | Izipay IPN webhook (dormant) |

## Culqi Payment Integration (active gateway)

### Overview
Culqi (https://culqi.com) is the **active** payment gateway, selected via the
`PAYMENT_GATEWAY` setting (default `culqi`). The Izipay integration below is
kept **dormant** — code and endpoints stay registered but the frontend does
not exercise them while `PAYMENT_GATEWAY=culqi`.

Culqi uses **Checkout Custom** in the browser: card data is tokenized client
side and never reaches the backend. Two payment paths:
- **Card / Yape** → browser produces a token → `POST /api/payments/culqi/charge/`
  charges it synchronously; the charge result is authoritative.
- **PagoEfectivo / wallets / bank apps / Cuotéalo** → `POST /api/payments/culqi/order/`
  creates a Culqi Order; the customer pays later and Culqi notifies us via the
  webhook (`order.status.changed`).

### Webhook
Culqi sends **no signature header**. Authenticity is established by re-fetching
the referenced resource (`GET /charges/{id}` / `GET /orders/{id}`) with the
secret key. The webhook URL path carries an unguessable slug from
`CULQI_WEBHOOK_PATH_SECRET`. The endpoint is `AllowAny`, CSRF-exempt, idempotent
and **always returns HTTP 200**. The Culqi account is shared with sibling
projects, so events for their resources also arrive here — they are self-filtered
by DB lookup (`metadata.project='qlca'`) and acknowledged with 200.

On a confirmed payment the handler atomically:
1. Updates `order.payment_status = 'paid'`, stores `culqi_charge_id`
2. Creates a `Payment` record (method `culqi`/`yape`, status `verified`)
3. Auto-confirms order: `pending → confirmed`
4. Clears the user's cart (safety net)
5. Creates an `IpnEvent` audit record (`gateway='culqi'`)
6. Queues confirmation + admin notification emails

### Refunds
`POST /api/admin/orders/<id>/refund/` refunds via **Culqi** when the order has
a `culqi_charge_id`, else via **Izipay** for legacy Izipay-paid orders.

### Env Vars Required
```
PAYMENT_GATEWAY=culqi
CULQI_PUBLIC_KEY=pk_test_...
CULQI_SECRET_KEY=sk_test_...
CULQI_WEBHOOK_PATH_SECRET=<random unguessable slug>
```

## Izipay Payment Integration (dormant)

### Overview
Orders were previously paid via Izipay (card / Yape) using the embedded form
(Krypton). This path is **dormant** — kept as a fallback, selectable by setting
`PAYMENT_GATEWAY=izipay`. The payment flow uses an intermediary router
(`izipay-router`) that dispatches IPNs by order-number prefix.

### Order Number Format
New orders generate `QLCA-YYYYMMDD-XXXX` via `Order.save()`. The `QLCA` prefix
enables the Izipay router to dispatch to this service (now just a label under
Culqi — Culqi routes by `metadata`, not the order-number prefix).

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

## Email Notification System

### Overview

All transactional emails are dispatched through `orders/email_dispatch.py`. This layer:
- Creates an `EmailLog` row (status=`pending`) **before** sending
- Wraps the actual send in `transaction.on_commit` so IPN handlers return immediately
- Falls back to a background thread when `USE_CELERY=False` (local dev)
- Uses Celery tasks when `USE_CELERY=True` (production)

### Email Events

| EmailType | Recipient | Trigger |
|-----------|-----------|---------|
| `customer_payment_received` | Customer | IPN PAID |
| `customer_status_update` | Customer | Admin status change |
| `customer_refund` | Customer | IPN REFUNDED/CANCELLED |
| `admin_new_paid_order` | Admin | IPN PAID |
| `admin_status_update` | Admin | Status changes (see routing rule) |
| `admin_amount_mismatch` | Admin | IPN amount differs from order total |

**Admin status-update routing rule** (`should_notify_admin_of_status_change`):
- Always notify on `cancelled` or `refunded`
- Always notify when triggered by a customer (non-staff) or system (IPN)
- Skip when a staff member manually changes to a non-terminal status (confirmed/shipped/delivered)

### EmailLog Model

| Field | Type | Notes |
|-------|------|-------|
| `email_type` | TextChoices | One of the 6 types above |
| `template_name` | CharField | Django template path used |
| `subject` | CharField | Email subject line |
| `recipient_email` | EmailField | Destination address |
| `recipient_user` | FK(User) | Nullable; linked if recipient is a site user |
| `order` | FK(Order) | Nullable; linked order |
| `status` | TextChoices | `pending` / `retrying` / `confirmed` / `failed` |
| `task_name` | CharField | Fully-qualified Celery task name for retry |
| `task_args` | JSONField | `{args: [...], kwargs: {...}}` stored for retry |
| `error_message` | TextField | Last SMTP error (truncated to 500 chars) |
| `attempts` | PositiveSmallInt | Incremented on each send attempt |
| `sent_at` | DateTimeField | Timestamp of first successful send |
| `last_attempt_at` | DateTimeField | Timestamp of most recent attempt |

### Retryability Rule

`email_log_is_retryable(email_log)`:
- `confirmed` → never retryable
- `failed` → always retryable
- `pending` or `retrying` → retryable only if `last_attempt_at` is older than `EMAIL_LOG_STALE_AFTER` (5 minutes); fresh rows are still in-flight

### Admin Retry Endpoint

`POST /api/admin/email-logs/<id>/retry/`
- Returns `409` if the row is not retryable (confirmed or fresh pending/retrying)
- Calls `retry_email_log(email_log)` which re-resolves the task from Celery's registry and re-dispatches via `dispatch_order_email`
- Returns the updated `EmailLogSerializer` payload on success

### Email Templates

Templates live in `core/templates/orders/`:
```
orders/
  payment_received.html + .txt
  order_status_update.html + .txt
  refund_notification.html + .txt
  admin/
    new_paid_order.html + .txt
    order_status_update.html + .txt
    amount_mismatch.html + .txt
```

All templates extend `base_layout.html`.

### Env Vars for Email

```
USE_CELERY=False          # True in production to use Celery workers
EMAIL_TIMEOUT=10          # SMTP connection/send timeout in seconds
ADMIN_USER=admin@...      # Must be a valid email — receives admin alerts
```
