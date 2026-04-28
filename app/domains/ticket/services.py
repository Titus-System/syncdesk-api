from datetime import UTC, datetime
from uuid import UUID, uuid4

from beanie import PydanticObjectId
from fastapi import status

from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import (
    TicketAssigneeUpdatedEventSchema,
    TicketCreatedEventSchema,
    TicketEscalatedEventSchema,
)
from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.domains.auth.entities import UserWithRoles
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.metrics import tickets_created_total, tickets_status_changed_total
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketHistory,
    TicketStatus,
    TicketComment,
)
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import (
    AddTicketCommentDTO,
    AssignTicketRequest,
    CreateTicketDTO,
    CreateTicketResponseDTO,
    EscalateTicketRequest,
    TicketClientResponse,
    TicketCommentResponse,
    TicketCompanyResponse,
    TicketHistoryResponse,
    TicketPaginatedList,
    TicketQueueFiltersDTO,
    TicketQueueItemResponse,
    TicketQueueListResponse,
    TicketResponse,
    TicketSearchFiltersDTO,
    TransferTicketRequest,
    UpdateTicketCommentDTO,
    UpdateTicketDTO,
    UpdateTicketStatusDTO,
    UpdateTicketStatusResponseDTO,
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

    def __init__(self, repository: TicketRepository, user_service: UserService, event_dispatcher: EventDispatcher):
        self.repo = repository
        self.user_service = user_service
        self.dispatcher = event_dispatcher
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
        assert created_ticket.id is not None

        await self.dispatcher.publish(
            AppEvent.TICKET_CREATED,
            TicketCreatedEventSchema(
                ticket_id=created_ticket.id,
                client_id=created_ticket.client.id,
            ),
        )
        
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

    async def list_tickets(self, filters: TicketSearchFiltersDTO) -> TicketPaginatedList[TicketResponse]:
        tickets, total = await self.repo.list_tickets_paginated(filters)
        return TicketPaginatedList[TicketResponse](
            items=[self._to_ticket_response(ticket) for ticket in tickets],
            page=filters.page,
            page_size=filters.page_size,
            total=total,
        )

    async def get_ticket(self, ticket_id: PydanticObjectId) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        return self._to_ticket_response(ticket)

    async def list_ticket_queue(self, filters: TicketQueueFiltersDTO) -> TicketQueueListResponse:
        tickets = await self.repo.list_queue_candidates(filters)
        filtered_tickets = [ticket for ticket in tickets if self._matches_queue_filters(ticket, filters)]
        sorted_tickets = sorted(filtered_tickets, key=self._queue_sort_key)

        offset = (filters.page - 1) * filters.page_size
        paginated_tickets = sorted_tickets[offset : offset + filters.page_size]

        return TicketQueueListResponse(
            items=[self._to_ticket_queue_item_response(ticket) for ticket in paginated_tickets],
            page=filters.page,
            page_size=filters.page_size,
            total=len(sorted_tickets),
        )

    async def take_ticket(
        self,
        ticket_id: PydanticObjectId,
        actor: UserWithRoles,
    ) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)

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
                exit_date=None,
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

    async def assign_ticket(
        self,
        ticket_id: PydanticObjectId,
        dto: AssignTicketRequest,
    ) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        agent = await self.user_service.get_by_id_with_roles(dto.agent_id)
        if agent is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {dto.agent_id} does not exist.",
            )

        agent_roles = agent.roles_names()
        if "agent" not in agent_roles and "admin" not in agent_roles:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided user cannot be assigned as a ticket agent.",
            )

        if ticket.status == TicketStatus.FINISHED:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Finished tickets cannot receive a new assignee.",
            )

        previous_assignment = self._get_active_assignment(ticket)
        previous_agent_id = previous_assignment.agent_id if previous_assignment is not None else None
        now = datetime.now(UTC)

        if previous_assignment is not None:
            previous_assignment.exit_date = now

        ticket.agent_history.append(
            TicketHistory(
                agent_id=agent.id,
                name=self._resolve_user_display_name(agent),
                level=self._resolve_agent_level(agent_roles),
                assignment_date=now,
                exit_date=None,
                transfer_reason=dto.reason,
            )
        )

        ticket.status = self._derive_status_after_assignment(ticket.status)
        updated_ticket = await self.repo.save(ticket)

        await self.dispatcher.publish(
            AppEvent.TICKET_ASSIGNEE_UPDATED,
            TicketAssigneeUpdatedEventSchema(
                ticket_id=updated_ticket.id,
                client_id=updated_ticket.client.id,
                new_agent_id=agent.id,
                reason=dto.reason,
            ),
        )

        self.logger.info(
            "Ticket assigned",
            extra={
                "ticket_id": str(ticket_id),
                "previous_agent_id": str(previous_agent_id) if previous_agent_id is not None else None,
                "new_agent_id": str(agent.id),
            },
        )

        return self._to_ticket_response(updated_ticket)

    async def escalate_ticket(
        self,
        ticket_id: PydanticObjectId,
        dto: EscalateTicketRequest,
    ) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        current_assignment = self._get_active_assignment(ticket)
        previous_agent_id = (
            current_assignment.agent_id if current_assignment is not None else None
        )
        source_level = self._resolve_ticket_level(ticket)
        target_level = self._normalize_support_level(dto.target_level)

        if source_level is None:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket has no current support level to escalate from.",
            )

        self._validate_escalation_level(source_level, target_level)

        now = datetime.now(UTC)
        if current_assignment is not None:
            current_assignment.exit_date = now
            current_assignment.transfer_reason = dto.reason

        ticket.status = TicketStatus.AWAITING_ASSIGNMENT
        updated_ticket = await self.repo.save(ticket)

        await self.dispatcher.publish(
            AppEvent.TICKET_ESCALATED,
            TicketEscalatedEventSchema(
                ticket_id=updated_ticket.id,
                client_id=updated_ticket.client.id,
                new_agent_id=None,
                new_agent_name=None,
                new_level=target_level,
                transfer_reason=dto.reason,
            ),
        )

        self.logger.info(
            "Ticket escalated",
            extra={
                "ticket_id": str(ticket_id),
                "previous_agent_id": (
                    str(previous_agent_id) if previous_agent_id is not None else None
                ),
                "source_level": source_level,
                "target_level": target_level,
                "target_department_id": dto.target_department_id,
            },
        )

        return self._to_ticket_response(updated_ticket)

    async def transfer_ticket(
        self,
        ticket_id: PydanticObjectId,
        dto: TransferTicketRequest,
    ) -> TicketResponse:
        ticket = await self._get_ticket_or_404(ticket_id)
        current_assignment = self._get_active_assignment(ticket)
        if current_assignment is None:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket must have an active assignee before it can be transferred.",
            )

        if current_assignment.agent_id == dto.target_agent_id:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already assigned to the target agent.",
            )

        if ticket.status == TicketStatus.FINISHED:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Finished tickets cannot be transferred.",
            )

        target_agent = await self.user_service.get_by_id_with_roles(dto.target_agent_id)
        if target_agent is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {dto.target_agent_id} does not exist.",
            )

        target_agent_roles = target_agent.roles_names()
        if "agent" not in target_agent_roles and "admin" not in target_agent_roles:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided user cannot be assigned as a ticket agent.",
            )

        source_level = self._normalize_support_level(current_assignment.level)
        target_level = self._normalize_support_level(
            self._resolve_agent_level(target_agent_roles)
        )
        if target_level != source_level:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Direct ticket transfer must keep the same support level.",
            )

        # The current Ticket model has no department snapshot, so same-department
        # validation cannot be completed here without inventing state.
        now = datetime.now(UTC)
        current_assignment.exit_date = now
        current_assignment.transfer_reason = dto.reason

        ticket.agent_history.append(
            TicketHistory(
                agent_id=target_agent.id,
                name=self._resolve_user_display_name(target_agent),
                level=source_level,
                assignment_date=now,
                exit_date=None,
                transfer_reason=dto.reason,
            )
        )
        ticket.status = TicketStatus.IN_PROGRESS
        updated_ticket = await self.repo.save(ticket)

        await self.dispatcher.publish(
            AppEvent.TICKET_ASSIGNEE_UPDATED,
            TicketAssigneeUpdatedEventSchema(
                ticket_id=updated_ticket.id,
                client_id=updated_ticket.client.id,
                new_agent_id=target_agent.id,
                reason=dto.reason,
            ),
        )

        self.logger.info(
            "Ticket transferred",
            extra={
                "ticket_id": str(ticket_id),
                "previous_agent_id": str(current_assignment.agent_id),
                "new_agent_id": str(target_agent.id),
                "level": source_level,
            },
        )

        return self._to_ticket_response(updated_ticket)

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
            return self._to_ticket_response(ticket)

        for field_name, value in updates.items():
            setattr(ticket, field_name, value)

        if status_update is None and not updates:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one updatable field must be provided.",
            )

        updated_ticket = await self.repo.save(ticket)
        if previous_status is not None and status_update is not None:
            self._record_status_transition(
                ticket_id, previous_status, status_update, actor=None
            )
        return self._to_ticket_response(updated_ticket)
    
    async def add_comment_to_ticket(
        self,
        ticket_id: PydanticObjectId,
        author_name: str,
        dto: AddTicketCommentDTO
    ) -> TicketComment | None:
        tc = TicketComment(
            comment_id=uuid4(),
            author = author_name,
            text = dto.text,
            date = datetime.now(UTC),
            internal = dto.internal
        )
        return await self.repo.add_ticket_comment(ticket_id, tc)

    async def list_ticket_comments(
        self, ticket_id: PydanticObjectId
    ) -> list[TicketCommentResponse] | None:
        ticket = await self.repo.get_by_id(ticket_id)
        if ticket is None:
            return None
        return [
            TicketCommentResponse(
                comment_id=comment.comment_id,
                author=comment.author,
                text=comment.text,
                date=comment.date,
                internal=comment.internal,
            )
            for comment in ticket.comments
        ]

    async def update_ticket_comment(
        self, ticket_id: PydanticObjectId, comment_id: UUID, dto: UpdateTicketCommentDTO
    ) -> TicketComment | None:
        return await self.repo.update_ticket_comment(ticket_id, comment_id, dto)

    async def delete_ticket_comment(
        self, ticket_id: PydanticObjectId, comment_id: UUID
    ) -> TicketComment | None:
        return await self.repo.delete_ticket_comment(ticket_id, comment_id)

    async def update_status(
        self,
        ticket_id: PydanticObjectId,
        dto: UpdateTicketStatusDTO,
        actor: UserWithRoles,
    ) -> UpdateTicketStatusResponseDTO:
        ticket = await self._get_ticket_or_404(ticket_id)

        self._authorize_status_change(ticket, actor)

        previous_status = ticket.status
        if dto.status == previous_status:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket is already in the requested status.",
            )

        self._validate_status_change(previous_status, dto.status)
        ticket.status = dto.status

        updated_ticket = await self.repo.save(ticket)
        self._record_status_transition(ticket_id, previous_status, dto.status, actor=actor)

        return UpdateTicketStatusResponseDTO(
            id=str(updated_ticket.id),
            previous_status=previous_status,
            current_status=updated_ticket.status,
        )

    async def _build_ticket_client(
        self,
        client_id: UUID,
        company_id: UUID | None,
        company_name: str | None,
    ) -> TicketClient:
        user = await self.user_service.get_by_id(client_id)
        if user is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {client_id} does not exist.",
            )

        client_name = user.name or user.username or user.email
        company = TicketCompany(
            id=company_id if company_id is not None else user.id,
            name=company_name if company_name is not None else f"{client_name} account",
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

    def _authorize_status_change(self, ticket: Ticket, actor: UserWithRoles) -> None:
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

    def _validate_status_change(
        self, previous_status: TicketStatus, new_status: TicketStatus
    ) -> None:
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
        self,
        ticket_id: PydanticObjectId,
        previous_status: TicketStatus,
        new_status: TicketStatus,
        actor: UserWithRoles | None,
    ) -> None:
        tickets_status_changed_total.labels(
            from_status=previous_status.value, to_status=new_status.value
        ).inc()
        extra: dict[str, str] = {
            "ticket_id": str(ticket_id),
            "from": previous_status.value,
            "to": new_status.value,
        }
        if actor is not None:
            extra["actor_user_id"] = str(actor.id)
        self.logger.info("Ticket status updated", extra=extra)

    def _get_current_assigned_agent_id(self, ticket: Ticket) -> UUID | None:
        current_assignment = self._get_active_assignment(ticket)
        if current_assignment is None:
            return None
        return current_assignment.agent_id

    def _get_active_assignment(self, ticket: Ticket) -> TicketHistory | None:
        for history in reversed(ticket.agent_history):
            if history.exit_date is None:
                return history
        return None

    def _get_current_assignment(self, ticket: Ticket) -> TicketHistory | None:
        if ticket.agent_history:
            return ticket.agent_history[-1]
        return None

    def _resolve_ticket_level(self, ticket: Ticket) -> str | None:
        current_assignment = self._get_active_assignment(ticket)
        if current_assignment is not None:
            return self._normalize_support_level(current_assignment.level)

        return None

    def _normalize_support_level(self, level: str) -> str:
        normalized = level.strip().upper()
        if normalized == "AGENT":
            return "N1"
        return normalized

    def _support_level_rank(self, level: str) -> int | None:
        normalized = self._normalize_support_level(level)
        if len(normalized) < 2 or normalized[0] != "N":
            return None

        numeric_level = normalized[1:]
        if not numeric_level.isdigit():
            return None

        return int(numeric_level)

    def _validate_escalation_level(self, source_level: str, target_level: str) -> None:
        source_rank = self._support_level_rank(source_level)
        target_rank = self._support_level_rank(target_level)

        if source_rank is None or target_rank is None:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Support levels must use the N<number> format.",
            )

        if target_rank <= source_rank:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket escalation must target a higher support level.",
            )

    def _resolve_user_display_name(self, user: UserWithRoles) -> str:
        return user.name or user.username or user.email

    def _resolve_agent_level(self, roles_names: list[str]) -> str:
        for role_name in roles_names:
            normalized = role_name.strip().upper()
            if normalized in {"N1", "N2", "N3"}:
                return normalized
        if "admin" in roles_names:
            return "admin"
        return "N1"

    def _derive_status_after_assignment(self, current_status: TicketStatus) -> TicketStatus:
        if current_status in {TicketStatus.OPEN, TicketStatus.AWAITING_ASSIGNMENT}:
            return TicketStatus.IN_PROGRESS
        return current_status

    def _resolve_assigned_agent(
        self, ticket: Ticket
    ) -> tuple[UUID | None, str | None]:
        current_assignment = self._get_active_assignment(ticket)
        if current_assignment is not None:
            last = current_assignment
            return last.agent_id, last.name
        return None, None

    def _matches_queue_filters(self, ticket: Ticket, filters: TicketQueueFiltersDTO) -> bool:
        current_assignment = self._get_active_assignment(ticket)
        current_level = current_assignment.level if current_assignment is not None else None
        current_assignee_id = current_assignment.agent_id if current_assignment is not None else None
        unassigned = current_assignee_id is None

        # department_id is a provisional contract field. The current persisted model
        # does not store a department snapshot yet, so queue items can only expose None.
        if filters.department_id is not None:
            return False

        if filters.unassigned_only is True and not unassigned:
            return False

        if filters.level is not None and filters.level != current_level:
            return False

        if filters.assignee_id is not None and filters.assignee_id != current_assignee_id:
            return False

        return True

    def _queue_sort_key(self, ticket: Ticket) -> tuple[int, datetime]:
        criticality_priority = {
            TicketCriticality.HIGH: 0,
            TicketCriticality.MEDIUM: 1,
            TicketCriticality.LOW: 2,
        }
        return criticality_priority[ticket.criticality], ticket.creation_date

    def _to_ticket_queue_item_response(self, ticket: Ticket) -> TicketQueueItemResponse:
        current_assignment = self._get_active_assignment(ticket)
        assignee_id, assignee_name = self._resolve_assigned_agent(ticket)
        level = current_assignment.level if current_assignment is not None else None

        return TicketQueueItemResponse(
            id=str(ticket.id),
            triage_id=str(ticket.triage_id),
            type=ticket.type,
            criticality=ticket.criticality,
            product=ticket.product,
            status=ticket.status,
            creation_date=ticket.creation_date,
            description=ticket.description,
            client=TicketClientResponse(
                id=ticket.client.id,
                name=ticket.client.name,
                email=ticket.client.email,
                company=TicketCompanyResponse(
                    id=ticket.client.company.id,
                    name=ticket.client.company.name,
                ),
            ),
            department_id=None,
            department_name=None,
            level=level,
            assignee_id=assignee_id,
            assignee_name=assignee_name,
            unassigned=assignee_id is None,
        )

    def _to_ticket_response(self, ticket: Ticket) -> TicketResponse:
        assigned_agent_id, assigned_agent_name = self._resolve_assigned_agent(ticket)

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
            assigned_agent_id=assigned_agent_id,
            assigned_agent_name=assigned_agent_name,
        )
