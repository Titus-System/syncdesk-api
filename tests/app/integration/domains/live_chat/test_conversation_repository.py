from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.live_chat.entities import ChatMessage, Conversation
from app.domains.live_chat.exceptions import ParentConversationNotFoundError
from app.domains.live_chat.repositories import ConversationRepository
from app.domains.live_chat.schemas import CreateConversationDTO


# Clean up the Conversation collection before each test
@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversation_collection():
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()


class TestConversationRepository:

    create_dto = CreateConversationDTO(
        ticket_id = PydanticObjectId(),
        agent_id = uuid4(),
        client_id = uuid4(),
    )

    @pytest.fixture
    def conversation_repo(
        self, mongo_db_conn: AsyncIOMotorDatabase[dict[str,Any]]
    ) -> ConversationRepository:
        return ConversationRepository(mongo_db_conn)


    @pytest.mark.asyncio
    async def test_create_conversation_success(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        assert isinstance(conversation.id, PydanticObjectId)
        assert conversation.agent_id == self.create_dto.agent_id


    @pytest.mark.asyncio
    async def test_create_conversation_duplicate_index_should_fail(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c1 = await conversation_repo.create(self.create_dto)
        with pytest.raises(ResourceAlreadyExistsError):
            await conversation_repo.create(
                CreateConversationDTO(
                    ticket_id = self.create_dto.ticket_id,
                    agent_id = uuid4(),
                    client_id = self.create_dto.client_id,
                    sequential_index = c1.sequential_index
                )
            )


    @pytest.mark.asyncio
    async def test_create_conversation_sequential_index(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c1 = await conversation_repo.create(self.create_dto)
        c2 = await conversation_repo.create(
            CreateConversationDTO(
                ticket_id = self.create_dto.ticket_id,
                agent_id = uuid4(),
                client_id = self.create_dto.client_id,
                sequential_index = c1.sequential_index + 1,
                parent_id = c1.id
            )
        )
        assert c1.id is not None
        assert c2.id is not None
        assert c1.id != c2.id
        assert c2.parent_id == c1.id
        assert c1.sequential_index == 0
        assert c2.sequential_index == 1


    @pytest.mark.asyncio
    async def test_create_conversation_invalid_parent_should_fail(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c1 = await conversation_repo.create(self.create_dto)
        with pytest.raises(ParentConversationNotFoundError):
            await conversation_repo.create(
                CreateConversationDTO(
                    ticket_id = self.create_dto.ticket_id,
                    agent_id = uuid4(),
                    client_id = self.create_dto.client_id,
                    sequential_index = c1.sequential_index + 1,
                    parent_id = PydanticObjectId()
                )
            )

    @pytest.mark.asyncio
    async def test_get_conversation_by_id(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        found = await conversation_repo.get_by_id(conversation.id)
        assert found is not None
        assert found.id == conversation.id
        assert found.client_id == self.create_dto.client_id

    @pytest.mark.asyncio
    async def test_get_conversation_participants(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        participants = await conversation_repo.get_chat_participants(conversation.id)
        assert participants is not None
        assert participants.client_id == self.create_dto.client_id
        assert participants.agent_id == self.create_dto.agent_id


    @pytest.mark.asyncio
    async def test_get_conversation_by_service_id(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        found_list = await conversation_repo.get_by_ticket_id(
                        self.create_dto.ticket_id
                        )
        assert isinstance(found_list, list)
        assert any(c.id == conversation.id for c in found_list)


    @pytest.mark.asyncio
    async def test_get_paginated_messages(
        self, conversation_repo: ConversationRepository
    ) -> None:
        self.create_dto.sequential_index = 0
        conversation_ids: list[PydanticObjectId] = []
        for i in range(10):
            c = await conversation_repo.create(self.create_dto)
            assert c is not None
            conversation_ids.append(c.id)
            for j in range(5):
                message = ChatMessage.create(
                    c.id, self.create_dto.client_id, "text", f"conversation {i}, message {j}"
                )
                await conversation_repo.add_message(c.id, message)
            self.create_dto.sequential_index += 1
        self.create_dto.sequential_index = 0

        page1 = await conversation_repo.get_paginated_messages(
            self.create_dto.ticket_id, 1, 10
        )

        assert page1 is not None
        assert page1.total == 50
        assert page1.page == 1
        assert page1.limit == 10
        assert page1.has_next is True
        assert len(page1.messages) == 10

        assert page1.messages[0].conversation_id == conversation_ids[8]
        assert page1.messages[0].content == "conversation 8, message 0"
        assert page1.messages[4].content == "conversation 8, message 4"
        assert page1.messages[5].conversation_id == conversation_ids[9]
        assert page1.messages[9].content == "conversation 9, message 4"

        page2 = await conversation_repo.get_paginated_messages(
            self.create_dto.ticket_id, 2, 10
        )
        assert page2 is not None
        assert page2.total == 50
        assert page2.page == 2
        assert page2.limit == 10
        assert page2.has_next is True
        assert len(page2.messages) == 10
        assert page2.messages[0].conversation_id == conversation_ids[6]
        assert page2.messages[5].conversation_id == conversation_ids[7]

        page5 = await conversation_repo.get_paginated_messages(
            self.create_dto.ticket_id, 5, 10
        )
        assert page5 is not None
        assert page5.total == 50
        assert page5.page == 5
        assert page5.has_next is False
        assert len(page5.messages) == 10
        assert page5.messages[0].conversation_id == conversation_ids[0]
        assert page5.messages[0].content == "conversation 0, message 0"

    @pytest.mark.asyncio
    async def test_get_paginated_messages_last_page_partial(
        self, conversation_repo: ConversationRepository
    ) -> None:
        self.create_dto.sequential_index = 0
        for i in range(3):
            c = await conversation_repo.create(self.create_dto)
            assert c is not None
            for j in range(5):
                message = ChatMessage.create(
                    c.id, self.create_dto.client_id, "text", f"conv {i}, msg {j}"
                )
                await conversation_repo.add_message(c.id, message)
            self.create_dto.sequential_index += 1
        self.create_dto.sequential_index = 0

        # 15 total, limit 10 → page 2 should have only 5, not 10
        page2 = await conversation_repo.get_paginated_messages(
            self.create_dto.ticket_id, 2, 10
        )
        assert page2 is not None
        assert page2.total == 15
        assert page2.page == 2
        assert page2.has_next is False
        assert len(page2.messages) == 5
        assert page2.messages[0].content == "conv 0, msg 0"
        assert page2.messages[4].content == "conv 0, msg 4"

    async def get_current_conversation_participants(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        participants = await conversation_repo.get_current_ticket_participants(
            self.create_dto.ticket_id)

        assert isinstance(participants, tuple)
        assert self.create_dto.client_id in participants
        assert self.create_dto.agent_id in participants

        participants = await conversation_repo.get_current_ticket_participants(
            PydanticObjectId())
        assert participants is None


    @pytest.mark.asyncio
    async def test_conversation_exists(
        self, conversation_repo: ConversationRepository
    ) -> None:
        conversation = await conversation_repo.create(self.create_dto)
        assert conversation is not None
        exists = await conversation_repo.conversation_exists(conversation.id)
        assert exists is True
        not_exists = await conversation_repo.conversation_exists(PydanticObjectId())
        assert not_exists is False


    @pytest.mark.asyncio
    async def test_update_conversation(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c = await conversation_repo.create(self.create_dto)
        assert c is not None
        assert c.agent_id == self.create_dto.agent_id
        assert c.client_id == self.create_dto.client_id
        assert c.sequential_index == 0
        # Update multiple fields
        new_agent = uuid4()
        new_sequential_index = 42
        c.agent_id = new_agent
        c.sequential_index = new_sequential_index
        await conversation_repo.update(c)
        updated = await conversation_repo.get_by_id(c.id)
        assert updated is not None
        assert updated.agent_id == new_agent
        assert updated.sequential_index == new_sequential_index
        assert updated.client_id == self.create_dto.client_id
        assert updated.id == c.id


    @pytest.mark.asyncio
    async def test_delete_conversation(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c = await conversation_repo.create(self.create_dto)
        assert c is not None
        deleted = await conversation_repo.delete(c.id)
        assert deleted is not None
        assert deleted.id == c.id
        # Ensure it is gone
        found = await conversation_repo.get_by_id(c.id)
        assert found is None


    @pytest.mark.asyncio
    async def test_add_conversation_message_success(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c = await conversation_repo.create(self.create_dto)
        assert c is not None
        message = ChatMessage.create(
            conversation_id=c.id,
            sender_id=self.create_dto.client_id,
            type="text",
            content="Hello!"
        )
        await conversation_repo.add_message(c.id, message)
        updated = await conversation_repo.get_by_id(c.id)
        assert updated is not None
        assert len(updated.messages) == 1
        assert updated.messages[0].content == "Hello!"
        assert updated.messages[0].sender_id == self.create_dto.client_id

    @pytest.mark.asyncio
    async def test_add_message_invalid_conversation_should_fail(
        self, conversation_repo: ConversationRepository
    ) -> None:
        invalid_id = PydanticObjectId()
        message = ChatMessage.create(
            conversation_id=invalid_id,
            sender_id=self.create_dto.client_id,
            type="text",
            content="Should fail"
        )
        with pytest.raises(ValueError):
            await conversation_repo.add_message(invalid_id, message)

    @pytest.mark.asyncio
    async def test_attribute_agent(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c = await conversation_repo.create(self.create_dto)
        assert c is not None
        new_agent = uuid4()
        await conversation_repo.attribute_agent(c.id, new_agent)
        updated = await conversation_repo.get_by_id(c.id)
        assert updated is not None
        assert updated.agent_id == new_agent

    @pytest.mark.asyncio
    async def test_attribute_agent_invalid_conversation(
        self, conversation_repo: ConversationRepository
    ) -> None:
        invalid_id = PydanticObjectId()
        new_agent = uuid4()
        with pytest.raises(ResourceNotFoundError):
            await conversation_repo.attribute_agent(invalid_id, new_agent)

    async def test_get_by_client_id(
        self, conversation_repo: ConversationRepository
    ) -> None:
        # Edge: client_id com uma conversa
        self.create_dto.client_id = uuid4()
        c = await conversation_repo.create(self.create_dto)
        assert c is not None

        convos = await conversation_repo.get_by_client_id(self.create_dto.client_id)
        assert convos
        assert isinstance(convos, list)
        assert convos[0].id
        assert convos[0].client_id == self.create_dto.client_id

    async def test_get_by_client_empty(
        self, conversation_repo: ConversationRepository
    ) -> None:
        # Edge: client_id nunca usado
        convos = await conversation_repo.get_by_client_id(uuid4())
        assert convos == []
        assert len(convos) == 0
        assert isinstance(convos, list)

    async def test_get_by_client_multiple_conversations(self, conversation_repo: ConversationRepository) -> None:
        # Edge: client_id com múltiplas conversas
        client_id = uuid4()
        dtos = [
            CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=uuid4(), client_id=client_id, sequential_index=i)
            for i in range(3)
        ]
        for dto in dtos:
            await conversation_repo.create(dto)
        convos = await conversation_repo.get_by_client_id(client_id)
        assert len(convos) == 3
        # Deve estar ordenado por sequential_index
        indices = [c.sequential_index for c in convos]
        assert indices == sorted(indices)

    async def test_get_by_client_with_and_without_agent(self, conversation_repo: ConversationRepository) -> None:
        # Edge: client_id com conversas com e sem agent_id
        client_id = uuid4()
        dto1 = CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=None, client_id=client_id)
        dto2 = CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=uuid4(), client_id=client_id)
        await conversation_repo.create(dto1)
        await conversation_repo.create(dto2)
        convos = await conversation_repo.get_by_client_id(client_id)
        assert len(convos) == 2
        agent_ids = [c.agent_id for c in convos]
        assert any(a is None for a in agent_ids)
        assert any(a is not None for a in agent_ids)

    async def test_get_by_client_id_with_finalized_and_open_conversations(self, conversation_repo: ConversationRepository) -> None:
        # Edge: client_id com conversas abertas e finalizadas
        client_id = uuid4()
        dto_open = CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=uuid4(), client_id=client_id)
        dto_closed = CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=uuid4(), client_id=client_id)
        open_conv = await conversation_repo.create(dto_open)
        closed_conv = await conversation_repo.create(dto_closed)
        # Finaliza uma conversa
        closed_conv.finished_at = datetime.now()
        await conversation_repo.update(closed_conv)
        convos = await conversation_repo.get_by_client_id(client_id)
        assert len(convos) == 2
        assert any(c.finished_at is not None for c in convos)
        assert any(c.finished_at is None for c in convos)

    # --- ticket_has_conversation ---

    @pytest.mark.asyncio
    async def test_ticket_has_conversation_true(
        self, conversation_repo: ConversationRepository
    ) -> None:
        await conversation_repo.create(self.create_dto)
        assert await conversation_repo.ticket_has_conversation(self.create_dto.ticket_id) is True

    @pytest.mark.asyncio
    async def test_ticket_has_conversation_false(
        self, conversation_repo: ConversationRepository
    ) -> None:
        assert await conversation_repo.ticket_has_conversation(PydanticObjectId()) is False

    @pytest.mark.asyncio
    async def test_ticket_has_conversation_multiple(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        for i in range(3):
            await conversation_repo.create(CreateConversationDTO(
                ticket_id=ticket_id,
                agent_id=uuid4(),
                client_id=client_id,
                sequential_index=i,
            ))
        assert await conversation_repo.ticket_has_conversation(ticket_id) is True

    # --- get_last_by_ticket_id ---

    @pytest.mark.asyncio
    async def test_get_last_by_ticket_id_single(
        self, conversation_repo: ConversationRepository
    ) -> None:
        c = await conversation_repo.create(self.create_dto)
        last = await conversation_repo.get_last_by_ticket_id(self.create_dto.ticket_id)
        assert last is not None
        assert last.id == c.id
        assert last.sequential_index == 0

    @pytest.mark.asyncio
    async def test_get_last_by_ticket_id_multiple_inserted_out_of_order(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        insertion_order = [1, 0, 2]
        ids: dict[int, PydanticObjectId] = {}
        for idx in insertion_order:
            c = await conversation_repo.create(CreateConversationDTO(
                ticket_id=ticket_id,
                agent_id=uuid4(),
                client_id=client_id,
                sequential_index=idx,
            ))
            assert c.id is not None
            ids[idx] = c.id

        last = await conversation_repo.get_last_by_ticket_id(ticket_id)
        assert last is not None
        assert last.id == ids[2]
        assert last.sequential_index == 2

    @pytest.mark.asyncio
    async def test_get_last_by_ticket_id_does_not_cross_tickets(
        self, conversation_repo: ConversationRepository
    ) -> None:
        client_id = uuid4()
        ticket_a = PydanticObjectId()
        ticket_b = PydanticObjectId()

        await conversation_repo.create(CreateConversationDTO(
            ticket_id=ticket_a, agent_id=uuid4(), client_id=client_id, sequential_index=0,
        ))
        await conversation_repo.create(CreateConversationDTO(
            ticket_id=ticket_b, agent_id=uuid4(), client_id=client_id, sequential_index=5,
        ))

        last_a = await conversation_repo.get_last_by_ticket_id(ticket_a)
        assert last_a is not None
        assert last_a.sequential_index == 0
        assert last_a.ticket_id == ticket_a

    @pytest.mark.asyncio
    async def test_get_last_by_ticket_id_none(
        self, conversation_repo: ConversationRepository
    ) -> None:
        last = await conversation_repo.get_last_by_ticket_id(PydanticObjectId())
        assert last is None

    # --- add_child ---

    @pytest.mark.asyncio
    async def test_add_child(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        parent = await conversation_repo.create(CreateConversationDTO(
            ticket_id=ticket_id, agent_id=uuid4(), client_id=client_id,
        ))
        assert parent.id is not None
        child = await conversation_repo.create(CreateConversationDTO(
            ticket_id=ticket_id, agent_id=uuid4(), client_id=client_id,
            sequential_index=1, parent_id=parent.id,
        ))
        assert child.id is not None

        await conversation_repo.add_child(parent.id, child.id)

        updated_parent = await conversation_repo.get_by_id(parent.id)
        assert updated_parent is not None
        assert updated_parent.children_ids is not None
        assert child.id in updated_parent.children_ids

    @pytest.mark.asyncio
    async def test_add_child_multiple(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        parent = await conversation_repo.create(CreateConversationDTO(
            ticket_id=ticket_id, agent_id=uuid4(), client_id=client_id,
        ))
        assert parent.id is not None

        child_ids: list[PydanticObjectId] = []
        for i in range(1, 4):
            child = await conversation_repo.create(CreateConversationDTO(
                ticket_id=ticket_id, agent_id=uuid4(), client_id=client_id,
                sequential_index=i, parent_id=parent.id,
            ))
            assert child.id is not None
            child_ids.append(child.id)
            await conversation_repo.add_child(parent.id, child.id)

        updated_parent = await conversation_repo.get_by_id(parent.id)
        assert updated_parent is not None
        assert updated_parent.children_ids is not None
        assert updated_parent.children_ids == child_ids

    @pytest.mark.asyncio
    async def test_add_child_nonexistent_parent_is_noop(
        self, conversation_repo: ConversationRepository
    ) -> None:
        fake_parent = PydanticObjectId()
        fake_child = PydanticObjectId()
        await conversation_repo.add_child(fake_parent, fake_child)

        doc = await conversation_repo.get_by_id(fake_parent)
        assert doc is None

    # --- search_conversation_by_text ---

    async def _seed_conversation_with_messages(
        self,
        conversation_repo: ConversationRepository,
        contents: list[str],
        ticket_id: PydanticObjectId | None = None,
        client_id: UUID | None = None,
        agent_id: UUID | None = None,
        sequential_index: int = 0,
    ) -> Conversation:
        conv = await conversation_repo.create(
            CreateConversationDTO(
                ticket_id=ticket_id or PydanticObjectId(),
                agent_id=agent_id if agent_id is not None else uuid4(),
                client_id=client_id or uuid4(),
                sequential_index=sequential_index,
            )
        )
        assert conv.id is not None
        for content in contents:
            await conversation_repo.add_message(
                conv.id,
                ChatMessage.create(
                    conversation_id=conv.id,
                    sender_id=conv.client_id,
                    type="text",
                    content=content,
                ),
            )
        refreshed = await conversation_repo.get_by_id(conv.id)
        assert refreshed is not None
        return refreshed

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_matches_message_content(
        self, conversation_repo: ConversationRepository
    ) -> None:
        match = await self._seed_conversation_with_messages(
            conversation_repo, ["olá, preciso de ajuda com o boleto"]
        )
        await self._seed_conversation_with_messages(
            conversation_repo, ["nada relacionado aqui"]
        )

        res = await conversation_repo.search_conversation_by_text("boleto")
        assert len(res) == 1
        assert res[0].id == match.id

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_is_case_insensitive(
        self, conversation_repo: ConversationRepository
    ) -> None:
        match = await self._seed_conversation_with_messages(
            conversation_repo, ["Erro no LOGIN do sistema"]
        )

        res = await conversation_repo.search_conversation_by_text("login")
        assert len(res) == 1
        assert res[0].id == match.id

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_escapes_regex_metacharacters(
        self, conversation_repo: ConversationRepository
    ) -> None:
        match = await self._seed_conversation_with_messages(
            conversation_repo, ["valor cobrado: R$ 1.99 (promo)"]
        )
        await self._seed_conversation_with_messages(
            conversation_repo, ["valor cobrado: R$ 1X99"]
        )

        res = await conversation_repo.search_conversation_by_text("1.99")
        assert len(res) == 1
        assert res[0].id == match.id

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_returns_one_per_ticket(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await self._seed_conversation_with_messages(
            conversation_repo,
            ["primeira menção ao reembolso"],
            ticket_id=ticket_id,
            client_id=client_id,
            sequential_index=0,
        )
        latest_match = await self._seed_conversation_with_messages(
            conversation_repo,
            ["nova mensagem sobre reembolso"],
            ticket_id=ticket_id,
            client_id=client_id,
            sequential_index=1,
        )

        res = await conversation_repo.search_conversation_by_text("reembolso")
        assert len(res) == 1
        assert res[0].id == latest_match.id
        assert res[0].sequential_index == 1

    @pytest.mark.asyncio
    async def test_search_conversation_picks_highest_match_score_per_ticket(
        self, conversation_repo: ConversationRepository
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        best = await self._seed_conversation_with_messages(
            conversation_repo,
            [
                "primeiro contato sobre reembolso",
                "ainda discutindo reembolso",
                "novo pedido de reembolso registrado",
            ],
            ticket_id=ticket_id,
            client_id=client_id,
            sequential_index=0,
        )
        await self._seed_conversation_with_messages(
            conversation_repo,
            ["apenas uma menção a reembolso aqui"],
            ticket_id=ticket_id,
            client_id=client_id,
            sequential_index=1,
        )

        res = await conversation_repo.search_conversation_by_text("reembolso")
        assert len(res) == 1
        assert res[0].id == best.id
        assert res[0].sequential_index == 0

    @pytest.mark.asyncio
    async def test_search_conversation_orders_results_by_match_score(
        self, conversation_repo: ConversationRepository
    ) -> None:
        few = await self._seed_conversation_with_messages(
            conversation_repo, ["uma menção a reembolso"]
        )
        many = await self._seed_conversation_with_messages(
            conversation_repo,
            [
                "reembolso solicitado",
                "reembolso em análise",
                "reembolso aprovado",
            ],
        )

        res = await conversation_repo.search_conversation_by_text("reembolso")
        assert [c.id for c in res] == [many.id, few.id]

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_scoped_by_client(
        self, conversation_repo: ConversationRepository
    ) -> None:
        target_client = uuid4()
        owned = await self._seed_conversation_with_messages(
            conversation_repo,
            ["preciso de ajuda urgente"],
            client_id=target_client,
        )
        await self._seed_conversation_with_messages(
            conversation_repo, ["preciso de ajuda urgente"]
        )

        res = await conversation_repo.search_conversation_by_text(
            "urgente", client_id=target_client
        )
        assert len(res) == 1
        assert res[0].id == owned.id
        assert res[0].client_id == target_client

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_scoped_by_agent(
        self, conversation_repo: ConversationRepository
    ) -> None:
        target_agent = uuid4()
        owned = await self._seed_conversation_with_messages(
            conversation_repo,
            ["cliente reclamou da fatura"],
            agent_id=target_agent,
        )
        await self._seed_conversation_with_messages(
            conversation_repo, ["cliente reclamou da fatura"]
        )

        res = await conversation_repo.search_conversation_by_text(
            "fatura", agent_id=target_agent
        )
        assert len(res) == 1
        assert res[0].id == owned.id
        assert res[0].agent_id == target_agent

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_scoped_by_agent_string_legacy(
        self, conversation_repo: ConversationRepository
    ) -> None:
        target_agent = uuid4()
        legacy = await self._seed_conversation_with_messages(
            conversation_repo, ["assunto sobre integração"]
        )
        assert legacy.id is not None
        await Conversation.get_motor_collection().update_one(
            {"_id": legacy.id},
            {"$set": {"agent_id": str(target_agent)}},
        )

        res = await conversation_repo.search_conversation_by_text(
            "integração", agent_id=target_agent
        )
        assert len(res) == 1
        assert res[0].id == legacy.id

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_no_results(
        self, conversation_repo: ConversationRepository
    ) -> None:
        await self._seed_conversation_with_messages(
            conversation_repo, ["alguma mensagem qualquer"]
        )

        res = await conversation_repo.search_conversation_by_text("inexistente")
        assert res == []

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_skips_conversations_without_messages(
        self, conversation_repo: ConversationRepository
    ) -> None:
        await conversation_repo.create(
            CreateConversationDTO(
                ticket_id=PydanticObjectId(),
                agent_id=uuid4(),
                client_id=uuid4(),
            )
        )

        res = await conversation_repo.search_conversation_by_text("qualquer")
        assert res == []

    @pytest.mark.asyncio
    async def test_search_conversation_by_text_scope_excludes_other_users(
        self, conversation_repo: ConversationRepository
    ) -> None:
        other_client = uuid4()
        await self._seed_conversation_with_messages(
            conversation_repo,
            ["cobrança duplicada"],
            client_id=other_client,
        )

        res = await conversation_repo.search_conversation_by_text(
            "cobrança", client_id=uuid4()
        )
        assert res == []
