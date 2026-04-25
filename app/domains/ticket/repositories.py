from typing import Any

from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.ticket.models import Ticket, TicketStatus
from app.domains.ticket.schemas import TicketSearchFiltersDTO


class TicketRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        await ticket.insert()
        return ticket

    async def search_tickets(self, filters: TicketSearchFiltersDTO) -> list[Ticket]:
        query: dict[str, Any] = {}

        if filters.ticket_id is not None:
            query["_id"] = filters.ticket_id
        if filters.client_id is not None:
            query["client.id"] = filters.client_id
        if filters.triage_id is not None:
            query["triage_id"] = filters.triage_id
        if filters.status is not None:
            query["status"] = filters.status.value
        if filters.criticality is not None:
            query["criticality"] = filters.criticality.value
        if filters.type is not None:
            query["type"] = filters.type.value
        if filters.product is not None:
            query["product"] = filters.product

        if not query:
            return await Ticket.find_all().to_list()

        return await Ticket.find(query).to_list()

    async def get_by_id(self, ticket_id: PydanticObjectId) -> Ticket | None:
        return await Ticket.get(ticket_id)

    async def update_status(self, ticket: Ticket, status: TicketStatus) -> Ticket:
        ticket.status = status
        await ticket.save()
        return ticket
