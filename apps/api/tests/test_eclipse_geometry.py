from __future__ import annotations

from math import isfinite

import pytest

from services.scientific_skills.eclipse_geometry import (
    EclipseKind,
    compute_shadow_cone,
    compute_solar_eclipse,
    sample_shadow_boundary,
)


AU_M = 149_597_870_700.0


def _centres(*, moon_x_m: float = -384_400_000.0, moon_y_m: float = 0.0):
    return (-AU_M, 0.0, 0.0), (moon_x_m, moon_y_m, 0.0), (0.0, 0.0, 0.0)


def test_central_geometry_classifies_total_and_builds_bounded_boundaries():
    sun, moon, earth = _centres(moon_x_m=-360_000_000.0)

    result = compute_solar_eclipse(sun, moon, earth)

    assert result.kind is EclipseKind.TOTAL
    assert result.near_surface_distance_m is not None
    assert result.penumbra_radius_at_surface_m is not None
    assert result.umbra_radius_at_surface_m is not None
    assert result.umbra_radius_at_surface_m > 0
    assert result.central_latitude_degrees == pytest.approx(0.0, abs=1.0e-8)
    assert result.central_longitude_degrees == pytest.approx(180.0, abs=1.0e-8)

    penumbra = sample_shadow_boundary(result.cone, "penumbra", samples=36)
    umbra = sample_shadow_boundary(result.cone, "umbra", samples=36)
    assert len(penumbra) == 36
    assert len(umbra) == 36
    assert all(isfinite(point.latitude_degrees) for point in penumbra)
    assert all(isfinite(point.longitude_degrees) for point in umbra)
    assert all(point.shadow_radius_m > 0 for point in umbra)


def test_central_geometry_classifies_annular_after_umbra_apex():
    sun, moon, earth = _centres()

    result = compute_solar_eclipse(sun, moon, earth)

    assert result.kind is EclipseKind.ANNULAR
    assert result.umbra_radius_at_surface_m is not None
    assert result.umbra_radius_at_surface_m < 0
    assert sample_shadow_boundary(result.cone, "umbra", samples=36) == ()
    assert len(sample_shadow_boundary(result.cone, "penumbra", samples=36)) == 36


def test_off_axis_penumbra_is_partial_and_clear_miss_is_none():
    sun, moon, earth = _centres(moon_y_m=8_000_000.0)
    partial = compute_solar_eclipse(sun, moon, earth)

    assert partial.kind is EclipseKind.PARTIAL
    assert partial.near_surface_distance_m is None
    assert partial.central_latitude_degrees is None
    assert sample_shadow_boundary(partial.cone, "umbra", samples=36) == ()
    assert sample_shadow_boundary(partial.cone, "penumbra", samples=36)

    sun, moon, earth = _centres(moon_y_m=15_000_000.0)
    clear = compute_solar_eclipse(sun, moon, earth)

    assert clear.kind is EclipseKind.NONE
    assert sample_shadow_boundary(clear.cone, "penumbra", samples=36) == ()


def test_geometry_and_boundary_sampling_are_deterministic():
    centres = _centres(moon_x_m=-360_000_000.0)

    first = compute_solar_eclipse(*centres)
    second = compute_solar_eclipse(*centres)

    assert first == second
    assert sample_shadow_boundary(first.cone, "penumbra", samples=24) == sample_shadow_boundary(
        second.cone, "penumbra", samples=24
    )


@pytest.mark.parametrize(
    ("sun", "moon", "earth", "kwargs", "message"),
    [
        ((float("nan"), 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), {}, "finite"),
        ((0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 0.0), {}, "exactly three"),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), {}, "non-zero"),
        ((-AU_M, 0.0, 0.0), (-384_400_000.0, 0.0, 0.0), (0.0, 0.0, 0.0), {"sun_radius_m": 0.0}, "within"),
    ],
)
def test_invalid_inputs_fail_closed(sun, moon, earth, kwargs, message):
    with pytest.raises(ValueError, match=message):
        compute_solar_eclipse(sun, moon, earth, **kwargs)


def test_invalid_sampling_and_shadow_names_fail_closed():
    sun, moon, earth = _centres(moon_x_m=-360_000_000.0)
    cone = compute_shadow_cone(sun, moon, earth)

    with pytest.raises(ValueError, match="samples"):
        sample_shadow_boundary(cone, "penumbra", samples=3)
    with pytest.raises(ValueError, match="samples"):
        sample_shadow_boundary(cone, "penumbra", samples=361)
    with pytest.raises(ValueError, match="shadow"):
        sample_shadow_boundary(cone, "invalid")


def test_equal_radii_have_parallel_umbra_without_a_finite_apex():
    sun, moon, earth = _centres(moon_x_m=-360_000_000.0)
    cone = compute_shadow_cone(
        sun,
        moon,
        earth,
        sun_radius_m=2_000_000.0,
        moon_radius_m=2_000_000.0,
    )

    assert cone.umbra_apex_distance_m is None
    assert cone.umbra_slope == pytest.approx(0.0)
