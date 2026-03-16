# alembic/ — Database Migrations

Manages PostgreSQL schema migrations using [Alembic](https://alembic.sqlalchemy.org/) with async SQLAlchemy (`asyncpg`).

## Structure

```
alembic/
├── env.py               # Migration environment (async engine, metadata)
├── script.py.mako       # Template for new migration files
├── README               # This file
└── versions/            # Migration scripts (ordered by revision chain)
    └── aeca945a00f8_initial_schema.py
```

Configuration lives in `alembic.ini` at the project root.

## How It Works

### Connection URL

`env.py` reads the database URL from `app.core.config.Settings`:

- **default** → `settings.database_url` (main database)
- **test** (`ENVIRONMENT=test`) → `settings.test_database_url` (`{db}_test`)

No `sqlalchemy.url` is set in `alembic.ini` — the URL is resolved at runtime from environment variables / `.env`.

### Target Metadata

`env.py` imports `Base.metadata` from `app.db.postgres.base`. Alembic compares this metadata against the current database state when auto-generating migrations. **All SQLAlchemy models must inherit from `Base`** for their tables to be detected.

### Async Execution

The environment uses `create_async_engine` and runs migrations inside an async connection. Both online (connected to a live DB) and offline (SQL script generation) modes are supported.

## Quick Reference (Makefile)

```bash
# Apply all pending migrations
make migrate

# Auto-generate a new migration from model changes
make makemigration m="add_movies_table"
```

## CLI Commands

All commands are run from the project root. Replace `poetry run` with your runner if needed.

### Apply migrations

```bash
# Upgrade to the latest revision
poetry run alembic upgrade head

# Upgrade by one revision
poetry run alembic upgrade +1

# Upgrade to a specific revision
poetry run alembic upgrade aeca945a00f8
```

### Rollback migrations

```bash
# Downgrade by one revision
poetry run alembic downgrade -1

# Downgrade to a specific revision
poetry run alembic downgrade aeca945a00f8

# Downgrade all the way (empty database)
poetry run alembic downgrade base
```

### Create a new migration

```bash
# Auto-generate from model diff
poetry run alembic revision --autogenerate -m "describe the change"

# Create an empty migration (for manual SQL)
poetry run alembic revision -m "describe the change"
```

After generating, **always review the file** in `alembic/versions/` — autogenerate may miss or misdetect certain changes (e.g. column renames, custom types, triggers, indexes with expressions).

### Inspect current state

```bash
# Show current revision in the database
poetry run alembic current

# Show full migration history
poetry run alembic history --verbose

# Show pending (not yet applied) migrations
poetry run alembic heads
```

## Writing Migrations

### Auto-generated migrations

1. Modify your SQLAlchemy models (classes inheriting from `Base`).
2. Run `make makemigration m="description"`.
3. Review the generated file in `alembic/versions/`.
4. Run `make migrate` to apply.

### Manual migrations

For changes that autogenerate cannot detect — raw SQL, custom functions, triggers, enum types, extensions — create an empty revision and write the SQL yourself:

```bash
poetry run alembic revision -m "add updated_at trigger"
```

Then edit the generated file:

```python
def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION fn_set_updated_at() ...
    """)

def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fn_set_updated_at;")
```

### Guidelines

- **Always implement `downgrade()`**. Every `upgrade()` operation should have a corresponding rollback so migrations can be reversed safely.
- **Keep migrations atomic**. One logical change per migration file.
- **Use parameterized queries** with `op.execute(text(...), {...})` when interpolating values to avoid SQL injection. Static DDL strings (like `CREATE TABLE`) are fine as literals.
- **Test both directions**: run `alembic upgrade head` followed by `alembic downgrade base` to verify the full chain works.
- **Don't edit applied migrations**. If a migration has already been applied (to staging/production), create a new migration to fix issues — never modify the existing file.

## Initial Schema

The first migration (`aeca945a00f8_initial_schema`) sets up:

| Object                    | Type       | Description                                      |
| ------------------------- | ---------- | ------------------------------------------------ |
| `uuid-ossp`               | Extension  | UUID generation (`uuid_generate_v4()`)           |
| `fn_set_updated_at()`     | Function   | Trigger function for automatic `updated_at`      |
| `roles`                   | Table      | Role definitions (id, name, description)         |
| `permissions`             | Table      | Permission definitions (id, name, description)   |
| `role_permissions`        | Table      | Many-to-many: roles ↔ permissions                |
| `oauth_provider`          | Enum type  | `local`, `google`, `microsoft`                   |
| `users`                   | Table      | User accounts with OAuth support, soft delete    |
| `user_roles`              | Table      | Many-to-many: users ↔ roles                      |
| `session_status`          | Enum type  | `active`, `expired`, `invalid`, `revoked`        |
| `sessions`                | Table      | Auth sessions with refresh token hash, device info |
| `set_session_revoked_at()`| Function   | Trigger function to set `revoked_at` on revoke   |

The `downgrade()` drops everything in reverse order with `CASCADE`.
