from datetime import UTC, datetime
from uuid import UUID

from beanie import PydanticObjectId
from fastapi import status

from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.domains.auth.entities import UserWithRoles
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.metrics import tickets_created_total, tickets_status_changed_total
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketHistory,
    TicketStatus,
)
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import (
    CreateTicketDTO,
    CreateTicketResponseDTO,
    TicketClientResponseDTO,
    TicketCommentResponseDTO,
    TicketCompanyResponseDTO,
    TicketHistoryResponseDTO,
    TicketResponseDTO,
    TicketSearchFiltersDTO,
    UpdateTicketStatusDTO,
    UpdateTicketStatusResponseDTO,
)


class TicketService:
    allowed_transitions: dict[TicketStatus, set[TicketStatus]] = {
        TicketStatus.OPEN: {TicketStatus.IN_PROGRESS},
        TicketStatus.IN_PROGRESS: {
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
        client = await self._build_ticket_client(dto.client_id)
        ticket = Ticket(
            triage_id=dto.triage_id,
            type=dto.type,
            criticality=dto.criticality,
            product=dto.product,
            status=TicketStatus.OPEN,
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

    async def search_tickets(self, filters: TicketSearchFiltersDTO) -> list[TicketResponseDTO]:
        tickets = await self.repo.search_tickets(filters)
        return [self._to_ticket_response(ticket) for ticket in tickets]

    async def get_ticket_by_id(self, ticket_id: PydanticObjectId) -> TicketResponseDTO:
        ticket = await self.repo.get_by_id(ticket_id)

        if ticket is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} does not exist.",
            )

        return self._to_ticket_response(ticket)

    async def take_ticket(
        self,
        ticket_id: PydanticObjectId,
        actor: UserWithRoles,
    ) -> TicketResponseDTO:
        ticket = await self.repo.get_by_id(ticket_id)

        if ticket is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} does not exist.",
            )

        actor_roles = actor.roles_names()
        if "admin" not in actor_roles and "agent" not in actor_roles:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only agents or admins can take tickets.",
            )

        current_agent_id = self._get_current_assigned_agent_id(ticket)

        if current_agent_id is not None:
            if current_agent_id == actor.id:
                return self._to_ticket_response(ticket)

            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este chamado já foi atribuído a outro atendente.",
            )

        actor_name = actor.name or actor.username or actor.email
        actor_level = "admin" if "admin" in actor_roles else "agent"
        now = datetime.now(UTC)

        ticket.agent_history.append(
            TicketHistory(
                agent_id=actor.id,
                name=actor_name,
                level=actor_level,
                assignment_date=now,
                exit_date=now,
                transfer_reason="Assumido via fila",
            )
        )

        await ticket.save()

        self.logger.info(
            "Ticket taken",
            extra={
                "ticket_id": str(ticket_id),
                "actor_user_id": str(actor.id),
            },
        )

        return self._to_ticket_response(ticket)

    async def update_status(
        self,
        ticket_id: PydanticObjectId,
        dto: UpdateTicketStatusDTO,
        actor: UserWithRoles,
    ) -> UpdateTicketStatusResponseDTO:
        ticket = await self.repo.get_by_id(ticket_id)
        if ticket is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ticket {ticket_id} does not exist.",
            )

        current_agent_id = self._get_current_assigned_agent_id(ticket)
        actor_roles = actor.roles_names()

        if current_agent_id is None:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O chamado precisa ser assumido por um atendente antes de alterar o status.",
            )

        if "admin" not in actor_roles and actor.id != current_agent_id:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Somente o atendente responsável ou um administrador pode alterar o status deste chamado.",
            )

        previous_status = ticket.status
        if dto.status == previous_status:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already in the requested status.",
            )

        allowed_statuses = self.allowed_transitions.get(previous_status, set())
        if dto.status not in allowed_statuses:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid status transition from '{previous_status.value}' "
                    f"to '{dto.status.value}'."
                ),
            )

        updated_ticket = await self.repo.update_status(ticket, dto.status)

        tickets_status_changed_total.labels(
            from_status=previous_status.value, to_status=dto.status.value
        ).inc()
        self.logger.info(
            "Ticket status updated",
            extra={
                "ticket_id": str(ticket_id),
                "from": previous_status.value,
                "to": dto.status.value,
                "actor_user_id": str(actor.id),
                "assigned_agent_id": str(current_agent_id),
            },
        )

        return UpdateTicketStatusResponseDTO(
            id=str(updated_ticket.id),
            previous_status=previous_status,
            current_status=updated_ticket.status,
        )

    async def _build_ticket_client(self, client_id: UUID) -> TicketClient:
        user = await self.user_service.get_by_id(client_id)
        if user is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {client_id} does not exist.",
            )

        client_name = user.name or user.username or user.email
        company = TicketCompany(
            id=user.id,
            name=f"{client_name} account",
        )
        return TicketClient(
            id=user.id,
            name=client_name,
            email=user.email,
            company=company,
        )

    def _get_current_assigned_agent_id(self, ticket: Ticket) -> UUID | None:
        if ticket.agent_history:
            return ticket.agent_history[-1].agent_id
        return None

    def _resolve_assigned_agent(
        self, ticket: Ticket
    ) -> tuple[UUID | None, str | None]:
        if ticket.agent_history:
            last = ticket.agent_history[-1]
            return last.agent_id, last.name
        return None, None

    def _to_ticket_response(self, ticket: Ticket) -> TicketResponseDTO:
        assigned_agent_id, assigned_agent_name = self._resolve_assigned_agent(ticket)

        return TicketResponseDTO(
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
                TicketHistoryResponseDTO(
                    agent_id=history.agent_id,
                    name=history.name,
                    level=history.level,
                    assignment_date=history.assignment_date,
                    exit_date=history.exit_date,
                    transfer_reason=history.transfer_reason,
                )
                for history in ticket.agent_history
            ],
            client=TicketClientResponseDTO(
                id=ticket.client.id,
                name=ticket.client.name,
                email=ticket.client.email,
                company=TicketCompanyResponseDTO(
                    id=ticket.client.company.id,
                    name=ticket.client.company.name,
                ),
            ),
            comments=[
                TicketCommentResponseDTO(
                    comment_id=comment.comment_id,
                    author=comment.author,
                    text=comment.text,
                    date=comment.date,
                    internal=comment.internal,
                )
                for comment in ticket.comments
            ],
            assigned_agent_id=assigned_agent_id,
            assigned_agent_name=assigned_agent_name,
        )
