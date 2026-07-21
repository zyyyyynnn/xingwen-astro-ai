"""Engine and Unit-of-Work session factories."""

from collections.abc import Callable

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(database_url, echo=echo, hide_parameters=True, pool_pre_ping=True)


def session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
