from app.core.config import get_settings
from app.core.event_dispatcher.schemas import (
    PasswordResetEventSchema,
    WelcomeInviteEventSchema,
)
from app.core.logger import get_logger

from app.domains.notifications.enums import EmailEventType
from app.domains.notifications.repositories.email_outbox_repository import (
    EmailOutboxRepository,
)
from app.domains.notifications.schemas import EnqueueEmailOutboxDTO, PasswordResetPayload, WelcomeInvitePayload


class EmailOutboxService:
    def __init__(self, repo: EmailOutboxRepository) -> None:
        self.repo = repo
        self.logger = get_logger("app.notifications.outbox")

    @staticmethod
    def _resolve_frontend_url(roles: list[str]) -> str:
        settings = get_settings()
        if "agent" in roles or "admin" in roles:
            return settings.WEB_FRONTEND_URL
        return settings.MOBILE_FRONTEND_URL

    async def enqueue_welcome_invite(self, schema: WelcomeInviteEventSchema) -> None:
        payload = WelcomeInvitePayload(
            user_id=schema.user_id,
            user_name=schema.user_name,
            user_email=schema.user_email,
            one_time_password=schema.one_time_password,
            frontend_url=self._resolve_frontend_url(schema.roles),
            token=schema.raw_token,
        )
        row = await self.repo.enqueue(
            EnqueueEmailOutboxDTO(
                event_type=EmailEventType.WELCOME_INVITE,
                recipient=schema.user_email,
                payload=payload,
                max_attempts=schema.max_attempts,
            )
        )
        self.logger.info(
            "Enqueued welcome invite email",
            extra={"outbox_id": str(row.id), "user_id": str(schema.user_id)},
        )

    async def enqueue_password_reset(self, schema: PasswordResetEventSchema) -> None:
        payload = PasswordResetPayload(
            user_id=schema.user_id,
            user_email=schema.user_email,
            frontend_url=self._resolve_frontend_url(schema.roles),
            token=schema.raw_token,
        )
        row = await self.repo.enqueue(
            EnqueueEmailOutboxDTO(
                event_type=EmailEventType.PASSWORD_RESET,
                recipient=schema.user_email,
                payload=payload,
                max_attempts=schema.max_attempts,
            )
        )
        self.logger.info(
            "Enqueued password reset email",
            extra={"outbox_id": str(row.id), "user_id": str(schema.user_id)},
        )
