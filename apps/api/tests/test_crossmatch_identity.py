from __future__ import annotations

import math

import pytest

from services.data_pipeline.crossmatch.identity import (
    angular_separation_arcsec,
    normalize_gaia_dr3_id,
    normalize_name,
    normalize_sky_coordinate,
    normalize_tic_id,
    normalize_toi_id,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (123, "TIC 123"),
        ("123", "TIC 123"),
        (" tic 000123 ", "TIC 123"),
    ],
)
def test_tic_identifier_normalization_is_deterministic(
    raw_value: str | int,
    expected: str,
) -> None:
    assert normalize_tic_id(raw_value) == expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (456, "Gaia DR3 456"),
        ("456", "Gaia DR3 456"),
        (" Gaia DR3 000456 ", "Gaia DR3 456"),
    ],
)
def test_gaia_identifier_normalization_is_deterministic(
    raw_value: str | int,
    expected: str,
) -> None:
    assert normalize_gaia_dr3_id(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    ["", "TIC", "TIC -1", "1.5", 0, -1, float("nan"), float("inf")],
)
def test_identifier_normalization_rejects_invalid_values(raw_value: object) -> None:
    with pytest.raises(ValueError):
        normalize_tic_id(raw_value)


def test_tic_identifier_rejects_values_beyond_frozen_length_boundary() -> None:
    with pytest.raises(ValueError, match="length"):
        normalize_tic_id("1" * 20)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1243.01", "1243.01"),
        ("TOI 1243.01", "1243.01"),
        ("toi-1243.01", "1243.01"),
        (" TOI   001243.01 ", "1243.01"),
    ],
)
def test_toi_identifier_normalization_preserves_candidate_number(
    raw_value: str,
    expected: str,
) -> None:
    assert normalize_toi_id(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    [
        "",
        "TOI",
        "TOI-0.01",
        "TOI 1243 b",
        "TOI 1243.01 OR 1=1",
        "TOI 1243.01, TOI 1244.01",
    ],
)
def test_toi_identifier_normalization_rejects_unverified_forms(
    raw_value: object,
) -> None:
    with pytest.raises(ValueError):
        normalize_toi_id(raw_value)


def test_name_normalization_uses_unicode_nfkc_whitespace_and_casefold() -> None:
    assert normalize_name("  ＴＯＩ\u30001243.01  ") == "toi 1243.01"


def test_coordinate_normalization_handles_ra_wrap_and_boundaries() -> None:
    wrapped = normalize_sky_coordinate(360.0, -90.0)
    origin = normalize_sky_coordinate(0.0, 90.0)

    assert wrapped.right_ascension == 0.0
    assert wrapped.declination == -90.0
    assert origin.right_ascension == 0.0
    assert origin.declination == 90.0


@pytest.mark.parametrize(
    ("right_ascension", "declination"),
    [
        (-0.001, 0.0),
        (360.001, 0.0),
        (0.0, -90.001),
        (0.0, 90.001),
        (float("nan"), 0.0),
        (0.0, float("inf")),
    ],
)
def test_coordinate_normalization_rejects_invalid_ranges(
    right_ascension: float,
    declination: float,
) -> None:
    with pytest.raises(ValueError):
        normalize_sky_coordinate(right_ascension, declination)


def test_angular_separation_handles_wrap_poles_and_zero_distance() -> None:
    first = normalize_sky_coordinate(359.999, 0.0)
    second = normalize_sky_coordinate(0.001, 0.0)
    north_a = normalize_sky_coordinate(0.0, 90.0)
    north_b = normalize_sky_coordinate(180.0, 90.0)

    assert angular_separation_arcsec(first, first) == 0.0
    assert angular_separation_arcsec(first, second) == pytest.approx(7.2, abs=1e-6)
    assert angular_separation_arcsec(north_a, north_b) == pytest.approx(
        0.0,
        abs=1e-6,
    )


def test_angular_separation_threshold_boundary_is_numerically_stable() -> None:
    first = normalize_sky_coordinate(10.0, 0.0)
    second = normalize_sky_coordinate(10.0 + 1.0 / 3600.0, 0.0)

    separation = angular_separation_arcsec(first, second)

    assert math.isfinite(separation)
    assert separation == pytest.approx(1.0, abs=1e-7)
