import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.metrics import db_query_latency

engine = create_async_engine(get_settings().database_url, echo=True, future=True)

AsyncSessionFactory = async_sessionmaker[AsyncSession]
async_session: AsyncSessionFactory = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(
    conn: Connection,
    _cursor: DBAPICursor,
    _statement: str,
    _parameters: Any,
    _context: ExecutionContext | None,
    _executemany: bool,
) -> None:
    conn.info["query_start"] = time.perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(
    conn: Connection,
    _cursor: DBAPICursor,
    statement: str,
    _parameters: Any,
    _context: ExecutionContext | None,
    _executemany: bool,
) -> None:
    elapsed = time.perf_counter() - conn.info["query_start"]
    operation = statement.strip().split()[0].upper()
    db_query_latency.labels(operation=operation).observe(elapsed)
