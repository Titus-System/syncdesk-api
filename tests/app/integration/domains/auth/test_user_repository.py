import random
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.entities import User
from app.domains.auth.enums import OAuthProvider
from app.domains.auth.models import Role as RoleModel
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.schemas import CreateUserDTO
from app.domains.auth.schemas.user_schemas import ReplaceUserDTO, UpdateUserDTO


class TestUserDTOs:
    def test_create_user_with_password_and_username(self) -> None:
        dto = CreateUserDTO(
            email="user@example.com",
            password_hash="hashed-password",
        )
        assert dto.password_hash is not None
        assert dto.password_hash == "hashed-password"
        assert dto.email == "user@example.com"
        assert dto.is_active is True
        assert dto.is_verified is False

    def test_create_user_with_oauth(self) -> None:
        dto = CreateUserDTO(
            email="user@example.com",
            oauth_provider=OAuthProvider.GOOGLE,
            oauth_provider_id="google-123",
            name="OAuth User",
        )
        assert dto.oauth_provider == OAuthProvider.GOOGLE
        assert dto.oauth_provider_id == "google-123"
        assert dto.name == "OAuth User"
        assert dto.is_active is True
        assert dto.is_verified is False

    def test_create_user_without_password_and_oauth_should_fail(self) -> None:
        with pytest.raises(ValidationError) as exc:
            CreateUserDTO(
                email="user@example.com",
                name="Test User",
            )
        assert "User must have either password or OAuth provider" in str(exc.value)

    def test_create_user_with_oauth_without_provider_id_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            CreateUserDTO(
                email="user@example.com",
                oauth_provider=OAuthProvider.GOOGLE,
                name="OAuth User",
            )

    def test_invalid_update_user_dto_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            UpdateUserDTO(
                id=uuid4(),  # type: ignore
                email="user@example.com",
                name="Updated User",
            )


