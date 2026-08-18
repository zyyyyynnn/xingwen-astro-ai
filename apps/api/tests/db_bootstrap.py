"""Shared PostgreSQL test bootstrap for the current schema contract."""

from __future__ import annotations

from app.db.base import Base
from app.db.schema import create_current_schema
from app.db.session import create_engine_from_url


def bootstrap_current_schema(database_url: str) -> None:
    engine = create_engine_from_url(database_url)
    try:
        create_current_schema(engine)
    finally:
        engine.dispose()


def reset_current_schema(database_url: str) -> None:
    engine = create_engine_from_url(database_url)
    try:
        with engine.begin() as connection:
            Base.metadata.drop_all(connection)
        create_current_schema(engine)
    finally:
        engine.dispose()
