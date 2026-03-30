from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep

from .repositories import ConversationRepository
from .services import ConversationService


def get_conversation_repo(db: MongoSessionDep) -> ConversationRepository:
    return ConversationRepository(db)


ConversationRepositoryDep = Annotated[ConversationRepository, Depends(get_conversation_repo)]


def get_conversation_service(
    chat_repo: Annotated[ConversationRepository, Depends(get_conversation_repo)],
) -> ConversationService:
    return ConversationService(chat_repo)


ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
