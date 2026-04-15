from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService


def get_chatbot_repo(db: MongoSessionDep) -> ChatbotRepository:
    return ChatbotRepository(db)


ChatbotRepositoryDep = Annotated[ChatbotRepository, Depends(get_chatbot_repo)]


def get_chatbot_service(chatbot_repo: ChatbotRepositoryDep) -> ChatbotService:
    return ChatbotService(chatbot_repo)


ChatbotServiceDep = Annotated[ChatbotService, Depends(get_chatbot_service)]
