# app/domains/chatbot/schemas.py
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any

from app.domains.chatbot.enums import AttendanceStatus

# --- ENTRADA (Frontend -> Backend) ---
class TriageInputDTO(BaseModel):
    triage_id: str = Field(..., description="Identificador da sessão de triagem")
    step_id: str = Field(..., description="Etapa que está sendo respondida")
    answer_text: Optional[str] = Field(None, description="Resposta em texto livre")
    answer_value: Optional[str] = Field(None, description="Valor da opção selecionada (quick reply)")
    client_id: UUID | None = Field(
        None,
        description="UUID do cliente. Obrigatorio quando triage_id nao existir.",
    )
    client_name: str | None = Field(
        None,
        description="Nome do cliente. Obrigatorio quando triage_id nao existir.",
    )
    client_email: str | None = Field(
        None,
        description="Email do cliente. Obrigatorio quando triage_id nao existir.",
    )

    @model_validator(mode='after')
    def check_answers(self):
        if self.answer_text is not None and self.answer_value is not None:
            raise ValueError("answer_text e answer_value não devem ser enviados juntos.")
        return self


class AttendanceCompany(BaseModel):
    id: UUID
    name: str


class AttendanceClient(BaseModel):
    id: UUID
    name: str
    email: str
    company: AttendanceCompany | None = None


class AttendanceResult(BaseModel):
    type: str
    closure_message: str


class AttendanceEvaluation(BaseModel):
    rating: int


class CreateAttendanceDTO(BaseModel):
    status: AttendanceStatus = AttendanceStatus.OPENED
    start_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_date: datetime | None = None
    client: AttendanceClient
    result: AttendanceResult | None = None
    evaluation: AttendanceEvaluation | None = None


# --- SAÍDA (Backend -> Frontend) ---
class QuickReply(BaseModel):
    label: str
    value: str

class TriageInputDef(BaseModel):
    mode: str
    quick_replies: Optional[List[QuickReply]] = None

class TriageResult(BaseModel):
    type: str
    id: str

class TriageData(BaseModel):
    triage_id: str
    step_id: Optional[str] = None
    message: Optional[str] = None
    input: Optional[TriageInputDef] = None
    finished: Optional[bool] = None
    closure_message: Optional[str] = None
    result: Optional[TriageResult] = None

class TriageResponseMeta(BaseModel):
    timestamp: str
    success: bool
    request_id: str

class TriageResponseDTO(BaseModel):
    data: TriageData
    meta: TriageResponseMeta

class InternalBotResponseDTO(BaseModel):
    new_state: Any  # TriageState
    response_text: str
    is_free_text: bool = False
    quick_replies: Optional[List[Dict[str, str]]] = None
    is_finished: bool = False