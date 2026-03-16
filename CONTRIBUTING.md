# Contributing Guide

Guidelines and conventions for contributing to the SyncDesk project.

---

## Table of Contents

- [Project Architecture](#project-architecture)
- [Domain Modules](#domain-modules)
- [Layered Architecture & Separation of Concerns](#layered-architecture--separation-of-concerns)
- [Naming Conventions](#naming-conventions)
- [Entities vs Models](#entities-vs-models)
- [Repositories](#repositories)
- [Services](#services)
- [Routers](#routers)
- [Schemas & DTOs](#schemas--dtos)
- [Dependency Injection](#dependency-injection)
- [Exceptions](#exceptions)
- [Database Migrations](#database-migrations)
- [Logging](#logging)
- [Metrics](#metrics)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Import & Export Conventions](#import--export-conventions)
- [Commit & PR Guidelines](#commit--pr-guidelines)

---

## Project Architecture

The codebase follows a **domain-driven modular structure**. Business features live under `app/domains/`, while cross-cutting infrastructure lives under `app/core/` and `app/db/`.

```
app/
├── core/       # Infrastructure: config, logging, security, middleware, metrics
├── db/         # Database engine, session, shared exceptions
├── domains/    # Feature modules (auth, health, …)
├── schemas/    # Shared response envelope schemas
├── api/        # Versioned API router aggregation
└── seed/       # Database seed scripts
```

Each layer has a single responsibility. Never import upward (e.g., `core/` must not import from `domains/`).

---

## Domain Modules

Each business feature is a self-contained module under `app/domains/`. A full-featured domain follows this structure:

```
domains/{feature}/
├── __init__.py          # Exports routers only
├── dependencies.py      # FastAPI DI wiring
├── entities.py          # Domain dataclasses (no ORM)
├── enums.py             # Enums for the domain
├── exceptions.py        # Domain-specific exceptions
├── models.py            # SQLAlchemy ORM models
├── types.py             # Custom types (NewType aliases)
├── README.md            # Domain documentation
├── repositories/
│   └── {resource}_repository.py
├── routers/
│   └── {resource}_router.py
├── schemas/
│   ├── __init__.py      # Re-exports all schemas
│   ├── api_schemas.py   # API request/response shapes
│   └── {resource}_schemas.py
└── services/
    └── {resource}_service.py
```

Simple domains (like `health`) can flatten this — a single `routers.py` is fine when there are no repositories or complex logic.

**When creating a new domain:**

1. Create the folder under `app/domains/`.
2. Define models, entities, enums, and exceptions.
3. Write the repository, service, and router layers.
4. Wire dependencies in `dependencies.py`.
5. Export routers from `__init__.py`.
6. Register routers in `app/api/api_router.py`.
7. Create an Alembic migration for any new tables.
8. Add a `README.md` documenting the domain.

---

## Layered Architecture & Separation of Concerns

The data flow follows strict layers:

```
Router → Service → Repository → Database
```

| Layer        | Responsibility                                          | Can depend on            |
| ------------ | ------------------------------------------------------- | ------------------------ |
| **Router**   | HTTP handling, request/response shapes, status codes     | Service, Schemas, ResponseFactory |
| **Service**  | Business logic, orchestration, validation                | Repository, Entities     |
| **Repository** | Database access, ORM queries, entity mapping           | Models, Entities, DB session |
| **Entity**   | Domain objects, business rules (no I/O)                  | Nothing (pure domain)    |
| **Model**    | ORM table definitions (no business logic)                | Base                     |

**Rules:**

- **Routers** never access the database directly — always go through a service.
- **Services** never import SQLAlchemy or ORM models — they work with entities and DTOs.
- **Repositories** map between ORM models and domain entities. They own the `_to_entity()` conversion.
- **Entities** are pure Python dataclasses. They must not depend on FastAPI, SQLAlchemy, or any framework.
- **Models** define the database schema. They have no business logic.

---

## Naming Conventions

### Files

| Type          | Pattern                       | Example                    |
| ------------- | ----------------------------- | -------------------------- |
| Repository    | `{resource}_repository.py`    | `user_repository.py`       |
| Service       | `{resource}_service.py`       | `user_service.py`          |
| Router        | `{resource}_router.py`        | `user_router.py`           |
| Schemas       | `{resource}_schemas.py`       | `user_schemas.py`          |
| API schemas   | `api_schemas.py`              | `api_schemas.py`           |
| Domain shared | Singular name                 | `models.py`, `entities.py`, `enums.py` |

### Classes

| Type          | Pattern                       | Example                          |
| ------------- | ----------------------------- | -------------------------------- |
| Entity        | `{Entity}`                    | `User`, `Session`, `UserWithRoles` |
| Model         | `{Entity}`                    | `User`, `Role`, `Permission`     |
| Repository    | `{Entity}Repository`          | `UserRepository`                 |
| Service       | `{Entity}Service`             | `UserService`, `AuthService`     |
| Create DTO    | `Create{Entity}DTO`           | `CreateUserDTO`                  |
| Update DTO    | `Update{Entity}DTO`           | `UpdateUserDTO`                  |
| Replace DTO   | `Replace{Entity}DTO`          | `ReplaceUserDTO`                 |
| API request   | `{Entity}{Action}Request`     | `UserLoginRequest`               |
| API response  | `{Action}Response`            | `LoginResponse`                  |
| Exception     | `{Description}Error`          | `UserNotFoundError`              |
| DI alias      | `{Entity}{Type}Dep`           | `UserServiceDep`, `PgSessionDep` |

### Functions and Variables

- **snake_case** for all functions and variables.
- **Repository methods**: `create()`, `get_all()`, `get_by_id()`, `get_by_{field}()`, `update()`, `delete()`, `get_with_{relation}()`, `add_{relation}()`.
- **DI factory functions**: `get_{resource}_{type}()` — e.g., `get_user_repository()`, `get_user_service()`.
- **Router handlers**: descriptive verb + noun — e.g., `create_user()`, `get_users()`, `update_user()`.
- **Private helpers**: prefix with `_` — e.g., `_to_entity()`, `_create_tables()`.

### Router variables

Router instances are **lowercase snake_case**: `user_router`, `auth_router`, `metrics_router`.

---

## Entities vs Models

The project separates **domain entities** from **ORM models**:

### Entities (`entities.py`)

- Python `@dataclass` classes — no SQLAlchemy imports.
- Contain business logic methods (e.g., `is_expired()`, `can_login()`, `matches_device_fingerprint()`).
- Validation helpers (e.g., `validate_email()`, `validate_username()`).
- Serialization helpers (e.g., `to_response_dict()`).
- Can compose other entities (e.g., `UserWithRoles` has a list of `Role`).

### Models (`models.py`)

- SQLAlchemy 2.0 classes using `Mapped[]` types and inheriting from `Base`.
- Define the database schema: table name, columns, foreign keys, indexes, relationships.
- **No business logic** — they are pure schema definitions.

### Why

This decouples domain logic from the persistence layer. Services and business rules operate on entities, making them testable without a database.

---

## Repositories

Repositories encapsulate all database access for a given resource.

### Structure

```python
class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @require_dto(CreateUserDTO)
    async def create(self, dto: CreateUserDTO) -> User:
        # Insert + commit + return entity
        ...

    async def get_by_id(self, user_id: UUID) -> User | None:
        # Query + map to entity
        ...

    def _to_entity(self, row: Row[Any]) -> User:
        # Map ORM row to entity dataclass
        ...
```

### Conventions

- Accept DTOs or primitive types as input, return **entities** (never ORM models).
- Use `@require_dto()` to guard mutation methods.
- Catch `IntegrityError` and raise `ResourceAlreadyExistsError` for unique constraint violations.
- Call `await self.db.commit()` after write operations.
- Private `_to_entity()` method handles the mapping from database rows to domain entities.

---

## Services

Services contain business logic and orchestrate repositories.

### Structure

```python
class UserService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def create(self, dto: CreateUserDTO) -> User:
        return await self.user_repository.create(dto)

    async def get_by_id(self, user_id: UUID) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        return user
```

### Conventions

- Receive **repositories** (not sessions) via constructor.
- Work with **entities and DTOs** — never import SQLAlchemy or ORM models.
- Raise **domain-specific exceptions** when business rules are violated.
- Complex services (like `AuthService`) can depend on multiple other services.
- Keep methods focused — one action per method.

---

## Routers

Routers handle HTTP concerns: parsing requests, calling services, formatting responses.

### Structure

```python
router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED, responses=create_responses)
async def create_user(
    body: RegisterUserRequest,
    service: UserServiceDep,
    response: ResponseFactoryDep,
    _auth: CurrentUserSessionDep,
    _perm: bool = require_permission("user:create"),
) -> JSONResponse:
    try:
        user = await service.create(CreateUserDTO(**body.model_dump()))
        return response.success(data=user.to_response_dict(), status_code=status.HTTP_201_CREATED)
    except ResourceAlreadyExistsError:
        raise AppHTTPException(status_code=409, title="Conflict", detail="Email already exists")
```

### Conventions

- Always use `ResponseFactory` to build responses — never return raw dicts.
- Convert domain exceptions to `AppHTTPException` with appropriate HTTP status codes.
- Use `Annotated[..., Depends()]` type aliases (e.g., `UserServiceDep`) for clean signatures.
- Use `require_permission("resource:action")` for authorization.
- Prefix unused auth/permission dependencies with `_` (e.g., `_auth`, `_perm`).
- Document responses with a `responses` dict for OpenAPI.
- Use appropriate status codes: `201` for creation, `200` for success, `204` for no content.

---

## Schemas & DTOs

### Internal DTOs (`{resource}_schemas.py`)

- Inherit from `BaseDTO` (which sets `extra = "forbid"` — rejects unexpected fields).
- `CreateDTO`: all required fields for creation.
- `UpdateDTO`: all fields optional (partial update).
- `ReplaceDTO`: extends `CreateDTO` (full replacement).
- Use Pydantic validators (`@field_validator`, `@model_validator`) for input validation.

### API Schemas (`api_schemas.py`)

- Inherit from `BaseModel` (not `BaseDTO`).
- Define the shape of HTTP request bodies and response data.
- `{Entity}{Action}Request` for input, `{Action}Response` for output.

### Export

All schemas for a domain are re-exported from `schemas/__init__.py` with `__all__`.

---

## Dependency Injection

All DI wiring for a domain lives in `dependencies.py`.

### Pattern

```python
# Repository → needs DB session
def get_user_repository(db: PgSessionDep) -> UserRepository:
    return UserRepository(db)

# Service → needs repository
def get_user_service(
    repo: Annotated[UserRepository, Depends(get_user_repository)]
) -> UserService:
    return UserService(repo)

# Type alias for routers
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
```

### Conventions

- One factory function per dependency: `get_{resource}_{type}()`.
- Export `Annotated` type aliases (`{Resource}{Type}Dep`) for use in routers.
- Async dependencies for anything requiring I/O (e.g., auth validation).
- Permission checking uses higher-order functions (`require_permission(name)`).

---

## Exceptions

### Domain exceptions (`exceptions.py` in each domain)

- Inherit from `Exception`.
- Include a default error message with optional context.
- Naming: `{Description}Error` (e.g., `UserNotFoundError`, `InvalidCredentialsError`).

### Shared database exceptions (`app/db/exceptions.py`)

- `ResourceAlreadyExistsError(resource_name, identifier)` — for unique constraint violations.
- `ResourceNotFoundError(resource_name, identifier)` — for missing resources.

### Converting to HTTP errors

In routers, catch domain exceptions and raise `AppHTTPException`:

```python
except UserNotFoundError:
    raise AppHTTPException(status_code=404, title="Not Found", detail="User not found")
```

Never let domain exceptions leak to the client unhandled. The global exception handler catches anything unhandled and returns a generic 500 response, but explicit handling is preferred.

---

## Database Migrations

Migrations are managed with Alembic. See [alembic/README](alembic/README) for full CLI reference.

### Workflow

1. **Modify the SQLAlchemy model** in the domain's `models.py`.
2. **Generate a migration**: `make makemigration m="describe the change"`.
3. **Review** the generated file in `alembic/versions/` — autogenerate can miss column renames, enum changes, custom functions, and triggers.
4. **Apply**: `make migrate`.
5. **Test both directions**: verify `upgrade` and `downgrade` work.

### Rules

- **Always implement `downgrade()`** — every migration must be reversible.
- **One logical change per migration** — don't combine unrelated schema changes.
- **Never edit a migration that has been applied** to shared environments. Create a new one to fix issues.
- **Manual SQL** is required for triggers, functions, extensions, and enum types. Autogenerate won't handle these.
- **Update the seed** (`app/seed/seed.py`) if the migration adds tables that need default data.

### Development mode caveat

When `ENVIRONMENT=development`, the app auto-creates and drops all tables on startup via `init_postgres_db()`. This bypasses Alembic entirely. For anything beyond throwaway local dev, always use migrations.

---

## Logging

Use the project's `AsyncLogger` — never use `print()` or raw `logging`.

```python
from app.core.logger import get_logger

logger = get_logger()
logger.info("User created", extra={"user_id": str(user.id)})
logger.error("Payment failed", extra={"order_id": order_id})
```

### Rules

- Use **structured data** via `extra={}` — don't concatenate variables into the message string for context.
- Use appropriate levels: `debug` for development trace, `info` for business events, `warning` for recoverable issues, `error` for failures.
- **Never log sensitive data**: passwords, tokens, full credit card numbers, or personal data.
- Logs are JSON — keep messages short and machine-parseable.
- The logger is a singleton (`@lru_cache`). Import `get_logger` where needed.

---

## Metrics

The project uses Prometheus metrics via the `app.core.metrics` module.

### Adding request metrics

HTTP request metrics (count, latency, errors) are collected **automatically** by the metrics middleware. No action is needed for new endpoints.

### Adding custom metrics

1. Register the metric in `app/core/metrics/global_metrics.py`:

   ```python
   order_count = prometheus.register_counter(
       "app_orders_total", "Total orders placed", ["status"]
   )
   ```

2. Use it in your service or repository:

   ```python
   from app.core.metrics.global_metrics import order_count

   order_count.labels(status="completed").inc()
   ```

### Background job metrics

Wrap any background async function with `@track_background_job("job_name")` to automatically track run count, failures, and duration.

### Naming convention

- Prefix all metrics with `app_` for application metrics.
- Use `_total` suffix for counters, `_seconds` for histograms measuring time, `_percentage` for gauges measuring percentages.

---

## Testing

### Structure

```
tests/
├── conftest.py          # Global fixtures (DB, client, app)
├── app/
│   ├── e2e/
│   │   ├── conftest.py  # E2E-specific fixtures
│   │   └── domains/     # E2E tests per domain
│   └── integration/
│       └── domains/     # Integration tests per domain
```

### Conventions

- Tests run with `ENVIRONMENT=test`, targeting a separate `_test` database.
- Use the `client` fixture for HTTP-level tests (AsyncClient with ASGI transport).
- Use the `db_session` fixture for direct database operations in tests.
- **Each test is isolated** — the session is rolled back after every test.
- All test functions are `async def` and use `pytest-asyncio`.
- Name test files `test_{feature}.py` and test functions `test_{what_it_tests}`.

### Running

```bash
make test          # Full suite with coverage
make test-e2e      # E2E tests only
```

### Writing tests

- **E2E tests**: Hit real endpoints via `client`, assert on HTTP status + response body.
- **Integration tests**: Test service/repository logic with a real database (via `db_session`).
- Test both success paths and error paths (invalid input, missing resources, permission denied).
- Override dependencies with `app.dependency_overrides[original] = replacement` when needed.

---

## Code Quality

### Pre-commit hooks

Install once:

```bash
poetry run pre-commit install
```

Hooks run automatically on every commit: Ruff (lint + format), mypy, Bandit.

### Manual checks

```bash
make lint          # Ruff + Bandit
make format        # Auto-format
make typecheck     # mypy strict mode
make pre-commit    # All of the above + tests
```

### Rules

- **Ruff** handles linting and formatting. Line length is 100. Target is Python 3.12.
- **mypy** runs in strict mode. All functions must have type annotations.
- **Bandit** scans for security issues. Don't suppress warnings without justification.
- Fix all lint/type errors before pushing — CI will enforce the same checks.

---

## Import & Export Conventions

### Domain `__init__.py`

Export **only routers**. Everything else is accessed via direct imports within the domain.

```python
# app/domains/auth/__init__.py
from .routers.auth_router import auth_router
from .routers.user_router import user_router

__all__ = ["auth_router", "user_router"]
```

### Schema `__init__.py`

Re-export **all DTOs and schemas** for convenient single-point imports.

### Core `__init__.py`

Exports the public API surface that other modules depend on.

### General rules

- Use explicit `__all__` lists in every `__init__.py`.
- Prefer relative imports within a module (`from .models import User`).
- Use absolute imports when crossing module boundaries (`from app.db import PgSessionDep`).

---

## Commit & PR Guidelines

- Write clear, concise commit messages describing **what** changed and **why**.
- Keep commits focused — one logical change per commit.
- Run `make pre-commit` before pushing.
- PRs should include tests for new features and bug fixes.
- Update the domain's `README.md` if the change affects behavior or API contracts.
- If adding a new domain, include documentation from the start.
