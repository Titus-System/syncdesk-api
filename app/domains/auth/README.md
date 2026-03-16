# Auth Module

The auth module handles user authentication, authorization, and session management. It provides a JWT-based authentication system with refresh token rotation and device fingerprinting.

## Architecture

```
auth/
├── routers/          # HTTP endpoints (FastAPI routers)
├── services/         # Business logic
├── repositories/     # Database access (SQLAlchemy)
├── schemas/          # Pydantic DTOs (request/response validation)
├── entities.py       # Domain dataclasses (decoupled from ORM)
├── models.py         # SQLAlchemy ORM models
├── enums.py          # SessionStatus, OAuthProvider, DeviceType
├── exceptions.py     # Domain-specific exceptions
├── dependencies.py   # FastAPI dependency injection wiring
└── types.py          # Type aliases
```

## Data Model

### Users

| Field              | Type              | Description                         |
|--------------------|-------------------|-------------------------------------|
| `id`               | `UUID`            | Primary key                         |
| `email`            | `string(255)`     | Unique, indexed                     |
| `username`         | `string(50)`      | Unique, nullable                    |
| `name`             | `string(50)`      | Nullable                            |
| `password_hash`    | `string(255)`     | Argon2 hash, nullable (OAuth users) |
| `oauth_provider`   | `enum`            | `local`, `google`, `microsoft`      |
| `oauth_provider_id`| `string(255)`     | Nullable, unique                    |
| `is_active`        | `bool`            | Default `true`                      |
| `is_verified`      | `bool`            | Default `false`                     |
| `created_at`       | `datetime`        | Server default `now()`              |
| `updated_at`       | `datetime`        | Nullable                            |
| `deleted_at`       | `datetime`        | Nullable (soft delete)              |

A user must have **at least one** login method: a password or an OAuth provider.

### Roles

| Field         | Type          | Description            |
|---------------|---------------|------------------------|
| `id`          | `int`         | Primary key            |
| `name`        | `string(30)`  | Unique. Letters and `_` only, min 3 chars |
| `description` | `string(255)` | Nullable               |

### Permissions

| Field         | Type          | Description            |
|---------------|---------------|------------------------|
| `id`          | `int`         | Primary key            |
| `name`        | `string(50)`  | Unique. Format: `<resource>:<action>` (lowercase + `_`, min 3 chars each side) |
| `description` | `string(255)` | Nullable               |

### Sessions

| Field                | Type          | Description                                |
|----------------------|---------------|--------------------------------------------|
| `id`                 | `UUID`        | Primary key                                |
| `user_id`            | `UUID`        | FK → `users.id`                            |
| `refresh_token_hash` | `string(255)` | Argon2 hash of the current refresh token   |
| `status`             | `enum`        | `active`, `expired`, `invalid`, `revoked`  |
| `device_info`        | `JSONB`       | Device fingerprint (user-agent, IP, OS, browser) |
| `expires_at`         | `datetime`    | Session expiration                         |
| `last_used_at`       | `datetime`    | Updated on refresh                         |
| `revoked_at`         | `datetime`    | Set when explicitly revoked                |

### Relationships

- **Users ↔ Roles**: Many-to-many via `user_roles` join table.
- **Roles ↔ Permissions**: Many-to-many via `role_permissions` join table.
- **Users → Sessions**: One-to-many with cascade delete.

---

## Authentication Flow

### Token Strategy

The system uses **two JWT tokens** plus a **server-side session**:

| Token          | Lifetime       | Contains                              | Storage recommendation    |
|----------------|----------------|---------------------------------------|---------------------------|
| Access Token   | 15 minutes     | `sub` (user ID), `roles`, `sid` (session ID), `type: access`  | Memory (JS variable)     |
| Refresh Token  | 60 days        | `sub` (user ID), `roles`, `sid` (session ID), `type: refresh` | `httpOnly` cookie or secure storage |

Both tokens include `iss` (project identifier) and `aud` (client identifier) claims. Access tokens and refresh tokens are signed with **separate keys** (`ACCESS_TOKEN_SIGNING_KEY` / `REFRESH_TOKEN_SIGNING_KEY`) for defense-in-depth.

Each user can have at most **5 active sessions**. When a new session is created and the limit is reached, the oldest session is freed.

### Register

