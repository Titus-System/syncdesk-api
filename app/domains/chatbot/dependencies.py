from typing import Annotated

from fastapi import Depends

from app.core.event_dispatcher.event_dispatcher import EventDispatcherDep
from app.db.mongo.dependencies import MongoSessionDep
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService


def get_chatbot_repo(db: MongoSessionDep) -> ChatbotRepository:
    return ChatbotRepository(db)


ChatbotRepositoryDep = Annotated[ChatbotRepository, Depends(get_chatbot_repo)]


def get_chatbot_service(
    chatbot_repo: ChatbotRepositoryDep,
    event_dispatcher: EventDispatcherDep
) -> ChatbotService:
    return ChatbotService(chatbot_repo, event_dispatcher)


ChatbotServiceDep = Annotated[ChatbotService, Depends(get_chatbot_service)]
