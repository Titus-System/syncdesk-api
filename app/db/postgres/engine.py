from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(get_settings().database_url, echo=True, future=True)

AsyncSessionFactory = async_sessionmaker[AsyncSession]
async_session: AsyncSessionFactory = async_sessionmaker(
    autocommit=False, autoflush=False, bind=engine, expire_on_commit=False
)
