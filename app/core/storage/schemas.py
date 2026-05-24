from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PresignedUpload(BaseModel):
    """Result of generating a single-use presigned upload for an object storage backend."""

    url: str
    method: Literal["POST", "PUT"]
    fields: dict[str, str]
    expires_at: datetime
