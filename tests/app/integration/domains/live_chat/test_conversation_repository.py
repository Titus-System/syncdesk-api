from typing import Any
from uuid import uuid4

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
        service_session_id = PydanticObjectId(),
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
                    service_session_id = self.create_dto.service_session_id,
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
                service_session_id = self.create_dto.service_session_id,
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
                    service_session_id = self.create_dto.service_session_id,
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
        found_list = await conversation_repo.get_by_service_session_id(
                        self.create_dto.service_session_id
                        )
        assert isinstance(found_list, list)
        assert any(c.id == conversation.id for c in found_list)


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
