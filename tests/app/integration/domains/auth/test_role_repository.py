import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.models import Permission as PermissionModel
from app.domains.auth.repositories.role_repository import RoleRepository
from app.domains.auth.schemas import CreateRoleDTO, ReplaceRoleDTO, UpdateRoleDTO


class TestRoleDTOs:
    @pytest.mark.asyncio
    async def test_create_role_dto_with_empty_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateRoleDTO(name="", description="A test role")
            assert not dto

    @pytest.mark.asyncio
    async def test_create_role_dto_with_none_name_should_fail(self) -> None:
        with pytest.raises(ValueError):
            dto = CreateRoleDTO(name=None, description="A test role")  # pyright: ignore
            assert not dto

    @pytest.mark.asyncio
    async def test_create_role_dto_with_short_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateRoleDTO(name="A", description="A test role")
            assert not dto

    @pytest.mark.asyncio
    async def test_create_role_dto_with_description_none(self) -> None:
        dto = CreateRoleDTO(name="test_role")
        assert dto.name == "test_role"
        assert dto.description is None

    @pytest.mark.asyncio
    async def test_create_role_dto_with_valid_data(self) -> None:
        dto = CreateRoleDTO(name="test_role", description="A test role")
        assert dto.name == "test_role"
        assert dto.description == "A test role"

    @pytest.mark.asyncio
    async def test_replace_role_dto_with_valid_data(self) -> None:
        dto = ReplaceRoleDTO(name="test_role", description="A test role")
        assert dto.name == "test_role"
        assert dto.description == "A test role"

    @pytest.mark.asyncio
    async def test_replace_role_dto_with_none_name_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = ReplaceRoleDTO(name=None, description="A test role")  # pyright: ignore
            assert not dto


