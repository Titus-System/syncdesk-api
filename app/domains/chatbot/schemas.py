from datetime import UTC, datetime
from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import BaseDTO
from app.domains.chatbot.enums import AttendanceStatus
from app.domains.chatbot.models import (
    AttendanceClient,
    AttendanceEvaluation,
    AttendanceResult,
)


class TriageInputDTO(BaseModel):
    triage_id: str = Field(..., description="Identificador da sessão de triagem")
    step_id: str = Field(..., description="Etapa que está sendo respondida")
    answer_text: Optional[str] = Field(None, description="Resposta em texto livre")
    answer_value: Optional[str] = Field(None, description="Valor da opção selecionada")
    client_id: UUID | None = Field(
        None,
        description="UUID do cliente. Obrigatório quando triage_id não existir.",
    )
    client_name: str | None = Field(
        None,
        description="Nome do cliente. Obrigatório quando triage_id não existir.",
    )
    client_email: str | None = Field(
        None,
        description="Email do cliente. Obrigatório quando triage_id não existir.",
    )

    @model_validator(mode="after")
    def check_answers(self) -> "TriageInputDTO":
        if self.answer_text is not None and self.answer_value is not None:
            raise ValueError("answer_text e answer_value não devem ser enviados juntos.")
        return self


class CreateAttendanceDTO(BaseModel):
    status: AttendanceStatus = AttendanceStatus.OPENED
    start_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_date: datetime | None = None
    client: AttendanceClient
    result: AttendanceResult | None = None
    evaluation: AttendanceEvaluation | None = None


class QuickReply(BaseModel):
    label: str
    value: str


class TriageInputDef(BaseModel):
    mode: str
    quick_replies: Optional[List[QuickReply]] = None


class TriageResult(BaseModel):
    type: str
    id: str
    ticket_id: str | None = None
    chat_id: str | None = None


class TriageData(BaseModel):
    triage_id: str
    step_id: Optional[str] = None
    message: Optional[str] = None
    input: Optional[TriageInputDef] = None
    finished: Optional[bool] = None
    closure_message: Optional[str] = None
    result: Optional[TriageResult] = None


class InternalBotResponseDTO(BaseModel):
    new_state: object | None
    response_text: str
    is_free_text: bool = False
    quick_replies: Optional[List[Dict[str, str]]] = None
    is_finished: bool = False


class AttendanceSearchFiltersDTO(BaseDTO):
    client_id: UUID | None = Field(default=None)
    client_name: str | None = Field(default=None)
    status: AttendanceStatus | None = Field(default=None)
    result_type: str | None = Field(default=None)
    start_date_from: datetime | None = Field(default=None)
    start_date_to: datetime | None = Field(default=None)
    has_evaluation: bool | None = Field(default=None)
    rating: int | None = Field(default=None, ge=1, le=5)


class TriageStepSchema(BaseModel):
    step: str
    question: str
    answer_value: str | None = None
    answer_text: str | None = None


class EvaluationRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Nota de satisfação de 1 a 5")


class EvaluationResponse(BaseModel):
    triage_id: str
    rating: int
    evaluated_at: datetime


class AttendanceResponse(BaseModel):
    triage_id: str
    status: AttendanceStatus
    start_date: datetime
    end_date: datetime | None = None
    client: AttendanceClient
    triage: list[TriageStepSchema] = Field(default_factory=list)
    result: AttendanceResult | None = None
    evaluation: AttendanceEvaluation | None = None
    needs_evaluation: bool = False
    current_step_id: str | None = None
    current_message: str | None = None
    current_input: TriageInputDef | None = None

    @model_validator(mode="after")
    def compute_needs_evaluation(self) -> "AttendanceResponse":
        self.needs_evaluation = (
            self.status == AttendanceStatus.FINISHED and self.evaluation is None
        )
        return self