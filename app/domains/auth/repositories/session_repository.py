from uuid import UUID

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.decorators import require_dto
from app.core.http.schemas import SessionDeviceInfo
from app.domains.auth.enums import SessionStatus

from ..entities import Session as SessionEntity
from ..models import Session as SessionModel
from ..schemas import CreateSessionDTO, UpdateSessionDTO


class SessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @require_dto(CreateSessionDTO)
    async def create(self, dto: CreateSessionDTO) -> SessionEntity:
        insert_values = dto.model_dump(exclude={"role_names"}, exclude_none=True)
        stmt = insert(SessionModel).values(**insert_values).returning(SessionModel)
        try:
            res = await self.db.execute(stmt)
            row = res.scalar_one()
            await self.db.commit()
            return self._to_entity(row)
        except IntegrityError:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def add(self, session: SessionModel) -> SessionModel:
        self.db.add(session)
        return session

    async def get_all(self) -> list[SessionEntity]:
        stmt = select(SessionModel)
        res = await self.db.execute(stmt)
        rows = res.scalars().all()
        return [self._to_entity(row) for row in rows]

    async def get_by_id(self, id: UUID) -> SessionEntity | None:
        stmt = select(SessionModel).where(SessionModel.id == id)
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def get_by_refresh_token_hash(self, refresh_token_hash: str) -> SessionEntity | None:
        stmt = select(SessionModel).where(SessionModel.refresh_token_hash == refresh_token_hash)
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        return self._to_entity(row)

    async def get_by_user_id(self, user_id: UUID) -> list[SessionEntity]:
        stmt = select(SessionModel).where(SessionModel.user_id == user_id)
        res = await self.db.execute(stmt)
        rows = res.scalars().all()
        return [self._to_entity(row) for row in rows]

    async def get_active_by_user_id(self, user_id: UUID) -> list[SessionEntity]:
        stmt = select(SessionModel).where(
            SessionModel.user_id == user_id, SessionModel.status == SessionStatus.ACTIVE
        )
        res = await self.db.execute(stmt)
        rows = res.scalars().all()
        return [self._to_entity(row) for row in rows]

    @require_dto(UpdateSessionDTO)
    async def update(self, session_id: UUID, dto: UpdateSessionDTO) -> SessionEntity | None:
        update_values = dto.model_dump(exclude_none=True)
        if not update_values:
            return None

        distinct_conditions = [
            getattr(SessionModel, field).is_distinct_from(value)
            for field, value in update_values.items()
        ]

        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id, or_(*distinct_conditions))
            .values(**update_values)
            .returning(SessionModel)
        )
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            existing = await self.get_by_id(session_id)
            return existing
        await self.db.commit()
        return self._to_entity(row)

    async def revoke(self, session_id: UUID) -> SessionEntity | None:
        return await self.update(session_id, UpdateSessionDTO(status=SessionStatus.REVOKED))

    @require_dto(UpdateSessionDTO)
    async def atomic_refresh_token(
        self, session_id: UUID, old_refresh_token_hash: str, dto: UpdateSessionDTO
    ) -> SessionEntity | None:
        """
        Atomically update the session only if the current refresh_token_hash matches
        the expected old hash. Prevents race conditions where two concurrent
        requests could both use the same refresh token.
        """
        update_values = dto.model_dump(exclude_none=True)
        stmt = (
            update(SessionModel)
            .where(
                SessionModel.id == session_id,
                SessionModel.refresh_token_hash == old_refresh_token_hash,
                SessionModel.status == SessionStatus.ACTIVE,
            )
            .values(**update_values)
            .returning(SessionModel)
        )
        res = await self.db.execute(stmt)
        row = res.scalar_one_or_none()
        if row is None:
            return None
        await self.db.commit()
        return self._to_entity(row)

    async def count_active_sessions_per_user(self, user_id: UUID) -> int:
        stmt = select(func.count(SessionModel.id)).where(
            SessionModel.user_id == user_id, SessionModel.status == SessionStatus.ACTIVE
        )
        res = await self.db.execute(stmt)
        return res.scalar_one()

    async def has_reached_active_sessions_limit(self, user_id: UUID, limit: int) -> bool:
        stmt = (
            select(SessionModel.id)
            .where(SessionModel.user_id == user_id, SessionModel.status == SessionStatus.ACTIVE)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return len(rows) >= limit

    async def free_active_sessions_limit(self, user_id: UUID, limit: int) -> None:
        """
        Revokes the farthest used user session in case the limit is reached.
        Should only be called inside a transaction.
        """
        old_stmt = (
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.status == SessionStatus.ACTIVE)
            .order_by(SessionModel.last_used_at.asc())
            .offset(limit - 1)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        old_res = await self.db.execute(old_stmt)
        session_to_revoke = old_res.scalar_one_or_none()
        if session_to_revoke:
            session_to_revoke.status = SessionStatus.REVOKED
        await self.db.flush()

    def _to_entity(self, model: SessionModel) -> SessionEntity:
        device_info = SessionDeviceInfo.model_validate(model.device_info)
        return SessionEntity(
            id=model.id,
            user_id=model.user_id,
            refresh_token_hash=model.refresh_token_hash,
            status=model.status,
            expires_at=model.expires_at,
            created_at=model.created_at,
            device_info=device_info,
            last_used_at=model.last_used_at,
        )
