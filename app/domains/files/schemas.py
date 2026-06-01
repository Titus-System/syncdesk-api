from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import FileContext, FileStatus


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(gt=0)
    context: FileContext
    context_ref: dict[str, str] = Field(default_factory=dict)


class PresignUploadResponse(BaseModel):
    file_id: UUID
    upload_url: str
    method: Literal["POST", "PUT"]
    fields: dict[str, str]
    expires_at: datetime
    max_size_bytes: int


class ConfirmUploadResponse(BaseModel):
    file_id: UUID
    status: FileStatus


class DownloadUrlResponse(BaseModel):
    url: str
    expires_at: datetime


class FileRead(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    context: FileContext
    status: FileStatus
    uploaded_at: datetime | None
