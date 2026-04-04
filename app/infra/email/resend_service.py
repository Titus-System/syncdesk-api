import asyncio

import httpx
import resend
from resend.exceptions import ResendError

from app.core.config import get_settings
from app.core.email import EmailStrategy, ResetPasswordEmailParams
from app.core.email.renderer import render_password_reset_email, render_welcome_email
from app.core.email.schemas import WelcomeEmailParams
from app.core.logger import get_logger

settings = get_settings()

MAX_RETRIES = 3
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class ResendEmailService(EmailStrategy):
    def __init__(self) -> None:
        resend.api_key = settings.RESEND_API_KEY
        self.from_email = settings.RESEND_FROM_EMAIL
        self.logger = get_logger()

    async def _send(self, to: str, subject: str, html: str) -> None:
        last_error: Exception = RuntimeError("Email send failed before exception capture")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await resend.Emails.send_async(
                    {
                        "from": self.from_email,
                        "to": to,
                        "subject": subject,
                        "html": html,
                    }
                )
                return

            except httpx.TimeoutException as e:
                reason = "timeout"
                last_error = e

            except httpx.RequestError as e:
                reason = "network"
                last_error = e

            except ResendError as e:
                status = getattr(e, "status_code", None)

                if status in RETRY_STATUS_CODES:
                    reason = f"resend_{status}"
                    last_error = e
                else:
                    self.logger.error(
                        "Non-retryable resend error",
                        extra={"to": to, "status": status},
                        exc_info=e,
                    )
                    raise

            if attempt == MAX_RETRIES:
                self.logger.error(
                    "Email failed after retries",
                    extra={"to": to, "attempts": attempt, "reason": reason},
                    exc_info=(type(last_error), last_error, last_error.__traceback__),
                )
                raise last_error

            self.logger.warning(
                "Retrying email send",
                extra={"to": to, "attempt": attempt, "reason": reason},
            )

            await asyncio.sleep(2**attempt)

    async def send_reset_email(self, to: str, email_params: ResetPasswordEmailParams) -> None:
        await self._send(to, "Reset Your Password", render_password_reset_email(email_params))

    async def send_welcome_email(self, to: str, email_params: WelcomeEmailParams) -> None:
        await self._send(to, "Welcome to SyncDesk!", render_welcome_email(email_params))
