from datetime import datetime
from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.core.schemas import BaseDTO
from app.domains.ticket.models import TicketCriticality, TicketStatus, TicketType


class CreateTicketDTO(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "type": "issue",
                "criticality": "high",
                "product": "Sistema Financeiro",
                "description": "Erro ao emitir boleto",
                "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
                "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
            }
        }
    }

    triage_id: PydanticObjectId
    type: TicketType
    criticality: TicketCriticality
    product: str
    description: str
    chat_ids: list[PydanticObjectId]
    client_id: UUID = Field(description="Identifier of the client user in the auth domain.")


class CreateTicketResponseDTO(BaseModel):
    id: str
    status: TicketStatus
    creation_date: datetime


class UpdateTicketStatusDTO(BaseDTO):
    model_config = {"json_schema_extra": {"example": {"status": "in_progress"}}}

    status: TicketStatus


class UpdateTicketStatusResponseDTO(BaseModel):
    id: str
    previous_status: TicketStatus
    current_status: TicketStatus
