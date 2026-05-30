from datetime import date, datetime
from typing import Literal
from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.core.schemas import BaseDTO
from app.domains.ticket.models import TicketCriticality, TicketLevel, TicketStatus, TicketType


class PaginationDTO(BaseDTO):
    page: int = Field(default=1, ge=1, description="1-indexed page number.")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page.")


class TicketPaginatedList[T](BaseModel):
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)
    items: list[T]


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
    company_id: UUID | None = Field(
        default=None,
        description="Identifier of the client company. Falls back to the client identity when omitted.",
    )
    company_name: str | None = Field(
        default=None,
        description="Company name snapshot for the ticket. Falls back to a client-derived label when omitted.",
    )
    level: TicketLevel = Field(
        default=TicketLevel.N1,
        description="Support queue level assigned to the ticket. Defaults to N1.",
    )


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
        description="Support level snapshot from the assigned user's operational levels.",
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
    level: TicketLevel = TicketLevel.N1
    creation_date: datetime
    due_date: datetime | None = None
    description: str
    chat_ids: list[str]
    agent_history: list[TicketHistoryResponse]
    client: TicketClientResponse
    comments: list[TicketCommentResponse]
    assigned_agent_id: UUID | None = None
    assigned_agent_name: str | None = None


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
        description="Support level filter. Example values: N1, N2, N3.",
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
        description="Current ticket support level. Example values: N1, N2, N3.",
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


class UpdateTicketStatusDTO(BaseDTO):
    model_config = {"json_schema_extra": {"example": {"status": "in_progress"}}}

    status: TicketStatus


class UpdateTicketStatusResponseDTO(BaseModel):
    id: str
    previous_status: TicketStatus
    current_status: TicketStatus


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
                "target_agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "reason": "Necessario apoio do nivel superior.",
            }
        }
    }

    target_agent_id: UUID
    reason: str = Field(..., description="Business reason for the escalation.")


class CancelTicketRequest(BaseDTO):
    model_config = {
        "json_schema_extra": {
            "example": {
                "reason": "Solicitante desistiu da abertura do chamado.",
            }
        }
    }

    reason: str = Field(
        ...,
        min_length=3,
        description="Motivo do cancelamento. Obrigatório e registrado no histórico do ticket.",
    )


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


class TicketDashboardFiltersDTO(BaseDTO):
    type: TicketType = Field(..., description="Ticket type filter for the dashboard.")


class TicketDashboardKPIsDTO(BaseModel):
    open_count: int = Field(..., ge=0, description="Tickets not in finished/cancelled.")
    cancelled_count: int = Field(..., ge=0, description="Tickets in cancelled.")
    unassigned_count: int = Field(..., ge=0, description="Open tickets without an active assignee.")
    overdue_count: int = Field(..., ge=0, description="Open tickets past their SLA window.")


class TicketStatusBucketDTO(BaseModel):
    bucket: Literal["pendente", "em_atendimento", "nao_atribuidos"]
    label: str
    count: int = Field(..., ge=0)


class TicketAssigneeBucketDTO(BaseModel):
    agent_id: UUID | None = Field(
        default=None,
        description="Assignee UUID. None when the bucket aggregates the long tail (is_aggregate=True).",
    )
    agent_name: str
    count: int = Field(..., ge=0)
    is_aggregate: bool = False


class TicketDashboardResponseDTO(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "issue",
                "generated_at": "2026-05-18T12:00:00Z",
                "kpis": {
                    "open_count": 190,
                    "cancelled_count": 80,
                    "unassigned_count": 110,
                    "overdue_count": 5,
                },
                "open_breakdown": [
                    {"bucket": "pendente", "label": "Pendente", "count": 30},
                    {"bucket": "em_atendimento", "label": "Em atendimento", "count": 50},
                    {"bucket": "nao_atribuidos", "label": "Não atribuídos", "count": 110},
                ],
                "assigned_breakdown": [
                    {"agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8", "agent_name": "Julia", "count": 20, "is_aggregate": False},
                    {"agent_id": "97f0c9b8-e4b0-41a2-83d4-e5f600000001", "agent_name": "Mafe", "count": 30, "is_aggregate": False},
                    {"agent_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2", "agent_name": "Angelina", "count": 30, "is_aggregate": False},
                ],
            }
        }
    }

    type: TicketType
    generated_at: datetime
    kpis: TicketDashboardKPIsDTO
    open_breakdown: list[TicketStatusBucketDTO]
    assigned_breakdown: list[TicketAssigneeBucketDTO]


class AgentClosingsChartFiltersDTO(BaseDTO):
    month: int | None = Field(
        default=None,
        ge=1,
        le=12,
        description="Mês (1-12) do encerramento. Default: mês corrente UTC.",
    )
    year: int | None = Field(
        default=None,
        ge=2000,
        le=2100,
        description="Ano do encerramento. Default: ano corrente UTC.",
    )
    level: TicketLevel | None = Field(
        default=None,
        description="Filtra por nível do agente que encerrou (snapshot).",
    )