```
POST /api/v1/auth/register
```

**Request body:**
```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "SecureP@ss1"
}
```

> **Note:** Passwords must be at least 8 characters and contain uppercase, lowercase, digit, and special character. The `email` field is validated with `EmailStr`.

**Response `201`:**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe",
    "access_token": "eyJ...",
    "refresh_token": "eyJ..."
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

The password is hashed with **Argon2** before storage. A session is created immediately, so the user is logged in upon registration. The default `user` role is auto-assigned.

> Role assignment is an **admin-only** operation via `POST /api/users/{id}/roles`. The registration endpoint does not accept `role_ids`.

**Error responses:**
- `400 Bad Request` — invalid registration data (e.g. duplicate email). Generic message to prevent user enumeration.

### Login

```
POST /api/v1/auth/login
```

**Request body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response `200`:**
```json
{
  "data": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ..."
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

Device info (user-agent, IP, OS, browser) is automatically extracted from the request and stored in the session.

**Error responses:**
- `401 Unauthorized` — invalid email or password.

### Refresh

```
POST /api/v1/auth/refresh
Authorization: Bearer <access_token>
```

**Request body:**
```json
{
  "refresh_token": "eyJ..."
}
```

**Response `200`:**
```json
{
  "data": {
    "access_token": "eyJ...(new)",
    "refresh_token": "eyJ...(new)"
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

This endpoint implements **refresh token rotation**: each refresh issues a new pair of tokens and invalidates the previous refresh token hash. The session expiration is also extended.

**Validation checks:**
1. The provided refresh token hash must match the one stored in the session.
2. The device fingerprint (OS + browser + device type) must match the original session.
3. The `sub` claim in the refresh token must match the authenticated user.

If any check fails, the session is **revoked** (not just rejected), forcing a full re-login. This protects against token theft.

**Error responses:**
- `404 Not Found` — session not found.
- `401 Unauthorized` — invalid session (fingerprint mismatch, token mismatch, etc.).

### Logout

```
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
```

Revokes the current session. No request body needed.

**Response `200`:**
```json
{
  "data": null,
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

### Get Current User

```
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Returns the authenticated user profile with roles.

**Response `200`:**
```json
{
  "data": {
    "id": "uuid",
    "email": "user@example.com",
    "username": "johndoe",
    "name": null,
    "oauth_provider": null,
    "oauth_provider_id": null,
    "is_active": true,
    "is_verified": false,
    "roles": [
      { "id": 1, "name": "admin", "description": "Administrator" }
    ]
  },
  "meta": { "timestamp": "...", "success": true, "request_id": null }
}
```

The `password_hash` field is never included in responses.

---

## Protected Endpoints

All endpoints outside of `/auth/login` and `/auth/register` require a valid access token via the `Authorization: Bearer <token>` header. Authentication is enforced through the `CurrentUserSessionDep` dependency, which:

1. Extracts the bearer token from the `Authorization` header.
2. Decodes and validates the JWT (signature, expiration, issuer, audience, token type).
3. Loads the user and session from the database.
4. Verifies the user is active and has a valid login method.
5. Verifies the session is active and not expired.
6. Confirms the token's user ID matches the session's user ID.

If any step fails, a `401 Unauthorized` response is returned.

---

## CRUD Endpoints

### Users — `/api/v1/users`

| Method   | Path              | Description                 |
|----------|-------------------|-----------------------------|
| `POST`   | `/`               | Create a user               |
| `GET`    | `/`               | List all users              |
| `GET`    | `/{id}`           | Get user by ID              |
| `PUT`    | `/{id}`           | Replace user (full update)  |
| `PATCH`  | `/{id}`           | Partial update              |
| `POST`   | `/{id}/roles`     | Assign roles to a user      |

### Roles — `/api/v1/roles`

| Method   | Path                  | Description                      |
|----------|-----------------------|----------------------------------|
| `POST`   | `/`                   | Create a role                    |
| `GET`    | `/`                   | List all roles                   |
| `GET`    | `/{id}`               | Get role by ID                   |
| `PUT`    | `/{id}`               | Replace role                     |
| `PATCH`  | `/{id}`               | Partial update                   |
| `DELETE` | `/{id}`               | Delete role                      |
| `GET`    | `/{id}/permissions`   | Get role with its permissions    |
| `POST`   | `/{id}/permissions`   | Assign permissions to a role     |

### Permissions — `/api/v1/permissions`

| Method   | Path              | Description                          |
|----------|-------------------|--------------------------------------|
| `POST`   | `/`               | Create a permission                  |
| `GET`    | `/`               | List all permissions                 |
| `GET`    | `/{id}`           | Get permission by ID                 |
| `PUT`    | `/{id}`           | Replace permission                   |
| `PATCH`  | `/{id}`           | Partial update                       |
| `DELETE` | `/{id}`           | Delete permission                    |
| `GET`    | `/{id}/roles`     | Get permission with its roles        |
| `POST`   | `/{id}/roles`     | Assign permission to roles           |

---

## Frontend Integration Guide

### 1. Storing Tokens

| Token         | Recommended Storage               | Reason                                          |
|---------------|------------------------------------|-------------------------------------------------|
| Access Token  | In-memory variable (e.g., Zustand, React context, Pinia store) | Short-lived; avoids XSS exposure from `localStorage` |
| Refresh Token | `httpOnly` secure cookie **or** secure device storage (mobile) | Protected from JavaScript access               |

> **Avoid `localStorage`** for tokens — it is accessible to any script running on the page.

### 2. Sending Authenticated Requests

Include the access token in every request:

```
Authorization: Bearer <access_token>
```

### 3. Handling Token Expiration

Access tokens expire in **15 minutes**. Implement transparent refresh:

```
1. Send request with access token
2. If 401 response:
   a. Call POST /api/v1/auth/refresh with the refresh token
   b. Store the new access token and refresh token
   c. Retry the original request with the new access token
3. If refresh also fails (401):
   a. Clear stored tokens
   b. Redirect to login
```

Common implementation patterns:
- **Axios interceptor** (React/Vue): intercept 401 responses, refresh, and retry.
- **Fetch wrapper**: same logic in a custom `fetch` function.
- **Queue pending requests** during refresh to avoid multiple simultaneous refresh calls.

### 4. Device Info

The backend automatically extracts device information from every request via middleware and stores it in the session. The frontend does **not** need to send device info explicitly. The following headers are parsed:

- `User-Agent` — browser, OS, and device type detection.
- Client IP — from the connecting address.

The device fingerprint (OS + browser + device type) is used to validate refresh requests. If a refresh comes from a different device fingerprint than the original session, the session is revoked.

### 5. CORS

The backend is configured with CORS middleware. The default development settings allow all origins (`*`). In production, set `CORS_ALLOW_ORIGINS` to your frontend domain(s).

### 6. Response Envelope

All responses follow a consistent envelope:

```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2026-03-09T12:00:00+00:00",
    "success": true,
    "request_id": "optional-uuid"
  }
}
```

Error responses follow RFC 7807 format. The frontend can always check `meta.success` for the request status.

### 7. Request ID Tracking

The backend attaches a `X-Request-ID` header to every response. If the frontend sends an `X-Request-ID` header, the same value is echoed back; otherwise one is generated. Use this for log correlation and debugging.

---

## Configuration

Relevant environment variables (set via `.env`):

| Variable                      | Default  | Description                         |
|-------------------------------|----------|-------------------------------------|
| `JWT_SECRET_KEY`              | —        | Secret for signing JWTs             |
| `JWT_ALGORITHM`               | `HS256`  | JWT signing algorithm               |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15`     | Access token lifetime in minutes    |
| `REFRESH_TOKEN_EXPIRE_DAYS`   | `60`     | Refresh token lifetime in days      |
| `SESSION_EXPIRE_DAYS`         | `180`    | Server-side session lifetime in days|
| `CORS_ALLOW_ORIGINS`          | `["*"]`  | Allowed origins for CORS            |

---

## Known Security Limitations

The following security improvements are **deferred for a future release**:

| # | Severity | Issue | Notes |
|---|----------|-------|-------|
| 2 | 🔴 Critical | Hardcoded JWT secret default | `config.py` uses a placeholder if env vars are missing. Add startup validation before production. |
| 3 | 🟠 High | No rate limiting on login/register | Middleware stub exists but is not implemented. Recommend Redis-backed sliding window. |
| 11 | 🔵 Low | HS256 symmetric algorithm | Consider RS256/ES256 for microservice architectures. |
