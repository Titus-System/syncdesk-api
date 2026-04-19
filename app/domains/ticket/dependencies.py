from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep
from app.domains.auth.dependencies import UserServiceDep
from app.domains.live_chat.dependencies import ConversationServiceDep

from .repositories import TicketRepository
from .services import TicketService


def get_ticket_repository(db: MongoSessionDep) -> TicketRepository:
    return TicketRepository(db)


TicketRepositoryDep = Annotated[TicketRepository, Depends(get_ticket_repository)]


def get_ticket_service(
    repository: TicketRepositoryDep,
    user_service: UserServiceDep,
    conversation_service: ConversationServiceDep,
) -> TicketService:
    return TicketService(repository, user_service, conversation_service)


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]