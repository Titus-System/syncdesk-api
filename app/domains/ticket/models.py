from datetime import datetime
from uuid import UUID, uuid4

from beanie import Document, PydanticObjectId
from enum import Enum
from pydantic import BaseModel, Field


class TicketType(Enum):
    ISSUE = "issue"
    ACCESS = "access"
    NEW_FEATURE = "new_feature"


class TicketCriticality(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(Enum):
    OPEN = "open"
    AWAITING_ASSIGNMENT = "awaiting_assignment"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_PROVIDER = "waiting_for_provider"
    WAITING_FOR_VALIDATION = "waiting_for_validation"
    FINISHED = "finished"


class TicketComment(BaseModel):
    comment_id: UUID = Field(default_factory=uuid4)
    author: str
    text: str
    date: datetime
    internal: bool = False


class TicketCompany(BaseModel):
    id: UUID
    name: str


class TicketClient(BaseModel):
    id: UUID
    name: str
    email: str
    company: TicketCompany


class TicketHistory(BaseModel):
    agent_id: UUID
    name: str
    level: str
    assignment_date: datetime
    exit_date: datetime
    transfer_reason: str


class Ticket(Document):
    triage_id: PydanticObjectId
    type: TicketType
    criticality: TicketCriticality
    product: str
    status: TicketStatus
    creation_date: datetime
    description: str
    chat_ids: list[PydanticObjectId]
    agent_history: list[TicketHistory]
    client: TicketClient
    comments: list[TicketComment]

    class Settings:
        name = "tickets"
