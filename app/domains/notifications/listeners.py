from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import PasswordResetEventSchema, WelcomeInviteEventSchema
from app.core.logger import get_logger
from app.db.postgres.engine import async_session
from app.domains.notifications.repositories.email_outbox_repository import EmailOutboxRepository
from app.domains.notifications.services.email_outbox_service import EmailOutboxService

logger = get_logger("app.notifications.listener")


class EmailOutboxListener:
    @event_handler(WelcomeInviteEventSchema)
    async def on_welcome_invite(self, schema: WelcomeInviteEventSchema) -> None:
        async with async_session() as db:
            service = EmailOutboxService(EmailOutboxRepository(db))
            await service.enqueue_welcome_invite(schema)
            await db.commit()

    @event_handler(PasswordResetEventSchema)
    async def on_password_reset(self, schema: PasswordResetEventSchema) -> None:
        async with async_session() as db:
            service = EmailOutboxService(EmailOutboxRepository(db))
            await service.enqueue_password_reset(schema)
            await db.commit()


def register_email_outbox_listener(dispatcher: EventDispatcher) -> None:
    listener = EmailOutboxListener()
    dispatcher.subscribe(AppEvent.USER_WELCOME_INVITE, listener.on_welcome_invite)
    dispatcher.subscribe(AppEvent.USER_PASSWORD_RESET, listener.on_password_reset)
