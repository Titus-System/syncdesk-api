from typing import Any

from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.ticket.models import Ticket
from app.domains.ticket.schemas import TicketSearchFiltersDTO


class TicketRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        await ticket.insert()
        return ticket

    async def list_tickets_paginated(self, filters: TicketSearchFiltersDTO) -> tuple[list[Ticket], int]:
        query = self._build_query(filters)
        offset = (filters.page - 1) * filters.limit

        total = await Ticket.find(query).count()
        items = await Ticket.find(query).skip(offset).limit(filters.limit).to_list()
        return items, total

    async def get_by_id(self, ticket_id: PydanticObjectId) -> Ticket | None:
        return await Ticket.get(ticket_id)

    async def save(self, ticket: Ticket) -> Ticket:
        await ticket.save()
        return ticket

    @staticmethod
    def _build_query(filters: TicketSearchFiltersDTO) -> dict[str, Any]:
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

        return query
