import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import (
    EVENT_PAYLOAD_MAP,
    TicketAssigneeUpdatedEventSchema,
    TicketCreatedEventSchema,
)
from app.core.logger import get_logger
from app.domains.auth.entities import Role, User, UserWithRoles
from app.domains.auth.services.user_service import UserService
from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.listeners import ConversationListener
from app.domains.live_chat.repositories.conversation_repository import ConversationRepository
from app.domains.live_chat.services.conversation_service import ConversationService
from app.domains.ticket.models import Ticket, TicketCriticality, TicketType
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import AssignTicketRequest, CreateTicketDTO
from app.domains.ticket.services import TicketService


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_collections() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    await Conversation.delete_all()
    yield
    await Ticket.delete_all()
    await Conversation.delete_all()


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.ticket_pubsub"))


@pytest.fixture
def user_service() -> UserService:
    service = AsyncMock(spec=UserService)

    async def _get_by_id(user_id: UUID) -> User:
        return User(
            id=user_id,
            email="client@example.com",
            name="Test Client",
            username="testclient",
        )

    async def _get_by_id_with_roles(user_id: UUID) -> UserWithRoles:
        return UserWithRoles(
            id=user_id,
            email="agent@example.com",
            name="Test Agent",
            username="testagent",
            roles=[Role(id=1, name="agent")],
        )

    service.get_by_id.side_effect = _get_by_id
    service.get_by_id_with_roles.side_effect = _get_by_id_with_roles
    return service


@pytest.fixture
def conversation_listener(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> ConversationListener:
    repo = ConversationRepository(mongo_db_conn)
    service = ConversationService(repo)
    return ConversationListener(service)


@pytest.fixture
def ticket_service(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    user_service: UserService,
    dispatcher: EventDispatcher,
) -> TicketService:
    return TicketService(TicketRepository(mongo_db_conn), user_service, dispatcher)


def _make_dto(client_id: UUID | None = None) -> CreateTicketDTO:
    return CreateTicketDTO(
        triage_id=PydanticObjectId(),
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema Financeiro",
        description="Erro ao emitir boleto",
        chat_ids=[],
        client_id=client_id or uuid4(),
        company_id=None,
        company_name=None,
    )


async def _drain_background_tasks() -> None:
    """The dispatcher runs handlers as fire-and-forget ``asyncio.create_task``.

    Tests must await those tasks before asserting on side effects.
    """
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class TestTicketCreatedPubSub:
    @pytest.mark.asyncio
    async def test_publishes_ticket_created_event(
        self,
        ticket_service: TicketService,
        dispatcher: EventDispatcher,
    ) -> None:
        received: list[TicketCreatedEventSchema] = []

        original_publish = dispatcher.publish

        async def spy_publish(event: AppEvent, payload: Any) -> None:
            if event == AppEvent.TICKET_CREATED:
                received.append(payload)
            await original_publish(event, payload)

        dispatcher.publish = spy_publish  # type: ignore[method-assign]

        dto = _make_dto()
        response = await ticket_service.create_ticket(dto)
        await _drain_background_tasks()

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, TicketCreatedEventSchema)
        assert str(event.ticket_id) == response.id
        assert event.client_id == dto.client_id

    @pytest.mark.asyncio
    async def test_listener_creates_conversation_for_published_event(
        self,
        ticket_service: TicketService,
        conversation_listener: ConversationListener,
        dispatcher: EventDispatcher,
    ) -> None:
        dispatcher.subscribe(
            AppEvent.TICKET_CREATED, conversation_listener.on_ticket_created
        )

        dto = _make_dto()
        response = await ticket_service.create_ticket(dto)
        await _drain_background_tasks()

        ticket_id = PydanticObjectId(response.id)
        conv = await conversation_listener.service.get_last_conversation_from_ticket(
            ticket_id
        )
        assert conv is not None
        assert conv.ticket_id == ticket_id
        assert conv.client_id == dto.client_id
        assert conv.is_opened()
        assert conv.sequential_index == 0

    @pytest.mark.asyncio
    async def test_event_is_not_delivered_without_subscription(
        self,
        ticket_service: TicketService,
        conversation_listener: ConversationListener,
    ) -> None:
        # Dispatcher has no subscribers registered here — listener is built but not wired up.
        dto = _make_dto()
        response = await ticket_service.create_ticket(dto)
        await _drain_background_tasks()

        conv = await conversation_listener.service.get_last_conversation_from_ticket(
            PydanticObjectId(response.id)
        )
        assert conv is None

    @pytest.mark.asyncio
    async def test_multiple_tickets_produce_one_conversation_each(
        self,
        ticket_service: TicketService,
        conversation_listener: ConversationListener,
        dispatcher: EventDispatcher,
    ) -> None:
        dispatcher.subscribe(
            AppEvent.TICKET_CREATED, conversation_listener.on_ticket_created
        )

        responses = [
            await ticket_service.create_ticket(_make_dto()) for _ in range(3)
        ]
        await _drain_background_tasks()

        for response in responses:
            conv = await conversation_listener.service.get_last_conversation_from_ticket(
                PydanticObjectId(response.id)
            )
            assert conv is not None
            assert conv.sequential_index == 0

    @pytest.mark.asyncio
    async def test_listener_idempotency_when_event_replayed(
        self,
        ticket_service: TicketService,
        conversation_listener: ConversationListener,
        dispatcher: EventDispatcher,
    ) -> None:
        dispatcher.subscribe(
            AppEvent.TICKET_CREATED, conversation_listener.on_ticket_created
        )

        dto = _make_dto()
        response = await ticket_service.create_ticket(dto)
        await _drain_background_tasks()

        replay = TicketCreatedEventSchema(
            ticket_id=PydanticObjectId(response.id),
            client_id=dto.client_id,
        )
        await dispatcher.publish(AppEvent.TICKET_CREATED, replay)
        await _drain_background_tasks()

        convs = await conversation_listener.service.get_chats_from_ticket(
            PydanticObjectId(response.id)
        )
        assert len(convs) == 1


