from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.http.schemas import SessionDeviceInfo
from app.core.security import JWTService
from app.domains.auth.enums import SessionStatus
from app.domains.auth.exceptions import SessionExpiredError, SessionNotFoundError

from ..entities import Session
from ..models import Session as SessionModel
from ..repositories.session_repository import SessionRepository
from ..schemas import CreateSessionDTO, UpdateSessionDTO


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-naive datetime (matches DB columns)."""
    return datetime.now(UTC).replace(tzinfo=None)


class SessionService:
    def __init__(
        self,
        db: AsyncSession,
        session_repo: SessionRepository,
        jwt_service: JWTService,
    ) -> None:
        self.db = db
        self.session_repo = session_repo
        self.jwt_service = jwt_service
        self.repo = session_repo
        self.max_active_sessions = 5

    async def init_session(
        self, user_id: UUID, role_names: list[str], device_info: SessionDeviceInfo | None = None
    ) -> tuple[str, str]:
        session_dto = CreateSessionDTO(
            user_id=user_id,
            role_names=role_names,
            status=SessionStatus.ACTIVE,
            expires_at=_utcnow() + get_settings().session_default_timedelta,
            device_info=device_info,
            last_used_at=_utcnow(),
        )
        session, refresh_token = await self.create(session_dto)
        access_token = self.jwt_service.create_access_token(user_id, role_names, session.id)

        return access_token, refresh_token

    async def create(self, dto: CreateSessionDTO) -> tuple[Session, str]:
        await self.repo.free_active_sessions_limit(dto.user_id, self.max_active_sessions)
        session_model = await self.repo.add(
            SessionModel(**dto.model_dump(exclude={"role_names"}, exclude_none=True))
        )
        refresh_token = self.jwt_service.create_refresh_token(
            session_model.user_id, dto.role_names, session_model.id
        )
        refresh_token_hash = self.jwt_service.hash_token(refresh_token)
        session_model.refresh_token_hash = refresh_token_hash
        await self.db.flush()
        await self.db.commit()

        device_info = SessionDeviceInfo.model_validate(session_model.device_info)
        session_entity = Session(
            id=session_model.id,
            user_id=session_model.user_id,
            refresh_token_hash=session_model.refresh_token_hash,
            status=session_model.status,
            expires_at=session_model.expires_at,
            created_at=session_model.created_at,
            device_info=device_info,
            last_used_at=session_model.last_used_at,
        )

        return session_entity, refresh_token

    async def get_all(self) -> list[Session]:
        return await self.repo.get_all()

    async def get_by_id(self, sesion_id: UUID) -> Session | None:
        return await self.repo.get_by_id(sesion_id)

    async def get_by_refresh_token_hash(self, refresh_token_hash: str) -> Session | None:
        return await self.repo.get_by_refresh_token_hash(refresh_token_hash)

    async def get_active_by_user_id(self, user_id: UUID) -> list[Session]:
        return await self.repo.get_active_by_user_id(user_id)

    async def get_by_user_id(self, user_id: UUID) -> list[Session]:
        return await self.repo.get_by_user_id(user_id)

    async def revoke(self, session_id: UUID) -> Session | None:
        return await self.repo.revoke(session_id)

    async def mark_used(self, session_id: UUID) -> Session | None:
        last_used_at = _utcnow()
        return await self.repo.update(session_id, UpdateSessionDTO(last_used_at=last_used_at))

    async def mark_expired(self, session_id: UUID) -> Session | None:
        return await self.repo.update(session_id, UpdateSessionDTO(status=SessionStatus.EXPIRED))

    async def refresh(
        self, session: Session, new_refresh_token_hash: str, time_delta: timedelta
    ) -> Session:
        if session.expires_at < _utcnow():
            raise SessionExpiredError("Session cannot be refreshed after expired.")

        update_dto = UpdateSessionDTO(
            refresh_token_hash=new_refresh_token_hash,
            status=SessionStatus.ACTIVE,
            expires_at=_utcnow() + time_delta,
            last_used_at=_utcnow(),
        )
        updated_session = await self.repo.atomic_refresh_token(
            session.id, session.refresh_token_hash, update_dto
        )
        if updated_session is None:
            raise SessionNotFoundError(
                "Session could not be refreshed. Token may have been reused."
            )
        return updated_session

    async def revoke_all_user_sessions(self, user_id: UUID) -> None:
        active_sessions = await self.repo.get_active_by_user_id(user_id)
        for session in active_sessions:
            await self.repo.revoke(session.id)
