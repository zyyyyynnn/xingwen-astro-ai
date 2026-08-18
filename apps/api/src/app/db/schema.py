"""Bootstrap the current PostgreSQL schema directly from SQLAlchemy models."""

from __future__ import annotations

import os

from sqlalchemy import Engine

from app.db.base import Base
from app.db.postgres_invariants import install_postgres_invariants
from app.db.session import create_engine_from_url

# Importing the models registers every current table with Base.metadata.
from app.db import models as _models  # noqa: F401


def create_current_schema(engine: Engine) -> None:
    """Create the current schema and install its PostgreSQL invariants."""

    with engine.begin() as connection:
        Base.metadata.create_all(connection)
        install_postgres_invariants(connection)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to bootstrap the current schema")
    engine = create_engine_from_url(database_url)
    try:
        create_current_schema(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
