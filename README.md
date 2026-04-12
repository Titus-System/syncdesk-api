# SyncDesk API

Backend and API Gateway built with **FastAPI**, **SQLAlchemy 2** (async), **PostgreSQL**, and **MongoDB (Motor)**.

## Tech Stack

| Layer        | Technology                            |
| ------------ | ------------------------------------- |
| Framework    | FastAPI 0.121+                        |
| Language     | Python 3.12+                          |
| Database     | PostgreSQL + asyncpg, MongoDB + Motor |
| ORM          | SQLAlchemy 2 (async)                  |
| Migrations   | Alembic                               |
| Auth         | JWT (PyJWT) + Argon2 password hashing |
| Metrics      | prometheus-client + psutil            |
| Package mgmt | Poetry                                |
| Linting      | Ruff, Bandit, mypy                    |
| Testing      | pytest + pytest-asyncio + httpx       |

## Project Structure

```
├── app/
│   ├── main.py              # FastAPI app factory + lifespan
│   ├── api/                  # Versioned API router
│   ├── core/                 # Config, logging, security, middleware, metrics
│   ├── db/                   # Database engines, dependencies, exceptions (Postgres + MongoDB)
│   ├── domains/              # Feature modules (auth, health, …)
│   ├── schemas/              # Shared response schemas
│   └── seed/                 # Database seed scripts
├── alembic/                  # Database migrations
├── tests/                    # Test suite (unit, integration, e2e)
├── logs/                     # JSON log files (auto-created)
├── scripts/                  # Utility scripts
├── alembic.ini               # Alembic configuration
├── pyproject.toml            # Poetry config, tool settings
├── Makefile                  # Common commands
└── run.py                    # Dev entry point
```

Each sub-module has its own README with detailed documentation:

- [app/core/README.md](app/core/README.md) — configuration, logging, security, middleware, metrics
- [app/db/README.md](app/db/README.md) — database layer, sessions, exceptions
- [app/domains/auth/README.md](app/domains/auth/README.md) — authentication, authorization, session management
- [alembic/README](alembic/README) — migration system and commands

---

## Prerequisites

