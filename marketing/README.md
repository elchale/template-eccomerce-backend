# marketing

Manages promotional content for the e-commerce storefront: promotions, banners, popups, and store configuration.

## Models

| Model | Purpose |
|-------|---------|
| `Promocion` | Discount promotions (percentage, fixed amount, buy-X-get-Y) |
| `Banner` | Hero, announcement, and category banners |
| `Popup` | Triggered popups (welcome, cart abandonment, exit intent, subscription) |
| `ConfiguracionTienda` | Key/value store for site-wide settings |

## URL Patterns

### Public Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/marketing/promociones/` | Active promotions (filtered by date and es_activo) |
| GET | `/api/marketing/banners/` | Active banners; optional `?tipo=hero\|anuncio\|categoria` |
| GET | `/api/marketing/popups/` | Active popups; optional `?tipo=bienvenida\|abandono_carrito\|intencion_salida\|suscripcion` |
| GET | `/api/marketing/configuracion/` | All store config as `{clave: valor}` dict |
| GET | `/api/search/suggestions/?q=<query>` | Top 5 product name suggestions (min 2 chars) |

### Admin Endpoints

All admin endpoints require `IsAdminUser`.

| Method | URL | Description |
|--------|-----|-------------|
| GET/POST | `/api/admin/marketing/promociones/` | List / create promotions |
| GET/PUT/PATCH/DELETE | `/api/admin/marketing/promociones/<id>/` | Retrieve / update / delete promotion |
| GET/POST | `/api/admin/marketing/banners/` | List / create banners |
| GET/PUT/PATCH/DELETE | `/api/admin/marketing/banners/<id>/` | Retrieve / update / delete banner |
| GET/POST | `/api/admin/marketing/popups/` | List / create popups |
| GET/PUT/PATCH/DELETE | `/api/admin/marketing/popups/<id>/` | Retrieve / update / delete popup |
| GET/PUT/PATCH/DELETE | `/api/admin/marketing/banners/<id>/` | Retrieve / update / delete banner |
| POST | `/api/admin/marketing/banners/<id>/upload-image/` | Upload banner image to GCS. Optional `?variant=desktop\|mobile`. Returns `{image_url}`. |
| GET/PUT/PATCH/DELETE | `/api/admin/marketing/popups/<id>/` | Retrieve / update / delete popup |
| POST | `/api/admin/marketing/popups/<id>/upload-image/` | Upload popup image to GCS. Returns `{image_url}`. |
| GET | `/api/admin/marketing/configuracion/` | All config as flat `{clave: valor}` dict |
| PATCH | `/api/admin/marketing/configuracion/` | Upsert config values via `{clave: valor}` dict |

## Caching

| Resource | TTL |
|----------|-----|
| Active promotions | 2 minutes |
| Active banners (per tipo) | 5 minutes |
| Active popups (per tipo) | 5 minutes |
| Store configuration | 10 minutes |
| Search suggestions (per query) | 1 minute |

Cache is invalidated on admin PATCH to configuracion.

## Management Commands

| Command | Description |
|---------|-------------|
| `python manage.py seed_site_config` | Idempotently seeds canonical `ConfiguracionTienda` keys (`site_name`, `contact_email`, `contact_phone`, `contact_address`, `social_*`, `footer_tagline`, `footer_byline`, `meta_description`, `meta_keywords`, `og_image_url`, `currency`, `free_shipping_threshold`). Uses `update_or_create` — safe to run multiple times. Also called automatically via data migration `0002_seed_site_config`. |

## Celery Tasks

| Task | Purpose |
|------|---------|
| `deactivate_expired_promociones` | Sets `es_activo=False` on promotions whose `fecha_fin` has passed (cleanup only — views already filter by date) |

## Promo Pricing on Products

`ProductListSerializer` and `ProductDetailSerializer` include two computed fields:

- `precio_promocion`: The discounted price as a string, or `null` if no active promo applies.
- `promocion`: A summary object with `{id, nombre, slug, tipo, valor_descuento, es_flash_sale}`, or `null`.

Priority resolution: product-specific → category-specific → store-wide (`aplica_a_todo`), ordered by `prioridad` descending.
