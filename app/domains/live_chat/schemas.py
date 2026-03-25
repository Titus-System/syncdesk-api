from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel


class CreateConversationDTO(BaseModel):
    service_session_id: PydanticObjectId
    agent_id: UUID | None = None
    client_id: UUID
    sequential_index: int = 0
    parent_id: PydanticObjectId | None = None
