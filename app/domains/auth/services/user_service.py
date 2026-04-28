from uuid import UUID

from app.core.logger import get_logger
from app.db.exceptions import ResourceNotFoundError
from app.domains.auth.exceptions import UserCannotLoseLoginMethodError
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.schemas.user_schemas import UpdateUserRolesDTO

from ..entities import Permission, Role, User, UserWithRoles
from ..schemas import CreateUserDTO, ReplaceUserDTO, UpdateUserDTO


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo: UserRepository = repo
        self.logger = get_logger("app.auth.user_service")

    async def create(self, dto: CreateUserDTO) -> UserWithRoles:
        return await self.repo.create(dto)

    async def get_all(self) -> list[User]:
        return await self.repo.get_all()

    async def get_all_with_roles(self) -> list[UserWithRoles]:
        return await self.repo.get_all_with_roles()

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
        self.logger.info("User soft-deleted", extra={"user_id": str(id)})
        return await self.repo.soft_delete(id)

    async def hard_delete(self, id: UUID) -> User | None:
        self.logger.warning("User hard-deleted", extra={"user_id": str(id)})
        return await self.repo.hard_delete(id)

    async def add_roles(self, id: UUID, role_ids: list[int]) -> UserWithRoles:
        user, missing_ids = await self.repo.add_roles(id, role_ids)
        if user is None:
            raise ResourceNotFoundError("User", str(id))
        if missing_ids is not None:
            raise ValueError(f"Roles not found: {missing_ids}")
        self.logger.info("Roles assigned to user", extra={"user_id": str(id), "role_ids": role_ids})
        return user

    async def remove_roles(self, user_id: UUID, role_ids: list[int]) -> UserWithRoles:
        await self.repo.remove_roles(user_id, role_ids)
        user = await self.get_by_id_with_roles(user_id)
        if user is None:
            raise ResourceNotFoundError("User", str(user_id))
        return user

    async def update_user_roles(self, user_id: UUID, dto: UpdateUserRolesDTO) -> UserWithRoles:
        user, missing_ids = await self.repo.update_user_roles(
            user_id, dto.add_role_ids, dto.remove_role_ids
        )
        if missing_ids:
            self.logger.warning(
                "Update user roles failed: roles not found",
                extra={"user_id": str(user_id), "missing_role_ids": list(missing_ids)},
            )
            raise ValueError(f"Roles not found: {missing_ids}")
        if user is None:
            self.logger.warning(
                "Update user roles failed: user not found",
                extra={"user_id": str(user_id)},
            )
            raise ResourceNotFoundError("User", str(user_id))
        self.logger.info(
            "User roles updated",
            extra={
                "user_id": str(user_id),
                "added": dto.add_role_ids,
                "removed": dto.remove_role_ids,
            },
        )
        return user

    async def get_user_permissions(self, id: UUID) -> list[Permission]:
        return await self.repo.get_user_permissions(id)

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.repo.user_exists(user_id)

    async def get_user_roles(self, user_id: UUID) -> list[Role]:
        return await self.repo.get_user_roles(user_id)

    async def update_password(self, user_id: UUID, new_password_hash: str) -> User | None:
        return await self.repo.update_password(user_id, new_password_hash)
