import asyncio

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.logger import get_logger

from .engine import engine


async def init_postgres_db() -> None:
    for _ in range(10):
        try:
            await _create_db_if_not_exists()
            await _run_migrations()
            return
        except Exception as e:
            get_logger().error(f"[{_ + 1}] Error connecting to database: {e.with_traceback(None)}")
            await asyncio.sleep(0.5)


async def close_postgres_db() -> None:
    await engine.dispose()


async def _create_db_if_not_exists() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_server_url, isolation_level="AUTOCOMMIT")
    get_logger().info(f"Attemting to connect to database {settings.POSTGRES_DB}...")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": settings.POSTGRES_DB}
        )
        if not result.scalar():
            get_logger().info(f"Database {settings.POSTGRES_DB} not found. Creating database...")
            await conn.execute(
                text(f'CREATE DATABASE "{settings.POSTGRES_DB}" OWNER {settings.POSTGRES_USER}')
            )
            get_logger().info(f"Database {settings.POSTGRES_DB} created successfully.")


async def _run_migrations() -> None:
    alembic_cfg = AlembicConfig("alembic.ini")

    # Avoid running upgrade on every startup when schema is already at head.
    if not await _needs_migration(alembic_cfg):
        get_logger().info("Alembic already at head; skipping startup migration.")
        return

    loop = asyncio.get_event_loop()
    get_logger().info("Running Alembic migrations (upgrade head)...")
    await loop.run_in_executor(None, alembic_command.upgrade, alembic_cfg, "head")
    get_logger().info("Alembic migrations applied successfully.")


async def _needs_migration(alembic_cfg: AlembicConfig) -> bool:
    settings = get_settings()
    script = ScriptDirectory.from_config(alembic_cfg)
    target_head = script.get_current_head()
    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as conn:
            try:
                result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                current_revision = result.scalar_one_or_none()
            except Exception:
                # Table may not exist yet; run migrations in this case.
                return True

            return current_revision != target_head
    finally:
        await engine.dispose()
