import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from beanie import init_beanie
from fastapi import FastAPI

from app.core import (
    get_settings,
    register_exception_handlers,
)
from app.core.background_tasks import global_background_tasks
from app.core.event_dispatcher import get_event_dispatcher
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.init_routers import initiate_routers
from app.core.logger import get_logger, stop_logger
from app.core.middleware import add_middlewares
from app.db import close_postgres_db, init_postgres_db, mongo_db
from app.db.postgres.engine import engine as pg_engine
from app.domains.chatbot.models import Attendance
from app.domains.live_chat import Conversation
from app.domains.live_chat.listeners import register_conversation_listener
from app.domains.ticket import Ticket


def register_app_events_listeners(dispatcher: EventDispatcher) -> None:
    logger = get_logger("app.main")
    register_conversation_listener(dispatcher)
    logger.info("Registered event listeners to EventDispatcher.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger = get_logger("app.main")
    settings = get_settings()
    logger.info("Starting Application...")
    tasks = global_background_tasks(pg_engine)

    dispatcher = get_event_dispatcher()

    try:
        if settings.ENVIRONMENT == "development":
            await init_postgres_db()

        await mongo_db.connect()
        await init_beanie(
            database=mongo_db.get_db(),
            document_models=[Conversation, Ticket, Attendance]
        )
        register_app_events_listeners(dispatcher)    
        yield

    finally:
        logger.info("🛑 Shutting Down Application...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await close_postgres_db()
        await mongo_db.disconnect()
        stop_logger()


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
