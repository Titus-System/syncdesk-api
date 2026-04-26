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

    class Settings:
        name = "attendances"
