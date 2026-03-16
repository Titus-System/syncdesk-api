import random
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.schemas import SessionDeviceInfo
from app.domains.auth.entities import Session
from app.domains.auth.enums import SessionStatus
from app.domains.auth.models import User as UserModel
from app.domains.auth.repositories.session_repository import SessionRepository
from app.domains.auth.schemas.session_schemas import (
    CreateSessionDTO,
    UpdateSessionDTO,
)


class TestSessionDTOs:
    def test_create_dto_success(self) -> None:
        user_id = uuid4()
        refresh_token_hash = uuid4().hex
        expires_at = datetime.now() + timedelta(days=2)
        dto = CreateSessionDTO(
            user_id=user_id,
            role_names=[],
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )
        assert dto is not None
        assert dto.user_id

    def test_create__dto_invalid_user_id_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateSessionDTO(
                user_id="string_to_fail",  # pyright: ignore
                refresh_token_hash=f"{uuid4().hex}",
                expires_at=datetime.now() + timedelta(days=2),
            )
            assert dto is None

    def test_create_dto_invalid_token_type_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateSessionDTO(
                user_id=uuid4(),
                refresh_token_hash=1234354,  # pyright: ignore
                expires_at=datetime.now() + timedelta(days=2),
            )
            assert dto is None

    def test_create_dto_no_expiration_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateSessionDTO(  # type: ignore
                user_id=uuid4(), refresh_token_hash=f"{uuid4().hex}"
            )
            assert dto is None

    def test_create_dto_expiration_in_past_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateSessionDTO(
                user_id=uuid4(),
                refresh_token_hash=uuid4().hex,
                expires_at=datetime.now() - timedelta(seconds=2),
            )
            assert dto is None

    def test_create_dto_invalid_device_info_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            dto = CreateSessionDTO(
                user_id=uuid4(),
                refresh_token_hash=uuid4().hex,
                expires_at=datetime.now() - timedelta(seconds=2),
                device_info={  # pyright: ignore
                    "user_agent": "test_agent"
                },
            )
            assert dto is None


