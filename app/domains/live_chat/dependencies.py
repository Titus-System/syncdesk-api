from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep
from app.domains.ticket.repositories import TicketRepository

from .repositories import ConversationRepository
from .services import ConversationService


def get_conversation_repo(db: MongoSessionDep) -> ConversationRepository:
    return ConversationRepository(db)


ConversationRepositoryDep = Annotated[ConversationRepository, Depends(get_conversation_repo)]


def get_ticket_repo(db: MongoSessionDep) -> TicketRepository:
    return TicketRepository(db)


TicketRepositoryDep = Annotated[TicketRepository, Depends(get_ticket_repo)]


def get_conversation_service(
    chat_repo: ConversationRepositoryDep,
    ticket_repo: TicketRepositoryDep,
) -> ConversationService:
    return ConversationService(chat_repo, ticket_repo)


ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]