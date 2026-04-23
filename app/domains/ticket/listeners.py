from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import TriageFinishedEventSchema
from app.core.logger import get_logger
from app.db.mongo.db import mongo_db
from app.db.postgres.engine import async_session
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import CreateTicketDTO
from app.domains.ticket.services import TicketService


logger = get_logger("app.ticket.listener")


class TicketListener:
    def __init__(
        self, 
        service_factory: Callable[[AsyncSession], TicketService]
    ) -> None:
        self._service_factory = service_factory

    @event_handler(TriageFinishedEventSchema)
    async def on_triage_finished(self, schema: TriageFinishedEventSchema) -> None:
        async with async_session() as db:
            service = self._service_factory(db)
            await service.create_ticket(
                CreateTicketDTO(
                    triage_id = schema.attendance_id,
                    type = schema.ticket_type,
                    criticality=schema.ticket_criticality,
                    product=schema.product_name,
                    description=schema.ticket_description,
                    client_id=schema.client_id,
                    company_id=schema.company_id,
                    company_name=schema.company_name,
                )
            )


def register_ticket_listener(dispatcher: EventDispatcher) -> None:
    ticket_repo = TicketRepository(mongo_db.get_db())

    def build_service(db: AsyncSession) -> TicketService:
        return TicketService(ticket_repo, UserService(UserRepository(db)), dispatcher)

    listener = TicketListener(build_service)

    dispatcher.subscribe(AppEvent.TRIAGE_FINISHED, listener.on_triage_finished)
