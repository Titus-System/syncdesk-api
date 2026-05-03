from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import (
    TicketAssigneeUpdatedEventSchema,
    TicketClosedEventSchema,
    TicketCreatedEventSchema,
    TicketEscalatedEventSchema,
)
from app.db.mongo.db import mongo_db
from app.domains.live_chat.entities import ChatMessage
from app.domains.live_chat.metrics import (
    listener_conversations_closed_total,
    listener_conversations_created_total,
)
from app.domains.live_chat.repositories.conversation_repository import ConversationRepository
from app.domains.live_chat.services.conversation_service import ConversationService
from app.domains.ticket.models import Ticket


class ConversationListener:
    def __init__(self, service: ConversationService) -> None:
        self.service = service

    @event_handler(TicketCreatedEventSchema)
    async def on_ticket_created(self, schema: TicketCreatedEventSchema) -> None:
        has_conversation = await self.service.ticket_has_conversation(schema.ticket_id)

        if has_conversation:
            return

        conversation = await self.service.append_conversation_to_ticket(
            ticket_id=schema.ticket_id,
            client_id=schema.client_id,
            agent_id=schema.agent_id,
        )

        if conversation.id is not None:
            await self._attach_chat_to_ticket(str(schema.ticket_id), str(conversation.id))

        listener_conversations_created_total.labels(event="ticket_created").inc()

    @event_handler(TicketAssigneeUpdatedEventSchema)
    async def on_ticket_assignee_updated(
        self,
        schema: TicketAssigneeUpdatedEventSchema,
    ) -> None:
        conversation = await self.service.get_latest_open_by_ticket_id(schema.ticket_id)

        if conversation is None:
            conversation = await self.service.append_conversation_to_ticket(
                ticket_id=schema.ticket_id,
                client_id=schema.client_id,
                agent_id=schema.new_agent_id,
            )

            if conversation.id is not None:
                await self._attach_chat_to_ticket(str(schema.ticket_id), str(conversation.id))

            listener_conversations_created_total.labels(event="ticket_assignee_updated").inc()

            return

        if conversation.id is None:
            return

        await self.service.attribute_agent(conversation.id, schema.new_agent_id)

        await self.service.add_message_to_conversation(
            conversation.id,
            ChatMessage.create(
                conversation_id=conversation.id,
                sender_id="System",
                type="text",
                content="Chamado atribuído a um atendente.",
            ),
        )

    @event_handler(TicketEscalatedEventSchema)
    async def on_ticket_escalated(self, schema: TicketEscalatedEventSchema) -> None:
        conversation = await self.service.append_conversation_to_ticket(
            ticket_id=schema.ticket_id,
            client_id=schema.client_id,
            agent_id=schema.new_agent_id,
            closing_message="Atendimento transferido para outro nível de suporte.",
        )

        if conversation.id is not None:
            await self._attach_chat_to_ticket(str(schema.ticket_id), str(conversation.id))

        listener_conversations_created_total.labels(event="ticket_escalated").inc()
        listener_conversations_closed_total.labels(event="ticket_escalated").inc()

    @event_handler(TicketClosedEventSchema)
    async def on_ticket_closed(self, schema: TicketClosedEventSchema) -> None:
        closed = await self.service.close_active_ticket_conversation(
            ticket_id=schema.ticket_id,
            system_message="Atendimento encerrado.",
        )

        if closed is not None:
            listener_conversations_closed_total.labels(event="ticket_closed").inc()

    async def _attach_chat_to_ticket(self, ticket_id: str, chat_id: str) -> None:
        ticket = await Ticket.get(ticket_id)

        if ticket is None:
            return

        if chat_id in [str(item) for item in ticket.chat_ids]:
            return

        ticket.chat_ids.append(chat_id)
        await ticket.save()


def register_conversation_listener(dispatcher: EventDispatcher) -> None:
    service = ConversationService(
        ConversationRepository(mongo_db.get_db()),
    )

    listener = ConversationListener(service)

    dispatcher.subscribe(AppEvent.TICKET_CREATED, listener.on_ticket_created)
    dispatcher.subscribe(AppEvent.TICKET_ASSIGNEE_UPDATED, listener.on_ticket_assignee_updated)
    dispatcher.subscribe(AppEvent.TICKET_ESCALATED, listener.on_ticket_escalated)
    dispatcher.subscribe(AppEvent.TICKET_CLOSED, listener.on_ticket_closed)