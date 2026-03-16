from uuid import UUID

from app.db.exceptions import ResourceNotFoundError
from app.domains.auth.exceptions import UserCannotLoseLoginMethodError
from app.domains.auth.repositories.user_repository import UserRepository

from ..entities import Permission, User, UserWithRoles
from ..schemas import CreateUserDTO, ReplaceUserDTO, UpdateUserDTO


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo: UserRepository = repo

    async def create(self, dto: CreateUserDTO) -> UserWithRoles:
        return await self.repo.create(dto)

    async def get_all(self) -> list[User]:
        return await self.repo.get_all()

    async def get_by_id(self, id: UUID) -> User | None:
        return await self.repo.get_by_id(id)

    async def get_by_id_with_roles(self, id: UUID) -> UserWithRoles | None:
        return await self.repo.get_with_roles(id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.repo.get_by_email(email)

    async def get_by_email_with_roles(self, email: str) -> UserWithRoles | None:
        return await self.repo.get_by_email_with_roles(email)

    async def update(self, id: UUID, dto: UpdateUserDTO | ReplaceUserDTO) -> User | None:
        user = await self.repo.get_by_id(id)
        if user is None:
            return None

        update_values = dto.model_dump(exclude_none=True)
        temp_user = User(**{**user.__dict__, **update_values})

        if not temp_user.can_login():
            raise UserCannotLoseLoginMethodError()

        return await self.repo.update(id, dto)

    async def delete(self, id: UUID) -> User | None:
        return await self.repo.soft_delete(id)

    async def hard_delete(self, id: UUID) -> User | None:
        return await self.repo.hard_delete(id)

    async def add_roles(self, id: UUID, role_ids: list[int]) -> UserWithRoles:
        user, missing_ids = await self.repo.add_roles(id, role_ids)
        if user is None:
            raise ResourceNotFoundError("User", str(id))
        if missing_ids is not None:
            raise ValueError(f"Roles not found: {missing_ids}")
        return user

    async def get_user_permissions(self, id: UUID) -> list[Permission]:
        return await self.repo.get_user_permissions(id)
