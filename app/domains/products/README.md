# Products Module

The products module manages the product catalog — the services offered to companies. It provides CRUD operations for products and manages the many-to-many association between products and companies.

## Architecture

```
products/
├── routers.py        # HTTP endpoints (FastAPI router)
├── services.py       # Business logic
├── repositories.py   # Database access (SQLAlchemy)
├── schemas.py        # Pydantic DTOs (request/response validation)
├── entities.py       # Domain dataclasses (decoupled from ORM)
├── models.py         # SQLAlchemy ORM models
├── dependencies.py   # FastAPI dependency injection wiring
└── swagger_utils.py  # Swagger/OpenAPI documentation configs
```

## Data Model

### Products

| Field         | Type          | Description                    |
|---------------|---------------|--------------------------------|
| `id`          | `int`         | Primary key (auto-increment)   |
| `name`        | `string(127)` | Required, 3-127 characters     |
| `description` | `string(500)` | Nullable, 3-500 characters     |
| `created_at`  | `datetime`    | Server default `now()`         |
| `deleted_at`  | `datetime`    | Nullable (soft delete)         |

### Relationships

- **Products <-> Companies**: Many-to-many via `company_products` join table (defined in the companies domain). A product can be contracted by multiple companies, and a company can contract multiple products.

---

## CRUD Endpoints

All endpoints are mounted under `/api/products` and require authentication via `Authorization: Bearer <access_token>`.

### Products

| Method   | Path                    | Permission            | Description                   |
|----------|-------------------------|-----------------------|-------------------------------|
| `POST`   | `/`                     | `product:create`      | Create a new product          |
| `GET`    | `/`                     | `product:list`        | List products (paginated)     |
| `GET`    | `/{product_id}`         | `product:read`        | Get product by ID             |
| `PUT`    | `/{product_id}`         | `product:replace`     | Replace product (full update) |
| `PATCH`  | `/{product_id}`         | `product:update`      | Partial update                |
| `DELETE` | `/{product_id}`         | `product:soft_delete` | Soft-delete product           |

### Product Companies

| Method   | Path                              | Permission                | Description                          |
|----------|-----------------------------------|---------------------------|--------------------------------------|
| `POST`   | `/{product_id}/companies`                   | `product:add_companies`   | Associate companies with a product   |
| `DELETE` | `/{product_id}/companies`                   | `product:remove_companies`| Remove company associations (batch)  |
| `DELETE` | `/{product_id}/companies/{company_id}`      | `product:remove_company`  | Remove a single company              |
| `GET`    | `/{product_id}/companies`                   | `product:list_companies`  | List companies of a product          |

---

## Request / Response Examples

### Create Product

```
POST /api/products/
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "name": "SyncDesk Chat",
  "description": "Real-time chat support module with agent routing"
}
```

**Response `201`:**
```json
{
  "data": {
    "id": 1,
    "name": "SyncDesk Chat",
    "description": "Real-time chat support module with agent routing",
    "created_at": "2026-04-15T12:00:00"
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `409 Conflict` — a product with the same name already exists.
- `422 Unprocessable Entity` — request body validation failed.

### List Products (Paginated)

```
GET /api/products/?page=1&limit=20
Authorization: Bearer <access_token>
```

**Response `200`:**
```json
{
  "data": {
    "items": [
      {
        "id": 1,
        "name": "SyncDesk Chat",
        "description": "Real-time chat support module with agent routing"
      }
    ],
    "total": 1,
    "page": 1,
    "limit": 20
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

### Partial Update

```
PATCH /api/products/{product_id}
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "description": "Updated description for the product"
}
```

> At least one field (`name` or `description`) must be provided.

**Response `200`:**
```json
{
  "data": {
    "id": 1,
    "name": "SyncDesk Chat",
    "description": "Updated description for the product"
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — product not found.
- `422 Unprocessable Entity` — no valid field provided or validation failed.

### Add Companies to a Product

```
POST /api/products/{product_id}/companies
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "company_ids": ["uuid-1", "uuid-2"]
}
```

**Response `201`:**
```json
{
  "data": null,
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

**Error responses:**
- `404 Not Found` — product or one of the referenced companies not found.
- `409 Conflict` — one or more companies are already associated with this product.

---

## Validation Rules

- **name**: required, between 3 and 127 characters.
- **description**: optional on create, between 3 and 500 characters when provided.
- **Partial update** (`PATCH`): at least one field must be present in the payload.

---

## Implementation Status

> **All endpoints currently return `501 Not Implemented`.** This is a temporary scaffold — each endpoint **must** be replaced with proper business logic in the service and repository layers as the domain is implemented.
