# core/ Module

Cross-cutting infrastructure for the FastAPI application: configuration, logging, security, response formatting, middleware, metrics, and shared utilities.

## Structure

```
core/
├── __init__.py            # Public API re-exports
├── background_tasks.py    # Global background task registry
├── config.py              # Application settings (pydantic-settings)
├── decorators.py          # Service-layer decorators (require_dto)
├── dependencies.py        # FastAPI Depends wrappers for core services
├── exceptions.py          # Centralized exception handling
├── init_routers.py        # Router registration + root endpoint
├── logger.py              # Async structured logger with context propagation
├── middleware.py           # HTTP middleware orchestration
├── response.py            # ResponseFactory (success/error envelopes)
├── schemas.py             # Base DTO class
├── security.py            # Password hashing & JWT token services
├── http/
│   ├── device.py          # Device/browser info extraction from headers
│   └── schemas.py         # DeviceType enum & SessionDeviceInfo model
└── metrics/
    ├── decorators.py      # @track_background_job decorator
    ├── global_metrics.py  # Pre-registered Prometheus counters/gauges/histograms
    ├── metrics_background_tasks.py  # Periodic system metrics collector
    ├── metrics_middleware.py        # HTTP request metrics middleware
    ├── metrics_router.py            # /metrics endpoints
    └── prometheus.py                # Prometheus abstraction layer
```

## Public API

Everything re-exported from `app.core`:

```python
from app.core import (
    add_middlewares,
    get_settings,
    Settings,
    get_logger,
    stop_logger,
    register_exception_handlers,
    global_background_tasks,
    ResponseFactory,
    AppHTTPException,
    get_response_factory,
)
```

---

## Configuration (`config.py`)

`Settings` extends `pydantic_settings.BaseSettings` and reads values from environment variables or a `.env` file.

### Key settings groups

| Group       | Variables                                                                                       | Defaults                              |
| ----------- | ----------------------------------------------------------------------------------------------- | ------------------------------------- |
| Project     | `PROJECT_NAME`, `PROJECT_DESCRIPTION`, `PROJECT_VERSION`, `ENVIRONMENT`                         | See source                            |
| CORS        | `CORS_ALLOW_ORIGINS`, `CORS_ALLOW_CREDENTIALS`, `CORS_ALLOW_METHODS`, `CORS_ALLOW_HEADERS`     | All `"*"` / `True`                    |
| Postgres    | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`           | `postgres` / `localhost` / `5432`     |
| JWT         | `ACCESS_TOKEN_SIGNING_KEY`, `REFRESH_TOKEN_SIGNING_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `SESSION_EXPIRE_DAYS` | `HS256` / `15 min` / `60 d` / `180 d` |

### Derived properties

| Property                      | Description                                         |
| ----------------------------- | --------------------------------------------------- |
| `project_identifier`          | Lowercase, hyphenated project name                  |
| `project_client_identifier`   | `project_identifier + "-client"` (JWT audience)     |
| `database_url`                | Full asyncpg connection URL for the main DB         |
| `test_database_url`           | Connection URL for the test DB (`{db}_test`)        |
| `database_server_url`         | Connection URL targeting the default `postgres` DB  |
| `access_token_timedelta`      | `timedelta` from `ACCESS_TOKEN_EXPIRE_MINUTES`      |
| `refresh_token_timedelta`     | `timedelta` from `REFRESH_TOKEN_EXPIRE_DAYS`        |
| `session_default_timedelta`   | `timedelta` from `SESSION_EXPIRE_DAYS`              |

### Usage

`get_settings()` is cached with `@lru_cache`, so the settings object is created once:

```python
from app.core import get_settings

settings = get_settings()
print(settings.database_url)
```

---

## Logger (`logger.py`)

Structured, async-safe logging with per-domain names, automatic request/user context, and environment-aware formatting.

### Output destinations

| Destination          | Level   | File             | Format    |
| -------------------- | ------- | ---------------- | --------- |
| Rotating file        | INFO+   | `logs/app.json`  | JSON      |
| Rotating error file  | ERROR+  | `logs/error.json`| JSON      |
| Console (stderr)     | DEBUG+  | —                | JSON in production, plaintext with colors in development |

Files rotate at **10 MB** with up to **5 backups**.

Log writing is non-blocking: records go through a `ContextQueueHandler` → `QueueListener` pipeline so the calling coroutine is not held up by I/O. The custom `ContextQueueHandler` snapshots `request_id` and `user_id` from `ContextVar` onto each record before enqueuing, so the values are preserved when the listener thread processes them.

### JSON log fields

