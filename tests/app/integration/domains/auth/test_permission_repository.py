import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.models import Role as RoleModel
from app.domains.auth.repositories.permission_repository import PermissionRepository
from app.domains.auth.schemas.permission_schemas import (
    CreatePermissionDTO,
    ReplacePermissionDTO,
    UpdatePermissionDTO,
)


class TestPermissionDTOs:
    @pytest.mark.asyncio
    async def test_create_permission_dto_with_empty_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreatePermissionDTO(name="", description="A test permission")
            assert not dto

    @pytest.mark.asyncio
    async def test_create_permission_dto_with_none_name_should_fail(self) -> None:
        with pytest.raises(ValueError):
            dto = CreatePermissionDTO(name=None, description="A test permission")  # pyright: ignore
            assert not dto

    @pytest.mark.asyncio
    async def test_create_permission_dto_with_short_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreatePermissionDTO(name="a", description="A test permission")
            assert not dto

    @pytest.mark.asyncio
    async def test_create_permission_dto_with_invalid_name_format_should_fail(self) -> None:
        with pytest.raises(ValueError):
            dto = CreatePermissionDTO(name="test", description="A test permission")
            assert not dto
        with pytest.raises(ValueError):
            dto = CreatePermissionDTO(name="test:", description="A test permission")
            assert not dto
        with pytest.raises(ValueError):
            dto = CreatePermissionDTO(name=":permission", description="A test permission")
            assert not dto

    @pytest.mark.asyncio
    async def test_create_permission_dto_success(self) -> None:
        dto = CreatePermissionDTO(name="test:permission", description="A test permission")
        assert dto.name == "test:permission"
        assert dto.description == "A test permission"

    @pytest.mark.asyncio
    async def test_create_permission_dto_with_description_none(self) -> None:
        dto = CreatePermissionDTO(name="test:permission")
        assert dto.name == "test:permission"
        assert dto.description is None

    @pytest.mark.asyncio
    async def test_replace_permission_dto_with_valid_data(self) -> None:
        dto = ReplacePermissionDTO(name="test:permission", description="A test permission")
        assert dto.name == "test:permission"
        assert dto.description == "A test permission"

    @pytest.mark.asyncio
    async def test_replace_permission_dto_with_none_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = ReplacePermissionDTO(name=None, description="A test permission")  # pyright: ignore
            assert not dto


