from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.event_dispatcher.schemas import (
    TicketAssigneeUpdatedEventSchema,
    TicketClosedEventSchema,
    TicketCreatedEventSchema,
    TicketEscalatedEventSchema,
    TicketStatusUpdatedEventSchema,
)
from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.listeners import ConversationListener
from app.domains.live_chat.repositories.conversation_repository import ConversationRepository
from app.domains.live_chat.services.conversation_service import ConversationService
from app.domains.ticket.models import TicketStatus


@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversation_collection():
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()


@pytest.fixture
def listener(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> ConversationListener:
    repo = ConversationRepository(mongo_db_conn)
    service = ConversationService(repo)
    return ConversationListener(service)


TICKET_ID = PydanticObjectId()
CLIENT_ID = uuid4()
AGENT_ID = uuid4()


def _ticket_created_schema(
    ticket_id: PydanticObjectId = TICKET_ID,
    client_id: UUID = CLIENT_ID,
    agent_id: UUID | None = AGENT_ID,
) -> TicketCreatedEventSchema:
    return TicketCreatedEventSchema(
        ticket_id=ticket_id,
        client_id=client_id,
        agent_id=agent_id,
    )



class TestOnTicketCreated:

    @pytest.mark.asyncio
    async def test_creates_conversation(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        schema = _ticket_created_schema(ticket_id=ticket_id)

        await listener.on_ticket_created(schema)

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.ticket_id == ticket_id
        assert conv.client_id == schema.client_id
        assert conv.agent_id == schema.agent_id
        assert conv.sequential_index == 0
        assert conv.is_opened()

    @pytest.mark.asyncio
    async def test_idempotent_does_not_duplicate(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        schema = _ticket_created_schema(ticket_id=ticket_id)

        await listener.on_ticket_created(schema)
        await listener.on_ticket_created(schema)

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 1

    @pytest.mark.asyncio
    async def test_without_agent(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        schema = _ticket_created_schema(ticket_id=ticket_id, agent_id=None)

        await listener.on_ticket_created(schema)

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.agent_id is None



class TestOnTicketAssigneeUpdated:

    @pytest.mark.asyncio
    async def test_closes_old_and_opens_new_conversation(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        new_agent = uuid4()
        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=new_agent,
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 2

        old_conv = convs[0]
        new_conv = convs[1]

        assert not old_conv.is_opened()
        assert new_conv.is_opened()
        assert new_conv.agent_id == new_agent
        assert new_conv.sequential_index == 1
        assert new_conv.parent_id == old_conv.id

    @pytest.mark.asyncio
    async def test_posts_closing_message_to_old_conversation(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert convs[0].id is not None
        old_conv = await listener.service.get_by_id(convs[0].id)
        assert old_conv is not None
        assert len(old_conv.messages) == 1
        assert old_conv.messages[0].sender_id == "System"
        assert "transferido" in old_conv.messages[0].content

    @pytest.mark.asyncio
    async def test_populates_children_ids_on_parent(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert convs[0].id is not None
        parent = await listener.service.get_by_id(convs[0].id)
        assert parent is not None
        assert convs[1].id in parent.children_ids

    @pytest.mark.asyncio
    async def test_multiple_consecutive_assignee_changes(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        agent_1 = uuid4()
        agent_2 = uuid4()
        agent_3 = uuid4()

        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id, agent_id=agent_1)
        )

        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(ticket_id=ticket_id, client_id=client_id, new_agent_id=agent_2)
        )
        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(ticket_id=ticket_id, client_id=client_id, new_agent_id=agent_3)
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 3

        assert not convs[0].is_opened()
        assert convs[0].agent_id == agent_1
        assert convs[0].sequential_index == 0

        assert not convs[1].is_opened()
        assert convs[1].agent_id == agent_2
        assert convs[1].sequential_index == 1
        assert convs[1].parent_id == convs[0].id

        assert convs[2].is_opened()
        assert convs[2].agent_id == agent_3
        assert convs[2].sequential_index == 2
        assert convs[2].parent_id == convs[1].id

        # children_ids chain
        assert convs[0].id is not None
        assert convs[1].id is not None
        c0 = await listener.service.get_by_id(convs[0].id)
        c1 = await listener.service.get_by_id(convs[1].id)
        assert c0 is not None
        assert convs[1].id in c0.children_ids
        assert c1 is not None
        assert convs[2].id in c1.children_ids

    @pytest.mark.asyncio
    async def test_no_previous_conversation_creates_first(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()

        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
            )
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.sequential_index == 0
        assert conv.parent_id is None



class TestOnTicketEscalated:

    @pytest.mark.asyncio
    async def test_closes_old_and_opens_new_conversation(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        new_agent = uuid4()
        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=new_agent,
                new_agent_name="Senior Agent",
                new_level="L2",
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 2

        old_conv = convs[0]
        new_conv = convs[1]

        assert not old_conv.is_opened()
        assert new_conv.is_opened()
        assert new_conv.agent_id == new_agent
        assert new_conv.sequential_index == 1

    @pytest.mark.asyncio
    async def test_posts_escalation_message_to_both_conversations(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
                new_agent_name="Senior Agent",
                new_level="L2",
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert convs[0].id is not None
        assert convs[1].id is not None
        old_conv = await listener.service.get_by_id(convs[0].id)
        new_conv = await listener.service.get_by_id(convs[1].id)

        assert old_conv is not None
        assert len(old_conv.messages) == 1
        assert "escalonado" in old_conv.messages[0].content
        assert "L2" in old_conv.messages[0].content
        assert "Senior Agent" in old_conv.messages[0].content

        assert new_conv is not None
        assert len(new_conv.messages) == 1
        assert "escalonado" in new_conv.messages[0].content

    @pytest.mark.asyncio
    async def test_escalation_without_agent_name_shows_pending(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=None,
                new_agent_name=None,
                new_level="L3",
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert convs[0].id is not None
        old_conv = await listener.service.get_by_id(convs[0].id)
        assert old_conv is not None
        assert "agente pendente" in old_conv.messages[0].content

    @pytest.mark.asyncio
    async def test_no_previous_conversation_creates_first(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()

        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
                new_agent_name="Agent",
                new_level="L2",
            )
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.sequential_index == 0
        assert conv.parent_id is None

    @pytest.mark.asyncio
    async def test_populates_children_ids_on_parent(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=uuid4(),
                new_agent_name="Agent",
                new_level="L2",
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert convs[0].id is not None
        parent = await listener.service.get_by_id(convs[0].id)
        assert parent is not None
        assert convs[1].id in parent.children_ids


class TestOnTicketStatusUpdated:

    @pytest.mark.asyncio
    async def test_posts_status_message(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id)
        )

        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(
                ticket_id=ticket_id,
                new_status=TicketStatus.IN_PROGRESS,
            )
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.id is not None
        conv_full = await listener.service.get_by_id(conv.id)
        assert conv_full is not None
        assert len(conv_full.messages) == 1
        assert conv_full.messages[0].sender_id == "System"
        assert "in_progress" in conv_full.messages[0].content

    @pytest.mark.asyncio
    async def test_no_conversation_is_noop(self, listener: ConversationListener) -> None:
        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(
                ticket_id=PydanticObjectId(),
                new_status=TicketStatus.OPEN,
            )
        )
        # no exception raised

    @pytest.mark.asyncio
    async def test_multiple_status_updates_append_messages(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id)
        )

        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(ticket_id=ticket_id, new_status=TicketStatus.IN_PROGRESS)
        )
        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(ticket_id=ticket_id, new_status=TicketStatus.WAITING_FOR_PROVIDER)
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.id is not None
        conv_full = await listener.service.get_by_id(conv.id)
        assert conv_full is not None
        assert len(conv_full.messages) == 2
        assert "in_progress" in conv_full.messages[0].content
        assert "waiting_for_provider" in conv_full.messages[1].content

    @pytest.mark.asyncio
    async def test_status_update_on_closed_conversation(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_closed(
            TicketClosedEventSchema(
                ticket_id=ticket_id,
                triage_id=PydanticObjectId(),
                client_id=client_id,
            )
        )

        # late status event arrives after close
        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(ticket_id=ticket_id, new_status=TicketStatus.FINISHED)
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.id is not None
        assert not conv.is_opened()
        conv_full = await listener.service.get_by_id(conv.id)
        assert conv_full is not None
        assert len(conv_full.messages) == 2
        assert "encerrado" in conv_full.messages[0].content
        assert "finished" in conv_full.messages[1].content


class TestOnTicketClosed:

    @pytest.mark.asyncio
    async def test_closes_conversation_with_message(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        await listener.on_ticket_closed(
            TicketClosedEventSchema(
                ticket_id=ticket_id,
                triage_id=PydanticObjectId(),
                client_id=client_id,
            )
        )

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert not conv.is_opened()
        assert conv.finished_at is not None
        assert conv.id is not None

        conv_full = await listener.service.get_by_id(conv.id)
        assert conv_full is not None
        assert len(conv_full.messages) == 1
        assert "encerrado" in conv_full.messages[0].content

    @pytest.mark.asyncio
    async def test_no_conversation_is_noop(self, listener: ConversationListener) -> None:
        await listener.on_ticket_closed(
            TicketClosedEventSchema(
                ticket_id=PydanticObjectId(),
                triage_id=PydanticObjectId(),
                client_id=uuid4(),
            )
        )
        # no exception raised

    @pytest.mark.asyncio
    async def test_double_close_does_not_duplicate_message(self, listener: ConversationListener) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id)
        )

        close_schema = TicketClosedEventSchema(
            ticket_id=ticket_id,
            triage_id=PydanticObjectId(),
            client_id=client_id,
        )

        await listener.on_ticket_closed(close_schema)
        await listener.on_ticket_closed(close_schema)

        conv = await listener.service.get_last_conversation_from_ticket(ticket_id)
        assert conv is not None
        assert conv.id is not None
        assert not conv.is_opened()
        conv_full = await listener.service.get_by_id(conv.id)
        assert conv_full is not None
        assert len(conv_full.messages) == 1
        assert "encerrado" in conv_full.messages[0].content


class TestFullFlow:

    @pytest.mark.asyncio
    async def test_ticket_lifecycle(self, listener: ConversationListener) -> None:
        """triage -> created -> status update -> assignee change -> escalation -> close"""
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        agent_1 = uuid4()
        agent_2 = uuid4()
        agent_3 = uuid4()

        # 1. ticket created
        await listener.on_ticket_created(
            _ticket_created_schema(ticket_id=ticket_id, client_id=client_id, agent_id=agent_1)
        )

        # 2. status update
        await listener.on_ticket_status_updated(
            TicketStatusUpdatedEventSchema(ticket_id=ticket_id, new_status=TicketStatus.IN_PROGRESS)
        )

        # 3. assignee change
        await listener.on_ticket_assignee_updated(
            TicketAssigneeUpdatedEventSchema(
                ticket_id=ticket_id, client_id=client_id, new_agent_id=agent_2
            )
        )

        # 4. escalation
        await listener.on_ticket_escalated(
            TicketEscalatedEventSchema(
                ticket_id=ticket_id,
                client_id=client_id,
                new_agent_id=agent_3,
                new_agent_name="L2 Agent",
                new_level="L2",
            )
        )

        # 5. close
        await listener.on_ticket_closed(
            TicketClosedEventSchema(
                ticket_id=ticket_id, triage_id=PydanticObjectId(), client_id=client_id
            )
        )

        convs = await listener.service.get_chats_from_ticket(ticket_id)
        assert len(convs) == 3

        # conv 0: agent_1, closed by assignee change
        assert convs[0].id is not None
        c0 = await listener.service.get_by_id(convs[0].id)
        assert c0 is not None
        assert c0.agent_id == agent_1
        assert not c0.is_opened()
        assert c0.sequential_index == 0
        # messages: status update + transfer closing
        assert len(c0.messages) == 2
        assert "in_progress" in c0.messages[0].content
        assert "transferido" in c0.messages[1].content

        # conv 1: agent_2, closed by escalation
        assert convs[1].id is not None
        c1 = await listener.service.get_by_id(convs[1].id)
        assert c1 is not None
        assert c1.agent_id == agent_2
        assert not c1.is_opened()
        assert c1.sequential_index == 1
        assert c1.parent_id == c0.id
        # messages: escalation closing
        assert len(c1.messages) == 1
        assert "escalonado" in c1.messages[0].content

        # conv 2: agent_3, closed by ticket close
        assert convs[2].id is not None
        c2 = await listener.service.get_by_id(convs[2].id)
        assert c2 is not None
        assert c2.agent_id == agent_3
        assert not c2.is_opened()
        assert c2.sequential_index == 2
        assert c2.parent_id == c1.id
        # messages: escalation opening + close
        assert len(c2.messages) == 2
        assert "escalonado" in c2.messages[0].content
        assert "encerrado" in c2.messages[1].content

        # children_ids chain
        assert c0.id is not None
        assert c1.id is not None
        c0_fresh = await listener.service.get_by_id(c0.id)
        c1_fresh = await listener.service.get_by_id(c1.id)
        assert c0_fresh is not None
        assert c1.id in c0_fresh.children_ids
        assert c1_fresh is not None
        assert c2.id in c1_fresh.children_ids
