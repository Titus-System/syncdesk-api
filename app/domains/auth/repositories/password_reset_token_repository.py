from uuid import UUID
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.enums import TokenPurpose

from ..entities import PasswordResetToken as PasswordResetTokenEntity
from ..models import PasswordResetToken as PasswordResetTokenModel
from ..schemas import CreatePasswordResetTokenDTO


class PasswordResetTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @require_dto(CreatePasswordResetTokenDTO)
    async def create(self, dto: CreatePasswordResetTokenDTO) -> PasswordResetTokenEntity:
        insert_values = dto.model_dump(exclude_none=True)
        stmt = (
            insert(PasswordResetTokenModel)
            .values(**insert_values)
            .returning(PasswordResetTokenModel)
        )
        try:
            result = await self.db.execute(stmt)
            row = result.scalar_one()
            await self.db.commit()
            return self._to_entity(row)
        except IntegrityError as err:
            await self.db.rollback()
            raise ResourceAlreadyExistsError(
                "PasswordResetToken", f"user_id={dto.user_id}, purpose={dto.purpose}"
            ) from err
        except Exception:
            await self.db.rollback()
            raise

    async def get_by_hash(self, token_hash: str) -> PasswordResetTokenEntity | None:
        stmt = select(PasswordResetTokenModel).where(
            PasswordResetTokenModel.token_hash == token_hash
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def consume_by_hash(self, token_hash: str) -> PasswordResetTokenEntity | None:
        query = text("""
            UPDATE password_reset_tokens
            SET used_at = now()
            WHERE token_hash = :token_hash
            AND used_at IS NULL
            AND expires_at > now()
            RETURNING *;
        """)

        result = await self.db.execute(query, {"token_hash": token_hash})
        row = result.mappings().first()

        if not row:
            return None

        await self.db.commit()

        model = PasswordResetTokenModel(**row)
        return self._to_entity(model)

    async def invalidate_user_tokens(self, user_id: UUID, purpose: TokenPurpose) -> None:
        query = text("""
            UPDATE password_reset_tokens
            SET used_at = now()
            WHERE user_id = :user_id
            AND purpose = :purpose
            AND used_at IS NULL;
        """)

        await self.db.execute(
            query,
            {"user_id": user_id, "purpose": purpose.value},
        )
        await self.db.commit()

    def _to_entity(self, model: PasswordResetTokenModel) -> PasswordResetTokenEntity:
        return PasswordResetTokenEntity(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            purpose=model.purpose,
            created_at=model.created_at,
            expires_at=model.expires_at,
            used_at=model.used_at,
        )
