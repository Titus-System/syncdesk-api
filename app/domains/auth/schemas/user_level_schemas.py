from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict

from app.core.schemas import BaseDTO


class LevelResponseDTO(BaseDTO):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class UserLevelResponseDTO(BaseDTO):
    user_id: UUID
    level: LevelResponseDTO
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLevelsResponseDTO(BaseDTO):
    user_id: UUID
    levels: list[LevelResponseDTO]

    model_config = ConfigDict(from_attributes=True)


class LevelUserResponseDTO(BaseDTO):
    id: UUID
    name: str | None = None
    email: str
    username: str | None = None

    model_config = ConfigDict(from_attributes=True)


class LevelUsersResponseDTO(BaseDTO):
    level: LevelResponseDTO
    users: list[LevelUserResponseDTO]

    model_config = ConfigDict(from_attributes=True)


class DeleteUserLevelResponseDTO(BaseDTO):
    user_id: UUID
    level_id: int
    deleted: bool
