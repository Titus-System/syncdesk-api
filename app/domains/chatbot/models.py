from datetime import datetime
from uuid import UUID

from beanie import Document
from pydantic import BaseModel, Field

from app.domains.chatbot.enums import AttendanceStatus


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


class Triage(BaseModel):
    step: str
    question: str
    answer_value: str | None = None
    answer_text: str | None = None


class Attendance(Document):
    status: AttendanceStatus
    start_date: datetime
    end_date: datetime | None = None
    client: AttendanceClient
    triage: list[Triage] = Field(default_factory=list[Triage])
    result: AttendanceResult | None = None
    evaluation: AttendanceEvaluation | None = None

    current_step_id: str | None = None
    current_message: str | None = None
    current_input_mode: str | None = None
    current_quick_replies: list[dict[str, str]] = Field(default_factory=list)

    class Settings:
        name = "attendances"