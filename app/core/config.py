from datetime import timedelta
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "SyncDesk API"
    PROJECT_DESCRIPTION: str = "Backend e API GATEWAY para o projeto SyncDesk"
    PROJECT_VERSION: str = "0.1.0"

    @property
    def project_identifier(self) -> str:
        return self.PROJECT_NAME.lower().replace(" ", "-")

    @property
    def project_client_identifier(self) -> str:
        return self.project_identifier + "-client"

    ENVIRONMENT: str = "development"

    MOBILE_FRONTEND_URL: str = "syncdesk:/"
    WEB_FRONTEND_URL: str = "http://localhost:3000"

    # CORS settings
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = False
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    CORS_ALLOW_HEADERS: list[str] = ["Authorization", "Content-Type"]

    # Postgres settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "syncdesk_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def postgres_db_test(self) -> str:
        return f"{self.POSTGRES_DB}_test"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def test_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{self.postgres_db_test}"
        )

    @property
    def database_server_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/postgres"
        )

    MONGO_USER: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DB: str = "syncdesk_db"

    @property
    def mongo_db_test(self) -> str:
        return f"{self.MONGO_DB}_test"

    @property
    def mongo_database_url(self) -> str:
        if self.MONGO_USER and self.MONGO_PASSWORD:
            return (
                f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@"
                f"{self.MONGO_HOST}:{self.MONGO_PORT}/{self.mongo_db_test}"
            )
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}/{self.mongo_db_test}"

    @property
    def test_mongo_bd_url(self) -> str:
        if self.MONGO_USER and self.MONGO_PASSWORD:
            return (
                f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}@"
                f"{self.MONGO_HOST}:{self.MONGO_PORT}/{self.MONGO_DB}"
            )
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}/{self.mongo_db_test}"

    # JWT variables
    JWT_SECRET_KEY: str = "your_jwt_secret_key"
    ACCESS_TOKEN_SIGNING_KEY: str = "your_access_token_siging_key"
    REFRESH_TOKEN_SIGNING_KEY: str = "your_refresh_token_siging_key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60
    SESSION_EXPIRE_DAYS: int = 180
    DEFAULT_ROLE_NAME: str = "user"

    @property
    def access_token_timedelta(self) -> timedelta:
        return timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)

    @property
    def refresh_token_timedelta(self) -> timedelta:
        return timedelta(days=self.REFRESH_TOKEN_EXPIRE_DAYS)

    @property
    def session_default_timedelta(self) -> timedelta:
        return timedelta(days=self.SESSION_EXPIRE_DAYS)

    MAX_CHAT_MESSAGE_CONTENT_SIZE: int = 2000

    # Password Token variables
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    INVITE_TOKEN_EXPIRE_HOURS: int = 72

    @property
    def password_reset_token_timedelta(self) -> timedelta:
        return timedelta(minutes=self.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    
    @property
    def invite_token_timedelta(self) -> timedelta:
        return timedelta(hours=self.INVITE_TOKEN_EXPIRE_HOURS)
    
    RESET_TOKEN_HMAC_SECRET: str = "your_reset_token_hmac_secret"

    # Email (Resend)
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "no_reply@syncdesk.pro"
    RUN_RESEND_INTEGRATION_TESTS: bool = False
    RESEND_TEST_TO_EMAIL: str = ""

    model_config = SettingsConfigDict(extra="allow", env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