class TestRolesRepository:
    """Unit tests for RoleRepository."""

    create_dto = CreateRoleDTO(name="test_role", description="A test role")
    update_dto = UpdateRoleDTO(name="updated_role", description="An updated test role")

    @pytest.fixture
    def role_repo(self, db_session: AsyncSession) -> RoleRepository:
        """Create a RoleRepository instance for each test."""
        return RoleRepository(db=db_session)

    @pytest.mark.asyncio
    async def test_get_all_roles_empty(self, role_repo: RoleRepository) -> None:
        roles = await role_repo.get_all()
        assert roles is not None
        assert len(roles) == 0

    @pytest.mark.asyncio
    async def test_create_role_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        assert role is not None
        assert role.name == self.create_dto.name
        assert role.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_create_role_with_existing_name_should_fail(
        self, role_repo: RoleRepository
    ) -> None:
        await role_repo.create(self.create_dto)
        with pytest.raises((SQLAlchemyError, ResourceAlreadyExistsError)):
            await role_repo.create(self.create_dto)

    @pytest.mark.asyncio
    async def test_create_role_with_long_name_should_fail(self, role_repo: RoleRepository) -> None:
        with pytest.raises(SQLAlchemyError):
            dto = CreateRoleDTO(name="a" * 31)
            await role_repo.create(dto)

    @pytest.mark.asyncio
    async def test_create_role_with_long_description_should_fail(
        self, role_repo: RoleRepository
    ) -> None:
        with pytest.raises(SQLAlchemyError):
            dto = CreateRoleDTO(name="test_role", description="a" * 256)
            await role_repo.create(dto)

    @pytest.mark.asyncio
    async def test_create_role_with_invalid_dto_should_fail(
        self, role_repo: RoleRepository
    ) -> None:
        with pytest.raises(TypeError):
            dto = self.update_dto
            await role_repo.create(dto)  # type: ignore

    @pytest.mark.asyncio
    async def test_get_all_roles_success(self, role_repo: RoleRepository) -> None:
        await role_repo.create(self.create_dto)
        roles = await role_repo.get_all()
        assert roles is not None
        assert len(roles) > 0

    @pytest.mark.asyncio
    async def test_get_role_by_id_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        get_role = await role_repo.get_by_id(role.id)
        assert get_role is not None
        assert get_role.name == self.create_dto.name
        assert get_role.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_get_role_by_id_not_found(self, role_repo: RoleRepository) -> None:
        role = await role_repo.get_by_id(1)
        assert role is None

    @pytest.mark.asyncio
    async def test_get_role_by_name_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        get_role = await role_repo.get_by_name(role.name)
        assert get_role is not None
        assert get_role.name == self.create_dto.name
        assert get_role.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_get_role_by_name_not_found(self, role_repo: RoleRepository) -> None:
        role = await role_repo.get_by_name("non_existent_role")
        assert role is None

    @pytest.mark.asyncio
    async def test_update_role_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        assert role is not None
        updated_role = await role_repo.update(role.id, self.update_dto)
        assert updated_role is not None
        assert updated_role.name == self.update_dto.name
        assert updated_role.description == self.update_dto.description
        assert updated_role.id == role.id

    @pytest.mark.asyncio
    async def test_update_role_not_found(self, role_repo: RoleRepository) -> None:
        role = await role_repo.update(1, self.update_dto)
        assert role is None

    @pytest.mark.asyncio
    async def test_update_role_with_invalid_dto_should_fail(
        self, role_repo: RoleRepository
    ) -> None:
        role = await role_repo.create(self.create_dto)
        with pytest.raises(TypeError):
            await role_repo.update(role.id, self.create_dto)  # type: ignore

    @pytest.mark.asyncio
    async def test_update_role_is_idempotent(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        await role_repo.update(role.id, self.update_dto)
        state_after_first = await role_repo.get_by_id(role.id)
        await role_repo.update(role.id, self.update_dto)
        state_after_second = await role_repo.get_by_id(role.id)
        assert state_after_first == state_after_second

    @pytest.mark.asyncio
    async def test_replace_role_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        assert role is not None
        replace_dto = ReplaceRoleDTO(name="replaced_role")
        replaced_role = await role_repo.update(role.id, replace_dto)
        assert replaced_role is not None
        assert replaced_role.name == replace_dto.name
        assert replaced_role.description is None
        assert replaced_role.id == role.id

    @pytest.mark.asyncio
    async def test_add_permissions_empty_permission_ids_raises(
        self, role_repo: RoleRepository
    ) -> None:
        role = await role_repo.create(self.create_dto)
        res = await role_repo.add_permissions(role.id, [])
        assert res is None

    @pytest.mark.asyncio
    async def test_add_permissions_to_nonexistent_role_raises(
        self, role_repo: RoleRepository
    ) -> None:
        res = await role_repo.add_permissions(9999, [1, 2])
        assert res is None

    @pytest.mark.asyncio
    async def test_add_permissions_nonexistent_permissions_raises(
        self, role_repo: RoleRepository
    ) -> None:
        role = await role_repo.create(self.create_dto)
        res = await role_repo.add_permissions(role.id, [123, 456])
        assert res is None

    @pytest.mark.asyncio
    async def test_add_permissions_success(
        self, role_repo: RoleRepository, db_session: AsyncSession
    ) -> None:
        role = await role_repo.create(self.create_dto)
        perm1 = PermissionModel(name="perm1", description="desc1")
        perm2 = PermissionModel(name="perm2", description="desc2")
        db_session.add_all([perm1, perm2])
        await db_session.commit()
        await db_session.refresh(perm1)
        await db_session.refresh(perm2)

        result = await role_repo.add_permissions(role.id, [perm1.id, perm2.id])
        assert result is not None
        assert result.id == role.id
        assert result.permissions is not None
        perm_ids = {p.id for p in result.permissions}
        assert perm_ids == {perm1.id, perm2.id}
        names = {p.name for p in result.permissions}
        assert names == {"perm1", "perm2"}

    @pytest.mark.asyncio
    async def test_add_duplicate_permissions_to_role_should_be_idempotent(
        self, role_repo: RoleRepository, db_session: AsyncSession
    ) -> None:
        role = await role_repo.create(self.create_dto)
        perm = PermissionModel(name="perm_idem", description="desc")
        db_session.add(perm)
        await db_session.commit()
        await db_session.refresh(perm)

        result1 = await role_repo.add_permissions(role.id, [perm.id])
        assert result1 is not None
        assert result1.permissions is not None
        assert perm.id in {p.id for p in result1.permissions}

        # Adds the same permission again
        result2 = await role_repo.add_permissions(role.id, [perm.id])
        assert result2 is not None
        assert result2.permissions is not None
        perm_ids = [p.id for p in result2.permissions]

        assert perm_ids.count(perm.id) == 1

    @pytest.mark.asyncio
    async def test_delete_role_success(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        assert role is not None
        deleted_role = await role_repo.delete(role.id)
        assert deleted_role is not None
        assert deleted_role.name == self.create_dto.name
        assert deleted_role.description == self.create_dto.description

    @pytest.mark.asyncio
    async def test_delete_role_not_found(self, role_repo: RoleRepository) -> None:
        role = await role_repo.delete(1)
        assert role is None

    @pytest.mark.asyncio
    async def test_remove_role_permissions_success(
        self, role_repo: RoleRepository, db_session: AsyncSession
    ) -> None:
        role = await role_repo.create(self.create_dto)
        perm1 = PermissionModel(name="perm1", description="desc1")
        perm2 = PermissionModel(name="perm2", description="desc2")
        db_session.add_all([perm1, perm2])
        await db_session.commit()
        await db_session.refresh(perm1)
        await db_session.refresh(perm2)

        result = await role_repo.add_permissions(role.id, [perm1.id, perm2.id])
        assert result is not None
        assert result.id == role.id
        assert result.permissions is not None

        result = await role_repo.get_with_permissions(role.id)
        assert result is not None
        assert result.permissions is not None
        assert len(result.permissions) == 2
        perm_ids = {p.id for p in result.permissions}
        assert perm_ids == {perm1.id, perm2.id}
        names = {p.name for p in result.permissions}
        assert names == {"perm1", "perm2"}

        role_permissions = await role_repo.remove_permissions(role.id, [])
        assert role_permissions is not None
        assert len(role_permissions) == 0

        role_permissions = await role_repo.remove_permissions(role.id, [perm1.id, perm2.id])
        assert role_permissions is not None
        assert len(role_permissions) == 2
        assert role_permissions[0].role_id == role.id
        assert {rp.permission_id for rp in role_permissions} == perm_ids

        role_after = await role_repo.get_with_permissions(role.id)
        assert role_after is not None
        assert role_after.permissions is not None
        assert len(role_after.permissions) == 0

    @pytest.mark.asyncio
    async def test_remove_unexistent_permissions_from_role(self, role_repo: RoleRepository) -> None:
        role = await role_repo.create(self.create_dto)
        assert role is not None
        result = await role_repo.remove_permissions(role.id, [1, 2, 3])
        assert result is not None
        assert result == []

    @pytest.mark.asyncio
    async def test_remove_permissions_from_unexistent_role(self, role_repo: RoleRepository) -> None:
        result = await role_repo.remove_permissions(1, [1, 2, 3])
        assert result is not None
        assert result == []