class TestUserRepository:
    """Unit tests for UserRepository."""

    create_with_email_password_dto = CreateUserDTO(
        email=f"test_{uuid4().hex[:8]}@example.com",
        username=f"testuser_{uuid4().hex[:8]}",
        name="Test User",
        password_hash="hashed_password_here",
        oauth_provider=OAuthProvider.LOCAL,
    )

    create_with_oauth_dto = CreateUserDTO(
        email=f"test_{uuid4().hex[:8]}@example.com",
        oauth_provider=random.choice(list(OAuthProvider)),
        oauth_provider_id="oauth-id-123",
    )

    update_dto = UpdateUserDTO(
        email=f"test_{uuid4().hex[:8]}@example.com",
        username=f"testuser_{uuid4().hex[:8]}",
        name="Test User",
    )

    @pytest.fixture
    def user_repo(self, db_session: AsyncSession) -> UserRepository:
        """Create a UserRepository instance for each test."""
        return UserRepository(db=db_session)

    @pytest.fixture
    async def user(self, user_repo: UserRepository) -> User:
        return await user_repo.create(self.create_with_oauth_dto)

    @pytest.mark.asyncio
    async def test_create_user_with_password_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        assert user is not None
        assert user.email == self.create_with_email_password_dto.email
        assert user.username == self.create_with_email_password_dto.username
        assert user.name == self.create_with_email_password_dto.name
        assert user.is_active is True
        assert user.is_verified is False

    @pytest.mark.asyncio
    async def test_create_user_with_roles(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        role1 = RoleModel(name="create_role_a", description="Role A")
        role2 = RoleModel(name="create_role_b", description="Role B")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        dto = CreateUserDTO(
            email=f"withroles_{uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            role_ids=[role1.id, role2.id],
        )
        user = await user_repo.create(dto)
        assert user is not None
        assert user.roles is not None
        assert len(user.roles) == 2
        assert {r.id for r in user.roles} == {role1.id, role2.id}
        assert {r.name for r in user.roles} == {"create_role_a", "create_role_b"}

    @pytest.mark.asyncio
    async def test_create_user_with_single_role(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        role = RoleModel(name="single_role", description="Only role")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"singlerole_{uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            role_ids=[role.id],
        )
        user = await user_repo.create(dto)
        assert user is not None
        assert user.roles is not None
        assert len(user.roles) == 1
        assert user.roles[0].id == role.id
        assert user.roles[0].name == "single_role"
        assert user.roles[0].description == "Only role"

    @pytest.mark.asyncio
    async def test_create_user_with_roles_returns_correct_entity(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        """Verify the returned UserWithRoles has all user fields plus roles."""
        role = RoleModel(name="entity_check_role")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"entitycheck_{uuid4().hex[:8]}@example.com",
            username="entityuser",
            name="Entity User",
            password_hash="hashed_password",
            role_ids=[role.id],
        )
        user = await user_repo.create(dto)
        assert user.email == dto.email
        assert user.username == dto.username
        assert user.name == dto.name
        assert user.password_hash == dto.password_hash
        assert user.is_active is True
        assert user.is_verified is False
        assert user.roles is not None
        assert len(user.roles) == 1
        assert user.roles[0].name == "entity_check_role"

    @pytest.mark.asyncio
    async def test_create_user_roles_persisted_in_db(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        """Roles assigned at creation should be visible via get_with_roles."""
        role = RoleModel(name="persist_role", description="Should persist")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"persist_{uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            role_ids=[role.id],
        )
        created = await user_repo.create(dto)
        fetched = await user_repo.get_with_roles(created.id)
        assert fetched is not None
        assert fetched.roles is not None
        assert len(fetched.roles) == 1
        assert fetched.roles[0].id == role.id
        assert fetched.roles[0].name == "persist_role"

    @pytest.mark.asyncio
    async def test_create_user_with_empty_role_ids(self, user_repo: UserRepository) -> None:
        dto = CreateUserDTO(
            email=f"noroles_{uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            role_ids=[],
        )
        user = await user_repo.create(dto)
        assert user is not None
        assert user.roles is not None
        assert len(user.roles) == 0

    @pytest.mark.asyncio
    async def test_create_user_with_nonexistent_role_ids(self, user_repo: UserRepository) -> None:
        dto = CreateUserDTO(
            email=f"badroles_{uuid4().hex[:8]}@example.com",
            password_hash="hashed_password",
            role_ids=[99999],
        )
        with pytest.raises(ResourceAlreadyExistsError):
            await user_repo.create(dto)

    @pytest.mark.asyncio
    async def test_create_user_with_oauth_success(self, user_repo: UserRepository) -> None:
        dto = self.create_with_oauth_dto
        user = await user_repo.create(dto)
        assert user is not None
        assert user.email == dto.email
        assert user.oauth_provider == dto.oauth_provider
        assert user.oauth_provider_id == dto.oauth_provider_id

    @pytest.mark.asyncio
    async def test_create_user_with_existing_email_should_fail(
        self, user_repo: UserRepository
    ) -> None:
        await user_repo.create(self.create_with_email_password_dto)
        new_dto = CreateUserDTO(
            email=self.create_with_email_password_dto.email,
            password_hash="new_hashed_password_here",
        )
        with pytest.raises((SQLAlchemyError, ResourceAlreadyExistsError)):
            await user_repo.create(new_dto)

    @pytest.mark.asyncio
    async def test_create_user_with_existing_username_should_fail(
        self, user_repo: UserRepository
    ) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        assert user is not None
        new_dto = CreateUserDTO(
            email=f"test_{uuid4().hex[:8]}@example.com",
            username=self.create_with_email_password_dto.username,
            password_hash="new_hashed_password_here",
        )
        with pytest.raises((SQLAlchemyError, ResourceAlreadyExistsError)):
            await user_repo.create(new_dto)

    @pytest.mark.asyncio
    async def test_create_user_with_existing_oauth_id_should_fail(
        self, user_repo: UserRepository
    ) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        new_dto = CreateUserDTO(
            email=f"test_{uuid4().hex[:8]}@example.com",
            oauth_provider=self.create_with_oauth_dto.oauth_provider,
            oauth_provider_id=self.create_with_oauth_dto.oauth_provider_id,
        )
        with pytest.raises((SQLAlchemyError, ResourceAlreadyExistsError)):
            await user_repo.create(new_dto)

    @pytest.mark.asyncio
    async def test_get_all_success(self, user_repo: UserRepository) -> None:
        user1 = await user_repo.create(self.create_with_email_password_dto)
        user2 = await user_repo.create(self.create_with_oauth_dto)
        users = await user_repo.get_all()
        assert len(users) == 2
        user_ids = {user.id for user in users}
        assert user1.id in user_ids
        assert user2.id in user_ids
        assert user1.id != user2.id
        assert {user.email for user in users} == {user1.email, user2.email}
        assert {user.username for user in users} == {user1.username, user2.username}
        assert {user.name for user in users} == {user1.name, user2.name}
        assert {user.oauth_provider for user in users} == {
            user1.oauth_provider,
            user2.oauth_provider,
        }

    @pytest.mark.asyncio
    async def test_get_all_empty(self, user_repo: UserRepository) -> None:
        users = await user_repo.get_all()
        assert len(users) == 0
        assert users == []

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        retrieved_user = await user_repo.get_by_id(user.id)
        assert retrieved_user is not None
        assert retrieved_user.id == user.id
        assert retrieved_user.email == user.email
        assert retrieved_user.username == user.username

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, user_repo: UserRepository) -> None:
        user = await user_repo.get_by_id(uuid4())
        assert user is None

    @pytest.mark.asyncio
    async def get_by_email_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        retrieved_user = await user_repo.get_by_email(user.email)
        assert retrieved_user is not None
        assert retrieved_user == user
        assert retrieved_user.id == user.id

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self, user_repo: UserRepository) -> None:
        user = await user_repo.get_by_email(f"test_{uuid4().hex[:8]}@example.com")
        assert user is None

    @pytest.mark.asyncio
    async def test_get_active(self, user_repo: UserRepository) -> None:
        user1 = await user_repo.create(self.create_with_email_password_dto)
        user2 = await user_repo.create(self.create_with_oauth_dto)
        users = await user_repo.get_active()
        assert len(users) == 2
        user_ids = {user.id for user in users}
        assert user1.id in user_ids
        assert user2.id in user_ids
        assert user1.id != user2.id
        assert {user.id for user in users} == {user1.id, user2.id}

    @pytest.mark.asyncio
    async def test_update_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        assert user is not None
        updated_user = await user_repo.update(user.id, self.update_dto)
        assert updated_user is not None
        assert updated_user.email == self.update_dto.email
        assert user.id == updated_user.id
        assert user.email != updated_user.email
        users = await user_repo.get_all()
        assert len(users) == 1
        assert updated_user in users
        assert user not in users

    @pytest.mark.asyncio
    async def test_update_should_be_idempotent(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_email_password_dto)
        assert user is not None
        updated_user1 = await user_repo.update(user.id, self.update_dto)
        assert updated_user1 is not None
        updated_user2 = await user_repo.update(user.id, self.update_dto)
        assert updated_user2 is not None
        assert updated_user1 == updated_user2

    @pytest.mark.asyncio
    async def test_update_empty_dto(self, user: User, user_repo: UserRepository) -> None:
        res = await user_repo.update(user.id, UpdateUserDTO())
        assert res is None

    @pytest.mark.asyncio
    async def test_update_id_not_found(self, user_repo: UserRepository) -> None:
        user = await user_repo.update(uuid4(), self.update_dto)
        assert user is None

    @pytest.mark.asyncio
    async def test_update_with_invalid_dto_should_fail(self, user_repo: UserRepository) -> None:
        with pytest.raises(TypeError):
            await user_repo.update(uuid4(), self.create_with_oauth_dto)  # type: ignore

    @pytest.mark.asyncio
    async def test_replace_user_success(self, user_repo: UserRepository) -> None:
        replace_dto = ReplaceUserDTO(
            email=f"test_{uuid4().hex[:8]}@example.com",
            password_hash="replace_hashed_password",
        )
        user = await user_repo.create(self.create_with_email_password_dto)
        assert user is not None
        replaced_user = await user_repo.update(user.id, replace_dto)
        assert replaced_user is not None
        assert replaced_user != user
        assert replaced_user.email == replace_dto.email
        assert user.id == replaced_user.id
        assert user.password_hash != replaced_user.password_hash
        assert replaced_user.username is None

    @pytest.mark.asyncio
    async def test_soft_delete_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        deleted_user = await user_repo.soft_delete(user.id)
        assert deleted_user is not None
        assert deleted_user.id == user.id
        fetched_user = await user_repo.get_by_id(user.id)
        assert fetched_user is not None
        assert fetched_user.is_active is False
        users = await user_repo.get_all()
        assert len(users) == 1
        assert deleted_user in users

    @pytest.mark.asyncio
    async def test_soft_delete_id_not_found(self, user_repo: UserRepository) -> None:
        user = await user_repo.soft_delete(uuid4())
        assert user is None

    @pytest.mark.asyncio
    async def test_soft_delete_is_idempotent(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        deleted_user1 = await user_repo.soft_delete(user.id)
        assert deleted_user1 is not None
        assert deleted_user1.id == user.id
        deleted_user2 = await user_repo.soft_delete(user.id)
        assert deleted_user2 is not None
        assert deleted_user2.id == user.id
        assert deleted_user1 == deleted_user2

    @pytest.mark.asyncio
    async def test_hard_delete_success(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        deleted_user = await user_repo.hard_delete(user.id)
        assert deleted_user is not None
        assert deleted_user.id == user.id
        assert deleted_user.email == user.email
        fetched_user = await user_repo.get_by_id(user.id)
        assert fetched_user is None

    @pytest.mark.asyncio
    async def test_hard_delete_id_not_found(self, user_repo: UserRepository) -> None:
        user = await user_repo.hard_delete(uuid4())
        assert user is None

    @pytest.mark.asyncio
    async def test_add_roles_success(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        updated_user, missing_ids = await user_repo.add_roles(user.id, [role1.id, role2.id])
        assert updated_user is not None and missing_ids is None
        assert updated_user.id == user.id
        assert updated_user.roles is not None
        assert len(updated_user.roles) == 2
        assert {role.id for role in updated_user.roles} == {role1.id, role2.id}

    @pytest.mark.asyncio
    async def test_add_duplicate_roles_to_user_should_be_idempotent(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        updated_user, missing_ids = await user_repo.add_roles(user.id, [role1.id, role2.id])
        assert updated_user is not None and missing_ids is None
        assert updated_user.roles is not None
        assert {role.id for role in updated_user.roles} == {role1.id, role2.id}

        updated_user2, missing_ids2 = await user_repo.add_roles(user.id, [role1.id, role2.id])
        assert updated_user2 is not None and missing_ids2 is None
        assert updated_user2 == updated_user
        assert missing_ids2 == missing_ids

    @pytest.mark.asyncio
    async def test_add_roles_to_unexistent_user(self, user_repo: UserRepository) -> None:
        user, ids = await user_repo.add_roles(uuid4(), [1, 2])
        assert user is None and ids is None

    @pytest.mark.asyncio
    async def test_add_unexistent_roles_to_user(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        updated_user, ids = await user_repo.add_roles(user.id, [1, 2])
        assert updated_user is None and ids == {1, 2}

    @pytest.mark.asyncio
    async def test_remove_roles_success(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        result, missing_ids = await user_repo.add_roles(user.id, [role1.id, role2.id])
        assert result is not None and missing_ids is None
        assert result.id == user.id
        assert result.roles is not None

        result = await user_repo.get_with_roles(user.id)
        assert result is not None
        assert result.roles is not None
        assert len(result.roles) == 2
        role_ids = {r.id for r in result.roles}
        assert role_ids == {role1.id, role2.id}
        names = {r.name for r in result.roles}
        assert names == {"role1", "role2"}

        ids = await user_repo.remove_roles(user.id, [role1.id, role2.id])
        assert len(ids) == 2
        assert {r.role_id for r in ids} == {role1.id, role2.id}

        result = await user_repo.get_with_roles(user.id)
        assert result is not None
        assert result.roles == []

    @pytest.mark.asyncio
    async def test_remove_unexistent_user_role_relationship(
        self, user_repo: UserRepository
    ) -> None:
        result = await user_repo.remove_roles(uuid4(), [1, 2])
        assert result == []

    @pytest.mark.asyncio
    async def test_remove_unexistent_roles_from_user(self, user_repo: UserRepository) -> None:
        user = await user_repo.create(self.create_with_oauth_dto)
        assert user is not None
        result = await user_repo.remove_roles(user.id, [1, 2])
        assert result == []

    @pytest.mark.asyncio
    async def test_remove_roles_from_unexistent_user(
        self, user_repo: UserRepository, db_session: AsyncSession
    ) -> None:
        role1 = RoleModel(name="role1", description="desc1")
        role2 = RoleModel(name="role2", description="desc2")
        db_session.add_all([role1, role2])
        await db_session.commit()
        await db_session.refresh(role1)
        await db_session.refresh(role2)

        res = await user_repo.remove_roles(uuid4(), [role1.id, role2.id])
        assert res == []
