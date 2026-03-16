import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import (
    get_settings,
    register_exception_handlers,
)
from app.core.background_tasks import global_background_tasks
from app.core.init_routers import initiate_routers
from app.core.logger import get_logger
from app.core.middleware import add_middlewares
from app.db import close_postgres_db, init_postgres_db, mongo_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger = get_logger()
    settings = get_settings()
    logger.info("Starting Application...")
    tasks = global_background_tasks()

    try:
        if settings.ENVIRONMENT == "development":
            await init_postgres_db()

        await mongo_db.connect()
        yield

    finally:
        logger.info("🛑 Shutting Down Application...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await close_postgres_db()
        await mongo_db.disconnect()
        logger.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.PROJECT_VERSION,
        lifespan=lifespan,
    )
    add_middlewares(app)
    initiate_routers(app)
    register_exception_handlers(app)
    return app
