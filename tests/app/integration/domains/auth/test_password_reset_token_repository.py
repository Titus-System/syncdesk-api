from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.enums import TokenPurpose
from app.domains.auth.models import User as UserModel
from app.domains.auth.repositories.password_reset_token_repository import (
	PasswordResetTokenRepository,
)
from app.domains.auth.schemas import CreatePasswordResetTokenDTO


class TestPasswordResetTokenDTOs:
	def test_create_dto_success(self) -> None:
		dto = CreatePasswordResetTokenDTO(
			user_id=uuid4(),
			token_hash=uuid4().hex,
			purpose=TokenPurpose.RESET,
			expires_at=datetime.now() + timedelta(hours=1),
		)
		assert dto.user_id is not None
		assert dto.token_hash
		assert dto.purpose == TokenPurpose.RESET

	def test_create_dto_invalid_user_id_should_fail(self) -> None:
		with pytest.raises(ValidationError):
			dto = CreatePasswordResetTokenDTO(
				user_id="invalid_uuid",  # pyright: ignore
				token_hash=uuid4().hex,
				purpose=TokenPurpose.RESET,
				expires_at=datetime.now() + timedelta(hours=1),
			)
			assert dto is None

	def test_create_dto_invalid_purpose_should_fail(self) -> None:
		with pytest.raises(ValidationError):
			dto = CreatePasswordResetTokenDTO(
				user_id=uuid4(),
				token_hash=uuid4().hex,
				purpose="invalid",  # pyright: ignore
				expires_at=datetime.now() + timedelta(hours=1),
			)
			assert dto is None