class TestPermissionRepository:
    """Unit tests for PermissionRepository"""

    create_dto = CreatePermissionDTO(name="test:permission", description="A test permission")
    update_dto = UpdatePermissionDTO(
        name="updated:permission", description="An updated test permission"
    )

    @pytest.fixture
    def permission_repo(self, db_session: AsyncSession) -> PermissionRepository:
        return PermissionRepository(db=db_session)

    @pytest.mark.asyncio
    async def test_create_permission_success(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        assert permission.name == self.create_dto.name
        assert permission.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_create_permission_with_existing_name_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        await permission_repo.create(self.create_dto)
        with pytest.raises((SQLAlchemyError, ResourceAlreadyExistsError)):
            await permission_repo.create(self.create_dto)

    @pytest.mark.asyncio
    async def test_create_permission_with_invalid_dto_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        with pytest.raises(TypeError):
            dto = self.update_dto
            await permission_repo.create(dto)  # type: ignore

    @pytest.mark.asyncio
    async def test_create_permission_with_long_name_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        with pytest.raises(SQLAlchemyError):
            dto = CreatePermissionDTO(name="aaaa:" + "b" * 51)
            await permission_repo.create(dto)

    @pytest.mark.asyncio
    async def test_create_permission_with_long_description_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        with pytest.raises(SQLAlchemyError):
            dto = CreatePermissionDTO(name="test:permission", description="a" * 256)
            await permission_repo.create(dto)

    @pytest.mark.asyncio
    async def test_get_all_permissions_empty(self, permission_repo: PermissionRepository) -> None:
        permissions = await permission_repo.get_all()
        assert permissions is not None
        assert len(permissions) == 0

    @pytest.mark.asyncio
    async def test_get_all_permissions_success(self, permission_repo: PermissionRepository) -> None:
        await permission_repo.create(self.create_dto)
        dto = CreatePermissionDTO(name="test:perm", description="A test permission")
        await permission_repo.create(dto)
        permissions = await permission_repo.get_all()
        assert permissions is not None
        assert len(permissions) == 2
        assert permissions == [permissions[0], permissions[1]]
        assert permissions[0].name == self.create_dto.name
        assert permissions[0].description == self.create_dto.description
        assert permissions[1].name == dto.name
        assert permissions[1].description == dto.description

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        found_permission = await permission_repo.get_by_id(permission.id)
        assert found_permission is not None
        assert found_permission.name == self.create_dto.name

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, permission_repo: PermissionRepository) -> None:
        found_permission = await permission_repo.get_by_id(1)
        assert found_permission is None

    @pytest.mark.asyncio
    async def test_get_by_name(self, permission_repo: PermissionRepository) -> None:
        await permission_repo.create(self.create_dto)
        permission = await permission_repo.get_by_name(self.create_dto.name)
        assert permission is not None
        assert permission.name == self.create_dto.name
        assert permission.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_get_by_name_not_found(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.get_by_name("test:perm")
        assert permission is None

    @pytest.mark.asyncio
    async def test_update_permission(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        updated_permission = await permission_repo.update(permission.id, self.update_dto)
        assert updated_permission is not None
        assert updated_permission.name == self.update_dto.name
        assert updated_permission.description == self.update_dto.description
        assert updated_permission.id == permission.id

    @pytest.mark.asyncio
    async def test_update_permission_not_found(self, permission_repo: PermissionRepository) -> None:
        updated_permission = await permission_repo.update(1, self.update_dto)
        assert updated_permission is None

    @pytest.mark.asyncio
    async def test_update_permission_with_invalid_dto(
        self, permission_repo: PermissionRepository
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        with pytest.raises(TypeError):
            await permission_repo.update(permission.id, self.create_dto)  # type: ignore

    @pytest.mark.asyncio
    async def test_update_permission_is_idempotent(
        self, permission_repo: PermissionRepository
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        await permission_repo.update(permission.id, self.update_dto)
        state_after_first = await permission_repo.get_by_id(permission.id)
        await permission_repo.update(permission.id, self.update_dto)
        state_after_second = await permission_repo.get_by_id(permission.id)
        assert state_after_first == state_after_second

    @pytest.mark.asyncio
    async def test_replace_permission_success(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        replace_dto = ReplacePermissionDTO(name="replaced:permission")
        replaced_permission = await permission_repo.update(permission.id, replace_dto)
        assert replaced_permission is not None
        assert replaced_permission.name == "replaced:permission"
        assert replaced_permission.description is None

    @pytest.mark.asyncio
    async def test_delete_permission_success(self, permission_repo: PermissionRepository) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        deleted_permission = await permission_repo.delete(permission.id)
        assert deleted_permission is not None
        assert deleted_permission.name == self.create_dto.name
        assert deleted_permission.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_delete_permission_not_found(self, permission_repo: PermissionRepository) -> None:
        role = await permission_repo.delete(1)
        assert role is None

    @pytest.mark.asyncio
    async def test_add_permissions_to_roles_success(
        self, permission_repo: PermissionRepository, db_session: AsyncSession
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        result = await permission_repo.add_to_roles(permission.id, [role1.id, role2.id])
        assert result is not None
        assert result.id == permission.id
        assert result.roles is not None
        role_ids = {r.id for r in result.roles}
        assert role_ids == {role1.id, role2.id}
        names = {r.name for r in result.roles}
        assert names == {"role1", "role2"}

    @pytest.mark.asyncio
    async def test_add_duplicate_permissions_to_role_should_be_idempotent(
        self, permission_repo: PermissionRepository, db_session: AsyncSession
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        role = RoleModel(name="role_idem", description="desc")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        result1 = await permission_repo.add_to_roles(permission.id, [role.id])
        assert result1 is not None
        assert result1.roles is not None
        assert role.id in {r.id for r in result1.roles}

        # Adds the same role again
        result2 = await permission_repo.add_to_roles(permission.id, [role.id])
        assert result2 is not None
        assert result2.roles is not None
        role_ids = [r.id for r in result2.roles]

        assert role_ids.count(role.id) == 1

    @pytest.mark.asyncio
    async def test_add_nonexistent_permission_to_roles_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        res = await permission_repo.add_to_roles(1, [1, 2])
        assert res is None

    @pytest.mark.asyncio
    async def test_add_permission_to_unexistet_role_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        rse = await permission_repo.add_to_roles(permission.id, [1, 3])
        assert rse is None

    @pytest.mark.asyncio
    async def test_add_permission_to_empty_list_should_fail(
        self, permission_repo: PermissionRepository
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        res = await permission_repo.add_to_roles(permission.id, [])
        assert res is None

    @pytest.mark.asyncio
    async def test_remove_permission_from_roles_success(
        self, permission_repo: PermissionRepository, db_session: AsyncSession
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        result = await permission_repo.add_to_roles(permission.id, [role1.id, role2.id])
        assert result is not None
        assert result.id == permission.id
        assert result.roles is not None

        result = await permission_repo.get_with_roles(permission.id)
        assert result is not None
        assert result.roles is not None
        assert len(result.roles) == 2
        role_ids = {r.id for r in result.roles}
        assert role_ids == {role1.id, role2.id}
        names = {r.name for r in result.roles}
        assert names == {"role1", "role2"}

        ids = await permission_repo.remove_from_roles(permission.id, [role1.id, role2.id])
        assert len(ids) == 2
        assert ids[0].permission_id == permission.id
        assert ids[0].role_id == role1.id

        permission_after = await permission_repo.get_with_roles(permission.id)
        assert permission_after is not None
        assert permission_after.roles is not None
        assert len(permission_after.roles) == 0

    @pytest.mark.asyncio
    async def test_remove_permission_from_unexistent_roles(
        self, permission_repo: PermissionRepository, db_session: AsyncSession
    ) -> None:
        permission = await permission_repo.create(self.create_dto)
        assert permission is not None
        result = await permission_repo.remove_from_roles(permission.id, [1, 2])
        assert result is not None
        assert result == []

    @pytest.mark.asyncio
    async def test_remove_unexistent_permission_from_roles(
        self, permission_repo: PermissionRepository
    ) -> None:
        result = await permission_repo.remove_from_roles(1, [1, 2])
        assert result is not None
        assert result == []
