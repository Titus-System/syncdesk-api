from datetime import datetime
from typing import Literal
from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.core.schemas import BaseDTO
from app.domains.ticket.models import TicketCriticality, TicketStatus, TicketType


class PaginationDTO(BaseDTO):
    page: int = Field(default=1, ge=1, description="1-indexed page number.")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page.")


class PaginatedResponseMeta(BaseModel):
    page: int = Field(..., ge=1, description="Current page number.")
    page_size: int = Field(..., ge=1, le=100, description="Items returned per page.")
    total: int = Field(..., ge=0, description="Total number of matching records.")


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
                "company_id": "a4b9e7f1-2e7d-4cc1-9c12-7c7c9d10b321",
                "company_name": "ACME Finance",
            }
        }
    }

    triage_id: PydanticObjectId
    type: TicketType
    criticality: TicketCriticality
    product: str
    description: str
    chat_ids: list[PydanticObjectId] = Field(default_factory=list)
    client_id: UUID = Field(description="Identifier of the client user in the auth domain.")
    company_id: UUID = Field(description="Identifier of the client company.")
    company_name: str = Field(description="Company name snapshot for the ticket.")


class CreateTicketResponseDTO(BaseModel):
    id: str
    status: TicketStatus
    creation_date: datetime


class TicketSearchFiltersDTO(PaginationDTO):
    ticket_id: PydanticObjectId | None = Field(default=None, description="Ticket ObjectId.")
    client_id: UUID | None = Field(default=None, description="Client UUID in auth domain.")
    triage_id: PydanticObjectId | None = Field(default=None, description="Triage ObjectId.")
    status: TicketStatus | None = Field(default=None, description="Ticket status.")
    criticality: TicketCriticality | None = Field(default=None, description="Ticket criticality.")
    type: TicketType | None = Field(default=None, description="Ticket type.")
    product: str | None = Field(default=None, description="Exact product name.")


class TicketCompanyResponse(BaseModel):
    id: UUID
    name: str


class TicketClientResponse(BaseModel):
    id: UUID
    name: str
    email: str
    company: TicketCompanyResponse


class TicketHistoryResponse(BaseModel):
    agent_id: UUID
    name: str
    level: str = Field(
        ...,
        description="Support level snapshot. Provisional string contract; examples: N1, N2, N3.",
    )
    assignment_date: datetime
    exit_date: datetime | None = None
    transfer_reason: str | None = None


class TicketCommentResponse(BaseModel):
    comment_id: UUID
    author: str
    text: str
    date: datetime
    internal: bool = False


class TicketResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "67f0ca60e4b0b1a2c3d4e601",
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "type": "issue",
                "criticality": "high",
                "product": "Sistema Financeiro",
                "status": "open",
                "creation_date": "2026-04-14T12:00:00Z",
                "description": "Erro ao emitir boleto",
                "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
                "agent_history": [],
                "client": {
                    "id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                    "name": "Maria Souza",
                    "email": "maria@smtp.dev",
                    "company": {
                        "id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                        "name": "Maria Souza account",
                    },
                },
                "comments": [],
            }
        }
    }

    id: str
    triage_id: str
    type: TicketType
    criticality: TicketCriticality
    product: str
    status: TicketStatus
    creation_date: datetime
    description: str
    chat_ids: list[str]
    agent_history: list[TicketHistoryResponse]
    client: TicketClientResponse
    comments: list[TicketCommentResponse]


class TicketListResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [],
                "page": 1,
                "page_size": 20,
                "total": 0,
            }
        }
    }

    items: list[TicketResponse]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)


class TicketQueueFiltersDTO(PaginationDTO):
    status: TicketStatus | None = Field(default=None, description="Filter queue items by status.")
    type: TicketType | None = Field(default=None, description="Filter queue items by ticket type.")
    department_id: str | None = Field(
        default=None,
        description="Provisional department reference from another domain.",
    )
    unassigned_only: bool | None = Field(
        default=None,
        description="When true, return only tickets without an active assignee.",
    )
    level: str | None = Field(
        default=None,
        description="Provisional support level filter. Example values: N1, N2, N3.",
    )
    assignee_id: UUID | None = Field(
        default=None,
        description="Filter queue items by current assignee identifier.",
    )


class TicketQueueItemResponse(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "67f0ca60e4b0b1a2c3d4e601",
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "type": "issue",
                "criticality": "high",
                "product": "Sistema Financeiro",
                "status": "awaiting_assignment",
                "creation_date": "2026-04-14T12:00:00Z",
                "description": "Erro ao emitir boleto",
                "client": {
                    "id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                    "name": "Maria Souza",
                    "email": "maria@smtp.dev",
                    "company": {
                        "id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                        "name": "Maria Souza account",
                    },
                },
                "department_id": "dept-finance",
                "department_name": "Financeiro",
                "level": "N1",
                "assignee_id": None,
                "assignee_name": None,
                "unassigned": True,
            }
        }
    }

    id: str
    triage_id: str
    type: TicketType
    criticality: TicketCriticality
    product: str
    status: TicketStatus
    creation_date: datetime
    description: str
    client: TicketClientResponse
    department_id: str | None = Field(
        default=None,
        description="Provisional department reference. Value comes from another domain contract.",
    )
    department_name: str | None = None
    level: str | None = Field(
        default=None,
        description="Provisional support level. Example values: N1, N2, N3.",
    )
    assignee_id: UUID | None = None
    assignee_name: str | None = None
    unassigned: bool = True