class TestPasswordResetTokenRepository:
	@pytest.fixture
	def token_repo(self, db_session: AsyncSession) -> PasswordResetTokenRepository:
		return PasswordResetTokenRepository(db=db_session)

	@pytest.fixture
	async def user_id(self, db_session: AsyncSession) -> UUID:
		user = UserModel(
			email=f"{uuid4().hex[:8]}@mail.com",
			password_hash="hashed_pass",
		)
		db_session.add(user)
		await db_session.commit()
		await db_session.refresh(user)
		return user.id

	@pytest.fixture
	async def create_dto(self, user_id: UUID) -> CreatePasswordResetTokenDTO:
		return CreatePasswordResetTokenDTO(
			user_id=user_id,
			token_hash=uuid4().hex,
			purpose=TokenPurpose.RESET,
			expires_at=datetime.now() + timedelta(hours=1),
		)

	@pytest.mark.asyncio
	async def test_create_success(
		self,
		create_dto: CreatePasswordResetTokenDTO,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		token = await token_repo.create(create_dto)
		assert token is not None
		assert token.user_id == create_dto.user_id
		assert token.token_hash == create_dto.token_hash
		assert token.purpose == create_dto.purpose
		assert token.expires_at == create_dto.expires_at
		assert token.used_at is None

	@pytest.mark.asyncio
	async def test_create_with_existing_hash_should_fail(
		self,
		create_dto: CreatePasswordResetTokenDTO,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		await token_repo.create(create_dto)
		with pytest.raises(ResourceAlreadyExistsError):
			await token_repo.create(create_dto)

	@pytest.mark.asyncio
	async def test_create_invalid_dto_should_fail(
		self,
		token_repo: PasswordResetTokenRepository,
		user_id: UUID,
	) -> None:
		dto = {
			"user_id": user_id,
			"token_hash": uuid4().hex,
			"purpose": TokenPurpose.RESET,
			"expires_at": datetime.now() + timedelta(hours=1),
		}
		with pytest.raises(TypeError):
			await token_repo.create(dto)  # type: ignore[arg-type]

	@pytest.mark.asyncio
	async def test_create_with_nonexistent_user_id_should_fail(
		self,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		dto = CreatePasswordResetTokenDTO(
			user_id=uuid4(),
			token_hash=uuid4().hex,
			purpose=TokenPurpose.RESET,
			expires_at=datetime.now() + timedelta(hours=1),
		)
		with pytest.raises(ResourceAlreadyExistsError):
			await token_repo.create(dto)

	@pytest.mark.asyncio
	async def test_get_by_hash_success(
		self,
		create_dto: CreatePasswordResetTokenDTO,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		created = await token_repo.create(create_dto)
		found = await token_repo.get_by_hash(created.token_hash)
		assert found is not None
		assert found.id == created.id
		assert found.user_id == created.user_id
		assert found.token_hash == created.token_hash

	@pytest.mark.asyncio
	async def test_get_by_hash_not_found(self, token_repo: PasswordResetTokenRepository) -> None:
		found = await token_repo.get_by_hash("nonexistent_hash")
		assert found is None

	@pytest.mark.asyncio
	async def test_consume_by_hash_success(
		self,
		create_dto: CreatePasswordResetTokenDTO,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		created = await token_repo.create(create_dto)
		consumed = await token_repo.consume_by_hash(created.token_hash)
		assert consumed is not None
		assert consumed.id == created.id
		assert consumed.token_hash == created.token_hash
		assert consumed.used_at is not None

		stored = await token_repo.get_by_hash(created.token_hash)
		assert stored is not None
		assert stored.used_at is not None

	@pytest.mark.asyncio
	async def test_consume_by_hash_not_found(self, token_repo: PasswordResetTokenRepository) -> None:
		consumed = await token_repo.consume_by_hash("nonexistent_hash")
		assert consumed is None

	@pytest.mark.asyncio
	async def test_consume_by_hash_already_used_returns_none(
		self,
		create_dto: CreatePasswordResetTokenDTO,
		token_repo: PasswordResetTokenRepository,
	) -> None:
		created = await token_repo.create(create_dto)
		first = await token_repo.consume_by_hash(created.token_hash)
		assert first is not None

		second = await token_repo.consume_by_hash(created.token_hash)
		assert second is None

	@pytest.mark.asyncio
	async def test_consume_by_hash_expired_returns_none(
		self,
		token_repo: PasswordResetTokenRepository,
		user_id: UUID,
	) -> None:
		dto = CreatePasswordResetTokenDTO(
			user_id=user_id,
			token_hash=uuid4().hex,
			purpose=TokenPurpose.RESET,
			expires_at=datetime.now() - timedelta(minutes=1),
		)
		created = await token_repo.create(dto)

		consumed = await token_repo.consume_by_hash(created.token_hash)
		assert consumed is None

	@pytest.mark.asyncio
	async def test_invalidate_user_tokens_marks_only_matching_tokens(
		self,
		token_repo: PasswordResetTokenRepository,
		user_id: UUID,
	) -> None:
		reset_1 = await token_repo.create(
			CreatePasswordResetTokenDTO(
				user_id=user_id,
				token_hash=uuid4().hex,
				purpose=TokenPurpose.RESET,
				expires_at=datetime.now() + timedelta(hours=1),
			)
		)
		reset_2 = await token_repo.create(
			CreatePasswordResetTokenDTO(
				user_id=user_id,
				token_hash=uuid4().hex,
				purpose=TokenPurpose.RESET,
				expires_at=datetime.now() + timedelta(hours=1),
			)
		)
		invite = await token_repo.create(
			CreatePasswordResetTokenDTO(
				user_id=user_id,
				token_hash=uuid4().hex,
				purpose=TokenPurpose.INVITE,
				expires_at=datetime.now() + timedelta(hours=1),
			)
		)

		await token_repo.invalidate_user_tokens(user_id, TokenPurpose.RESET)

		reset_1_after = await token_repo.get_by_hash(reset_1.token_hash)
		reset_2_after = await token_repo.get_by_hash(reset_2.token_hash)
		invite_after = await token_repo.get_by_hash(invite.token_hash)

		assert reset_1_after is not None
		assert reset_2_after is not None
		assert invite_after is not None
		assert reset_1_after.used_at is not None
		assert reset_2_after.used_at is not None
		assert invite_after.used_at is None

	@pytest.mark.asyncio
	async def test_invalidate_user_tokens_no_matching_tokens_is_noop(
		self,
		token_repo: PasswordResetTokenRepository,
		user_id: UUID,
	) -> None:
		await token_repo.invalidate_user_tokens(user_id, TokenPurpose.RESET)

	@pytest.mark.asyncio
	async def test_invalidate_user_tokens_skips_already_used_tokens(
		self,
		token_repo: PasswordResetTokenRepository,
		user_id: UUID,
	) -> None:
		created = await token_repo.create(
			CreatePasswordResetTokenDTO(
				user_id=user_id,
				token_hash=uuid4().hex,
				purpose=TokenPurpose.RESET,
				expires_at=datetime.now() + timedelta(hours=1),
			)
		)

		consumed = await token_repo.consume_by_hash(created.token_hash)
		assert consumed is not None
		original_used_at = consumed.used_at

		await token_repo.invalidate_user_tokens(user_id, TokenPurpose.RESET)

		after = await token_repo.get_by_hash(created.token_hash)
		assert after is not None
		assert after.used_at == original_used_at
