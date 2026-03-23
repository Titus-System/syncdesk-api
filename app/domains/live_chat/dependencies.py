from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep

from .repositories import ChatRepository
from .services.chat_service import ChatService


def get_chat_repository(db: MongoSessionDep) -> ChatRepository:
    return ChatRepository(db)


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]


def get_chat_service(
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repository)]
) -> ChatService:
    return ChatService(chat_repo)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
