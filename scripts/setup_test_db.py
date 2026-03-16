#!/usr/bin/env python3
"""
Script to set up the test database and apply migrations.

This script should be run before executing tests to ensure the test database
is in a clean state with all migrations applied.

Usage:
    python scripts/setup_test_db.py
"""

import asyncio
import re
import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import Settings


def validate_db_name(db_name: str) -> str:
    bd_name_re = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")
    if not bd_name_re.match(db_name):
        raise ValueError(f"Invalid database name: {db_name!r}")
    return db_name


async def drop_and_recreate_test_database(settings: Settings) -> None:
    """Drop and recreate the test database completely."""
    print(f"Setting up test database: {settings.postgres_db_test}")
    db_name = validate_db_name(settings.postgres_db_test)

    engine = create_async_engine(settings.database_server_url, isolation_level="AUTOCOMMIT")

    try:
        async with engine.connect() as conn:
            print("Terminating existing connections...")
            await conn.execute(
                text("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = :dbname
                AND pid <> pg_backend_pid();
            """),
                {"dbname": db_name},
            )

            print(f"Dropping database {settings.postgres_db_test}...")
            await conn.execute(text(f"DROP DATABASE IF EXISTS {settings.postgres_db_test};"))

            print(f"Creating database {settings.postgres_db_test}...")
            await conn.execute(text(f"CREATE DATABASE {settings.postgres_db_test};"))
    finally:
        await engine.dispose()


def apply_migrations(settings: Settings) -> None:
    """Apply Alembic migrations to the test database."""
    print("Applying migrations...")

    alembic_config = Config("alembic.ini")

    sync_test_url = settings.test_database_url

    alembic_config.set_main_option("sqlalchemy.url", sync_test_url)

    if "test" not in sync_test_url:
        raise ValueError("Migration must use test database URL")

    command.upgrade(alembic_config, "head")
    print("Migrations applied successfully!")


if __name__ == "__main__":
    settings = Settings()

    # Run async database setup
    asyncio.run(drop_and_recreate_test_database(settings))

    # Run migrations (sync, handles its own async internally)
    apply_migrations(settings)

    print("\n✅ Test database setup complete!")
    print(f"   Database: {settings.postgres_db_test}")
    print(f"   URL: {settings.test_database_url}")
