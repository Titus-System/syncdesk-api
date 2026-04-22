from datetime import UTC, datetime
from uuid import UUID

from beanie import PydanticObjectId
from fastapi import status

from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.metrics import tickets_created_total, tickets_status_changed_total
from app.domains.ticket.models import Ticket, TicketClient, TicketCompany, TicketStatus
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import (
    CreateTicketDTO,
    CreateTicketResponseDTO,
    PaginatedResponseMeta,
    TicketClientResponse,
    TicketCommentResponse,
    TicketCompanyResponse,
    TicketHistoryResponse,
    TicketListResponse,
    TicketResponse,
    TicketSearchFiltersDTO,
    UpdateTicketDTO,
)


class TicketService:
    allowed_transitions: dict[TicketStatus, set[TicketStatus]] = {
        TicketStatus.OPEN: {TicketStatus.AWAITING_ASSIGNMENT, TicketStatus.IN_PROGRESS},
        TicketStatus.AWAITING_ASSIGNMENT: {TicketStatus.IN_PROGRESS},
        TicketStatus.IN_PROGRESS: {
            TicketStatus.AWAITING_ASSIGNMENT,
            TicketStatus.WAITING_FOR_PROVIDER,
            TicketStatus.WAITING_FOR_VALIDATION,
            TicketStatus.FINISHED,
        },
        TicketStatus.WAITING_FOR_PROVIDER: {TicketStatus.IN_PROGRESS},
        TicketStatus.WAITING_FOR_VALIDATION: {
            TicketStatus.IN_PROGRESS,
            TicketStatus.FINISHED,
        },
        TicketStatus.FINISHED: set(),
    }

    def __init__(self, repository: TicketRepository, user_service: UserService):
        self.repo = repository
        self.user_service = user_service
        self.logger = get_logger("app.ticket.service")

    async def create_ticket(self, dto: CreateTicketDTO) -> CreateTicketResponseDTO:
        client = await self._build_ticket_client(
            dto.client_id,
            dto.company_id,
            dto.company_name,
        )
        ticket = Ticket(
            triage_id=dto.triage_id,
            type=dto.type,
            criticality=dto.criticality,
            product=dto.product,
            status=TicketStatus.AWAITING_ASSIGNMENT,
            creation_date=datetime.now(UTC),
            description=dto.description,
            chat_ids=dto.chat_ids,
            agent_history=[],
            client=client,
            comments=[],
        )
        created_ticket = await self.repo.create_ticket(ticket)

        tickets_created_total.labels(source="api", criticality=dto.criticality.value).inc()
        self.logger.info(
            "Ticket created",
            extra={
                "ticket_id": str(created_ticket.id),
                "type": dto.type.value,
                "criticality": dto.criticality.value,
            },
        )

        return CreateTicketResponseDTO(
            id=str(created_ticket.id),
            status=created_ticket.status,
            creation_date=created_ticket.creation_date,
        )

    async def list_tickets(self, filters: TicketSearchFiltersDTO) -> TicketListResponse:
        tickets, total = await self.repo.list_tickets_paginated(filters)
        pagination = PaginatedResponseMeta(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
        )
        return TicketListResponse(
            items=[self._to_ticket_response(ticket) for ticket in tickets],
            page=pagination.page,
            page_size=pagination.page_size,
            total=pagination.total,
        )

    async def get_ticket(self, ticket_id: PydanticObjectId) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        return self._to_ticket_response(ticket)

    async def update_ticket(
        self, ticket_id: PydanticObjectId, dto: UpdateTicketDTO
    ) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        updates = dto.model_dump(exclude_unset=True)
        status_update = updates.pop("status", None)
        previous_status: TicketStatus | None = None

        if status_update is not None and status_update != ticket.status:
            previous_status = ticket.status
            self._validate_status_change(previous_status, status_update)
            ticket.status = status_update
        elif status_update is not None and not updates:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already in the requested status.",
            )

        for field_name, value in updates.items():
            setattr(ticket, field_name, value)

        if status_update is None and not updates:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one updatable field must be provided.",
            )

        updated_ticket = await self.repo.save(ticket)
        if previous_status is not None and status_update is not None:
            self._record_status_transition(ticket_id, previous_status, status_update)
        return self._to_ticket_response(updated_ticket)

    async def _build_ticket_client(
        self,
        client_id: UUID,
        company_id: UUID,
        company_name: str,
    ) -> TicketClient:
        user = await self.user_service.get_by_id(client_id)
        if user is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {client_id} does not exist.",
            )

        client_name = user.name or user.username or user.email
        company = TicketCompany(
            id=company_id,
            name=company_name,
        )
        return TicketClient(
            id=user.id,
            name=client_name,
            email=user.email,
            company=company,
        )

    async def _get_ticket_or_404(self, ticket_id: PydanticObjectId) -> Ticket:
        ticket = await self.repo.get_by_id(ticket_id)
        if ticket is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} does not exist.",
            )
        return ticket

    def _validate_status_change(
        self, previous_status: TicketStatus, new_status: TicketStatus
    ) -> None:
        if new_status == previous_status:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already in the requested status.",
            )

        allowed_statuses = self.allowed_transitions.get(previous_status, set())
        if new_status not in allowed_statuses:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status transition from '{previous_status.value}' "
                    f"to '{new_status.value}'."
                ),
            )

    def _record_status_transition(
        self, ticket_id: PydanticObjectId, previous_status: TicketStatus, new_status: TicketStatus
    ) -> None:
        tickets_status_changed_total.labels(
            from_status=previous_status.value, to_status=new_status.value
        ).inc()
        self.logger.info(
            "Ticket status updated",
            extra={
                "ticket_id": str(ticket_id),
                "from": previous_status.value,
                "to": new_status.value,
            },
        )

    def _to_ticket_response(self, ticket: Ticket) -> TicketResponse:
        return TicketResponse(
            id=str(ticket.id),
            triage_id=str(ticket.triage_id),
            type=ticket.type,
            criticality=ticket.criticality,
            product=ticket.product,
            status=ticket.status,
            creation_date=ticket.creation_date,
            description=ticket.description,
            chat_ids=[str(chat_id) for chat_id in ticket.chat_ids],
            agent_history=[
                TicketHistoryResponse(
                    agent_id=history.agent_id,
                    name=history.name,
                    level=history.level,
                    assignment_date=history.assignment_date,
                    exit_date=history.exit_date,
                    transfer_reason=history.transfer_reason,
                )
                for history in ticket.agent_history
            ],
            client=TicketClientResponse(
                id=ticket.client.id,
                name=ticket.client.name,
                email=ticket.client.email,
                company=TicketCompanyResponse(
                    id=ticket.client.company.id,
                    name=ticket.client.company.name,
                ),
            ),
            comments=[
                TicketCommentResponse(
                    comment_id=comment.comment_id,
                    author=comment.author,
                    text=comment.text,
                    date=comment.date,
                    internal=comment.internal,
                )
                for comment in ticket.comments
            ],
        )
