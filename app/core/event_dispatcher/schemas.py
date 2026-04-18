from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel

from app.core.event_dispatcher.enums import AppEvent
from app.domains.ticket.models import TicketCriticality, TicketStatus, TicketType


class DispatcherSchema(BaseModel):
    """Base class for all event payloads. Every event schema must inherit from this."""

    pass


class TriageFinishedEventSchema(DispatcherSchema):
    """Emitted by ``ChatbotService`` when the triage flow completes.

    Listeners:
        - ``TicketListener`` - creates a ticket and publishes ``ticket.created``.
    """

    client_id: UUID
    client_email: str
    client_name: str
    company_id: UUID | None = None
    company_name: str | None = None
    attendance_id: PydanticObjectId
    ticket_type: TicketType
    ticket_criticality: TicketCriticality
    product_name: str
    ticket_description: str


class TicketCreatedEventSchema(DispatcherSchema):
    """Emitted by ``TicketListener`` after a ticket is created (in reaction to ``triage.finished``).

    Listeners:
        - ``ConversationListener`` - opens the first support conversation.
    """

    ticket_id: PydanticObjectId
    client_id: UUID
    agent_id: UUID | None = None


class TicketAssigneeUpdatedEventSchema(DispatcherSchema):
    """Emitted by ``TicketService`` when a ticket is assigned or transferred to another agent.

    Listeners:
        - ``ConversationListener`` - updates participants in the active conversation.
    """

    ticket_id: PydanticObjectId
    new_agent_id: UUID
    reason: str | None = None


class TicketStatusUpdatedEventSchema(DispatcherSchema):
    """Emitted by ``TicketService`` when a ticket's status changes.
    
    Listeners:
        - ``ConversationListener`` - updates message history with a system message
        - ``ChatbotService`` - Updates attendance status
        
    """

    ticket_id: PydanticObjectId
    new_status: TicketStatus


class TicketEscalatedEventSchema(DispatcherSchema):
    """Emitted by ``TicketService`` when a ticket is escalated to a higher support level.

    Listeners:
        - ``ConversationListener`` - opens a new conversation linked to the ticket.
    """

    ticket_id: PydanticObjectId
    new_agent_id: UUID | None = None
    new_agent_name: str | None = None
    new_level: str
    transfer_reason: str | None = None


class TicketClosedEventSchema(DispatcherSchema):
    """Emitted by ``TicketService`` when a ticket transitions to ``finished``.

    Listeners:
        - ``ConversationListener`` - closes the active conversation.
        - ``ChatbotListener`` - closes the attendance and requests evaluation.
    """

    ticket_id: PydanticObjectId
    triage_id: PydanticObjectId
    client_id: UUID


EVENT_PAYLOAD_MAP: dict[AppEvent, type[DispatcherSchema]] = {
    AppEvent.TRIAGE_FINISHED: TriageFinishedEventSchema,
    AppEvent.TICKET_ASSIGNEE_UPDATED: TicketAssigneeUpdatedEventSchema,
    AppEvent.TICKET_ESCALATED: TicketEscalatedEventSchema,
    AppEvent.TICKET_CLOSED: TicketClosedEventSchema,
    AppEvent.TICKET_CREATED: TicketCreatedEventSchema,
    AppEvent.TICKET_STATUS_UPDATED: TicketStatusUpdatedEventSchema,
}
