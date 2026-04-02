from typing import Any

from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.ticket.models import Ticket, TicketStatus


class TicketRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        await ticket.insert()
        return ticket

    async def get_by_id(self, ticket_id: PydanticObjectId) -> Ticket | None:
        return await Ticket.get(ticket_id)

    async def update_status(self, ticket: Ticket, status: TicketStatus) -> Ticket:
        ticket.status = status
        await ticket.save()
        return ticket
