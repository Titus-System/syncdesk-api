from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError

from ..entities import Permission as PermissionEntity
from ..entities import PermissionWithRoles, Role, RolePermission
from ..models import Permission as PermissionModel
from ..models import role_permissions
from ..schemas import CreatePermissionDTO, ReplacePermissionDTO, UpdatePermissionDTO


class PermissionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @require_dto(CreatePermissionDTO)
    async def create(self, dto: CreatePermissionDTO) -> PermissionEntity:
        insert_values = dto.model_dump(exclude_none=True)
        stmt = insert(PermissionModel).values(**insert_values).returning(PermissionModel)
        try:
            result = await self.db.execute(stmt)
            row = result.scalar_one()
            await self.db.commit()
            return self._to_entity(row)
        except IntegrityError as err:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Permission", dto.name) from err
        except Exception:
            await self.db.rollback()
            raise

    async def get_all(self) -> list[PermissionEntity]:
        stmt = select(PermissionModel)
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [self._to_entity(row) for row in rows] if len(rows) > 0 else []

    async def get_by_id(self, id: int) -> PermissionEntity | None:
        stmt = select(PermissionModel).where(PermissionModel.id == id)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    async def get_by_name(self, name: str) -> PermissionEntity | None:
        stmt = select(PermissionModel).where(PermissionModel.name == name)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row is not None else None

    @require_dto(UpdatePermissionDTO, ReplacePermissionDTO)
    async def update(
        self, id: int, dto: UpdatePermissionDTO | ReplacePermissionDTO
    ) -> PermissionEntity | None:
        update_values = None
        if isinstance(dto, ReplacePermissionDTO):
            update_values = dto.model_dump(exclude_none=False)
        else:
            update_values = dto.model_dump(exclude_none=True)
        if not update_values:
            return None

        distinct_conditions = [
            getattr(PermissionModel, field).is_distinct_from(value)
            for field, value in update_values.items()
        ]
        stmt = (
            update(PermissionModel)
            .where(PermissionModel.id == id, or_(*distinct_conditions))
            .values(**update_values)
            .returning(PermissionModel)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            existing = await self.get_by_id(id)
            return existing
        await self.db.commit()
        return self._to_entity(row)

    async def delete(self, id: int) -> PermissionEntity | None:
        stmt = delete(PermissionModel).where(PermissionModel.id == id).returning(PermissionModel)
        try:
            result = await self.db.execute(stmt)
            await self.db.commit()
            row = result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise RuntimeError(f"Failed to delete permission with id={id}") from e
        if row is None:
            return None
        return self._to_entity(row)

    async def get_with_roles(self, id: int) -> PermissionWithRoles | None:
        stmt = (
            select(PermissionModel)
            .where(PermissionModel.id == id)
            .options(selectinload(PermissionModel.roles))
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        roles = [Role(id=r.id, name=r.name, description=r.description) for r in row.roles]
        return PermissionWithRoles(
            id=row.id, name=row.name, description=row.description, roles=roles
        )

    async def add_to_roles(self, id: int, role_ids: list[int]) -> PermissionWithRoles | None:
        if len(role_ids) == 0:
            return None

        from ..models import Role as Role
        from ..models import role_permissions

        permission_stmt = select(PermissionModel.id).where(PermissionModel.id == id)
        permission_res = await self.db.execute(permission_stmt)
        if permission_res.scalar_one_or_none() is None:
            return None

        stmt = select(func.count(Role.id)).where(Role.id.in_(role_ids))
        count = (await self.db.execute(stmt)).scalar_one()

        if count != len(set(role_ids)):
            return None

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = [{"permission_id": id, "role_id": role_id} for role_id in role_ids]
        insert_stmt = pg_insert(role_permissions).values(values).on_conflict_do_nothing()
        await self.db.execute(insert_stmt)
        await self.db.commit()

        return await self.get_with_roles(id)

    async def remove_from_roles(self, id: int, role_ids: list[int]) -> list[RolePermission]:
        stmt = (
            delete(role_permissions)
            .where(role_permissions.c.permission_id == id, role_permissions.c.role_id.in_(role_ids))
            .returning(role_permissions)
        )
        try:
            result = await self.db.execute(stmt)
            rows = result.mappings().all()
            await self.db.commit()
            return (
                [
                    RolePermission(permission_id=row.permission_id, role_id=row.role_id)
                    for row in rows
                ]
                if len(rows) > 0
                else []
            )
        except SQLAlchemyError as e:
            await self.db.rollback()
            raise RuntimeError("Failed to remove permissions from roles") from e

    def _to_entity(self, model: PermissionModel) -> PermissionEntity:
        return PermissionEntity(id=model.id, name=model.name, description=model.description)
