from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError

from ..entities import Permission, RolePermission, RoleWithPermissions
from ..entities import Role as RoleEntity
from ..models import Role as Role
from ..models import role_permissions
from ..schemas import CreateRoleDTO, ReplaceRoleDTO, UpdateRoleDTO


class RoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @require_dto(CreateRoleDTO)
    async def create(self, dto: CreateRoleDTO) -> RoleEntity:
        insert_values = dto.model_dump(exclude_none=True)
        stmt = insert(Role).values(**insert_values).returning(Role)
        try:
            result = await self.db.execute(stmt)
            row = result.scalar_one()
            await self.db.commit()
            return self._to_entity(row)
        except IntegrityError as err:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Role", dto.name) from err
        except Exception:
            await self.db.rollback()
            raise

    async def get_all(self) -> list[RoleEntity]:
        stmt = select(Role)
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return [self._to_entity(row) for row in rows] if len(rows) > 0 else []

    async def get_by_id(self, id: int) -> RoleEntity | None:
        stmt = select(Role).where(Role.id == id)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def get_by_name(self, name: str) -> RoleEntity | None:
        stmt = select(Role).where(Role.name == name)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    @require_dto(UpdateRoleDTO, ReplaceRoleDTO)
    async def update(self, id: int, data: UpdateRoleDTO | ReplaceRoleDTO) -> RoleEntity | None:
        update_values = None
        if isinstance(data, ReplaceRoleDTO):
            update_values = data.model_dump(exclude_none=False)
        else:
            update_values = data.model_dump(exclude_none=True)

        if not update_values:
            return None

        distinct_conditions = [
            getattr(Role, field).is_distinct_from(value) for field, value in update_values.items()
        ]
        stmt = (
            update(Role)
            .where(Role.id == id, or_(*distinct_conditions))
            .values(**update_values)
            .returning(Role)
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            existing = await self.get_by_id(id)
            return existing
        await self.db.commit()
        return self._to_entity(row)

    async def delete(self, id: int) -> RoleEntity | None:
        stmt = delete(Role).where(Role.id == id).returning(Role)
        try:
            result = await self.db.execute(stmt)
            await self.db.commit()
            row = result.scalar_one_or_none()
        except SQLAlchemyError:
            raise
        if row is None:
            return None
        return self._to_entity(row)

    async def get_with_permissions(self, id: int) -> RoleWithPermissions | None:
        stmt = select(Role).where(Role.id == id).options(selectinload(Role.permissions))
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        permissions = [
            Permission(id=p.id, name=p.name, description=p.description) for p in row.permissions
        ]
        return RoleWithPermissions(
            id=row.id, name=row.name, description=row.description, permissions=permissions
        )

    async def add_permissions(
        self, id: int, permission_ids: list[int]
    ) -> RoleWithPermissions | None:
        from ..models import Permission as PermissionModel
        from ..models import role_permissions

        if len(permission_ids) == 0:
            return None

        role_stmt = select(Role.id).where(Role.id == id)
        role_result = await self.db.execute(role_stmt)
        if role_result.scalar_one_or_none() is None:
            return None

        stmt = select(PermissionModel.id).where(PermissionModel.id.in_(permission_ids))
        result = await self.db.execute(stmt)
        found_ids = set(result.scalars().all())

        missing_ids = set(permission_ids) - found_ids
        if missing_ids:
            return None

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        values = [{"role_id": id, "permission_id": perm_id} for perm_id in permission_ids]
        insert_stmt = pg_insert(role_permissions).values(values).on_conflict_do_nothing()
        await self.db.execute(insert_stmt)
        await self.db.commit()

        return await self.get_with_permissions(id)

    async def remove_permissions(self, id: int, permission_ids: list[int]) -> list[RolePermission]:
        stmt = (
            delete(role_permissions)
            .where(
                role_permissions.c.role_id == id,
                role_permissions.c.permission_id.in_(permission_ids),
            )
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
        except SQLAlchemyError:
            await self.db.rollback()
            raise

    def _to_entity(self, model: Role) -> RoleEntity:
        return RoleEntity(id=model.id, name=model.name, description=model.description)

    def _from_entity(self, entity: RoleEntity) -> Role:
        return Role(
            id=entity.id,
            name=entity.name,
            description=entity.description,
        )
