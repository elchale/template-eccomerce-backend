# Products App

Product catalog management including categories, products, variants, reviews, and wishlists.

## URL Patterns

| Method | URL | Permission | Description |
|--------|-----|-----------|-------------|
| GET | `/api/products/` | AllowAny | List products (filterable) |
| GET | `/api/products/<slug>/` | AllowAny | Product detail |
| GET | `/api/categories/` | AllowAny | Category tree |
| GET | `/api/categories/<slug>/` | AllowAny | Category detail |
| GET | `/api/products/<slug>/reviews/` | AllowAny | Product reviews |
| POST | `/api/reviews/` | IsAuthenticated | Create review |
| PUT/DELETE | `/api/reviews/<id>/` | IsAuthenticated (owner) | Update/delete review |
| GET | `/api/wishlist/` | IsAuthenticated | User's wishlist |
| POST | `/api/wishlist/toggle/` | IsAuthenticated | Toggle wishlist item |
| CRUD | `/api/admin/products/` | IsAdminUser | Admin product management |
| POST/DELETE | `/api/admin/products/<id>/images/` | IsAdminUser | Manage product images |
| CRUD | `/api/admin/products/<id>/variants/` | IsAdminUser | Manage variants |
| CRUD | `/api/admin/categories/` | IsAdminUser | Admin category management |
| CRUD | `/api/admin/variant-types/` | IsAdminUser | Manage variant types |
