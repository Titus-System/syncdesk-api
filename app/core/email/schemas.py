from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import get_settings

settings = get_settings()


class ResetPasswordEmailParams(BaseModel):
    user_email: str
    reset_url: str
    expiry_minutes: int = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    year: int | None = Field(default_factory=lambda: datetime.now().year)
    support_email: str | None = "support@syncdesk.pro"


class WelcomeEmailParams(BaseModel):
    user_name: str
    user_email: str
    one_time_password: str
    login_url: str
    support_email: str | None = "support@syncdesk.pro"
    expiry_minutes: int = settings.INVITE_TOKEN_EXPIRE_HOURS * 60
    year: int = Field(default_factory=lambda: datetime.now().year)