| Field        | Source             | Always present |
| ------------ | ------------------ | -------------- |
| `timestamp`  | UTC ISO 8601       | yes            |
| `message`    | Log message        | yes            |
| `level`      | INFO, ERROR, etc.  | yes            |
| `logger`     | Logger name        | yes            |
| `module`     | Python module      | yes            |
| `function`   | Function name      | yes            |
| `line`       | Line number        | yes            |
| `request_id` | `request_id_ctx`   | when in request scope |
| `user_id`    | `user_id_ctx`      | when authenticated    |
| `extra`      | `extra={...}` kwarg| when provided  |
| `exception`  | Traceback          | on `.exception()` or `exc_info=True` |

### Usage

Always pass a **domain-scoped name** to `get_logger()`:

```python
from app.core.logger import get_logger

logger = get_logger("app.auth.service")
```

**Naming convention:** `app.<domain>.<layer>` — e.g. `app.auth.service`, `app.live_chat.manager`, `app.infra.email`, `app.db.postgres`.

### Log levels

```python
logger.debug("Verbose detail for local debugging")
logger.info("Normal operation event")
logger.warning("Unexpected but recoverable situation")
logger.error("Error without traceback")
logger.exception("Error with automatic traceback")  # exc_info=True by default
```

### Adding contextual data

Pass structured data via `extra`:

```python
logger.warning("Retrying email send", extra={"to": email, "attempt": 2, "reason": "timeout"})
```

These appear under the `"extra"` key in JSON output.

### Context propagation (request_id & user_id)

Both values are stored in `ContextVar` — isolated per asyncio task, so concurrent requests never interfere:

```python
from app.core.logger import request_id_ctx, user_id_ctx
```

- **`request_id_ctx`** is set automatically by the Request ID middleware for every HTTP request.
- **`user_id_ctx`** is set automatically by `get_current_user_session` / `get_current_user_session_ws` dependencies when the user is authenticated.

You do **not** need to pass these manually — every log call within a request automatically includes them.

### Shutdown

Call `stop_logger()` during application shutdown to flush the listener queue:

```python
from app.core.logger import stop_logger

stop_logger()
```

This is already handled in the application lifespan (`main.py`).

---

## Exception Handling (`exceptions.py`)

### `AppHTTPException`

Extends FastAPI's `HTTPException` with extra fields for RFC 7807-style error responses:

| Field             | Type                           | Description                              |
| ----------------- | ------------------------------ | ---------------------------------------- |
| `status_code`     | `int`                          | HTTP status code                         |
| `detail`          | `str \| None`                  | Human-readable error explanation         |
| `title`           | `str \| None`                  | Short summary (defaults to "Application Error") |
| `errors`          | `Sequence \| dict \| None`     | Structured error details (e.g. validation) |
| `meta_extensions` | `dict \| None`                 | Arbitrary metadata to include in response |

### `register_exception_handlers(app)`

Registers three global handlers on the FastAPI app:

| Exception                | Status | Behavior                                                               |
| ------------------------ | ------ | ---------------------------------------------------------------------- |
| `StarletteHTTPException` | varies | Wraps into `AppHTTPException`, returns standard error envelope         |
| `RequestValidationError` | 422    | Sanitizes pydantic errors (strips non-serializable `ctx` values), returns error envelope |
| `Exception` (catch-all)  | 500    | Logs the error, returns generic "Internal Server Error" envelope       |

All handlers use `ResponseFactory` to produce a consistent `ErrorContent` JSON body.

---

## Response Formatting (`response.py`)

### `ResponseFactory`

Constructed per-request (receives the `Request` object). Automatically attaches the `X-Request-ID` to every response `meta`.

#### `success(data, status_code=200, headers=None, meta_extensions=None)`

Returns a `JSONResponse` with body:

```json
{
  "data": { ... },
  "meta": { "timestamp": "...", "success": true, "request_id": "..." }
}
```

#### `error(exc: HTTPException)`

Returns a `JSONResponse` with RFC 7807-based body:

```json
{
  "type": "https://httpstatuses.io/{status}",
  "title": "...",
  "status": 422,
  "detail": "...",
  "instance": "/api/...",
  "errors": [ ... ],
  "meta": { "timestamp": "...", "success": false, "request_id": "..." }
}
```

### FastAPI dependency

```python
from app.core import get_response_factory, ResponseFactory

@router.get("/items")
async def list_items(response_factory: ResponseFactory = Depends(get_response_factory)):
    return response_factory.success(data={"items": []})
```

Or use the pre-built annotated type:

```python
from app.core.dependencies import ResponseFactoryDep

@router.get("/items")
async def list_items(response_factory: ResponseFactoryDep):
    ...
```

---

## Middleware (`middleware.py`)

`add_middlewares(app)` registers all middleware in order:

