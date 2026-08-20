"""Tests for current runtime configuration and production safety guards."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_allows_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "development"
    assert settings.DEBUG is True
    assert settings.SESSION_COOKIE_SECURE is False
    assert settings.cors_origin_regex is not None
    assert re.fullmatch(settings.cors_origin_regex, "http://127.0.0.1:5174")
    assert re.fullmatch(settings.cors_origin_regex, "http://localhost:4173")
    assert not re.fullmatch(settings.cors_origin_regex, "https://example.test")


def test_dashscope_credentials_use_the_platform_environment_name() -> None:
    settings = Settings(_env_file=None, DASHSCOPE_API_KEY="test-key")

    assert settings.DASHSCOPE_API_KEY is not None
    assert settings.DASHSCOPE_API_KEY.get_secret_value() == "test-key"
    assert settings.DASHSCOPE_MODEL == "qwen3.8-max"
    assert settings.DASHSCOPE_EXPLICIT_MODEL_REVISION is None
    assert settings.DASHSCOPE_MAX_RETRIES == 2
    assert settings.MODEL_EXECUTION_LEASE_GRACE_SECONDS == 30.0


def test_dashscope_placeholder_credentials_fail_closed() -> None:
    settings = Settings(_env_file=None, DASHSCOPE_API_KEY="replace_me")

    assert settings.DASHSCOPE_API_KEY is None


def test_dashscope_retry_budget_is_bounded() -> None:
    with pytest.raises(ValidationError, match="DASHSCOPE_MAX_RETRIES"):
        Settings(_env_file=None, DASHSCOPE_MAX_RETRIES=5)


def test_production_accepts_managed_database_url_without_postgres_password() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        DEBUG=False,
        DATABASE_URL="postgresql+psycopg://app:strong-secret@db.example:5432/xingwen",
        CORS_ORIGINS="https://astro.example",
        SESSION_COOKIE_SECURE=True,
        CURSOR_SIGNING_KEY="production-cursor-signing-key-with-high-entropy",
    )

    assert settings.APP_ENV == "production"
    assert settings.cors_origin_regex is None


def test_production_rejects_local_defaults_and_wildcard_cors() -> None:
    with pytest.raises(ValidationError) as captured:
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=True,
            DATABASE_URL=(
                "postgresql+psycopg://postgres:postgres@postgres:5432/xingwen_astro_ai"
            ),
            POSTGRES_PASSWORD="postgres",
            CORS_ORIGINS="*",
        )

    message = str(captured.value)
    assert "DEBUG must be false" in message
    assert "DATABASE_URL must not use the local default credentials" in message
    assert "POSTGRES_PASSWORD must not use the local default" in message
    assert "CORS_ORIGINS must not contain '*'" in message


def test_production_requires_database_url() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL must be configured"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=False,
            CORS_ORIGINS="https://astro.example",
        )


def test_production_requires_secure_session_cookie() -> None:
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE must be true"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg://app:secret@db.example/xingwen",
            CORS_ORIGINS="https://astro.example",
            SESSION_COOKIE_SECURE=False,
        )


def test_production_requires_non_default_cursor_signing_key() -> None:
    with pytest.raises(ValidationError, match="CURSOR_SIGNING_KEY must be changed"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg://app:secret@db.example/xingwen",
            CORS_ORIGINS="https://astro.example",
            SESSION_COOKIE_SECURE=True,
        )


@pytest.mark.parametrize("value", ("", "x", "short-placeholder"))
def test_cursor_signing_key_rejects_empty_or_short_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CURSOR_SIGNING_KEY=value)


def test_config_loads_from_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    env_example = Path(__file__).parents[3] / ".env.example"
    assert env_example.is_file()

    monkeypatch.delenv("RESEARCH_INPUT_ALLOWED_MIME_TYPES", raising=False)
    monkeypatch.delenv("URL_FETCH_ALLOWED_PROTOCOLS", raising=False)
    monkeypatch.delenv("URL_FETCH_ALLOWED_HOSTS", raising=False)
    settings = Settings(_env_file=env_example)
    assert "application/pdf" in settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES
    assert "text/csv" in settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES
    assert settings.URL_FETCH_ALLOWED_PROTOCOLS == ("https",)
    assert settings.URL_FETCH_ALLOWED_HOSTS is None


def test_default_mime_allowlist_covers_production_research_inputs() -> None:
    settings = Settings(_env_file=None)
    allowed = settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES
    for mime in (
        "application/pdf",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.apache.parquet",
        "application/fits",
        "image/fits",
        "application/json",
        "application/zip",
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/tiff",
        "image/webp",
        "text/plain",
        "text/markdown",
        "text/x-markdown",
    ):
        assert mime in allowed


def test_env_example_mime_allowlist_matches_production_coverage() -> None:
    env_example = Path(__file__).parents[3] / ".env.example"
    settings = Settings(_env_file=env_example)
    allowed = settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES
    for mime in (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.apache.parquet",
        "application/fits",
        "image/fits",
        "application/zip",
        "image/tiff",
        "text/markdown",
        "text/x-markdown",
    ):
        assert mime in allowed


def test_config_parses_csv_list_and_empty_hosts() -> None:
    settings = Settings(
        _env_file=None,
        RESEARCH_INPUT_ALLOWED_MIME_TYPES=(
            "application/pdf, text/csv , APPLICATION/PDF"
        ),
        URL_FETCH_ALLOWED_PROTOCOLS="https, HTTPs",
        URL_FETCH_ALLOWED_HOSTS="",
    )
    assert settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES == [
        "application/pdf",
        "text/csv",
    ]
    assert settings.URL_FETCH_ALLOWED_PROTOCOLS == ("https",)
    assert settings.URL_FETCH_ALLOWED_HOSTS is None