class TestTicketAssigneeUpdatedPubSub:
    @pytest.mark.asyncio
    async def test_publishes_ticket_assignee_updated_event(
        self,
        ticket_service: TicketService,
        dispatcher: EventDispatcher,
    ) -> None:
        received: list[TicketAssigneeUpdatedEventSchema] = []

        original_publish = dispatcher.publish

        async def spy_publish(event: AppEvent, payload: Any) -> None:
            if event == AppEvent.TICKET_ASSIGNEE_UPDATED:
                received.append(payload)
            await original_publish(event, payload)

        dispatcher.publish = spy_publish  # type: ignore[method-assign]

        dto = _make_dto()
        created = await ticket_service.create_ticket(dto)
        ticket_id = PydanticObjectId(created.id)
        agent_id = uuid4()

        response = await ticket_service.assign_ticket(
            ticket_id,
            AssignTicketRequest(agent_id=agent_id, reason="Primeira atribuicao"),
        )
        await _drain_background_tasks()

        assert response.status.value == "in_progress"
        assert response.assigned_agent_id == agent_id
        assert len(received) == 1
        event = received[0]
        assert isinstance(event, TicketAssigneeUpdatedEventSchema)
        assert event.ticket_id == ticket_id
        assert event.client_id == dto.client_id
        assert event.new_agent_id == agent_id
        assert event.reason == "Primeira atribuicao"

    @pytest.mark.asyncio
    async def test_listener_reacts_to_published_assignee_event(
        self,
        ticket_service: TicketService,
        conversation_listener: ConversationListener,
        dispatcher: EventDispatcher,
    ) -> None:
        dispatcher.subscribe(
            AppEvent.TICKET_CREATED, conversation_listener.on_ticket_created
        )
        dispatcher.subscribe(
            AppEvent.TICKET_ASSIGNEE_UPDATED,
            conversation_listener.on_ticket_assignee_updated,
        )

        dto = _make_dto()
        created = await ticket_service.create_ticket(dto)
        ticket_id = PydanticObjectId(created.id)
        agent_id = uuid4()

        await _drain_background_tasks()

        await ticket_service.assign_ticket(
            ticket_id,
            AssignTicketRequest(agent_id=agent_id, reason="Encaminhado para atendimento"),
        )
        await _drain_background_tasks()

        convs = await conversation_listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 2
        assert not convs[0].is_opened()
        assert convs[1].is_opened()
        assert convs[1].agent_id == agent_id
