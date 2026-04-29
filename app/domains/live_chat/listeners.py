from app.core.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.schemas import (
    TicketAssigneeUpdatedEventSchema,
    TicketClosedEventSchema,
    TicketCreatedEventSchema,
    TicketEscalatedEventSchema,
    TicketStatusUpdatedEventSchema,
)
from app.core.logger import get_logger
from app.db.mongo.db import mongo_db
from app.domains.live_chat.entities import ChatMessage
from app.domains.live_chat.schemas import CreateConversationDTO

from .metrics import listener_conversations_closed_total, listener_conversations_created_total
from .repositories.conversation_repository import ConversationRepository
from .services.conversation_service import ConversationService

logger = get_logger("app.live_chat.listener")


class ConversationListener:
    def __init__(self, conversation_service: ConversationService) -> None:
        self.service = conversation_service

    @event_handler(TicketCreatedEventSchema)
    async def on_ticket_created(self, schema: TicketCreatedEventSchema) -> None:
        if await self.service.ticket_has_conversation(schema.ticket_id):
            logger.debug(
                "Skipping TICKET_CREATED - conversation already exists for ticket %s",
                schema.ticket_id,
            )
            return

        await self.service.create(
            CreateConversationDTO(
                ticket_id=schema.ticket_id,
                agent_id=schema.agent_id,
                client_id=schema.client_id,
            )
        )
        listener_conversations_created_total.labels(event="ticket_created").inc()

    @event_handler(TicketAssigneeUpdatedEventSchema)
    async def on_ticket_assignee_updated(self, schema: TicketAssigneeUpdatedEventSchema) -> None:
        await self.service.append_conversation_to_ticket(
            schema.ticket_id,
            schema.client_id,
            schema.new_agent_id,
            closing_message="Chamado foi transferido para outro agente.",
        )
        listener_conversations_created_total.labels(event="ticket_assignee_updated").inc()
        listener_conversations_closed_total.labels(event="ticket_assignee_updated").inc()

    @event_handler(TicketEscalatedEventSchema)
    async def on_ticket_escalated(self, schema: TicketEscalatedEventSchema) -> None:
        agent_info = schema.new_agent_name or "agente pendente"
        escalation_msg = f"Chamado foi escalonado para o nivel {schema.new_level} ({agent_info})."

        conversation = await self.service.append_conversation_to_ticket(
            schema.ticket_id,
            schema.client_id,
            schema.new_agent_id,
            closing_message=escalation_msg,
        )
        listener_conversations_created_total.labels(event="ticket_escalated").inc()
        listener_conversations_closed_total.labels(event="ticket_escalated").inc()

        if conversation.id is None:
            return

        await self.service.add_message_to_conversation(
            conversation.id,
            ChatMessage.create(
                conversation_id=conversation.id,
                sender_id="System",
                type="text",
                content=escalation_msg,
            ),
        )

    @event_handler(TicketStatusUpdatedEventSchema)
    async def on_ticket_status_updated(self, schema: TicketStatusUpdatedEventSchema) -> None:
        conversation = await self.service.get_last_conversation_from_ticket(schema.ticket_id)
        if conversation is None or conversation.id is None:
            logger.debug(
                "Skipping TICKET_STATUS_UPDATED - no conversation found for ticket %s",
                schema.ticket_id,
            )
            return

        await self.service.add_message_to_conversation(
            conversation.id,
            ChatMessage.create(
                conversation_id=conversation.id,
                sender_id="System",
                type="text",
                content=f"Novo status do chamado: {schema.new_status.value}.",
            ),
        )

    @event_handler(TicketClosedEventSchema)
    async def on_ticket_closed(self, schema: TicketClosedEventSchema) -> None:
        closed_conversation = await self.service.close_active_ticket_conversation(
            schema.ticket_id,
            system_message="Chamado foi encerrado.",
        )
        if closed_conversation is None:
            logger.debug(
                "Skipping TICKET_CLOSED - no open conversation found for ticket %s",
                schema.ticket_id,
            )
            return
        listener_conversations_closed_total.labels(event="ticket_closed").inc()


def register_conversation_listener(dispatcher: EventDispatcher) -> None:
    repo = ConversationRepository(mongo_db.get_db())
    service = ConversationService(repo)
    listener = ConversationListener(service)

    dispatcher.subscribe(AppEvent.TICKET_CREATED, listener.on_ticket_created)
    dispatcher.subscribe(AppEvent.TICKET_ASSIGNEE_UPDATED, listener.on_ticket_assignee_updated)
    dispatcher.subscribe(AppEvent.TICKET_ESCALATED, listener.on_ticket_escalated)
    dispatcher.subscribe(AppEvent.TICKET_STATUS_UPDATED, listener.on_ticket_status_updated)
    dispatcher.subscribe(AppEvent.TICKET_CLOSED, listener.on_ticket_closed)
