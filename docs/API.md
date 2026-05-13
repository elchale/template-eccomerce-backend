# API Documentation

## Interactive API Documentation

This project uses **drf-spectacular** to automatically generate OpenAPI 3.0 compliant API documentation from your Django REST Framework code.

### Access Documentation

**Development Environment:**
- **Swagger UI** (Interactive): [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
  - Modern, interactive interface
  - Test endpoints directly in browser
  - See request/response examples

- **ReDoc** (Clean): [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
  - Three-panel design
  - Better for reading/reference
  - Print-friendly

- **OpenAPI Schema** (Raw): [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)
  - JSON/YAML format
  - For generating client SDKs
  - For import into tools (Postman, Insomnia)

**Production Environment:**
- API docs are disabled by default for security
- Access requires authentication (staff users only)
- Contact administrator for API access

## Authentication

All protected endpoints require JWT authentication.

### Getting Started

1. **Register**: POST `/auth/registration/`
2. **Verify Email**: Check your email and confirm
3. **Login**: POST `/auth/login/` - Receives access & refresh tokens
4. **Authenticate**: Add header `Authorization: Bearer {access_token}`

### Token Refresh

Access tokens expire after 1 day. Use refresh token to get new access token:

```bash
curl -X POST http://localhost:8000/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "your-refresh-token"}'
```

## API Overview

### Authentication Endpoints
- `POST /auth/login/` - User login
- `POST /auth/registration/` - User registration
- `POST /auth/registration/account-confirm-email/` - Confirm email
- `POST /resend-email-confirmation/` - Resend verification email
- `POST /auth/password/change/` - Change password (authenticated)
- `POST /auth/password/reset/` - Request password reset
- `POST /auth/password/reset/confirm/` - Confirm password reset
- `POST /auth/token/refresh/` - Refresh access token

### Rate Limiting

| Scope | Limit |
|-------|-------|
| Anonymous users | 100 requests/hour |
| Authenticated users | 1000 requests/hour |
| Authentication endpoints | 5 requests/minute |

## Using the API

### Example: Login Flow

```bash
# 1. Register
curl -X POST http://localhost:8000/auth/registration/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password1": "securepass123",
    "password2": "securepass123",
    "first_name": "John",
    "last_name": "Doe"
  }'

# 2. Confirm email (check your inbox for verification link)

# 3. Login
curl -X POST http://localhost:8000/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123"
  }'

# Response includes tokens:
# {
#   "access_token": "eyJ...",
#   "refresh_token": "eyJ...",
#   "user": {...}
# }

# 4. Use access token for authenticated requests
curl http://localhost:8000/api/some-endpoint/ \
  -H "Authorization: Bearer eyJ..."
```

## Generating Client SDKs

You can generate client libraries in various languages using the OpenAPI schema:

```bash
# Download schema
curl http://localhost:8000/api/schema/ > openapi.json

# Generate Python client
openapi-generator-cli generate -i openapi.json -g python -o ./client-python

# Generate TypeScript client
openapi-generator-cli generate -i openapi.json -g typescript-axios -o ./client-ts
```

## Need Help?

- See interactive examples at `/api/docs/`
- Check the main [README.md](../README.md) for setup
- Review [DEVELOPMENT.md](./DEVELOPMENT.md) for contribution guidelines
