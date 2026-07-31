"""Deterministic identifier and ICRS coordinate normalization."""

from __future__ import annotations

import math
import re

from app.schemas.crossmatch import SkyCoordinate
from app.schemas.crossmatch import (
    angular_separation_arcsec as angular_separation_arcsec,
)
from app.schemas.crossmatch import (
    normalize_crossmatch_name as _normalize_crossmatch_name,
)
from app.schemas.crossmatch import (
    normalize_crossmatch_toi_id as _normalize_crossmatch_toi_id,
)


_TIC_IDENTIFIER = re.compile(r"^(?:tic\s*)?([0-9]+)$", re.IGNORECASE)
_GAIA_DR3_IDENTIFIER = re.compile(
    r"^(?:gaia\s*dr3\s*)?([0-9]+)$",
    re.IGNORECASE,
)
_MAX_CATALOG_IDENTIFIER_DIGITS = 19


def normalize_toi_id(value: object) -> str:
    return _normalize_crossmatch_toi_id(value)


def normalize_name(value: object) -> str:
    return _normalize_crossmatch_name(value)


def normalize_tic_id(value: object) -> str:
    return _normalize_catalog_identifier(value, _TIC_IDENTIFIER, "TIC")


def normalize_gaia_dr3_id(value: object) -> str:
    return _normalize_catalog_identifier(
        value,
        _GAIA_DR3_IDENTIFIER,
        "Gaia DR3",
    )


def normalize_sky_coordinate(
    right_ascension: object,
    declination: object,
) -> SkyCoordinate:
    ra = _finite_float(right_ascension, "right ascension")
    dec = _finite_float(declination, "declination")
    if ra < 0 or ra > 360:
        raise ValueError("right ascension must be within [0, 360]")
    if dec < -90 or dec > 90:
        raise ValueError("declination must be within [-90, 90]")
    return SkyCoordinate(
        right_ascension=0.0 if ra == 360 else ra,
        declination=dec,
    )


def _normalize_catalog_identifier(
    value: object,
    pattern: re.Pattern[str],
    prefix: str,
) -> str:
    if isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError(f"{prefix} identifier must be a string or integer")
    normalized = " ".join(str(value).strip().split())
    match = pattern.fullmatch(normalized)
    if (
        match is None
        or int(match.group(1)) == 0
        or len(match.group(1)) > _MAX_CATALOG_IDENTIFIER_DIGITS
    ):
        if match is not None and len(match.group(1)) > _MAX_CATALOG_IDENTIFIER_DIGITS:
            raise ValueError(f"{prefix} identifier exceeds frozen length boundary")
        raise ValueError(f"invalid {prefix} identifier")
    return f"{prefix} {int(match.group(1))}"


def _finite_float(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be numeric") from None
    if not math.isfinite(normalized):
        raise ValueError(f"{label} must be finite")
    return normalized
