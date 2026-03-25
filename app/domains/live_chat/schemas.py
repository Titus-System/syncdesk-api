from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel


class CreateConversationDTO(BaseModel):
    service_session_id: PydanticObjectId
    agent_id: UUID | None = None
    client_id: UUID
    sequential_index: int = 0
    parent_id: UUID | None = None


class SetConversationAgentDTO(BaseModel):
    chat_id: PydanticObjectId
    agent_id: UUID
