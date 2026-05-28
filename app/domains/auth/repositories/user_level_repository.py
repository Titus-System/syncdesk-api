from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.entities import Level, UserLevel, UserSummary

from ..models import Level as LevelModel
from ..models import Role as RoleModel
from ..models import User as UserModel
from ..models import user_levels, user_roles


class UserLevelRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def user_exists(self, user_id: UUID) -> bool:
        stmt = select(UserModel.id).where(UserModel.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_level(self, level_id: int) -> Level | None:
        stmt = select(LevelModel).where(LevelModel.id == level_id)
        result = await self.db.execute(stmt)
        level = result.scalar_one_or_none()
        if level is None:
            return None
        return self._to_level(level)

    async def user_has_role(self, user_id: UUID, role_name: str) -> bool:
        stmt = (
            select(RoleModel.id)
            .join(user_roles, user_roles.c.role_id == RoleModel.id)
            .where(user_roles.c.user_id == user_id, RoleModel.name == role_name)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def add_user_level(self, user_id: UUID, level_id: int) -> UserLevel:
        stmt = (
            pg_insert(user_levels)
            .values(user_id=user_id, level_id=level_id)
            .on_conflict_do_nothing(index_elements=["user_id", "level_id"])
        )
        try:
            await self.db.execute(stmt)
            await self.db.commit()
        except SQLAlchemyError:
            await self.db.rollback()
            raise

        user_level = await self.get_user_level(user_id, level_id)
        if user_level is None:
            raise RuntimeError("User level relation was not persisted")
        return user_level

    async def get_user_level(self, user_id: UUID, level_id: int) -> UserLevel | None:
        stmt = (
            select(
                user_levels.c.user_id,
                user_levels.c.level_id,
                user_levels.c.created_at,
                LevelModel.id.label("level_model_id"),
                LevelModel.name.label("level_name"),
            )
            .join(LevelModel, LevelModel.id == user_levels.c.level_id)
            .where(user_levels.c.user_id == user_id, user_levels.c.level_id == level_id)
        )
        result = await self.db.execute(stmt)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return UserLevel(
            user_id=row["user_id"],
            level_id=row["level_id"],
            created_at=row["created_at"],
            level=Level(id=row["level_model_id"], name=row["level_name"]),
        )

    async def get_levels_by_user(self, user_id: UUID) -> list[Level]:
        stmt = (
            select(LevelModel)
            .join(user_levels, user_levels.c.level_id == LevelModel.id)
            .where(user_levels.c.user_id == user_id)
            .order_by(LevelModel.id)
        )
        result = await self.db.execute(stmt)
        return [self._to_level(level) for level in result.scalars().all()]

    async def get_users_by_level(self, level_id: int) -> list[UserSummary]:
        stmt = (
            select(UserModel)
            .join(user_levels, user_levels.c.user_id == UserModel.id)
            .where(user_levels.c.level_id == level_id)
            .order_by(UserModel.name, UserModel.email)
        )
        result = await self.db.execute(stmt)
        return [self._to_user_summary(user) for user in result.scalars().all()]

    async def delete_user_level(self, user_id: UUID, level_id: int) -> bool:
        stmt = (
            delete(user_levels)
            .where(user_levels.c.user_id == user_id, user_levels.c.level_id == level_id)
            .returning(user_levels.c.user_id)
        )
        try:
            result = await self.db.execute(stmt)
            deleted_user_id = result.scalar_one_or_none()
            await self.db.commit()
            return deleted_user_id is not None
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    @staticmethod
    def _to_level(model: LevelModel) -> Level:
        return Level(id=model.id, name=model.name)

    @staticmethod
    def _to_user_summary(model: UserModel) -> UserSummary:
        return UserSummary(
            id=model.id,
            email=model.email,
            username=model.username,
            name=model.name,
        )
