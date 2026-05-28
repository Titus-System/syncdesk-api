from typing import Annotated

from fastapi import Depends

from app.core.event_dispatcher import EventDispatcherDep
from app.db.mongo.dependencies import MongoSessionDep
from app.domains.auth import UserServiceDep
from app.domains.auth.dependencies import UserLevelRepositoryDep
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.services import TicketService


def get_ticket_repo(db: MongoSessionDep) -> TicketRepository:
    return TicketRepository(db)


TicketRepositoryDep = Annotated[TicketRepository, Depends(get_ticket_repo)]


def get_ticket_service(
    ticket_repo: TicketRepositoryDep,
    user_service: UserServiceDep,
    user_level_repo: UserLevelRepositoryDep,
    event_dispatcher: EventDispatcherDep,
) -> TicketService:
    return TicketService(ticket_repo, user_service, user_level_repo, event_dispatcher)


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]
