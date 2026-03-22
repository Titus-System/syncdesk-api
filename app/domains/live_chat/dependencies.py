from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep

from .chat_manager import ChatManager, get_chat_manager
from .repositories import ChatRepository
from .services.chat_service import ChatService


def get_chat_repository(db: MongoSessionDep) -> ChatRepository:
    return ChatRepository(db)


ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]


def get_chat_service(
    chat_repo: Annotated[ChatRepository, Depends(get_chat_repository)],
    chat_manager: Annotated[ChatManager, Depends(get_chat_manager)],
) -> ChatService:
    return ChatService(chat_repo, chat_manager)


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
