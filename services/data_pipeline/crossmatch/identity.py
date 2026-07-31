"""Deterministic identifier and ICRS coordinate normalization."""

from __future__ import annotations

import math
import re
import unicodedata

from app.schemas.crossmatch import SkyCoordinate


_TIC_IDENTIFIER = re.compile(r"^(?:tic\s*)?([0-9]+)$", re.IGNORECASE)
_GAIA_DR3_IDENTIFIER = re.compile(
    r"^(?:gaia\s*dr3\s*)?([0-9]+)$",
    re.IGNORECASE,
)
_TOI_IDENTIFIER = re.compile(
    r"^(?:toi(?:\s+|-)\s*)?([0-9]+)(?:\.([0-9]+))?$",
    re.IGNORECASE,
)
_MAX_CATALOG_IDENTIFIER_DIGITS = 19
_ARCSECONDS_PER_RADIAN = 180.0 * 3600.0 / math.pi


def normalize_tic_id(value: object) -> str:
    return _normalize_catalog_identifier(value, _TIC_IDENTIFIER, "TIC")


def normalize_gaia_dr3_id(value: object) -> str:
    return _normalize_catalog_identifier(
        value,
        _GAIA_DR3_IDENTIFIER,
        "Gaia DR3",
    )


def normalize_toi_id(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("TOI identifier must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    match = _TOI_IDENTIFIER.fullmatch(normalized)
    if match is None or int(match.group(1)) == 0:
        raise ValueError("invalid TOI identifier")
    candidate_number = match.group(2)
    return (
        str(int(match.group(1)))
        if candidate_number is None
        else f"{int(match.group(1))}.{candidate_number}"
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


def angular_separation_arcsec(
    left: SkyCoordinate,
    right: SkyCoordinate,
) -> float:
    left_ra = math.radians(left.right_ascension)
    right_ra = math.radians(right.right_ascension)
    left_dec = math.radians(left.declination)
    right_dec = math.radians(right.declination)
    half_dec = (right_dec - left_dec) / 2.0
    half_ra = (right_ra - left_ra) / 2.0
    haversine = (
        math.sin(half_dec) ** 2
        + math.cos(left_dec) * math.cos(right_dec) * math.sin(half_ra) ** 2
    )
    angle = 2.0 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
    return angle * _ARCSECONDS_PER_RADIAN


def normalize_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("entity name must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized:
        raise ValueError("entity name must not be blank")
    return normalized.casefold()


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
        if (
            match is not None
            and len(match.group(1)) > _MAX_CATALOG_IDENTIFIER_DIGITS
        ):
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
