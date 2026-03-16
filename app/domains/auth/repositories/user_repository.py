from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError

from ..entities import Permission as PermissionEntity
from ..entities import Role as RoleEntity
from ..entities import User as UserEntity
from ..entities import UserRole, UserWithRoles
from ..models import Permission as PermissionModel
from ..models import Role as RoleModel
from ..models import User as UserModel
from ..models import role_permissions, user_roles
from ..schemas import CreateUserDTO, ReplaceUserDTO, UpdateUserDTO


class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @require_dto(CreateUserDTO)
    async def create(self, dto: CreateUserDTO) -> UserWithRoles:
        insert_values = dto.model_dump(exclude={"role_ids"}, exclude_none=True)
        stmt = insert(UserModel).values(**insert_values).returning(UserModel)
        try:
            res = await self.db.execute(stmt)
            user = res.scalar_one()
            if dto.role_ids:
                role_rows = [{"user_id": user.id, "role_id": role_id} for role_id in dto.role_ids]

                await self.db.execute(insert(user_roles).values(role_rows))

            await self.db.commit()
            await self.db.refresh(user, attribute_names=["roles"])
            return self._to_user_with_roles(user)

        except IntegrityError as err:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("User", dto.email) from err
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    async def get_all(self) -> list[UserEntity]:
        result = await self.db.execute(select(UserModel))
        rows = result.scalars().all()
        return [self._to_entity(row) for row in rows]

    async def get_by_id(self, id: UUID) -> UserEntity | None:
        stmt = select(UserModel).where(UserModel.id == id)
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def get_by_email(self, email: str) -> UserEntity | None:
        stmt = select(UserModel).where(UserModel.email == email)
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def get_active(self) -> list[UserEntity]:
        stmt = select(UserModel).where(UserModel.is_active)
        res = await self.db.execute(stmt)
        rows = res.scalars().all()
        return [self._to_entity(row) for row in rows]

    @require_dto(UpdateUserDTO, ReplaceUserDTO)
    async def update(self, id: UUID, dto: UpdateUserDTO | ReplaceUserDTO) -> UserEntity | None:
        update_values = None
        if isinstance(dto, ReplaceUserDTO):
            update_values = dto.model_dump(exclude={"role_ids"}, exclude_none=False)
        else:
            update_values = dto.model_dump(exclude_none=True)

        if not update_values:
            return None

        distinct_conditions = [
            getattr(UserModel, field).is_distinct_from(value)
            for field, value in update_values.items()
        ]
        stmt = (
            update(UserModel)
            .where(UserModel.id == id, or_(*distinct_conditions))
            .values(**update_values)
            .returning(UserModel)
        )
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            existing = await self.get_by_id(id)
            return existing
        await self.db.commit()
        return self._to_entity(row)

    async def soft_delete(self, id: UUID) -> UserEntity | None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == id)
            .values({"deleted_at": func.now(), "is_active": False})
            .returning(UserModel)
        )
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        await self.db.commit()
        return self._to_entity(row)

    async def hard_delete(self, id: UUID) -> UserEntity | None:
        stmt = delete(UserModel).where(UserModel.id == id).returning(UserModel)
        try:
            res = await self.db.execute(stmt)
            row = res.scalar_one_or_none()
            await self.db.commit()
            if row is None:
                return None
            return self._to_entity(row)
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    async def get_with_roles(self, id: UUID) -> UserWithRoles | None:
        stmt = select(UserModel).where(UserModel.id == id).options(selectinload(UserModel.roles))
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        roles = [RoleEntity(id=r.id, name=r.name, description=r.description) for r in row.roles]
        return UserWithRoles(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            username=row.username,
            name=row.name,
            oauth_provider=row.oauth_provider,
            oauth_provider_id=row.oauth_provider_id,
            is_active=row.is_active,
            is_verified=row.is_verified,
            roles=roles,
        )

    async def get_by_email_with_roles(self, email: str) -> UserWithRoles | None:
        stmt = (
            select(UserModel).where(UserModel.email == email).options(selectinload(UserModel.roles))
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        roles = [RoleEntity(id=r.id, name=r.name, description=r.description) for r in row.roles]
        return UserWithRoles(
            id=row.id,
            email=row.email,
            password_hash=row.password_hash,
            username=row.username,
            name=row.name,
            oauth_provider=row.oauth_provider,
            oauth_provider_id=row.oauth_provider_id,
            is_active=row.is_active,
            is_verified=row.is_verified,
            roles=roles,
        )

    async def add_roles(
        self, id: UUID, role_ids: list[int]
    ) -> tuple[UserWithRoles | None, set[int] | None]:
        if len(role_ids) == 0:
            return (None, None)

        user = await self.get_by_id(id)
        if user is None:
            return (None, None)

        roles_stmt = select(RoleModel.id).where(RoleModel.id.in_(role_ids))
        result = await self.db.execute(roles_stmt)
        found_ids = set(result.scalars().all())

        missing_ids = set(role_ids) - found_ids
        if missing_ids:
            return (None, missing_ids)

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        vlues: list[dict[str, UUID | int]] = [
            {"user_id": id, "role_id": role_id} for role_id in role_ids
        ]
        insert_stmt = pg_insert(user_roles).values(vlues).on_conflict_do_nothing()
        await self.db.execute(insert_stmt)
        await self.db.commit()

        updated_user = await self.get_with_roles(id)
        return (updated_user, None)

    async def remove_roles(self, id: UUID, role_ids: list[int]) -> list[UserRole]:
        stmt = (
            delete(user_roles)
            .where(
                user_roles.c.user_id == id,
                user_roles.c.role_id.in_(role_ids),
            )
            .returning(user_roles)
        )
        try:
            result = await self.db.execute(stmt)
            rows = result.mappings().all()
            await self.db.commit()
            return (
                [UserRole(role_id=row.role_id, user_id=row.user_id) for row in rows]
                if len(rows) > 0
                else []
            )
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    async def get_user_roles(self, user_id: UUID) -> list[RoleEntity]:
        stmt = (
            select(UserModel).where(UserModel.id == user_id).options(selectinload(UserModel.roles))
        )
        result = await self.db.execute(stmt)
        user: UserModel | None = result.scalar_one_or_none()
        if user is None:
            return []
        return [RoleEntity(id=r.id, name=r.name, description=r.description) for r in user.roles]

    async def get_user_permissions(self, user_id: UUID) -> list[PermissionEntity]:
        stmt = (
            select(PermissionModel)
            .join(role_permissions, PermissionModel.id == role_permissions.c.permission_id)
            .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
            .where(user_roles.c.user_id == user_id)
            .distinct()
        )
        result = await self.db.execute(stmt)
        permissions = result.scalars().all()
        if len(permissions) == 0:
            return []
        return [
            PermissionEntity(id=p.id, name=p.name, description=p.description) for p in permissions
        ]

    def _to_entity(self, model: UserModel) -> UserEntity:
        return UserEntity(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            username=model.username,
            name=model.name,
            oauth_provider=model.oauth_provider,
            oauth_provider_id=model.oauth_provider_id,
            is_active=model.is_active,
            is_verified=model.is_verified,
        )

    def _to_user_with_roles(self, model: UserModel) -> UserWithRoles:
        roles = [RoleEntity(id=r.id, name=r.name, description=r.description) for r in model.roles]
        return UserWithRoles(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            username=model.username,
            name=model.name,
            oauth_provider=model.oauth_provider,
            oauth_provider_id=model.oauth_provider_id,
            is_active=model.is_active,
            is_verified=model.is_verified,
            roles=roles,
        )
