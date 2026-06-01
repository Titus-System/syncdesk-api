from typing import Annotated

from fastapi import Depends

from app.core.event_dispatcher import get_event_dispatcher
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.db.mongo.dependencies import MongoSessionDep
from app.db.postgres.dependencies import PgSessionDep
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService


def get_chatbot_repo(db: MongoSessionDep) -> ChatbotRepository:
    return ChatbotRepository(db)


ChatbotRepositoryDep = Annotated[ChatbotRepository, Depends(get_chatbot_repo)]


def get_dispatcher() -> EventDispatcher:
    return get_event_dispatcher()


EventDispatcherDep = Annotated[EventDispatcher, Depends(get_dispatcher)]


def get_chatbot_service(
    chatbot_repo: ChatbotRepositoryDep,
    dispatcher: EventDispatcherDep,
    pg_db: PgSessionDep,
) -> ChatbotService:
    return ChatbotService(chatbot_repo, dispatcher, pg_db)


ChatbotServiceDep = Annotated[ChatbotService, Depends(get_chatbot_service)]