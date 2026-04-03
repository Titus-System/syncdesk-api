from abc import ABC, abstractmethod

from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams


class EmailStrategy(ABC):
    @abstractmethod
    async def send_welcome_email(self, to: str, email_params: WelcomeEmailParams) -> None:
        pass

    @abstractmethod
    async def send_reset_email(self, to: str, email_params: ResetPasswordEmailParams) -> None:
        pass
