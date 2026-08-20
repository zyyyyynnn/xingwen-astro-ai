"""Pure solar-eclipse shadow geometry adopted from the MAVIS calculator.

The reference ``calculate_eclipse`` routine combines Skyfield ephemeris
evaluation, time searching, local-observer assumptions and geometry in one
function.  This module deliberately adopts only the deterministic geometry
boundary: given Sun/Moon/Earth centres in one Earth-fixed Cartesian frame, it
constructs the penumbra and umbra cones and intersects them with a WGS-84
ellipsoid.  Ephemeris loading, time search and frame transforms remain the
responsibility of the caller.

No result from this module is Live evidence.  It is a bounded numerical
primitive that can be called by a controlled skill and then attached to a
versioned observation/artifact by the main workflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from math import (
    asin,
    atan2,
    cos,
    degrees,
    hypot,
    isfinite,
    pi,
    sin,
    sqrt,
)
from numbers import Real
from typing import Literal, TypeAlias


Vector3: TypeAlias = tuple[float, float, float]
ShadowKind: TypeAlias = Literal["penumbra", "umbra"]

WGS84_SEMI_MAJOR_M = 6_378_137.0
WGS84_SEMI_MINOR_M = 6_356_752.314245
SUN_RADIUS_M = 696_340_000.0
MOON_RADIUS_M = 1_737_400.0
_MAX_COORDINATE_M = 1.0e15
_MAX_RADIUS_M = 1.0e10
_MAX_DERIVED_DISTANCE_M = 1.0e16
_MIN_SAMPLES = 4
_MAX_SAMPLES = 360
_EPSILON_M = 1.0e-6


class EclipseKind(str, Enum):
    """Geometric solar-eclipse classification at the Earth."""

    NONE = "none"
    PARTIAL = "partial"
    TOTAL = "total"
    ANNULAR = "annular"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class ShadowCone:
    """A Sun-to-Moon shadow cone in an Earth-fixed Cartesian frame.

    ``axis_unit`` points from the Sun through the Moon, so positive
    ``distance_from_moon_m`` values are on the Earth-facing side of the Moon.
    The cone radius at distance ``x`` is ``moon_radius_m + slope * x``.
    """

    earth_center_m: Vector3
    moon_center_m: Vector3
    axis_unit: Vector3
    sun_moon_distance_m: float
    sun_radius_m: float
    moon_radius_m: float
    penumbra_slope: float
    umbra_slope: float
    umbra_apex_distance_m: float | None
    earth_semimajor_m: float
    earth_semiminor_m: float


@dataclass(frozen=True, slots=True)
class GroundTrackPoint:
    """One sampled intersection of a shadow cone with the WGS-84 surface."""

    latitude_degrees: float
    longitude_degrees: float
    distance_from_moon_m: float
    shadow_radius_m: float
    position_m: Vector3


@dataclass(frozen=True, slots=True)
class SolarEclipseGeometry:
    """Deterministic geometry result, without ephemeris or Live evidence."""

    kind: EclipseKind
    cone: ShadowCone
    angular_separation_rad: float
    sun_angular_radius_rad: float
    moon_angular_radius_rad: float
    near_surface_distance_m: float | None
    near_surface_point_m: Vector3 | None
    central_latitude_degrees: float | None
    central_longitude_degrees: float | None
    penumbra_radius_at_surface_m: float | None
    umbra_radius_at_surface_m: float | None
    umbra_apex_inside_earth: bool


def compute_shadow_cone(
    sun_position_m: Sequence[float],
    moon_position_m: Sequence[float],
    earth_center_m: Sequence[float] = (0.0, 0.0, 0.0),
    *,
    sun_radius_m: float = SUN_RADIUS_M,
    moon_radius_m: float = MOON_RADIUS_M,
    earth_semimajor_m: float = WGS84_SEMI_MAJOR_M,
    earth_semiminor_m: float = WGS84_SEMI_MINOR_M,
) -> ShadowCone:
    """Build the penumbra/umbra cones from body centres and radii.

    The formula is the finite-radius cone construction used by MAVIS:
    ``r_penumbra = R_moon + x * (R_sun + R_moon) / D`` and
    ``r_umbra = R_moon + x * (R_moon - R_sun) / D``.  A larger Sun therefore
    yields a finite umbral apex at ``D * R_moon / (R_sun - R_moon)``.
    """

    sun = _vector(sun_position_m, "sun_position_m")
    moon = _vector(moon_position_m, "moon_position_m")
    earth = _vector(earth_center_m, "earth_center_m")
    sun_radius = _positive_radius(sun_radius_m, "sun_radius_m")
    moon_radius = _positive_radius(moon_radius_m, "moon_radius_m")
    semi_major, semi_minor = _ellipsoid_axes(
        earth_semimajor_m, earth_semiminor_m
    )
    sun_to_moon = _sub(moon, sun)
    distance = _norm(sun_to_moon, "Sun-Moon distance")
    axis = _scale(sun_to_moon, 1.0 / distance)
    penumbra_slope = (sun_radius + moon_radius) / distance
    umbra_slope = (moon_radius - sun_radius) / distance
    apex = None
    if sun_radius > moon_radius:
        apex = distance * moon_radius / (sun_radius - moon_radius)
        if not isfinite(apex) or apex > _MAX_DERIVED_DISTANCE_M:
            raise ValueError("derived umbra apex exceeds the bounded distance")
    return ShadowCone(
        earth_center_m=earth,
        moon_center_m=moon,
        axis_unit=axis,
        sun_moon_distance_m=distance,
        sun_radius_m=sun_radius,
        moon_radius_m=moon_radius,
        penumbra_slope=penumbra_slope,
        umbra_slope=umbra_slope,
        umbra_apex_distance_m=apex,
        earth_semimajor_m=semi_major,
        earth_semiminor_m=semi_minor,
    )


def compute_solar_eclipse(
    sun_position_m: Sequence[float],
    moon_position_m: Sequence[float],
    earth_center_m: Sequence[float] = (0.0, 0.0, 0.0),
    *,
    sun_radius_m: float = SUN_RADIUS_M,
    moon_radius_m: float = MOON_RADIUS_M,
    earth_semimajor_m: float = WGS84_SEMI_MAJOR_M,
    earth_semiminor_m: float = WGS84_SEMI_MINOR_M,
) -> SolarEclipseGeometry:
    """Classify a solar eclipse and locate its central surface intersection.

    All positions must be Earth-fixed Cartesian metres.  The function does
    not load an ephemeris, infer a time scale, or transform ICRS coordinates.
    If the central axis misses Earth, a bounded penumbra-cone intersection
    determines whether a partial eclipse exists.
    """

    sun = _vector(sun_position_m, "sun_position_m")
    moon = _vector(moon_position_m, "moon_position_m")
    earth = _vector(earth_center_m, "earth_center_m")
    cone = compute_shadow_cone(
        sun,
        moon,
        earth,
        sun_radius_m=sun_radius_m,
        moon_radius_m=moon_radius_m,
        earth_semimajor_m=earth_semimajor_m,
        earth_semiminor_m=earth_semiminor_m,
    )

    earth_to_sun = _sub(sun, earth)
    earth_to_moon = _sub(moon, earth)
    sun_distance = _norm(earth_to_sun, "Earth-Sun distance")
    moon_distance = _norm(earth_to_moon, "Earth-Moon distance")
    sun_angular_radius = _angular_radius(sun_radius_m, sun_distance)
    moon_angular_radius = _angular_radius(moon_radius_m, moon_distance)
    angular_separation = _angle_between(earth_to_sun, earth_to_moon)

    near = _line_ellipsoid_near_intersection(cone)
    if near is None:
        penumbra_points = _sample_shadow_boundary(cone, "penumbra", 72)
        kind = EclipseKind.PARTIAL if penumbra_points else EclipseKind.NONE
        return SolarEclipseGeometry(
            kind=kind,
            cone=cone,
            angular_separation_rad=angular_separation,
            sun_angular_radius_rad=sun_angular_radius,
            moon_angular_radius_rad=moon_angular_radius,
            near_surface_distance_m=None,
            near_surface_point_m=None,
            central_latitude_degrees=None,
            central_longitude_degrees=None,
            penumbra_radius_at_surface_m=None,
            umbra_radius_at_surface_m=None,
            umbra_apex_inside_earth=False,
        )

    distance_from_moon, point = near
    penumbra_radius = _cone_radius(cone, "penumbra", distance_from_moon)
    umbra_radius = _cone_radius(cone, "umbra", distance_from_moon)
    apex_inside_earth = _apex_inside_earth(cone)
    if penumbra_radius <= _EPSILON_M:
        kind = EclipseKind.NONE
    elif umbra_radius > _EPSILON_M:
        kind = EclipseKind.HYBRID if apex_inside_earth else EclipseKind.TOTAL
    elif apex_inside_earth:
        kind = EclipseKind.HYBRID
    else:
        kind = EclipseKind.ANNULAR
    latitude, longitude = _geodetic_coordinates(
        point, cone.earth_center_m, cone.earth_semimajor_m, cone.earth_semiminor_m
    )
    return SolarEclipseGeometry(
        kind=kind,
        cone=cone,
        angular_separation_rad=angular_separation,
        sun_angular_radius_rad=sun_angular_radius,
        moon_angular_radius_rad=moon_angular_radius,
        near_surface_distance_m=distance_from_moon,
        near_surface_point_m=point,
        central_latitude_degrees=latitude,
        central_longitude_degrees=longitude,
        penumbra_radius_at_surface_m=penumbra_radius,
        umbra_radius_at_surface_m=umbra_radius,
        umbra_apex_inside_earth=apex_inside_earth,
    )


def sample_shadow_boundary(
    cone: ShadowCone,
    shadow: ShadowKind,
    *,
    samples: int = 72,
) -> tuple[GroundTrackPoint, ...]:
    """Sample a penumbra or umbra boundary on the configured Earth ellipsoid."""

    _validate_samples(samples)
    if shadow not in {"penumbra", "umbra"}:
        raise ValueError("shadow must be 'penumbra' or 'umbra'")
    return _sample_shadow_boundary(cone, shadow, samples)


def _sample_shadow_boundary(
    cone: ShadowCone, shadow: ShadowKind, samples: int
) -> tuple[GroundTrackPoint, ...]:
    basis_a, basis_b = _perpendicular_basis(cone.axis_unit)
    radius_at_moon = cone.moon_radius_m
    slope = (
        cone.penumbra_slope if shadow == "penumbra" else cone.umbra_slope
    )
    max_distance = (
        cone.umbra_apex_distance_m
        if shadow == "umbra" and cone.umbra_apex_distance_m is not None
        else None
    )
    points: list[GroundTrackPoint] = []
    for index in range(samples):
        angle = 2.0 * pi * index / samples
        transverse = _add(
            _scale(basis_a, cos(angle)), _scale(basis_b, sin(angle))
        )
        origin = _add(
            _sub(cone.moon_center_m, cone.earth_center_m),
            _scale(transverse, radius_at_moon),
        )
        direction = _add(cone.axis_unit, _scale(transverse, slope))
        for distance in _ellipsoid_line_roots(
            origin, direction, cone.earth_semimajor_m, cone.earth_semiminor_m
        ):
            if distance < -_EPSILON_M or (
                max_distance is not None and distance > max_distance + _EPSILON_M
            ):
                continue
            distance = max(0.0, distance)
            radius = radius_at_moon + slope * distance
            if radius <= _EPSILON_M:
                continue
            point = _add(
                cone.moon_center_m,
                _add(
                    _scale(cone.axis_unit, distance), _scale(transverse, radius)
                ),
            )
            latitude, longitude = _geodetic_coordinates(
                point,
                cone.earth_center_m,
                cone.earth_semimajor_m,
                cone.earth_semiminor_m,
            )
            points.append(
                GroundTrackPoint(
                    latitude_degrees=latitude,
                    longitude_degrees=longitude,
                    distance_from_moon_m=distance,
                    shadow_radius_m=radius,
                    position_m=point,
                )
            )
            break
    return tuple(points)


def _line_ellipsoid_near_intersection(
    cone: ShadowCone,
) -> tuple[float, Vector3] | None:
    origin = _sub(cone.moon_center_m, cone.earth_center_m)
    roots = _ellipsoid_line_roots(
        origin,
        cone.axis_unit,
        cone.earth_semimajor_m,
        cone.earth_semiminor_m,
    )
    candidates = [root for root in roots if root >= -_EPSILON_M]
    if not candidates:
        return None
    distance = max(0.0, min(candidates))
    point = _add(cone.moon_center_m, _scale(cone.axis_unit, distance))
    return distance, point


def _ellipsoid_line_roots(
    origin: Vector3,
    direction: Vector3,
    semi_major: float,
    semi_minor: float,
) -> tuple[float, ...]:
    inv_a2 = 1.0 / (semi_major * semi_major)
    inv_b2 = 1.0 / (semi_minor * semi_minor)
    a = (direction[0] ** 2 + direction[1] ** 2) * inv_a2
    a += direction[2] ** 2 * inv_b2
    b = 2.0 * (
        (origin[0] * direction[0] + origin[1] * direction[1]) * inv_a2
        + origin[2] * direction[2] * inv_b2
    )
    c = (origin[0] ** 2 + origin[1] ** 2) * inv_a2
    c += origin[2] ** 2 * inv_b2 - 1.0
    if a <= 0.0 or not all(isfinite(value) for value in (a, b, c)):
        return ()
    discriminant = b * b - 4.0 * a * c
    tolerance = 1.0e-14 * max(abs(b * b), abs(4.0 * a * c), 1.0)
    if discriminant < -tolerance:
        return ()
    root = sqrt(max(0.0, discriminant))
    first = (-b - root) / (2.0 * a)
    second = (-b + root) / (2.0 * a)
    return (first, second) if first <= second else (second, first)


def _apex_inside_earth(cone: ShadowCone) -> bool:
    apex = cone.umbra_apex_distance_m
    if apex is None:
        return False
    position = _add(
        _sub(cone.moon_center_m, cone.earth_center_m),
        _scale(cone.axis_unit, apex),
    )
    return _ellipsoid_level(
        position, cone.earth_semimajor_m, cone.earth_semiminor_m
    ) < 1.0


def _ellipsoid_level(position: Vector3, semi_major: float, semi_minor: float) -> float:
    return (position[0] ** 2 + position[1] ** 2) / (semi_major**2) + (
        position[2] ** 2 / semi_minor**2
    )


def _cone_radius(cone: ShadowCone, shadow: ShadowKind, distance: float) -> float:
    slope = cone.penumbra_slope if shadow == "penumbra" else cone.umbra_slope
    return cone.moon_radius_m + slope * distance


def _angular_radius(radius: float, distance: float) -> float:
    ratio = min(1.0, max(0.0, radius / distance))
    return asin(ratio)


def _angle_between(first: Vector3, second: Vector3) -> float:
    denominator = _norm(first, "first angle vector") * _norm(
        second, "second angle vector"
    )
    cosine = _dot(first, second) / denominator
    return acos_clamped(cosine)


def acos_clamped(value: float) -> float:
    """Return ``acos(value)`` after bounded floating-point clamping."""

    from math import acos

    if not isfinite(value):
        raise ValueError("angle cosine must be finite")
    return acos(min(1.0, max(-1.0, value)))


def _geodetic_coordinates(
    point: Vector3,
    earth_center: Vector3,
    semi_major: float,
    semi_minor: float,
) -> tuple[float, float]:
    x, y, z = _sub(point, earth_center)
    longitude = atan2(y, x)
    horizontal = hypot(x, y)
    if horizontal <= _EPSILON_M:
        latitude = pi / 2.0 if z >= 0.0 else -pi / 2.0
    else:
        eccentricity_squared = 1.0 - (semi_minor**2 / semi_major**2)
        second_eccentricity_squared = (
            semi_major**2 - semi_minor**2
        ) / semi_minor**2
        parametric = atan2(z * semi_major, horizontal * semi_minor)
        latitude = atan2(
            z + second_eccentricity_squared * semi_minor * sin(parametric) ** 3,
            horizontal - eccentricity_squared * semi_major * cos(parametric) ** 3,
        )
    return degrees(latitude), _normalize_longitude(degrees(longitude))


def _normalize_longitude(value: float) -> float:
    normalized = (value + 180.0) % 360.0 - 180.0
    return 180.0 if normalized == -180.0 else normalized


def _perpendicular_basis(axis: Vector3) -> tuple[Vector3, Vector3]:
    references = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    reference = min(references, key=lambda item: abs(_dot(axis, item)))
    first = _normalize(_cross(axis, reference), "transverse basis")
    second = _normalize(_cross(axis, first), "transverse basis")
    return first, second


def _vector(value: Sequence[float], name: str) -> Vector3:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a three-element numeric sequence")
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values")
    result: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, Real):
            raise ValueError(f"{name} must contain only numeric values")
        normalized = float(component)
        if not isfinite(normalized) or abs(normalized) > _MAX_COORDINATE_M:
            raise ValueError(f"{name} contains a non-finite or unbounded value")
        result.append(normalized)
    return result[0], result[1], result[2]


def _positive_radius(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be numeric")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 < normalized <= _MAX_RADIUS_M:
        raise ValueError(f"{name} must be finite and within (0, {_MAX_RADIUS_M:g}]")
    return normalized


def _ellipsoid_axes(semi_major: float, semi_minor: float) -> tuple[float, float]:
    major = _positive_radius(semi_major, "earth_semimajor_m")
    minor = _positive_radius(semi_minor, "earth_semiminor_m")
    if minor > major:
        raise ValueError("earth_semiminor_m cannot exceed earth_semimajor_m")
    return major, minor


def _validate_samples(samples: int) -> None:
    if isinstance(samples, bool) or not isinstance(samples, int):
        raise ValueError("samples must be an integer")
    if not _MIN_SAMPLES <= samples <= _MAX_SAMPLES:
        raise ValueError(f"samples must be within [{_MIN_SAMPLES}, {_MAX_SAMPLES}]")


def _norm(value: Vector3, name: str) -> float:
    result = sqrt(_dot(value, value))
    if not isfinite(result) or result <= _EPSILON_M:
        raise ValueError(f"{name} must be finite and non-zero")
    return result


def _normalize(value: Vector3, name: str) -> Vector3:
    return _scale(value, 1.0 / _norm(value, name))


def _dot(first: Vector3, second: Vector3) -> float:
    return first[0] * second[0] + first[1] * second[1] + first[2] * second[2]


def _cross(first: Vector3, second: Vector3) -> Vector3:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _add(first: Vector3, second: Vector3) -> Vector3:
    return first[0] + second[0], first[1] + second[1], first[2] + second[2]


def _sub(first: Vector3, second: Vector3) -> Vector3:
    return first[0] - second[0], first[1] - second[1], first[2] - second[2]


def _scale(value: Vector3, factor: float) -> Vector3:
    return value[0] * factor, value[1] * factor, value[2] * factor


__all__ = [
    "EclipseKind",
    "GroundTrackPoint",
    "MOON_RADIUS_M",
    "SUN_RADIUS_M",
    "SolarEclipseGeometry",
    "ShadowCone",
    "WGS84_SEMI_MAJOR_M",
    "WGS84_SEMI_MINOR_M",
    "compute_shadow_cone",
    "compute_solar_eclipse",
    "sample_shadow_boundary",
]
