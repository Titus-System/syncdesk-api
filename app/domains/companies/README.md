# Companies Module

The companies module manages companies (organizations that contract our services), their associated products, and their users. It provides CRUD operations for companies, product association management, and user listing per company.

## Architecture

```
companies/
├── routers/          # HTTP endpoints (FastAPI router)
├── services.py       # Business logic
├── repositories.py   # Database access (SQLAlchemy)
├── schemas.py        # Pydantic DTOs (request/response validation)
├── entities.py       # Domain dataclasses (decoupled from ORM)
├── models.py         # SQLAlchemy ORM models
├── dependencies.py   # FastAPI dependency injection wiring
└── swagger_utils.py  # Swagger/OpenAPI documentation configs
```

## Data Model

### Companies

| Field        | Type          | Description                              |
|--------------|---------------|------------------------------------------|
| `id`         | `UUID`        | Primary key                              |
| `legal_name` | `string(255)` | Unique, indexed (razao social)           |
| `trade_name` | `string(255)` | Nullable, indexed (nome fantasia)        |
| `tax_id`     | `string(14)`  | Unique, indexed (CNPJ)                   |
| `created_at` | `datetime`    | Server default `now()`                   |
| `deleted_at` | `datetime`    | Nullable (soft delete)                   |

### Company Products (association table)

| Field          | Type       | Description                                  |
|----------------|------------|----------------------------------------------|
| `company_id`   | `UUID`     | FK -> `companies.id`, composite PK           |
| `product_id`   | `int`      | FK -> `products.id`, composite PK            |
| `bought_at`    | `datetime` | Server default `now()`                       |
| `support_until`| `datetime` | Expiration date for the product support      |

### Relationships

- **Companies -> Users**: One-to-many. A company has many users; a user optionally belongs to one company (`users.company_id` FK).
- **Companies <-> Products**: Many-to-many via `company_products` join table.

---

## CRUD Endpoints

All endpoints are mounted under `/api/v1/companies` and require authentication via `Authorization: Bearer <access_token>`.

### Companies

| Method   | Path                              | Permission              | Description                        |
|----------|-----------------------------------|-------------------------|------------------------------------|
| `POST`   | `/`                               | `company:create`        | Create a new company               |
| `GET`    | `/`                               | `company:list`          | List companies (paginated)         |
| `GET`    | `/{company_id}`                   | `company:read`          | Get company by ID                  |
| `PUT`    | `/{company_id}`                   | `company:replace`       | Replace company (full update)      |
| `PATCH`  | `/{company_id}`                   | `company:update`        | Partial update                     |
| `DELETE` | `/{company_id}`                   | `company:soft_delete`   | Soft-delete company                |

### Company Products

| Method   | Path                                        | Permission               | Description                      |
|----------|---------------------------------------------|--------------------------|----------------------------------|
| `POST`   | `/{company_id}/products`                    | `company:add_product`    | Add products to a company        |
| `DELETE` | `/{company_id}/products`                    | `company:remove_products`| Remove products (batch)          |
| `DELETE` | `/{company_id}/products/{product_id}`       | `company:remove_product` | Remove a single product          |

### Company Users

| Method   | Path                              | Permission              | Description                        |
|----------|-----------------------------------|-------------------------|------------------------------------|
| `GET`    | `/{company_id}/users`             | `company:list_users`    | List users of a company (paginated)|

---

## Request / Response Examples

### Create Company

```
POST /api/v1/companies/
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "legal_name": "Acme Tecnologia Ltda",
  "trade_name": "Acme Tech",
  "tax_id": "12345678000190"
}
```

**Response `201`:**
```json
{
  "data": {
    "id": "uuid",
    "legal_name": "Acme Tecnologia Ltda",
    "trade_name": "Acme Tech",
    "tax_id": "12345678000190",
    "created_at": "2026-04-15T12:00:00"
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `409 Conflict` — a company with the same `tax_id` or `legal_name` already exists.
- `422 Unprocessable Entity` — request body validation failed.

### List Companies (Paginated)

```
GET /api/v1/companies/?page=1&limit=20
Authorization: Bearer <access_token>
```

**Response `200`:**
```json
{
  "data": {
    "items": [
      {
        "id": "uuid",
        "legal_name": "Acme Tecnologia Ltda",
        "trade_name": "Acme Tech",
        "tax_id": "12345678000190"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

### Get Company by ID

```
GET /api/v1/companies/{company_id}
Authorization: Bearer <access_token>
```

**Response `200`:**
```json
{
  "data": {
    "id": "uuid",
    "legal_name": "Acme Tecnologia Ltda",
    "trade_name": "Acme Tech",
    "tax_id": "12345678000190",
    "created_at": "2026-04-15T12:00:00"
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — company not found.

### Add Products to a Company

```
POST /api/v1/companies/{company_id}/products
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "product_ids": [1, 2, 3]
}
```

**Response `201`:**
```json
{
  "data": { ... },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — company or one of the referenced products not found.
- `409 Conflict` — one or more products are already associated with this company.

### Soft-Delete a Company

```
DELETE /api/v1/companies/{company_id}
Authorization: Bearer <access_token>
```

**Response `200`:**
```json
{
  "data": null,
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — company not found.

### List Company Users (Paginated)

```
GET /api/v1/companies/{company_id}/users?page=1&limit=20
Authorization: Bearer <access_token>
```

**Response `200`:**
```json
{
  "data": {
    "items": [
      {
        "id": "uuid",
        "email": "user@example.com",
        "username": "johndoe",
        "name": "John Doe"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — company not found.

---

## Validation Rules

- **legal_name**: required, between 3 and 255 characters.
- **trade_name**: required on create/replace, optional on update, between 3 and 255 characters.
- **tax_id**: required, between 11 and 14 characters. Auto-normalized on input: non-alphanumeric characters (dots, dashes, slashes) are stripped. Example: `12.345.678/0001-90` becomes `12345678000190`.

---

## User-Company Association

Users are linked to companies via a `company_id` foreign key on the `users` table (defined in the auth domain). This field is:

- **Nullable** — not all users belong to a company (e.g., admins, agents).
- **Indexed** — for efficient lookups of users by company.

The business rule that client-role users must have a `company_id` is enforced at the **service layer**, not via database constraints, since it depends on cross-table role checks.

---

## Implementation Status

> **All endpoints currently return `501 Not Implemented`.** This is a temporary scaffold — each endpoint **must** be replaced with proper business logic in the service and repository layers as the domain is implemented.