class AgentClosingsBucketDTO(BaseModel):
    agent_id: UUID | None = Field(
        default=None,
        description="UUID do agente. None apenas no bucket 'Outros' (is_aggregate=True).",
    )
    agent_name: str
    issue_count: int = Field(..., ge=0, description='Equivalente ao rótulo "Ticket" no front.')
    access_count: int = Field(..., ge=0, description='Equivalente ao rótulo "Liberação de acesso".')
    new_feature_count: int = Field(..., ge=0, description='Equivalente ao rótulo "Features".')
    total: int = Field(..., ge=0)
    is_aggregate: bool = False


class AgentClosingsChartResponseDTO(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "month": 5,
                "year": 2026,
                "level": None,
                "generated_at": "2026-05-19T12:00:00Z",
                "agents": [
                    {
                        "agent_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2",
                        "agent_name": "Angelina",
                        "issue_count": 4000,
                        "access_count": 7000,
                        "new_feature_count": 2500,
                        "total": 13500,
                        "is_aggregate": False,
                    },
                    {
                        "agent_id": "97f0c9b8-e4b0-41a2-83d4-e5f600000001",
                        "agent_name": "Mafe",
                        "issue_count": 3200,
                        "access_count": 2000,
                        "new_feature_count": 1700,
                        "total": 6900,
                        "is_aggregate": False,
                    },
                    {
                        "agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                        "agent_name": "Julia",
                        "issue_count": 2200,
                        "access_count": 5000,
                        "new_feature_count": 1200,
                        "total": 8400,
                        "is_aggregate": False,
                    },
                ],
            }
        }
    }

    month: int
    year: int
    level: TicketLevel | None = None
    agents: list[AgentClosingsBucketDTO]
    generated_at: datetime


class IssuesByProductChartFiltersDTO(BaseDTO):
    company_id: UUID | None = Field(
        default=None,
        description="Optional company UUID; when set, restricts to tickets whose client.company.id matches.",
    )
    date_from: date | None = Field(
        default=None,
        description="Inclusive start date (ISO 8601). Truncated to the first day of the month.",
    )
    date_to: date | None = Field(
        default=None,
        description="Inclusive end date (ISO 8601). Truncated to the last day of the month.",
    )


class ProductSeriesPointDTO(BaseModel):
    month: str = Field(..., description="Identificador do mês no formato YYYY-MM.")
    count: int = Field(..., ge=0)


class ProductSeriesDTO(BaseModel):
    product: str = Field(..., description="Nome do produto (snapshot guardado no ticket).")
    total: int = Field(..., ge=0, description="Soma de tickets do produto no período.")
    points: list[ProductSeriesPointDTO] = Field(
        ..., description="Um ponto por mês do eixo X, mesma ordem de months[]."
    )


class IssuesByProductChartResponseDTO(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "period_start": "2026-01-01",
                "period_end": "2026-05-31",
                "company_id": None,
                "months": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"],
                "generated_at": "2026-05-19T12:00:00Z",
                "series": [
                    {
                        "product": "Produto 1",
                        "total": 61,
                        "points": [
                            {"month": "2026-01", "count": 12},
                            {"month": "2026-02", "count": 14},
                            {"month": "2026-03", "count": 7},
                            {"month": "2026-04", "count": 18},
                            {"month": "2026-05", "count": 10},
                        ],
                    },
                    {
                        "product": "Produto 2",
                        "total": 75,
                        "points": [
                            {"month": "2026-01", "count": 10},
                            {"month": "2026-02", "count": 12},
                            {"month": "2026-03", "count": 16},
                            {"month": "2026-04", "count": 17},
                            {"month": "2026-05", "count": 20},
                        ],
                    },
                    {
                        "product": "Produto 3",
                        "total": 44,
                        "points": [
                            {"month": "2026-01", "count": 8},
                            {"month": "2026-02", "count": 8},
                            {"month": "2026-03", "count": 5},
                            {"month": "2026-04", "count": 10},
                            {"month": "2026-05", "count": 13},
                        ],
                    },
                ],
            }
        }
    }

    period_start: date
    period_end: date
    company_id: UUID | None = None
    months: list[str]
    series: list[ProductSeriesDTO]
    generated_at: datetime


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
                "status": "in_progress",
                "occurred_at": "2026-04-14T12:40:00Z",
                "previous_agent_id": "4b8b9bd2-6042-43f5-b5a3-6b36fdfaf9a8",
                "source_level": "N1",
                "target_agent_id": "97f0c9b8-e4b0-41a2-83d4-e5f600000001",
                "target_level": "N2",
                "reason": "Necessario apoio do nivel superior.",
            }
        }
    }

    event_name: Literal["ticket.escalated"] = "ticket.escalated"
    previous_agent_id: UUID | None = None
    source_level: str | None = None
    target_agent_id: UUID
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

class AddTicketCommentDTO(BaseDTO):
    text: str
    internal: bool = True

class UpdateTicketCommentDTO(BaseDTO):
    author: str | None = None
    text: str | None = None
    internal: bool = False


TicketCompanyResponseDTO = TicketCompanyResponse
TicketClientResponseDTO = TicketClientResponse
TicketHistoryResponseDTO = TicketHistoryResponse
TicketCommentResponseDTO = TicketCommentResponse
TicketResponseDTO = TicketResponse
