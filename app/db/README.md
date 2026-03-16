# db/ Module

Database layer for the application, providing:

- Async PostgreSQL support via SQLAlchemy.
- Async MongoDB support via Motor.

## Structure

```
db/
├── __init__.py          # Public API re-exports for Postgres and MongoDB
├── exceptions.py        # Shared database exceptions
├── mongo/
│   ├── db.py            # MongoDB client/database singleton and connect/disconnect
│   └── dependencies.py  # FastAPI MongoDB dependency
└── postgres/
    ├── base.py          # SQLAlchemy DeclarativeBase for all models
    ├── dependencies.py  # FastAPI session dependency
    ├── engine.py        # Engine and session factory configuration
    └── init_db.py       # Database initialization and teardown
```

## Public API

Everything needed by external modules is re-exported from `app.db`:

```python
from app.db import (
    init_postgres_db,
    close_postgres_db,
    PgSessionDep,
    mongo_db,
    MongoSessionDep,
)
```

| Symbol              | Type                     | Description                                                                 |
| ------------------- | ------------------------ | --------------------------------------------------------------------------- |
| `init_postgres_db`  | `async () -> None`       | Creates the database if it doesn't exist, then creates all Postgres tables. |
| `close_postgres_db` | `async () -> None`       | Disposes of the Postgres engine connection pool.                            |
| `PgSessionDep`      | FastAPI `Annotated` type | Inject an `AsyncSession` into route handlers via `Depends`.                 |
| `mongo_db`          | `MongoDb` singleton      | Shared MongoDB client/database holder with connect/disconnect.              |
| `MongoSessionDep`   | FastAPI `Annotated` type | Inject a Motor `AsyncIOMotorDatabase` into route handlers via `Depends`.    |

## Configuration

Connection settings are read from `app.core.config.get_settings()`.

### PostgreSQL

Relevant environment variables:

| Variable            | Default       |
| ------------------- | ------------- |
| `POSTGRES_USER`     | `postgres`    |
| `POSTGRES_PASSWORD` | `postgres`    |
| `POSTGRES_HOST`     | `localhost`   |
| `POSTGRES_PORT`     | `5432`        |
| `POSTGRES_DB`       | `syncdesk_db` |

These are composed into an `asyncpg` connection URL:

```
postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}
```

### MongoDB (Motor)

Relevant environment variables:

| Variable         | Default       |
| ---------------- | ------------- |
| `MONGO_USER`     | `""` (empty)  |
| `MONGO_PASSWORD` | `""` (empty)  |
| `MONGO_HOST`     | `localhost`   |
| `MONGO_PORT`     | `27017`       |
| `MONGO_DB`       | `syncdesk_db` |

MongoDB connection URL rules:

- If `MONGO_USER` and `MONGO_PASSWORD` are set:

```
mongodb://{user}:{password}@{host}:{port}/{db}
```

- Otherwise:

```
mongodb://{host}:{port}/{db}
```

## Lifecycle

### Startup — `init_postgres_db()`

Called during the FastAPI lifespan (in development mode). It:

1. Connects to the default `postgres` database with `AUTOCOMMIT` isolation.
2. Checks `pg_database` for the target database name. If it's missing, creates it.
3. Connects to the target database and recreates all tables (`drop_all` + `create_all` from `Base.metadata`).
4. Retries the full process up to **10 times** (with 500 ms delay) if any connection error occurs.

> **Warning:** `init_postgres_db` drops and recreates all tables on every call. It is intended for development only. In production, use Alembic migrations.

### Startup — MongoDB connect

During app lifespan startup, `mongo_db.connect()` is called. It:

1. Creates an `AsyncIOMotorClient` using `settings.mongo_database_url`.
2. Selects the database `settings.MONGO_DB`.
3. Runs `ping` against `admin` to fail fast if MongoDB is unavailable.

### Shutdown — `close_postgres_db()`

Called when the application shuts down. Disposes the async engine, releasing all pooled connections.

### Shutdown — MongoDB disconnect

During app shutdown, `mongo_db.disconnect()` closes the Mongo client and clears in-memory references.

## Session Management

### Engine (`engine.py`)

A single `AsyncEngine` is created at module load with:

- `echo=True` — logs all SQL statements.
- `future=True` — enables SQLAlchemy 2.0 style.

The `async_session` factory produces sessions configured with:

- `autocommit=False`
- `autoflush=False`
- `expire_on_commit=False`

### Dependency (`dependencies.py`)

`get_postgres_session()` is an async generator that yields one `AsyncSession` per request and closes it at the end:

```python
async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as db_session:
        yield db_session
```

Use `PgSessionDep` as a type annotation in FastAPI route parameters to inject a session automatically:

```python
from app.db import PgSessionDep

@router.get("/items")
async def list_items(db: PgSessionDep):
    result = await db.execute(select(Item))
    return result.scalars().all()
```

For tests, override the dependency to use a test database session:

```python
from app.db.postgres.dependencies import get_postgres_session

app.dependency_overrides[get_postgres_session] = my_test_session_generator
```

### MongoDB Client + Dependency (`mongo/db.py`, `mongo/dependencies.py`)

`mongo_db` is a singleton with:

- `connect()` / `disconnect()` lifecycle methods.
- `get_db()` to retrieve the selected Motor database.

`get_mongo_session()` returns the active `AsyncIOMotorDatabase` from `mongo_db`.

Use `MongoSessionDep` to inject the database in route handlers:

```python
from app.db import MongoSessionDep

@router.get("/events")
async def list_events(db: MongoSessionDep):
    return await db["events"].find().to_list(length=100)
```

For tests, you can override the dependency:

```python
from app.db.mongo.dependencies import get_mongo_session

app.dependency_overrides[get_mongo_session] = my_test_mongo_session
```

## Defining Models

All SQLAlchemy models must inherit from `Base`:

```python
from app.db.postgres.base import Base
from sqlalchemy import Column, String

class Item(Base):
    __tablename__ = "items"
    id = Column(String, primary_key=True)
```

## Database Exceptions

`db.exceptions` provides two reusable exceptions for repository layers:

| Exception                    | Attributes                    | Message format                                                   |
| ---------------------------- | ----------------------------- | ---------------------------------------------------------------- |
| `ResourceAlreadyExistsError` | `resource_name`, `identifier` | `"{resource_name} with identifier {identifier} already exists"`  |
| `ResourceNotFoundError`      | `resource_name`, `identifier` | `"{resource_name} with identifier {identifier} does not exists"` |

Usage:

```python
from app.db.exceptions import ResourceNotFoundError

raise ResourceNotFoundError("User", user_id)
```
