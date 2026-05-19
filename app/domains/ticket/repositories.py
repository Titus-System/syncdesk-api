import re
from typing import Any
from uuid import UUID

from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.ticket.models import Ticket, TicketComment, TicketHistory, TicketType
from app.domains.ticket.schemas import TicketQueueFiltersDTO, TicketSearchFiltersDTO
from app.domains.ticket.schemas import TicketSearchFiltersDTO, UpdateTicketCommentDTO


class TicketRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        await ticket.insert()
        return ticket

    async def list_tickets_paginated(self, filters: TicketSearchFiltersDTO) -> tuple[list[Ticket], int]:
        query = self._build_query(filters)
        offset = (filters.page - 1) * filters.page_size

        total = await Ticket.find(query).count()
        items = await Ticket.find(query).skip(offset).limit(filters.page_size).to_list()
        return items, total

    async def list_queue_candidates(self, filters: TicketQueueFiltersDTO) -> list[Ticket]:
        query = self._build_queue_query(filters)
        return await Ticket.find(query).to_list()

    async def get_by_id(self, ticket_id: PydanticObjectId) -> Ticket | None:
        return await Ticket.get(ticket_id)

    async def save(self, ticket: Ticket) -> Ticket:
        await ticket.save()
        return ticket
    
    async def add_ticket_comment(
        self, ticket_id: PydanticObjectId, comment: TicketComment
    ) -> TicketComment | None:
        ticket = await Ticket.get(ticket_id)
        if ticket is None:
            return None
        ticket.comments.append(comment)
        await ticket.save()
        return comment
    
    async def update_ticket_comment(
        self, ticket_id: PydanticObjectId, comment_id: UUID, dto: UpdateTicketCommentDTO
    ) -> TicketComment | None:
        updates = dto.model_dump(exclude_unset=True)
        if not updates:
            return None
        ticket = await Ticket.get(ticket_id)
        if ticket is None:
            return None
        comment = next(
            (c for c in ticket.comments if c.comment_id == comment_id), None
        )
        if comment is None:
            return None
        for field_name, value in updates.items():
            setattr(comment, field_name, value)
        await ticket.save()
        return comment

    async def delete_ticket_comment(
        self, ticket_id: PydanticObjectId, comment_id: UUID
    ) -> TicketComment | None:
        ticket = await Ticket.get(ticket_id)
        if ticket is None:
            return None
        comment = next(
            (c for c in ticket.comments if c.comment_id == comment_id), None
        )
        if comment is None:
            return None
        ticket.comments = [c for c in ticket.comments if c.comment_id != comment_id]
        await ticket.save()
        return comment
    
    async def get_ticket_history(
        self, ticket_id: PydanticObjectId
    ) -> list[TicketHistory] | None:
        ticket = await Ticket.get(ticket_id)
        if ticket is None:
            return None
        return ticket.agent_history
    

    async def search_ticket(
        self,
        search_query: str,
        client_id: UUID | None = None,
        agent_id: UUID | None = None,
        company_id: UUID | None = None,
        global_scope: bool = False,
    ) -> list[Ticket] | None:
        pattern = re.escape(search_query)
        text_filter: dict[str, Any] = {
            "$or": [
                {"description": {"$regex": pattern, "$options": "i"}},
                {"comments.text": {"$regex": pattern, "$options": "i"}},
            ]
        }

        scope_filter: dict[str, Any] | None = None
        if client_id is not None:
            scope_filter = {"client.id": client_id}
        elif agent_id is not None:
            scope_filter = {"agent_history.agent_id": agent_id}
        elif company_id is not None:
            scope_filter = {"client.company.id": company_id}
        elif not global_scope:
            return []

        query = text_filter if scope_filter is None else {"$and": [text_filter, scope_filter]}

        try:
            return await Ticket.find(query).to_list()
        except Exception:
            return None


    async def aggregate_dashboard(self, ticket_type: TicketType) -> dict[str, Any]:
        """Single-roundtrip aggregation for the dashboard.

        Returns a dict with keys: ``kpis``, ``open_breakdown``, ``assigned_breakdown_raw``.
        Top-10/Outros bucketing is intentionally left to the service layer.
        """
        pipeline: list[dict[str, Any]] = [
            {"$match": {"type": ticket_type.value}},
            {
                "$addFields": {
                    "sla_days": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$criticality", "high"]}, "then": 1},
                                {"case": {"$eq": ["$criticality", "medium"]}, "then": 3},
                                {"case": {"$eq": ["$criticality", "low"]}, "then": 5},
                            ],
                            "default": 5,
                        }
                    },
                    "active_assignments": {
                        "$filter": {
                            "input": {"$ifNull": ["$agent_history", []]},
                            "as": "h",
                            "cond": {"$eq": ["$$h.exit_date", None]},
                        }
                    },
                }
            },
            {
                "$addFields": {
                    "due_date": {
                        "$dateAdd": {
                            "startDate": "$creation_date",
                            "unit": "day",
                            "amount": "$sla_days",
                        }
                    },
                    "is_open": {
                        "$not": {"$in": ["$status", ["finished", "cancelled"]]}
                    },
                    "has_active_assignment": {
                        "$gt": [{"$size": "$active_assignments"}, 0]
                    },
                    "active_assignment": {"$first": "$active_assignments"},
                }
            },
            {
                "$facet": {
                    "kpis": [
                        {
                            "$group": {
                                "_id": None,
                                "open_count": {
                                    "$sum": {"$cond": ["$is_open", 1, 0]}
                                },
                                "cancelled_count": {
                                    "$sum": {
                                        "$cond": [
                                            {"$eq": ["$status", "cancelled"]},
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "unassigned_count": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    "$is_open",
                                                    {"$not": "$has_active_assignment"},
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                                "overdue_count": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    "$is_open",
                                                    {
                                                        "$lt": [
                                                            "$due_date",
                                                            "$$NOW",
                                                        ]
                                                    },
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                            }
                        }
                    ],
                    "open_breakdown": [
                        {"$match": {"is_open": True}},
                        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                    ],
                    "assigned_breakdown_raw": [
                        {
                            "$match": {
                                "is_open": True,
                                "has_active_assignment": True,
                            }
                        },
                        {
                            "$group": {
                                "_id": "$active_assignment.agent_id",
                                "agent_name": {"$first": "$active_assignment.name"},
                                "count": {"$sum": 1},
                            }
                        },
                        {"$sort": {"count": -1}},
                    ],
                }
            },
        ]

        cursor = Ticket.get_motor_collection().aggregate(pipeline)
        results: list[dict[str, Any]] = await cursor.to_list(length=1)
        if not results:
            return {
                "kpis": [],
                "open_breakdown": [],
                "assigned_breakdown_raw": [],
            }
        return results[0]

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

    @staticmethod
    def _build_queue_query(filters: TicketQueueFiltersDTO) -> dict[str, Any]:
        query: dict[str, Any] = {}

        if filters.status is not None:
            query["status"] = filters.status.value
        else:
            query["status"] = {
                "$in": [
                    "open",
                    "awaiting_assignment",
                    "in_progress",
                    "waiting_for_provider",
                    "waiting_for_validation",
                ]
            }

        if filters.type is not None:
            query["type"] = filters.type.value

        return query