class TestSessionRepository:
    @pytest.fixture
    async def session_repo(self, db_session: AsyncSession) -> SessionRepository:
        return SessionRepository(db_session)

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
    async def create_dto(self, user_id: UUID) -> CreateSessionDTO:
        return CreateSessionDTO(
            user_id=user_id,
            role_names=[],
            refresh_token_hash=uuid4().hex,
            expires_at=datetime.now() + timedelta(days=2),
        )

    @pytest.fixture
    async def session(
        self, create_dto: CreateSessionDTO, session_repo: SessionRepository
    ) -> Session:
        return await session_repo.create(create_dto)

    @pytest.fixture
    async def revoked_session(
        self, create_dto: CreateSessionDTO, session_repo: SessionRepository
    ) -> Session:
        create_dto.status = SessionStatus.REVOKED
        return await session_repo.create(create_dto)

    @pytest.fixture
    async def sessions(self, user_id: UUID, session_repo: SessionRepository) -> list[Session]:
        dtos: list[CreateSessionDTO] = []
        for _ in range(5):
            dto = CreateSessionDTO(
                user_id=user_id,
                role_names=[],
                refresh_token_hash=uuid4().hex,
                expires_at=datetime.now() + timedelta(days=2),
                status=random.choice(list(SessionStatus)),
            )
            dtos.append(dto)
        sessions: list[Session] = []
        for dto in dtos:
            session = await session_repo.create(dto)
            sessions.append(session)
        return sessions

    @pytest.fixture
    async def active_sessions(
        self, create_dto: CreateSessionDTO, session_repo: SessionRepository
    ) -> list[Session]:
        sessions: list[Session] = []
        for i in range(5):
            create_dto.refresh_token_hash = f"{i}_test_token"
            s = await session_repo.create(create_dto)
            sessions.append(s)
        return sessions

    @pytest.mark.asyncio
    async def test_create_session_success(
        self,
        create_dto: CreateSessionDTO,
        session_repo: SessionRepository,
    ) -> None:
        dto = create_dto
        session = await session_repo.create(dto)
        assert session is not None
        assert session.user_id == dto.user_id
        assert session.refresh_token_hash == dto.refresh_token_hash
        assert session.expires_at == dto.expires_at
        assert session.is_valid()

    @pytest.mark.asyncio
    async def test_create_session_existing_token_hash_should_fail(
        self, create_dto: CreateSessionDTO, session_repo: SessionRepository
    ) -> None:
        dto = create_dto
        session = await session_repo.create(dto)
        assert session is not None
        with pytest.raises(IntegrityError):
            new_session = await session_repo.create(dto)
            assert new_session is None

    @pytest.mark.asyncio
    async def test_create_session_invalid_dto_should_fail(
        self, user_id: UUID, session_repo: SessionRepository
    ) -> None:
        dto = UpdateSessionDTO(
            refresh_token_hash=uuid4().hex,
            expires_at=datetime.now() + timedelta(days=2),
        )
        with pytest.raises(TypeError):
            await session_repo.create(dto)  #  type: ignore

    @pytest.mark.asyncio
    async def test_create_session_unexistent_user_should_fail(
        self, session_repo: SessionRepository
    ) -> None:
        dto = CreateSessionDTO(
            user_id=uuid4(),
            role_names=[],
            refresh_token_hash=uuid4().hex,
            expires_at=datetime.now() + timedelta(days=2),
        )
        with pytest.raises(IntegrityError):
            await session_repo.create(dto)

    @pytest.mark.asyncio
    async def test_create_invalid_dto_should_fail(self, session_repo: SessionRepository) -> None:
        dto = UpdateSessionDTO()
        with pytest.raises(TypeError):
            await session_repo.create(dto)  #  type: ignore

    @pytest.mark.asyncio
    async def test_get_all(self, sessions: list[Session], session_repo: SessionRepository) -> None:
        get_sessions = await session_repo.get_all()
        assert len(get_sessions) == len(sessions)
        assert {session.id for session in get_sessions} == {session.id for session in sessions}
        assert {session.refresh_token_hash for session in get_sessions} == {
            session.refresh_token_hash for session in sessions
        }

    @pytest.mark.asyncio
    async def test_get_by_id(
        self, sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        session1 = sessions[0]
        get_session = await session_repo.get_by_id(session1.id)
        assert get_session is not None
        assert get_session == session1

        session2 = sessions[1]
        assert session1 != session2
        get_session = await session_repo.get_by_id(session2.id)
        assert get_session is not None
        assert get_session == session2

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, session_repo: SessionRepository) -> None:
        session = await session_repo.get_by_id(uuid4())
        assert session is None

    @pytest.mark.asyncio
    async def test_get_by_token(
        self, sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        session1 = sessions[0]
        get_session = await session_repo.get_by_refresh_token_hash(session1.refresh_token_hash)
        assert get_session is not None
        assert get_session == session1

        session2 = sessions[1]
        assert session1 != session2
        get_session = await session_repo.get_by_refresh_token_hash(session2.refresh_token_hash)
        assert get_session is not None
        assert get_session == session2

    @pytest.mark.asyncio
    async def test_get_by_token_not_found(self, session_repo: SessionRepository) -> None:
        session = await session_repo.get_by_refresh_token_hash("hashed_token")
        assert session is None

    @pytest.mark.asyncio
    async def test_active_by_user_id(
        self, user_id: UUID, sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        active_sessions = [s for s in sessions if s.is_active()]
        get_sessions = await session_repo.get_active_by_user_id(user_id)
        assert len(get_sessions) == len(active_sessions)
        assert {s.id for s in get_sessions} == {s.id for s in active_sessions}

    @pytest.mark.asyncio
    async def test_get_by_active_user_id_not_found(
        self, user_id: UUID, session_repo: SessionRepository
    ) -> None:
        sessions = await session_repo.get_active_by_user_id(user_id)
        assert sessions == []

    @pytest.mark.asyncio
    async def test_update_success(self, session: Session, session_repo: SessionRepository) -> None:
        last_used_at = datetime.now()
        update_dto = UpdateSessionDTO(
            refresh_token_hash="new_token_hash",
            last_used_at=last_used_at,
            device_info=SessionDeviceInfo(user_agent="test_agent"),
        )
        updated = await session_repo.update(session.id, update_dto)
        assert updated is not None
        assert updated.refresh_token_hash == update_dto.refresh_token_hash
        assert updated.device_info is not None
        assert updated.device_info.user_agent == "test_agent"
        assert updated.last_used_at == last_used_at

    @pytest.mark.asyncio
    async def test_update_empty_dto(
        self, session: Session, session_repo: SessionRepository
    ) -> None:
        res = await session_repo.update(session.id, UpdateSessionDTO())
        assert res is None

    @pytest.mark.asyncio
    async def test_update_unexistent_id(self, session_repo: SessionRepository) -> None:
        dto = UpdateSessionDTO(status=SessionStatus.INVALID)
        res = await session_repo.update(uuid4(), dto)
        assert res is None

    @pytest.mark.asyncio
    async def test_revokke_success(self, session: Session, session_repo: SessionRepository) -> None:
        res = await session_repo.revoke(session.id)
        assert res is not None
        assert session.status != SessionStatus.REVOKED
        assert res.status == SessionStatus.REVOKED

    @pytest.mark.asyncio
    async def test_revoke_id_not_found(self, session_repo: SessionRepository) -> None:
        res = await session_repo.revoke(uuid4())
        assert res is None

    @pytest.mark.asyncio
    async def test_revoke_session_already_revoked(
        self, revoked_session: Session, session_repo: SessionRepository
    ) -> None:
        assert revoked_session.is_revoked()
        res = await session_repo.revoke(revoked_session.id)
        assert res == revoked_session

    @pytest.mark.asyncio
    async def test_count_active_sessions_per_user_success(
        self, sessions: list[Session], user_id: UUID, session_repo: SessionRepository
    ) -> None:
        res = await session_repo.count_active_sessions_per_user(user_id)
        assert res is not None
        n_active = {s.id for s in sessions if s.status == SessionStatus.ACTIVE}
        assert res == len(n_active)

    @pytest.mark.asyncio
    async def test_count_active_sessions_per_user_not_found(
        self, sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        count = await session_repo.count_active_sessions_per_user(uuid4())
        assert count == 0

    @pytest.mark.asyncio
    async def test_has_reached_limit_success(
        self, active_sessions: list[Session], user_id: UUID, session_repo: SessionRepository
    ) -> None:
        limit = 5
        n_active = {s.id for s in active_sessions if s.status == SessionStatus.ACTIVE}
        assert len(n_active) >= 5
        assert await session_repo.has_reached_active_sessions_limit(user_id, limit)

    @pytest.mark.asyncio
    async def test_has_reached_limit_user_not_found(
        self, active_sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        res = await session_repo.has_reached_active_sessions_limit(uuid4(), 5)
        assert res is False

    @pytest.mark.asyncio
    async def test_free_active_sessions_limit_success(
        self, active_sessions: list[Session], user_id: UUID, session_repo: SessionRepository
    ) -> None:
        limit = 5
        n_active = {s.id for s in active_sessions if s.status == SessionStatus.ACTIVE}
        assert len(n_active) >= 5
        assert await session_repo.has_reached_active_sessions_limit(user_id, limit)
        await session_repo.free_active_sessions_limit(user_id, limit)
        assert not await session_repo.has_reached_active_sessions_limit(user_id, limit)

    @pytest.mark.asyncio
    async def test_free_active_session_limit_not_reached(
        self, active_sessions: list[Session], user_id: UUID, session_repo: SessionRepository
    ) -> None:
        limit = 7
        n_active = {s.id for s in active_sessions if s.status == SessionStatus.ACTIVE}
        get_active = await session_repo.count_active_sessions_per_user(user_id)
        assert len(n_active) == get_active
        assert not await session_repo.has_reached_active_sessions_limit(user_id, limit)
        await session_repo.free_active_sessions_limit(user_id, limit)
        new_get_active = await session_repo.count_active_sessions_per_user(user_id)
        assert get_active == new_get_active

    @pytest.mark.asyncio
    async def test_free_active_session_user_not_found(
        self, user_id: UUID, active_sessions: list[Session], session_repo: SessionRepository
    ) -> None:
        await session_repo.free_active_sessions_limit(uuid4(), 3)
        get_active = await session_repo.get_active_by_user_id(user_id)
        assert get_active is not None
        assert len(get_active) == len(active_sessions)
        assert {s.id for s in active_sessions} == {s.id for s in get_active}
