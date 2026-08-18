"""Shared identifiers for PostgreSQL-owned research resources."""

from typing import Annotated

from pydantic import StringConstraints


PersistedUuid = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        ),
        max_length=36,
    ),
]


__all__ = ["PersistedUuid"]
