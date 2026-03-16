import re

from ..entities import Permission, PermissionWithRoles
from ..repositories.permission_repository import PermissionRepository
from ..schemas import CreatePermissionDTO, ReplacePermissionDTO, UpdatePermissionDTO


class PermissionService:
    def __init__(self, permission_repo: PermissionRepository):
        self.repo = permission_repo
        self.name_pattern = r"^[a-z0-9_]+:[a-z0-9_]+$"

    async def create(self, dto: CreatePermissionDTO) -> Permission:
        dto.name = dto.name.strip().lower().replace(" ", "_")
        if not self._is_valid_name(dto.name):
            raise ValueError(
                f"Invalid permission name: '{dto.name}'. "
                "Name must be in the format <resource>:<action>. "
                "Only letters, numbers, and underscores are allowed."
            )
        permission = await self.repo.create(dto)
        return permission

    async def get_all(self) -> list[Permission]:
        permissions = await self.repo.get_all()
        return permissions

    async def get_one(self, id: int) -> Permission | None:
        permission = await self.repo.get_by_id(id)
        return permission

    async def update(
        self, id: int, dto: UpdatePermissionDTO | ReplacePermissionDTO
    ) -> Permission | None:
        permission = await self.repo.update(id, dto)
        return permission

    async def get_with_roles(self, id: int) -> PermissionWithRoles | None:
        permission = await self.repo.get_with_roles(id)
        return permission

    async def delete(self, id: int) -> Permission | None:
        role = await self.repo.delete(id)
        return role

    async def add_to_roles(self, id: int, role_ids: list[int]) -> Permission | None:
        permission = await self.repo.add_to_roles(id, role_ids)
        return permission

    def _is_valid_name(self, name: str) -> bool:
        return bool(re.match(self.name_pattern, name))
