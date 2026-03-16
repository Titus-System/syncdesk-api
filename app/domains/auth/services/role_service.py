from ..entities import Role, RoleWithPermissions
from ..repositories.role_repository import RoleRepository
from ..schemas import CreateRoleDTO, ReplaceRoleDTO, UpdateRoleDTO


class RoleService:
    def __init__(self, role_repo: RoleRepository):
        self.repo = role_repo

    async def create(self, dto: CreateRoleDTO) -> Role:
        new_role = await self.repo.create(dto)
        return new_role

    async def get_all(self) -> list[Role]:
        roles = await self.repo.get_all()
        return roles

    async def get_one(self, id: int) -> Role | None:
        role = await self.repo.get_by_id(id)
        return role

    async def update(self, id: int, dto: UpdateRoleDTO | ReplaceRoleDTO) -> Role | None:
        role = await self.repo.update(id, dto)
        return role

    async def delete(self, id: int) -> Role | None:
        role = await self.repo.delete(id)
        return role

    async def get_by_name(self, name: str) -> Role | None:
        return await self.repo.get_by_name(name)

    async def get_with_permissions(self, id: int) -> RoleWithPermissions | None:
        role = await self.repo.get_with_permissions(id)
        return role

    async def add_permissions(
        self, id: int, permission_ids: list[int]
    ) -> RoleWithPermissions | None:
        role = await self.repo.add_permissions(id, permission_ids)
        return role
