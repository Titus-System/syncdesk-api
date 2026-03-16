from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import async_session


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as db_session:
        yield db_session


PgSessionDep = Annotated[AsyncSession, Depends(get_postgres_session)]
