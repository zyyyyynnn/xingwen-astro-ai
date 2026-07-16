"""Application configuration with production safety guards."""

from __future__ import annotations

from pydantic import SecretStr, model_validator
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

    DATABASE_URL: SecretStr | None = None
    POSTGRES_PASSWORD: SecretStr | None = None
    DASHSCOPE_API_KEY: SecretStr | None = None
    PAPER_SOURCE_API_KEY: SecretStr | None = None

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.APP_ENV.lower() != "production":
            return self

        errors: list[str] = []
        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if self._secret_value(self.POSTGRES_PASSWORD) in {"", "postgres"}:
            errors.append("POSTGRES_PASSWORD must override the local default")
        if self._secret_value(self.DASHSCOPE_API_KEY) in {"", "replace_me"}:
            errors.append("DASHSCOPE_API_KEY must be configured")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        return value.get_secret_value().strip() if value is not None else ""


settings = Settings()
