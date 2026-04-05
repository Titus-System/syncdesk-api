# app/domains/chatbot/schemas.py
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any

# --- ENTRADA (Frontend -> Backend) ---
class TriageInputDTO(BaseModel):
    triage_id: str = Field(..., description="Identificador da sessão de triagem")
    step_id: str = Field(..., description="Etapa que está sendo respondida")
    answer_text: Optional[str] = Field(None, description="Resposta em texto livre")
    answer_value: Optional[str] = Field(None, description="Valor da opção selecionada (quick reply)")

    @model_validator(mode='after')
    def check_answers(self):
        if self.answer_text is not None and self.answer_value is not None:
            raise ValueError("answer_text e answer_value não devem ser enviados juntos.")
        return self

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