class TicketQueueListResponse(BaseModel):
    items: list[TicketQueueItemResponse]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    total: int = Field(..., ge=0)


class UpdateTicketDTO(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "finished",
                "criticality": "medium",
                "product": "Sistema Financeiro",
                "description": "Chamado concluido e validado.",
            }
        }
    }

    status: TicketStatus | None = Field(
        default=None,
        description=(
            "Optional status transition. If the resulting status is 'finished', "
            "the domain must emit 'ticket.closed' once the business "
            "implementation is completed."
        ),
    )
    criticality: TicketCriticality | None = None
    product: str | None = None
    description: str | None = None


class AssignTicketRequest(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "reason": "Primeira atribuicao na fila N1.",
            }
        }
    }

    agent_id: UUID
    reason: str | None = Field(
        default=None,
        description="Optional audit reason for the assignee change.",
    )


class EscalateTicketRequest(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "target_department_id": "dept-finance",
                "target_department_name": "Financeiro",
                "target_level": "N2",
                "reason": "Necessario apoio do nivel superior.",
            }
        }
    }

    target_department_id: str = Field(
        ...,
        description=(
            "Provisional department reference. Exact type may evolve when "
            "the department contract is imported."
        ),
    )
    target_department_name: str | None = Field(
        default=None,
        description="Optional human-readable department snapshot for API consumers.",
    )
    target_level: str = Field(
        ...,
        description="Provisional support level reference. Example values: N1, N2, N3.",
    )
    reason: str = Field(..., description="Business reason for the escalation.")


class TransferTicketRequest(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "target_agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "reason": "Redistribuicao interna do mesmo nivel.",
            }
        }
    }

    target_agent_id: UUID
    reason: str = Field(..., description="Business reason for the transfer.")


class TicketEventPayload(BaseModel):
    ticket_id: str
    triage_id: str
    client_id: UUID
    status: TicketStatus
    occurred_at: datetime


class TicketClosedEventPayload(TicketEventPayload):
    model_config = {
        "json_schema_extra": {
            "example": {
                "event_name": "ticket.closed",
                "ticket_id": "67f0ca60e4b0b1a2c3d4e601",
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                "status": "finished",
                "occurred_at": "2026-04-14T12:30:00Z",
                "previous_status": "in_progress",
                "closed_at": "2026-04-14T12:30:00Z",
            }
        }
    }

    event_name: Literal["ticket.closed"] = "ticket.closed"
    previous_status: TicketStatus
    closed_at: datetime


class TicketAssigneeUpdatedEventPayload(TicketEventPayload):
    model_config = {
        "json_schema_extra": {
            "example": {
                "event_name": "ticket.assignee_updated",
                "ticket_id": "67f0ca60e4b0b1a2c3d4e601",
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                "status": "in_progress",
                "occurred_at": "2026-04-14T12:35:00Z",
                "previous_agent_id": None,
                "current_agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "reason": "Primeira atribuicao na fila N1.",
                "department_id": "dept-finance",
                "level": "N1",
            }
        }
    }

    event_name: Literal["ticket.assignee_updated"] = "ticket.assignee_updated"
    previous_agent_id: UUID | None = None
    current_agent_id: UUID
    reason: str | None = None
    department_id: str | None = None
    level: str | None = Field(
        default=None,
        description="Provisional support level contract shared with queue/escalation APIs.",
    )


class TicketEscalatedEventPayload(TicketEventPayload):
    model_config = {
        "json_schema_extra": {
            "example": {
                "event_name": "ticket.escalated",
                "ticket_id": "67f0ca60e4b0b1a2c3d4e601",
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                "status": "awaiting_assignment",
                "occurred_at": "2026-04-14T12:40:00Z",
                "previous_agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "source_department_id": "dept-finance",
                "source_level": "N1",
                "target_department_id": "dept-finance-specialists",
                "target_level": "N2",
                "reason": "Necessario apoio do nivel superior.",
            }
        }
    }

    event_name: Literal["ticket.escalated"] = "ticket.escalated"
    previous_agent_id: UUID | None = None
    source_department_id: str | None = None
    source_level: str | None = None
    target_department_id: str
    target_level: str
    reason: str


class TriageFinishedEventPayload(BaseDTO):
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

    triage_id: str
    type: TicketType
    criticality: TicketCriticality
    product: str
    description: str
    chat_ids: list[str]
    client_id: UUID = Field(
        ...,
        description=(
            "Client identity must come from a trusted authenticated source "
            "outside the ticket domain."
        ),
    )


TicketCompanyResponseDTO = TicketCompanyResponse
TicketClientResponseDTO = TicketClientResponse
TicketHistoryResponseDTO = TicketHistoryResponse
TicketCommentResponseDTO = TicketCommentResponse
TicketResponseDTO = TicketResponse
