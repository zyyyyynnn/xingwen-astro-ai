"""Small typed parameter readers shared by bounded skill adapters."""

from __future__ import annotations

from math import isfinite
from typing import Any


def require_string(parameters: dict[str, object], key: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def optional_string(
    parameters: dict[str, object], key: str, *, default: str | None = None
) -> str | None:
    value = parameters.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def require_number(parameters: dict[str, object], key: str) -> float:
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{key} must be finite")
    return normalized


def optional_number(
    parameters: dict[str, object], key: str, *, default: float
) -> float:
    if key not in parameters:
        return default
    return require_number(parameters, key)


def optional_integer(
    parameters: dict[str, object],
    key: str,
    *,
    default: int,
    lower: int | None = None,
    upper: int | None = None,
) -> int:
    value = parameters.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be an integer")
    normalized = int(value)
    if not isfinite(float(value)) or value != normalized:
        raise ValueError(f"{key} must be an integer")
    if lower is not None and normalized < lower:
        raise ValueError(f"{key} must be at least {lower}")
    if upper is not None and normalized > upper:
        raise ValueError(f"{key} must be at most {upper}")
    return normalized


def require_rows(
    parameters: dict[str, object], *, max_rows: int
) -> tuple[dict[str, Any], ...]:
    value = parameters.get("rows")
    if not isinstance(value, list) or not value:
        raise ValueError("rows must be a non-empty array")
    if len(value) > max_rows:
        raise ValueError(f"rows exceed the {max_rows} row budget")
    result: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict) or not all(
            isinstance(key, str) and key for key in row
        ):
            raise ValueError("every row must be an object with string keys")
        result.append(dict(row))
    return tuple(result)


def require_string_list(
    parameters: dict[str, object], key: str, *, max_items: int = 256
) -> tuple[str, ...]:
    value = parameters.get(key)
    if not isinstance(value, list) or not 1 <= len(value) <= max_items:
        raise ValueError(f"{key} must contain between 1 and {max_items} strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{key} must contain only non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{key} must be unique")
    return normalized


def reject_unknown(parameters: dict[str, object], allowed: set[str]) -> None:
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"unsupported scientific skill parameters: {sorted(unknown)}")