1. **CORS** — configured from `Settings.CORS_*` variables.
2. **Metrics** — tracks request count, latency, and errors (see [Metrics](#metrics-metrics) below).
3. **Request ID** — reads `X-Request-ID` from the incoming header or generates a UUID v4. Stores it in `request.state.request_id`, sets `request_id_ctx` for log propagation, and echoes it back in the response header.
4. **Device Info** — parses `User-Agent`, `Sec-CH-UA`, `Sec-CH-UA-Platform`, and `Sec-CH-UA-Mobile` headers into a `SessionDeviceInfo` object stored in `request.state.device_info`.
5. **Security Headers** — sets `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: strict-origin-when-cross-origin` on all responses.
6. **Rate Limiting** — stub middleware targeting `/api/auth/login` and `/api/auth/register` (not yet implemented — see [Known Security Limitations](#known-security-limitations)).

---

## HTTP Utilities (`http/`)

### `SessionDeviceInfo` (schema)

| Field         | Type               |
| ------------- | ------------------ |
| `user_agent`  | `str \| None`      |
| `ip_address`  | `str \| None`      |
| `device_type` | `DeviceType \| None` (MOBILE / TABLET / DESKTOP) |
| `os`          | `str \| None`      |
| `browser`     | `str \| None`      |
| `app_version` | `str \| None`      |

`fingerprint()` returns a string like `"desktop | macOS | Chrome"` for session identification.

### `get_device_info(request)`

Extracts device metadata from Client Hints and User-Agent headers. Used by the device info middleware.

---

## Security (`security.py`)

### `PasswordSecurity`

Uses **Argon2** hashing via `passlib`.

| Method                  | Description                                |
| ----------------------- | ------------------------------------------ |
| `generate_password_hash(password)` | Hash a plaintext password       |
| `verify_password(plain, hashed)`   | Verify a password against its hash |
| `needs_rehash(hashed)`             | Check if the hash needs upgrading  |
| `generate_token_hash(token)`       | Hash an arbitrary token string     |
| `verify_token_hash(token, hashed)` | Verify a token against its hash    |

### `JWTService`

Handles JWT creation and verification using `PyJWT`.

| Method                   | Description                                               |
| ------------------------ | --------------------------------------------------------- |
| `create_access_token(user_id, roles, session_id)`  | Short-lived access token       |
| `create_refresh_token(user_id, roles, session_id)` | Long-lived refresh token       |
| `decode_access_token(token)`  | Decode + validate type is `"access"` (uses access signing key) |
| `decode_refresh_token(token)` | Decode + validate type is `"refresh"` (uses refresh signing key) |
| `hash_token(token)`           | Argon2-hash a token (e.g. for DB storage)           |

#### Token payload

| Claim  | Value                              |
| ------ | ---------------------------------- |
| `sub`  | User UUID                          |
| `roles`| List of role names                 |
| `exp`  | Expiration datetime                |
| `iat`  | Issued-at datetime                 |
| `iss`  | `project_identifier`               |
| `aud`  | `project_client_identifier`        |
| `type` | `"access"` or `"refresh"`          |
| `sid`  | Session UUID                       |

Decoding validates `iss`, `aud`, and `exp` automatically. Raises `ValueError` on expired or invalid tokens.

### FastAPI dependencies

```python
from app.core.dependencies import JWTServiceDep, PasswordSecurityDep

@router.post("/login")
async def login(jwt: JWTServiceDep, pwd: PasswordSecurityDep):
    ...
```

---

## Decorators (`decorators.py`)

### `@require_dto(*dto_types)`

Service-layer guard that validates the `data`/`dto` keyword argument (or last positional argument) is an instance of the specified Pydantic model types. Raises `TypeError` if the check fails.

```python
from app.core.decorators import require_dto

@require_dto(CreateUserDTO)
async def create_user(data: CreateUserDTO):
    ...
```

---

## Schemas (`schemas.py`)

### `BaseDTO`

Base Pydantic model with `extra = "forbid"` — rejects any unexpected fields in the request body.

```python
from app.core.schemas import BaseDTO

class CreateItemDTO(BaseDTO):
    name: str
```

---

## Metrics (`metrics/`)

Built on `prometheus_client` with a custom `Prometheus` abstraction that manages metric registration and serialization.

### Pre-registered metrics (`global_metrics.py`)

| Metric name                        | Type      | Labels                              | Description                       |
| ---------------------------------- | --------- | ----------------------------------- | --------------------------------- |
| `app_requests_total`               | Counter   | `method`, `endpoint`, `status`      | Total HTTP requests               |
| `app_request_latency_seconds`      | Histogram | `method`, `endpoint`                | HTTP request latency              |
| `app_errors_total`                 | Counter   | `endpoint`, `exception_type`        | Total application errors          |
| `system_memory_usage_percentage`   | Gauge     | `type` (used / free)                | System memory usage %             |
| `system_cpu_usage_percentage`      | Gauge     | —                                   | System CPU usage %                |
| `background_job_runs_total`        | Counter   | `job_name`                          | Background job execution count    |
| `background_job_failures_total`    | Counter   | `job_name`                          | Background job failure count      |
| `background_job_duration_seconds`  | Histogram | `job_name`                          | Background job duration           |
| `db_postgres_poolsize`             | Gauge     | —                                   | Total connections in the pool     |
| `db_postgres_pool_checked_out`     | Gauge     | —                                   | Connections currently in use      |
| `db_postgres_pool_overflow`        | Gauge     | —                                   | Connections beyond pool size      |
| `db_postgres_query_duration_seconds` | Histogram | `operation`                       | PostgreSQL query execution time   |
| `db_mongo_command_duration_seconds`  | Histogram | `command`, `collection`           | MongoDB command execution time    |

### Middleware (`metrics_middleware.py`)

Automatically records `app_requests_total`, `app_request_latency_seconds`, and `app_errors_total` for every HTTP request.

### Background task (`metrics_background_tasks.py`)

`update_system_metrics()` runs in an infinite loop (every 5 s), updating memory/CPU gauges via `psutil` and Postgres connection pool gauges (`db_postgres_poolsize`, `db_postgres_pool_checked_out`, `db_postgres_pool_overflow`) from the SQLAlchemy `QueuePool`. It receives the `AsyncEngine` as a parameter — wired in `main.py` — so `core/` never imports from `db/`.

### Database metrics in domains

Database query/command metrics are collected at the `db/` layer, **not** inside `core/`. The metrics objects are defined in `core/metrics/global_metrics.py`, but the instrumentation lives in:

- **Postgres** — `app/db/postgres/engine.py` uses SQLAlchemy `event.listens_for` hooks (`before_cursor_execute` / `after_cursor_execute`) to observe `db_postgres_query_duration_seconds` per SQL operation (SELECT, INSERT, UPDATE, DELETE).
- **MongoDB** — `app/db/mongo/monitoring.py` implements a `pymongo.monitoring.CommandListener` to observe `db_mongo_command_duration_seconds` per command and collection.

This keeps the dependency direction correct: `db/` imports metric objects from `core/`, never the other way around.

#### Using metrics inside a domain

Domains can import and use any metric from `global_metrics.py`, or register new domain-specific metrics via the `prometheus` singleton:

```python
from app.core.metrics.global_metrics import request_count

# Use a pre-registered metric
request_count.labels(method="POST", endpoint="/api/tickets", status="201").inc()
```

To register a new domain-specific metric:

```python
from app.core.metrics.prometheus import prometheus

tickets_created = prometheus.register_counter(
    "domain_tickets_created_total",
    "Total tickets created",
    ["criticality"],
)

# Then use it in your service
tickets_created.labels(criticality="high").inc()
```

**Naming convention:** prefix domain metrics with `domain_` to distinguish them from infrastructure metrics (`app_`, `db_`, `system_`).

### `@track_background_job(job_name)` decorator

Wraps any async function to automatically increment `background_job_runs_total`, record `background_job_duration_seconds`, and count `background_job_failures_total` on exception.

```python
from app.core.metrics import track_background_job

@track_background_job("send_emails")
async def send_emails():
    ...
```

### Endpoints (`metrics_router.py`)

| Route               | Description                                           |
| -------------------- | ----------------------------------------------------- |
| `GET /metrics`       | All Prometheus metrics in text exposition format       |
| `GET /metrics/{prefix}` | Only metrics whose name starts with `prefix`       |

---

## Background Tasks (`background_tasks.py`)

`global_background_tasks()` returns a list of `asyncio.Task` objects that are started during the application lifespan. Currently registers:

- `update_system_metrics` — periodic CPU/memory gauge updates.

Tasks are cancelled and awaited during shutdown.

---

## Router Registration (`init_routers.py`)

`initiate_routers(app)` mounts all routers onto the FastAPI application:

| Router           | Prefix   |
| ---------------- | -------- |
| `metrics_router` | `/`      |
| `health_router`  | `/`      |
| `api_router`     | `/api`   |

It also defines the root `GET /` endpoint that returns the project name, status, and environment.

---

## Known Security Limitations

The following security improvements are **deferred for a future release**:

| # | Severity | Issue | Notes |
|---|----------|-------|-------|
| 2 | 🔴 Critical | Hardcoded JWT secret default | `config.py` uses a placeholder if env vars are missing. Add startup validation before production. |
| 3 | 🟠 High | No rate limiting on login/register | Middleware stub exists but is not implemented. Recommend Redis-backed sliding window. |
| 11 | 🔵 Low | HS256 symmetric algorithm | Consider RS256/ES256 for microservice architectures. |
