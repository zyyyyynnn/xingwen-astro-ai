
"""Tests for production configuration guards."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_allows_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "development"
    assert settings.DEBUG is True
    assert settings.SESSION_COOKIE_SECURE is False
    assert settings.PERSISTENT_WORKFLOW_ENABLED is False


def test_persistent_workflow_requires_explicit_feature_flag() -> None:
    settings = Settings(_env_file=None, PERSISTENT_WORKFLOW_ENABLED=True)

    assert settings.PERSISTENT_WORKFLOW_ENABLED is True


def test_production_accepts_managed_database_url_without_postgres_password() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DEBUG=False,
        DATABASE_URL="postgresql+psycopg://app:strong-secret@db.example:5432/xingwen",
        DASHSCOPE_API_KEY="dashscope-secret",
        CORS_ORIGINS="https://astro.example",
        SESSION_COOKIE_SECURE=True,
    )

    assert settings.APP_ENV == "production"


def test_production_rejects_local_defaults_and_wildcard_cors() -> None:
    with pytest.raises(ValidationError) as captured:
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=True,
            DATABASE_URL=(
                "postgresql+psycopg://postgres:postgres@postgres:5432/"
                "xingwen_astro_ai"
            ),
            POSTGRES_PASSWORD="postgres",
            DASHSCOPE_API_KEY="replace_me",
            CORS_ORIGINS="*",
        )

    message = str(captured.value)
    assert "DEBUG must be false" in message
    assert "DATABASE_URL must not use the local default credentials" in message
    assert "POSTGRES_PASSWORD must not use the local default" in message
    assert "DASHSCOPE_API_KEY must be configured" in message
    assert "CORS_ORIGINS must not contain '*'" in message


def test_production_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must be configured"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=False,
            DASHSCOPE_API_KEY="dashscope-secret",
            CORS_ORIGINS="https://astro.example",
        )


def test_production_requires_secure_session_cookie() -> None:
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE must be true"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg://app:secret@db.example/xingwen",
            DASHSCOPE_API_KEY="dashscope-secret",
            CORS_ORIGINS="https://astro.example",
            SESSION_COOKIE_SECURE=False,
        )
