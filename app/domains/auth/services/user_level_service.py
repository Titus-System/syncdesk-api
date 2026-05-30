from uuid import UUID

from app.db.exceptions import ResourceNotFoundError
from app.domains.auth.entities import Level, UserLevel, UserSummary, UserWithRoles
from app.domains.auth.repositories.user_level_repository import UserLevelRepository


class UserLevelService:
    def __init__(self, repo: UserLevelRepository):
        self.repo = repo

    async def add_user_level(
        self, user_id: UUID, level_id: int, current_user: UserWithRoles
    ) -> UserLevel:
        if not self._is_admin(current_user):
            raise PermissionError("Insufficient permissions")

        await self._ensure_user_exists(user_id)
        await self._ensure_level_exists(level_id)

        if not await self.repo.user_has_role(user_id, "agent"):
            raise ValueError("Only users with agent role can receive support levels.")

        return await self.repo.add_user_level(user_id, level_id)

    async def get_user_levels(self, user_id: UUID, current_user: UserWithRoles) -> list[Level]:
        if self._is_admin(current_user):
            await self._ensure_user_exists(user_id)
            return await self.repo.get_levels_by_user(user_id)

        if self._is_agent(current_user) and current_user.id == user_id:
            await self._ensure_user_exists(user_id)
            return await self.repo.get_levels_by_user(user_id)

        raise PermissionError("Insufficient permissions")

    async def get_level_users(
        self, level_id: int, current_user: UserWithRoles
    ) -> tuple[Level, list[UserSummary]]:
        if not self._is_admin(current_user):
            raise PermissionError("Insufficient permissions")

        level = await self._ensure_level_exists(level_id)
        users = await self.repo.get_users_by_level(level_id)
        return level, users

    async def delete_user_level(
        self, user_id: UUID, level_id: int, current_user: UserWithRoles
    ) -> bool:
        if not self._is_admin(current_user):
            raise PermissionError("Insufficient permissions")

        await self._ensure_user_exists(user_id)
        await self._ensure_level_exists(level_id)

        deleted = await self.repo.delete_user_level(user_id, level_id)
        if not deleted:
            raise ResourceNotFoundError("User level relation", f"{user_id}:{level_id}")
        return True

    async def _ensure_user_exists(self, user_id: UUID) -> None:
        if not await self.repo.user_exists(user_id):
            raise ResourceNotFoundError("User", str(user_id))

    async def _ensure_level_exists(self, level_id: int) -> Level:
        level = await self.repo.get_level(level_id)
        if level is None:
            raise ResourceNotFoundError("Level", str(level_id))
        return level

    @staticmethod
    def _is_admin(user: UserWithRoles) -> bool:
        return "admin" in user.roles_names()

    @staticmethod
    def _is_agent(user: UserWithRoles) -> bool:
        return "agent" in user.roles_names()