- **Python 3.12+**
- **Poetry** (package manager) — [install guide](https://python-poetry.org/docs/#installation)
- **PostgreSQL** (running locally or in a container)
- **MongoDB** (running locally or in a container)
- **Docker + Docker Compose plugin** (recommended for quickest setup)

---

## Getting Started

### 1. Clone and install dependencies

```bash
git clone https://github.com/Titus-System/syncdesk-api.git
cd syncdesk-api
make install
# or: poetry install
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Use these values as a baseline for local development:

```dotenv
# .env

# Environment: development | test | production
ENVIRONMENT=development

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=syncdesk_db

# MongoDB
MONGO_USER=mongouser
MONGO_PASSWORD=mongopassword
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=syncdesk_db

# Mongo root user (required when Mongo runs via docker compose)
MONGO_INITDB_ROOT_USERNAME=mongouser
MONGO_INITDB_ROOT_PASSWORD=mongopassword

# JWT (change the secrets in any non-local environment)
JWT_SECRET_KEY=change-me-in-production
ACCESS_TOKEN_SIGNING_KEY=change-me-in-production
REFRESH_TOKEN_SIGNING_KEY=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=60
SESSION_EXPIRE_DAYS=180

# CORS (comma-separated origins, or * for all)
CORS_ALLOW_ORIGINS=["*"]

# Project metadata
PROJECT_NAME=SyncDesk API
PROJECT_VERSION=0.1.0
```

Full variable reference is in the [core/ docs](app/core/README.md#configuration-configpy).

Important:

- For Docker Compose, keep `MONGO_USER` / `MONGO_PASSWORD` equal to `MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`.
- The app authenticates MongoDB using `authSource=admin` when credentials are present.

### 3. Set up the databases

#### Option A: Local API run (with local DB services)

When `ENVIRONMENT=development`, the app:

- connects to MongoDB on startup,
- creates the PostgreSQL database if it does not exist,
- and runs Alembic migrations if the schema is behind `head`.

Start databases first (one simple option is using Compose only for DB services):

```bash
docker compose up -d db mongo
```

Then run the API locally:

```bash
make dev
```

#### Option B: Using Alembic migrations (recommended for staging/production)

```bash
# Apply all migrations
make migrate

# Seed initial roles and permissions
make seed
```

See [alembic/README](alembic/README) for full migration commands.

### 4. Run the server

```bash
# Development (with hot reload)
make dev

# Production
make run
```

The API will be available at **http://127.0.0.1:8000**.

- Interactive docs: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health check: `GET /`
- Metrics: `GET /metrics`

---

## Database Seeding

The seed script populates roles, permissions, and their associations:

```bash
make seed
```

Default seed data:

| Roles   | Permissions                                          |
| ------- | ---------------------------------------------------- |
| `admin` | All `user:*`, `role:*`, `permission:*` permissions   |
| `user`  | All `session:*` permissions (login, refresh, logout) |

---

## Running Tests

```bash
# All tests
make test

# E2E tests only
make test-e2e
```

Tests run with `ENVIRONMENT=test`, which targets a separate `{POSTGRES_DB}_test` database. Coverage is reported to the terminal.



---

## Running with Docker (API + PostgreSQL + MongoDB)

This project includes a complete Docker setup so all developers can run the same environment on any OS.

### 1. Prepare environment variables

If you do not have a `.env`, copy from `.env.example` and adjust values if needed.

Required database vars for Docker Compose:

```dotenv
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=syncdesk_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

MONGO_INITDB_ROOT_USERNAME=mongouser
MONGO_INITDB_ROOT_PASSWORD=mongopassword
MONGO_USER=mongouser
MONGO_PASSWORD=mongopassword
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=syncdesk_db
```

`POSTGRES_HOST` is automatically overridden to `db`, and `MONGO_HOST` to `mongo`, inside the API container.

`MONGO_INITDB_ROOT_*` is used to create the MongoDB root user on first startup. The API connects with `MONGO_USER`/`MONGO_PASSWORD` and authenticates against `admin`.

### 2. Start all services

```bash
docker compose up --build
```

To run in detached mode:

```bash
docker compose up -d --build
```

To follow API logs:

```bash
docker compose logs -f api
```

What happens automatically:

- PostgreSQL and MongoDB containers start and become healthy
- API container waits for PostgreSQL and MongoDB readiness
- Alembic runs: `alembic upgrade head`
- FastAPI starts on `http://localhost:8000`
- Prometheus starts collecting metrics from the API
- Grafana, Loki, AlertManager, and Promtail start for observability

### Access the services:

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://localhost:8000 | — |
| **API Docs** | http://localhost:8000/docs | — |
| **Grafana** | http://localhost:3000 | Username: `admin` / Password: `admin` |
| **Prometheus** | http://localhost:9090 | — |
| **AlertManager** | http://localhost:9093 | — |

**Grafana dashboards:** The "SyncDesk Overview" dashboard shows API health, latency, error rates, and logs. Access via Configuration → Dashboards.

If you previously changed Mongo credentials and still get `Authentication failed`, recreate containers and volumes once:

```bash
docker compose down -v
docker compose up --build
```

If ports are already in use locally, adjust host ports in `docker-compose.yaml`. See [deploy/README.md](deploy/README.md) for detailed observability stack documentation.

### 3. Stop services

```bash
docker compose down
```

To also remove Postgres and Mongo persisted data:

```bash
docker compose down -v
```

Data persistence behavior:

- `docker compose down` keeps DB data (named volumes are preserved)
- `docker compose down -v` removes DB data

Quick reset commands:

```bash
# Stop and keep data
docker compose down

# Stop and delete database data
docker compose down -v
```
---

## Code Quality

### Linting and formatting

```bash
# Lint (ruff + bandit)
make lint

# Auto-format
make format

# Type checking
make typecheck
```

### Pre-commit hooks

Pre-commit is configured with Ruff, mypy, and Bandit. Install the hooks once:

```bash
poetry run pre-commit install
```

Or run all checks manually (lint + format + typecheck + bandit + tests):

```bash
make pre-commit
```

---

## Makefile Reference

| Command                      | Description                                    |
| ---------------------------- | ---------------------------------------------- |
| `make install`               | Install all dependencies via Poetry            |
| `make dev`                   | Run dev server with hot reload                 |
| `make run`                   | Run production server                          |
| `make test`                  | Run full test suite with coverage              |
| `make test-e2e`              | Run end-to-end tests only                      |
| `make lint`                  | Run Ruff and Bandit linters                    |
| `make format`                | Auto-format code with Ruff                     |
| `make typecheck`             | Run mypy type checking                         |
| `make migrate`               | Apply all pending Alembic migrations           |
| `make makemigration m="msg"` | Auto-generate a new Alembic migration          |
| `make seed`                  | Seed roles, permissions, and associations      |
| `make pre-commit`            | Run all checks (lint + format + types + tests) |

---

## API Overview

All domain endpoints are mounted under `/api`:

| Prefix                    | Description                  |
| ------------------------- | ---------------------------- |
| `POST /api/auth/register` | User registration            |
| `POST /api/auth/login`    | Login (returns tokens)       |
| `POST /api/auth/refresh`  | Refresh token rotation       |
| `POST /api/auth/logout`   | Revoke session               |
| `GET  /api/auth/me`       | Current user profile         |
| `/api/users/`             | User management (CRUD)       |
| `/api/roles/`             | Role management (CRUD)       |
| `/api/permissions/`       | Permission management (CRUD) |
| `GET /`                   | Health check                 |
| `GET /metrics`            | Prometheus metrics           |
| `GET /metrics/{prefix}`   | Filtered metrics by prefix   |

All protected endpoints require a `Authorization: Bearer <access_token>` header. See the [auth docs](app/domains/auth/README.md) for full details on the authentication flow.

---

## Logging

Structured JSON logs are written to:

- `logs/app.json` — INFO and above
- `logs/error.json` — ERROR and above
- Console — DEBUG and above

Files rotate at 10 MB with 5 backups. See [core/ docs](app/core/README.md#logger-loggerpy) for details.

---

## Known Security Limitations

The following security improvements have been identified but are **deferred for a future release**:

| #   | Severity   | Issue                              | Notes                                                                                                                  |
| --- | ---------- | ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 2   | 🔴 Critical | Hardcoded JWT secret default       | `config.py` uses a placeholder if env vars are missing. Add startup validation before production deployment.           |
| 3   | 🟠 High     | No rate limiting on login/register | A middleware stub exists but is not yet implemented. Recommend a Redis-backed solution for multi-instance deployments. |
| 11  | 🔵 Low      | HS256 symmetric algorithm          | Consider RS256/ES256 for microservice architectures where verifying services should not hold the signing secret.       |
