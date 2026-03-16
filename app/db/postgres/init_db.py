import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.logger import get_logger

from .base import Base
from .engine import engine


async def init_postgres_db() -> None:
    for _ in range(10):
        try:
            await _create_db_if_not_exists()
            await _create_tables()
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


async def _create_tables() -> None:
    engine = create_async_engine(get_settings().database_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
