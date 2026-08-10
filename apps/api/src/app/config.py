from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_MIME_PATTERN = re.compile(r"^[a-zA-Z0-9!#$&^_\-\.\+]+/[a-zA-Z0-9!#$&^_\-\.\+]+$")


def _parse_csv_list(value: Any) -> list[str]:  # noqa: ANN401
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class Settings(BaseSettings):
    """Configuration consumed by the current API runtime only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_ENV: str = "development"
    DEBUG: bool = True
    APP_TITLE: str = "星文智析 API"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    SESSION_COOKIE_NAME: str = "xingwen_session"
    SESSION_TTL_SECONDS: int = Field(default=86400, gt=0)
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: str = "lax"
    SESSION_CREATE_RATE_LIMIT: int = Field(default=30, gt=0)
    SHARE_CREATE_RATE_LIMIT: int = Field(default=20, gt=0)
    CURSOR_SIGNING_KEY: SecretStr = Field(
        default=SecretStr("development-only-cursor-signing-key"),
        min_length=32,
    )

    DATABASE_URL: SecretStr | None = None
    POSTGRES_PASSWORD: SecretStr | None = None

    # Research Input ingestion. The content-addressed local store is the
    # reference boundary; uploads are capped, MIME-sniffed and never executed.
    RESEARCH_INPUT_MAX_SIZE_BYTES: int = Field(default=26214400, gt=0)
    RESEARCH_INPUT_ALLOWED_MIME_TYPES: list[str] | str = Field(
        default=[
            "application/pdf",
            "text/csv",
            "application/json",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "text/plain",
        ],
        description="Allowed MIME types for research input ingestion.",
    )
    RESEARCH_INPUT_UPLOAD_DIR: Path = Path(".data/research-inputs")
    RESEARCH_INPUT_RATE_LIMIT: int = Field(default=30, gt=0)
    RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS: int = Field(default=300, gt=0)

    # URL fetch is part of Research Input ingestion. Defaults are fail-closed:
    # HTTPS only and no external host until an allowlist is configured.
    URL_FETCH_ALLOWED_PROTOCOLS: tuple[str, ...] | str = Field(
        default=("https",),
        description="Allowed protocols for url_fetch ingestion.",
    )
    URL_FETCH_ALLOWED_HOSTS: tuple[str, ...] | str | None = Field(
        default=None,
        description="Allowed host domains/IPs for url_fetch ingestion.",
    )
    URL_FETCH_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0)
    URL_FETCH_MAX_REDIRECTS: int = Field(default=3, ge=0)
    URL_FETCH_MAX_RESPONSE_BYTES: int = Field(default=26214400, gt=0)

    @field_validator("RESEARCH_INPUT_ALLOWED_MIME_TYPES", mode="before")
    @classmethod
    def _validate_mime_types(cls, value: Any) -> list[str]:  # noqa: ANN401
        parsed = _parse_csv_list(value)
        if not parsed:
            raise ValueError("RESEARCH_INPUT_ALLOWED_MIME_TYPES must not be empty")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in parsed:
            lowered = item.lower()
            if not _MIME_PATTERN.match(lowered):
                raise ValueError(f"Invalid MIME type format: {item!r}")
            if lowered not in seen:
                seen.add(lowered)
                normalized.append(lowered)
        return normalized

    @field_validator("URL_FETCH_ALLOWED_PROTOCOLS", mode="before")
    @classmethod
    def _validate_protocols(cls, value: Any) -> tuple[str, ...]:  # noqa: ANN401
        parsed = _parse_csv_list(value)
        normalized: list[str] = []
        seen: set[str] = set()
        for item in parsed:
            lowered = item.lower()
            if lowered not in seen:
                seen.add(lowered)
                normalized.append(lowered)
        return tuple(normalized)

    @field_validator("URL_FETCH_ALLOWED_HOSTS", mode="before")
    @classmethod
    def _validate_allowed_hosts(cls, value: Any) -> list[str] | None:  # noqa: ANN401
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
            return None
        parsed = _parse_csv_list(value)
        if not parsed:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for item in parsed:
            lowered = item.lower()
            if lowered not in seen:
                seen.add(lowered)
                normalized.append(lowered)
        return normalized

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.URL_FETCH_MAX_RESPONSE_BYTES > self.RESEARCH_INPUT_MAX_SIZE_BYTES:
            raise ValueError(
                "URL_FETCH_MAX_RESPONSE_BYTES must not exceed RESEARCH_INPUT_MAX_SIZE_BYTES"
            )
        lease = self.RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS
        url_budget = self.URL_FETCH_TIMEOUT_SECONDS * (self.URL_FETCH_MAX_REDIRECTS + 1)
        if lease <= url_budget:
            raise ValueError(
                "RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS must exceed "
                "URL_FETCH_TIMEOUT_SECONDS * (URL_FETCH_MAX_REDIRECTS + 1)"
            )
        if self.SESSION_COOKIE_SAMESITE.lower() not in {"lax", "strict", "none"}:
            raise ValueError("SESSION_COOKIE_SAMESITE must be lax, strict, or none")
        if self.APP_ENV.lower() != "production":
            return self

        errors: list[str] = []
        database_url = self._secret_value(self.DATABASE_URL)
        postgres_password = self._secret_value(self.POSTGRES_PASSWORD)
        cors_origins = {origin.strip() for origin in self.CORS_ORIGINS.split(",")}

        if self.DEBUG:
            errors.append("DEBUG must be false in production")
        if not database_url:
            errors.append("DATABASE_URL must be configured in production")
        elif "://postgres:postgres@" in database_url:
            errors.append("DATABASE_URL must not use the local default credentials")
        if postgres_password == "postgres":
            errors.append("POSTGRES_PASSWORD must not use the local default")
        if "*" in cors_origins:
            errors.append("CORS_ORIGINS must not contain '*' in production")
        if not self.SESSION_COOKIE_SECURE:
            errors.append("SESSION_COOKIE_SECURE must be true in production")
        cursor_signing_key = self._secret_value(self.CURSOR_SIGNING_KEY)
        if cursor_signing_key.lower() in {
            "development-only-cursor-signing-key",
            "change_me_change_me_change_me_change_me",
            "replace_me_replace_me_replace_me_replace_me",
        }:
            errors.append("CURSOR_SIGNING_KEY must be changed in production")

        allowed_protocols = {
            protocol.strip().lower() for protocol in self.URL_FETCH_ALLOWED_PROTOCOLS
        }
        if allowed_protocols - {"https"}:
            errors.append("URL_FETCH_ALLOWED_PROTOCOLS must be https-only in production")
        if not self.RESEARCH_INPUT_ALLOWED_MIME_TYPES:
            errors.append("RESEARCH_INPUT_ALLOWED_MIME_TYPES must not be empty")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @staticmethod
    def _secret_value(value: SecretStr | None) -> str:
        return value.get_secret_value().strip() if value is not None else ""


settings = Settings()
