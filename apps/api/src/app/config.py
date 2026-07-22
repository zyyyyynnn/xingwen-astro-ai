"""Application configuration with production safety guards."""

from __future__ import annotations

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_ENV: str = "development"
    DEBUG: bool = True
    APP_TITLE: str = "星文智析 API"
    APP_VERSION: str = "0.1.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    SESSION_COOKIE_NAME: str = "xingwen_session"
    SESSION_TTL_SECONDS: int = Field(default=86400, gt=0)
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_CREATE_RATE_LIMIT: int = Field(default=30, gt=0)
    SHARE_CREATE_RATE_LIMIT: int = Field(default=20, gt=0)
    PERSISTENT_WORKFLOW_ENABLED: bool = False

    DATABASE_URL: SecretStr | None = None
    POSTGRES_PASSWORD: SecretStr | None = None
    DASHSCOPE_API_KEY: SecretStr | None = None
    PAPER_SOURCE_API_KEY: SecretStr | None = None

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.SESSION_COOKIE_SAMESITE.lower() not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
        if self.APP_ENV.lower() != "production":
            return self

        errors: list[str] = []
        database_url = self._secret_value(self.DATABASE_URL)
        postgres_password = self._secret_value(self.POSTGRES_PASSWORD)
        dashscope_api_key = self._secret_value(self.DASHSCOPE_API_KEY)
        cors_origins = {origin.strip() for origin in self.CORS_ORIGINS.split(",")}

        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if not database_url:
            errors.append("DATABASE_URL must be configured in production")
        elif "://postgres:postgres@" in database_url:
            errors.append("DATABASE_URL must not use the local default credentials")
        if postgres_password == "postgres":
            errors.append("POSTGRES_PASSWORD must not use the local default")
        if dashscope_api_key in {"", "replace_me"}:
            errors.append("DASHSCOPE_API_KEY must be configured")
        if "*" in cors_origins:
            errors.append("CORS_ORIGINS must not contain '*' in production")
        if not self.SESSION_COOKIE_SECURE:
            errors.append("SESSION_COOKIE_SECURE must be true in production")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        return value.get_secret_value().strip() if value is not None else ""


settings = Settings()
