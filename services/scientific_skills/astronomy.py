"""Astronomy adapters derived from MAVIS tasks without generated-code execution."""

from __future__ import annotations

from base64 import b64decode, b64encode
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from math import asin, degrees, isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator

from .parameters import (
    optional_number,
    optional_integer,
    optional_string,
    reject_unknown,
    require_number,
    require_string,
)
from .types import ScientificSkillRequest


_SOLAR_SYSTEM_TARGETS = frozenset(
    {
        "sun",
        "moon",
        "mercury",
        "venus",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
    }
)

_CELESTIAL_BODY_RADII_KM = {
    "sun": 696_340.0,
    "moon": 1_737.4,
    "mercury": 2_439.7,
    "venus": 6_051.8,
    "earth": 6_378.137,
    "mars": 3_396.2,
    "jupiter": 71_492.0,
    "saturn": 60_268.0,
    "uranus": 25_559.0,
    "neptune": 24_764.0,
    "pluto": 1_188.3,
}

_NOMINATIM_HOST = "nominatim.openstreetmap.org"
_NOMINATIM_URL = f"https://{_NOMINATIM_HOST}/search"
_MAX_LOCATION_NAME_LENGTH = 200
_MAX_GEOCODING_RESPONSE_BYTES = 256 * 1024


def get_celestial_body_radius(body_name: str) -> float:
    """Return the controlled mean radius of a supported body in kilometres."""

    if not isinstance(body_name, str) or not body_name.strip():
        raise ValueError("body_name must be non-empty text")
    normalized = body_name.strip().casefold()
    try:
        return float(_CELESTIAL_BODY_RADII_KM[normalized])
    except KeyError as error:
        supported = ", ".join(sorted(_CELESTIAL_BODY_RADII_KM))
        raise ValueError(
            f"unsupported celestial body {normalized!r}; supported bodies: {supported}"
        ) from error


def query_simbad(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(request.parameters, {"object_name", "radius_arcmin"})
    object_name = require_string(request.parameters, "object_name")
    radius_arcmin = request.parameters.get("radius_arcmin")

    from astropy import units as u
    from astroquery.simbad import Simbad

    client = Simbad()
    client.TIMEOUT = request.budget.timeout_seconds
    if radius_arcmin is None:
        table = client.query_object(object_name)
        query_kind = "object"
    else:
        radius = require_number(request.parameters, "radius_arcmin")
        if not 0 < radius <= 60:
            raise ValueError("radius_arcmin must be within (0, 60]")
        table = client.query_region(object_name, radius=radius * u.arcmin)
        query_kind = "region"
    rows = _table_rows(table, request.budget.max_output_rows)
    return {
        "service": "simbad",
        "query_kind": query_kind,
        "object_name": object_name,
        "row_count": len(rows),
        "rows": rows,
    }


def retrieve_skyview_fits(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {"position", "survey", "radius_degrees", "pixels"},
    )
    position = require_string(request.parameters, "position")
    survey = require_string(request.parameters, "survey")
    radius_degrees = optional_number(request.parameters, "radius_degrees", default=0.25)
    pixels = optional_integer(
        request.parameters, "pixels", default=512, lower=32, upper=2048
    )
    if not 0 < radius_degrees <= 5:
        raise ValueError("radius_degrees must be within (0, 5]")

    from astropy import units as u
    from astroquery.skyview import SkyView

    SkyView.TIMEOUT = request.budget.timeout_seconds
    images = SkyView.get_images(
        position=position,
        survey=[survey],
        radius=radius_degrees * u.deg,
        pixels=pixels,
    )
    documents = []
    total_size = 0
    for index, image in enumerate(images[:8]):
        buffer = BytesIO()
        image.writeto(buffer)
        content = buffer.getvalue()
        total_size += len(content)
        if total_size > request.budget.max_input_bytes:
            raise ValueError("SkyView FITS response exceeds the byte budget")
        primary = image[0]
        shape = list(primary.data.shape) if primary.data is not None else []
        digest = sha256(content).hexdigest()
        documents.append(
            {
                "document_id": f"fits.{index + 1}",
                "media_type": "application/fits",
                "content_base64": b64encode(content).decode("ascii"),
                "content_hash": f"sha256:{digest}",
                "shape": shape,
                "object": str(primary.header.get("OBJECT", position)),
                "survey": survey,
            }
        )
    return {
        "service": "skyview",
        "position": position,
        "survey": survey,
        "documents": documents,
    }


def calculate_ephemeris(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "ephemeris_base64",
            "target",
            "reference_target",
            "observed_at",
            "latitude_degrees",
            "longitude_degrees",
            "elevation_meters",
            "location_name",
        },
    )
    target_name = require_string(request.parameters, "target").casefold()
    _require_solar_system_target(target_name)
    observed_at = _parse_utc(require_string(request.parameters, "observed_at"))
    latitude, longitude, elevation, resolved_location = _observer_coordinates(request)

    reference_name = optional_string(request.parameters, "reference_target")
    if reference_name is not None:
        reference_name = reference_name.casefold()
        _require_solar_system_target(reference_name)

    from skyfield.api import wgs84
    from skyfield.framelib import ecliptic_frame
    from skyfield.magnitudelib import planetary_magnitude

    with _open_ephemeris(request) as (planets, ts):
        observer = planets["earth"] + wgs84.latlon(
            latitude, longitude, elevation_m=elevation
        )
        time = ts.from_datetime(observed_at)
        apparent = observer.at(time).observe(_planet(planets, target_name)).apparent()
        ra, dec, distance = apparent.radec()
        altitude, azimuth, _ = apparent.altaz()
        hour_angle, _, _ = apparent.hadec()
        ecliptic_latitude, ecliptic_longitude, _ = apparent.frame_latlon(ecliptic_frame)
        separation = None
        if reference_name is not None:
            reference = (
                observer.at(time).observe(_planet(planets, reference_name)).apparent()
            )
            separation = float(apparent.separation_from(reference).degrees)
        magnitude = None
        try:
            magnitude = float(planetary_magnitude(apparent))
        except ValueError:
            pass
    output: dict[str, object] = {
        "target": target_name,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "ra_hours": float(ra.hours),
        "dec_degrees": float(dec.degrees),
        "hour_angle_hours": float(hour_angle.hours),
        "ecliptic_latitude_degrees": float(ecliptic_latitude.degrees),
        "ecliptic_longitude_degrees": float(ecliptic_longitude.degrees),
        "distance_au": float(distance.au),
        "light_time_minutes": float(apparent.light_time * 24 * 60),
        "altitude_degrees": float(altitude.degrees),
        "azimuth_degrees": float(azimuth.degrees),
    }
    if magnitude is not None:
        output["apparent_magnitude"] = magnitude
    if reference_name is not None and separation is not None:
        output["reference_target"] = reference_name
        output["angular_separation_degrees"] = separation
    if resolved_location is not None:
        output["resolved_location"] = resolved_location
    return output


def find_celestial_events(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "ephemeris_base64",
            "event_type",
            "target",
            "start_at",
            "end_at",
            "latitude_degrees",
            "longitude_degrees",
            "elevation_meters",
            "location_name",
        },
    )
    event_type = optional_string(
        request.parameters, "event_type", default="rise_set_transit"
    )
    if event_type not in {
        "rise_set_transit",
        "moon_phases",
        "seasons",
        "twilight",
        "lunar_eclipses",
        "solar_eclipses",
        "venus_elongations",
        "transits",
        "occultations",
        "conjunctions_oppositions",
    }:
        raise ValueError("celestial event type is not supported")
    start_at = _parse_utc(require_string(request.parameters, "start_at"))
    end_at = _parse_utc(require_string(request.parameters, "end_at"))
    if end_at <= start_at or (end_at - start_at).total_seconds() > 3660 * 86400:
        raise ValueError("event interval must be positive and no longer than 10 years")

    observer_coordinates = None
    resolved_location = None
    if any(
        key in request.parameters
        for key in (
            "location_name",
            "latitude_degrees",
            "longitude_degrees",
            "elevation_meters",
        )
    ):
        observer_coordinates = _observer_coordinates(request)
        resolved_location = observer_coordinates[3]

    from skyfield import almanac

    with _open_ephemeris(request) as (planets, ts):
        start = ts.from_datetime(start_at)
        end = ts.from_datetime(end_at)
        if event_type == "rise_set_transit":
            target_name = require_string(request.parameters, "target").casefold()
            _require_solar_system_target(target_name)
            if observer_coordinates is None:
                observer_coordinates = _observer_coordinates(request)
                resolved_location = observer_coordinates[3]
            observer = _observer(
                planets,
                coordinates=observer_coordinates[:3],
            )
            target = _planet(planets, target_name)
            risings, rising_states = almanac.find_risings(observer, target, start, end)
            settings, setting_states = almanac.find_settings(
                observer, target, start, end
            )
            transits = almanac.find_transits(observer, target, start, end)
            events = [
                *(
                    {
                        "event": "rise",
                        "occurred_at": timestamp,
                        "crosses_horizon": bool(state),
                    }
                    for timestamp, state in zip(
                        risings.utc_iso(), rising_states, strict=True
                    )
                ),
                *(
                    {
                        "event": "set",
                        "occurred_at": timestamp,
                        "crosses_horizon": bool(state),
                    }
                    for timestamp, state in zip(
                        settings.utc_iso(), setting_states, strict=True
                    )
                ),
                *(
                    {
                        "event": "transit",
                        "occurred_at": timestamp,
                        "crosses_horizon": None,
                    }
                    for timestamp in transits.utc_iso()
                ),
            ]
        elif event_type == "twilight":
            from skyfield.api import wgs84

            if observer_coordinates is None:
                observer_coordinates = _observer_coordinates(request)
                resolved_location = observer_coordinates[3]
            latitude, longitude, elevation = observer_coordinates[:3]
            topos = wgs84.latlon(latitude, longitude, elevation_m=elevation)
            times, states = almanac.find_discrete(
                start, end, almanac.dark_twilight_day(planets, topos)
            )
            events = [
                {
                    "event": "twilight_transition",
                    "occurred_at": timestamp,
                    "state": almanac.TWILIGHTS[int(state)],
                    "state_code": int(state),
                }
                for timestamp, state in zip(times.utc_iso(), states, strict=True)
            ]
        elif event_type == "moon_phases":
            times, states = almanac.find_discrete(
                start, end, almanac.moon_phases(planets)
            )
            events = _labeled_events(times, states, almanac.MOON_PHASES)
        elif event_type == "seasons":
            times, states = almanac.find_discrete(start, end, almanac.seasons(planets))
            events = _labeled_events(times, states, almanac.SEASON_EVENTS)
        elif event_type == "lunar_eclipses":
            from skyfield.eclipselib import LUNAR_ECLIPSES, lunar_eclipses

            times, states, _details = lunar_eclipses(start, end, planets)
            events = _labeled_events(times, states, LUNAR_ECLIPSES)
        elif event_type == "solar_eclipses":
            events = _solar_eclipse_events(planets, start, end)
        elif event_type == "venus_elongations":
            if request.parameters.get("target") is not None:
                raise ValueError("venus_elongations fixes target to venus")
            events = _venus_elongation_events(planets, start, end)
        elif event_type == "transits":
            target_name = require_string(request.parameters, "target").casefold()
            events = _strict_transit_events(planets, start, end, target_name)
        elif event_type == "occultations":
            target_name = require_string(request.parameters, "target").casefold()
            events = _strict_occultation_events(planets, start, end, target_name)
        else:
            target_name = require_string(request.parameters, "target").casefold()
            if target_name in {"sun", "earth"}:
                raise ValueError(
                    "conjunction/opposition target must be a Moon or planet"
                )
            _require_solar_system_target(target_name)
            target = _planet(planets, target_name)
            times, states = almanac.find_discrete(
                start, end, almanac.oppositions_conjunctions(planets, target)
            )
            labels = (
                ("conjunction", "conjunction")
                if target_name in {"mercury", "venus", "moon"}
                else ("conjunction", "opposition")
            )
            events = _labeled_events(times, states, labels)
    events.sort(key=lambda item: str(item["occurred_at"]))
    response: dict[str, object] = {
        "event_type": event_type,
        "target": request.parameters.get("target"),
        "events": events[: request.budget.max_output_rows],
        "truncated": len(events) > request.budget.max_output_rows,
    }
    if resolved_location is not None:
        response["resolved_location"] = resolved_location
    return response


def _solar_eclipse_events(
    planets: Any, start: Any, end: Any
) -> list[dict[str, object]]:
    """Project new-moon ephemerides through the adopted MAVIS shadow geometry."""

    from skyfield import almanac
    from skyfield.framelib import itrs

    from .eclipse_geometry import (
        EclipseKind,
        compute_solar_eclipse,
        sample_shadow_boundary,
    )

    times, states = almanac.find_discrete(start, end, almanac.moon_phases(planets))
    earth = planets["earth"]
    sun = planets["sun"]
    moon = planets["moon"]
    events: list[dict[str, object]] = []
    for time, state in zip(times, states, strict=True):
        if int(state) != 0:
            continue
        earth_at_time = earth.at(time)
        sun_position = tuple(
            float(value)
            for value in earth_at_time.observe(sun).apparent().frame_xyz(itrs).m
        )
        moon_position = tuple(
            float(value)
            for value in earth_at_time.observe(moon).apparent().frame_xyz(itrs).m
        )
        geometry = compute_solar_eclipse(sun_position, moon_position)
        if geometry.kind is EclipseKind.NONE:
            continue
        penumbra = sample_shadow_boundary(geometry.cone, "penumbra", samples=72)
        umbra = sample_shadow_boundary(geometry.cone, "umbra", samples=72)
        events.append(
            {
                "event": f"solar_eclipse_{geometry.kind.value}",
                "occurred_at": time.utc_iso(),
                "eclipse_kind": geometry.kind.value,
                "angular_separation_degrees": float(
                    geometry.angular_separation_rad * 180 / 3.141592653589793
                ),
                "sun_angular_radius_degrees": float(
                    geometry.sun_angular_radius_rad * 180 / 3.141592653589793
                ),
                "moon_angular_radius_degrees": float(
                    geometry.moon_angular_radius_rad * 180 / 3.141592653589793
                ),
                "central_latitude_degrees": geometry.central_latitude_degrees,
                "central_longitude_degrees": geometry.central_longitude_degrees,
                "penumbra_radius_at_surface_m": (geometry.penumbra_radius_at_surface_m),
                "umbra_radius_at_surface_m": geometry.umbra_radius_at_surface_m,
                "umbra_apex_inside_earth": geometry.umbra_apex_inside_earth,
                "penumbra_boundary": [
                    {
                        "latitude_degrees": point.latitude_degrees,
                        "longitude_degrees": point.longitude_degrees,
                    }
                    for point in penumbra
                ],
                "umbra_boundary": [
                    {
                        "latitude_degrees": point.latitude_degrees,
                        "longitude_degrees": point.longitude_degrees,
                    }
                    for point in umbra
                ],
            }
        )
    return events


def _venus_elongation_events(
    planets: Any, start: Any, end: Any
) -> list[dict[str, object]]:
    """Find Venus greatest elongations with Skyfield's bounded maxima search."""

    from skyfield.framelib import ecliptic_frame
    from skyfield.searchlib import find_maxima

    earth = planets["earth"]
    sun = planets["sun"]
    venus = _planet(planets, "venus")

    def elongation_at(time: Any) -> Any:
        observer = earth.at(time)
        sun_apparent = observer.observe(sun).apparent()
        venus_apparent = observer.observe(venus).apparent()
        return sun_apparent.separation_from(venus_apparent).degrees

    elongation_at.step_days = 15.0
    times, elongations = find_maxima(start, end, elongation_at)
    results: list[dict[str, object]] = []
    for time, elongation in zip(times, elongations, strict=True):
        observer = earth.at(time)
        _, sun_longitude, _ = (
            observer.observe(sun).apparent().frame_latlon(ecliptic_frame)
        )
        _, venus_longitude, _ = (
            observer.observe(venus).apparent().frame_latlon(ecliptic_frame)
        )
        delta = (venus_longitude.degrees - sun_longitude.degrees) % 360.0
        elongation_degrees = float(elongation)
        if not isfinite(elongation_degrees) or not 0.0 <= elongation_degrees <= 180.0:
            raise ValueError("Skyfield returned an invalid Venus elongation")
        direction = "east" if delta < 180.0 else "west"
        results.append(
            {
                "event": "venus_greatest_elongation",
                "occurred_at": time.utc_iso(),
                "target": "venus",
                "direction": direction,
                "direction_code": 0 if direction == "east" else 1,
                "elongation_degrees": round(elongation_degrees, 1),
            }
        )
    return results


def _strict_transit_events(
    planets: Any, start: Any, end: Any, target_name: str
) -> list[dict[str, object]]:
    if target_name not in {"mercury", "venus"}:
        raise ValueError("transits target must be mercury or venus")
    return _strict_overlap_events(
        planets,
        start,
        end,
        foreground_name=target_name,
        background_name="sun",
        event_name=f"{target_name}_transit",
    )


def _strict_occultation_events(
    planets: Any, start: Any, end: Any, target_name: str
) -> list[dict[str, object]]:
    if target_name in {"sun", "earth", "moon"}:
        raise ValueError("occultations target must be a planet")
    _require_solar_system_target(target_name)
    return _strict_overlap_events(
        planets,
        start,
        end,
        foreground_name="moon",
        background_name=target_name,
        event_name=f"moon_occultation_{target_name}",
    )


def _strict_overlap_events(
    planets: Any,
    start: Any,
    end: Any,
    *,
    foreground_name: str,
    background_name: str,
    event_name: str,
) -> list[dict[str, object]]:
    """Return conjunctions whose apparent disks genuinely overlap.

    This is the controlled replacement for MAVIS' strict conjunction helpers.
    It retains the angular-radius and foreground-distance test, but removes
    NumPy and implicit global state.  The reference sampled a longitude
    conjunction and tested overlap at that instant; that can miss a transit
    because the minimum apparent separation is offset by orbital latitude.
    Skyfield's bounded ``find_minima`` is therefore used on the apparent
    separation itself.
    """

    foreground = _planet(planets, foreground_name)
    background = _planet(planets, background_name)
    from skyfield.searchlib import find_minima

    earth = planets["earth"]
    foreground_radius = get_celestial_body_radius(foreground_name)
    background_radius = get_celestial_body_radius(background_name)
    results: list[dict[str, object]] = []

    def separation_at(time: Any) -> Any:
        observer = earth.at(time)
        return (
            observer.observe(foreground)
            .apparent()
            .separation_from(observer.observe(background).apparent())
            .degrees
        )

    separation_at.step_days = (
        7.0 if "moon" in {foreground_name, background_name} else 40.0
    )
    times, separations = find_minima(start, end, separation_at)
    for time, separation_value in zip(times, separations, strict=True):
        observer = earth.at(time)
        foreground_apparent = observer.observe(foreground).apparent()
        background_apparent = observer.observe(background).apparent()
        separation = float(separation_value)
        foreground_distance_km = float(foreground_apparent.distance().au * 149597870.7)
        background_distance_km = float(background_apparent.distance().au * 149597870.7)
        foreground_radius_degrees = _apparent_radius_degrees(
            foreground_radius, foreground_distance_km
        )
        background_radius_degrees = _apparent_radius_degrees(
            background_radius, background_distance_km
        )
        if (
            separation < foreground_radius_degrees + background_radius_degrees
            and foreground_distance_km < background_distance_km
        ):
            results.append(
                {
                    "event": event_name,
                    "occurred_at": time.utc_iso(),
                    "foreground": foreground_name,
                    "background": background_name,
                    "angular_separation_degrees": separation,
                    "foreground_angular_radius_degrees": foreground_radius_degrees,
                    "background_angular_radius_degrees": background_radius_degrees,
                }
            )
    return results


def _apparent_radius_degrees(radius_km: float, distance_km: float) -> float:
    if not isfinite(distance_km) or distance_km <= 0:
        raise ValueError("apparent body distance must be positive and finite")
    ratio = radius_km / distance_km
    if not isfinite(ratio) or ratio <= 0 or ratio > 1:
        raise ValueError("body radius is outside the apparent-distance bound")
    return degrees(asin(ratio))


def analyze_fits_image(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "fits_base64",
            "image",
            "operation",
            "x",
            "y",
            "radius_pixels",
            "background",
            "sigma",
            "threshold_sigma",
            "fwhm_pixels",
            "max_sources",
            "npixels",
        },
    )
    operation = optional_string(
        request.parameters, "operation", default="background_statistics"
    )
    if operation not in {
        "background_statistics",
        "centroid",
        "source_detection",
        "segmentation",
        "aperture_photometry",
    }:
        raise ValueError("FITS image operation is not supported")
    import numpy as np
    from astropy.stats import sigma_clipped_stats

    array = np.asarray(_read_image(request), dtype=float)
    if array.ndim != 2 or not array.size:
        raise ValueError("FITS image analysis requires a non-empty 2D image")
    if array.nbytes > request.budget.max_input_bytes:
        raise ValueError("FITS image exceeds the byte budget")
    finite = np.isfinite(array)
    if not finite.any():
        raise ValueError("FITS image has no finite pixels")
    sigma = optional_number(request.parameters, "sigma", default=3)
    if not 0 < sigma <= 10:
        raise ValueError("sigma must be within (0, 10]")
    clipped_mean, clipped_median, clipped_stddev = sigma_clipped_stats(
        array[finite], sigma=sigma
    )
    prepared = np.where(finite, array, clipped_median)
    common: dict[str, object] = {
        "operation": operation,
        "image_shape": [int(array.shape[0]), int(array.shape[1])],
        "finite_pixel_count": int(finite.sum()),
        "masked_pixel_count": int(array.size - finite.sum()),
        "background_mean": float(clipped_mean),
        "background_median": float(clipped_median),
        "background_stddev": float(clipped_stddev),
    }
    if operation == "background_statistics":
        return common
    background = (
        require_number(request.parameters, "background")
        if "background" in request.parameters
        else float(clipped_median)
    )
    background_subtracted = prepared - background
    if operation == "centroid":
        from photutils.centroids import centroid_com

        x_centroid, y_centroid = centroid_com(background_subtracted)
        if not np.isfinite(x_centroid) or not np.isfinite(y_centroid):
            raise ValueError("FITS image centroid is undefined")
        return common | {
            "background_per_pixel": background,
            "x_centroid": float(x_centroid),
            "y_centroid": float(y_centroid),
        }
    if operation == "source_detection":
        from photutils.detection import DAOStarFinder

        threshold_sigma = _bounded_number(
            request, "threshold_sigma", default=5, lower=0, upper=50
        )
        fwhm = _bounded_number(request, "fwhm_pixels", default=3, lower=0, upper=1000)
        max_sources = _bounded_integer(
            request,
            "max_sources",
            default=min(100, request.budget.max_output_rows),
            lower=1,
            upper=request.budget.max_output_rows,
        )
        if clipped_stddev <= 0:
            raise ValueError("source detection requires non-zero background noise")
        sources = DAOStarFinder(
            fwhm=fwhm,
            threshold=threshold_sigma * float(clipped_stddev),
        )(background_subtracted)
        detected_count = 0 if sources is None else len(sources)
        rows = _table_rows(sources, request.budget.max_output_rows)
        rows.sort(key=lambda row: _sortable_number(row.get("flux")), reverse=True)
        return common | {
            "background_per_pixel": background,
            "threshold_sigma": threshold_sigma,
            "fwhm_pixels": fwhm,
            "source_count": detected_count,
            "sources": rows[:max_sources],
            "truncated": detected_count > max_sources,
        }
    if operation == "segmentation":
        from photutils.segmentation import (
            SourceCatalog,
            detect_sources,
            detect_threshold,
        )

        threshold_sigma = _bounded_number(
            request, "threshold_sigma", default=3, lower=0, upper=50
        )
        npixels = _bounded_integer(request, "npixels", default=5, lower=1, upper=10_000)
        threshold = detect_threshold(prepared, n_sigma=threshold_sigma)
        segment_map = detect_sources(prepared, threshold, n_pixels=npixels)
        if segment_map is None:
            rows = []
        else:
            catalog = SourceCatalog(prepared, segment_map)
            rows = _table_rows(
                catalog.to_table(
                    columns=(
                        "label",
                        "x_centroid",
                        "y_centroid",
                        "area",
                        "segment_flux",
                        "eccentricity",
                        "orientation",
                    )
                ),
                request.budget.max_output_rows,
            )
        return common | {
            "threshold_sigma": threshold_sigma,
            "minimum_connected_pixels": npixels,
            "segment_count": len(rows),
            "segments": rows,
        }
    x = require_number(request.parameters, "x")
    y = require_number(request.parameters, "y")
    radius = _bounded_number(request, "radius_pixels", default=3, lower=0, upper=10_000)
    from photutils.aperture import ApertureStats, CircularAperture

    aperture = CircularAperture((x, y), r=radius)
    stats = ApertureStats(prepared, aperture, local_bkg=background)
    return common | {
        "background_per_pixel": background,
        "x": x,
        "y": y,
        "radius_pixels": radius,
        "aperture_sum": float(stats.sum),
        "mean": float(stats.mean),
        "median": float(stats.median),
        "stddev": float(stats.std),
    }


def build_wwt_scene(request: ScientificSkillRequest) -> dict[str, object]:
    reject_unknown(
        request.parameters,
        {
            "view",
            "time",
            "observer",
            "background",
            "foreground",
            "solar_system",
            "coordinate_grids",
            "constellations",
            "precession_chart",
            "fits_layers",
            "table_layers",
            "annotations",
            "tour_steps",
            "tour_autoplay",
            "tour_loop",
            "readbacks",
            "text_alternative",
        },
    )
    from app.schemas.scientific_skills import WwtSceneVisualizationSpec

    payload = dict(request.parameters)
    payload["mode"] = "wwt_scene"
    return WwtSceneVisualizationSpec.model_validate(payload).model_dump(mode="json")


@contextmanager
def _open_ephemeris(request: ScientificSkillRequest) -> Iterator[tuple[Any, Any]]:
    encoded = request.parameters.get("ephemeris_base64")
    if encoded is None:
        from skyfield.api import load, load_file
        from skyfield_data import get_skyfield_data_path

        planets = load_file(str(Path(get_skyfield_data_path()) / "de421.bsp"))
        try:
            yield planets, load.timescale()
        finally:
            planets.close()
        return
    if not isinstance(encoded, str) or not encoded.strip():
        raise ValueError("ephemeris_base64 must be non-empty text")
    try:
        content = b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("ephemeris_base64 is not valid base64") from error
    if not content or len(content) > request.budget.max_input_bytes:
        raise ValueError("ephemeris content is empty or exceeds the byte budget")
    from skyfield.api import load, load_file

    temporary_path: Path | None = None
    planets: Any | None = None
    try:
        with NamedTemporaryFile(suffix=".bsp", delete=False) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)
        try:
            planets = load_file(str(temporary_path))
        except Exception as error:
            raise ValueError("ephemeris content is not a valid SPK kernel") from error
        yield planets, load.timescale()
    finally:
        if planets is not None:
            planets.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _planet(planets: Any, target_name: str) -> Any:
    candidates = (target_name, f"{target_name} barycenter")
    for name in candidates:
        try:
            return planets[name]
        except KeyError:
            continue
    raise ValueError(f"ephemeris does not contain target: {target_name}")


def _require_solar_system_target(target_name: str) -> None:
    if target_name not in _SOLAR_SYSTEM_TARGETS:
        raise ValueError(f"unsupported solar-system target: {target_name}")


def _observer(
    planets: Any,
    request: ScientificSkillRequest | None = None,
    *,
    coordinates: tuple[float, float, float] | None = None,
) -> Any:
    from skyfield.api import wgs84

    if coordinates is None:
        if request is None:
            raise ValueError("observer request or coordinates are required")
        coordinates = _observer_coordinates(request)[:3]
    latitude, longitude, elevation = coordinates
    return planets["earth"] + wgs84.latlon(latitude, longitude, elevation_m=elevation)


def _observer_coordinates(
    request: ScientificSkillRequest,
) -> tuple[float, float, float, dict[str, object] | None]:
    has_latitude = "latitude_degrees" in request.parameters
    has_longitude = "longitude_degrees" in request.parameters
    location_name = request.parameters.get("location_name")
    has_location_name = location_name is not None
    if has_latitude != has_longitude:
        raise ValueError(
            "latitude_degrees and longitude_degrees must be provided together"
        )
    if has_location_name == (has_latitude or has_longitude):
        raise ValueError(
            "provide exactly one observer location: location_name or latitude/longitude"
        )
    resolved_location: dict[str, object] | None = None
    if has_location_name:
        if not isinstance(location_name, str) or not location_name.strip():
            raise ValueError("location_name must be non-empty text")
        resolved_location = _geocode_location(
            location_name,
            timeout_seconds=request.budget.timeout_seconds,
            max_bytes=min(
                request.budget.max_input_bytes,
                _MAX_GEOCODING_RESPONSE_BYTES,
            ),
        )
        latitude = float(resolved_location["latitude_degrees"])
        longitude = float(resolved_location["longitude_degrees"])
    else:
        latitude = require_number(request.parameters, "latitude_degrees")
        longitude = require_number(request.parameters, "longitude_degrees")
    elevation = optional_number(request.parameters, "elevation_meters", default=0)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("observer coordinates are outside their valid range")
    return latitude, longitude, elevation, resolved_location


def _geocode_location(
    location_name: str,
    *,
    timeout_seconds: int = 30,
    max_bytes: int = _MAX_GEOCODING_RESPONSE_BYTES,
    transport: Any | None = None,
) -> dict[str, object]:
    """Resolve one location through the HTTPS Nominatim allowlist.

    ``transport`` is an internal recorded-test seam.  Production callers do
    not provide it; no user-controlled URL or redirect is ever followed.
    """

    if not isinstance(location_name, str) or not location_name.strip():
        raise ValueError("location_name must be non-empty text")
    normalized = location_name.strip()
    if len(normalized) > _MAX_LOCATION_NAME_LENGTH:
        raise ValueError("location_name exceeds the bounded length")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise ValueError("timeout_seconds must be an integer")
    if not 1 <= timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be within [1, 120]")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("max_bytes must be an integer")
    if not 1 <= max_bytes <= _MAX_GEOCODING_RESPONSE_BYTES:
        raise ValueError(
            f"max_bytes must be within [1, {_MAX_GEOCODING_RESPONSE_BYTES}]"
        )

    import httpx

    client_options: dict[str, object] = {
        "follow_redirects": False,
        "trust_env": False,
        "timeout": httpx.Timeout(timeout_seconds),
    }
    if transport is not None:
        client_options["transport"] = transport
    try:
        with httpx.Client(**client_options) as client:
            response = client.get(
                _NOMINATIM_URL,
                params={"q": normalized, "format": "jsonv2", "limit": "1"},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "xingwen-astro-ai/0.1 (scientific location resolution)",
                },
            )
            request_url = response.request.url
            if request_url.scheme != "https" or request_url.host != _NOMINATIM_HOST:
                raise ValueError("geocoding request escaped the HTTPS allowlist")
            if response.is_redirect or response.is_error:
                raise ValueError(
                    "Nominatim geocoding response was not a bounded success"
                )
            payload = _bounded_response_bytes(response, max_bytes)
    except httpx.HTTPError as error:
        raise ValueError("Nominatim geocoding request failed") from error

    try:
        rows = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("Nominatim returned invalid JSON") from error
    if not isinstance(rows, list) or not rows:
        raise ValueError("Nominatim returned no location result")
    candidate = rows[0]
    if not isinstance(candidate, dict):
        raise ValueError("Nominatim returned an invalid location result")
    try:
        latitude = float(candidate["lat"])
        longitude = float(candidate["lon"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Nominatim location result has invalid coordinates") from error
    if (
        not isfinite(latitude)
        or not isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Nominatim location coordinates are outside valid bounds")
    display_name = candidate.get("display_name", normalized)
    if not isinstance(display_name, str) or not display_name.strip():
        raise ValueError("Nominatim location result has no display name")
    if len(display_name) > 1000:
        raise ValueError("Nominatim display name exceeds the bounded length")
    return {
        "query": normalized,
        "display_name": display_name.strip(),
        "latitude_degrees": latitude,
        "longitude_degrees": longitude,
        "source": "nominatim",
        "source_host": _NOMINATIM_HOST,
        "response_uri": _NOMINATIM_URL,
        "response_content_hash": f"sha256:{sha256(payload).hexdigest()}",
        "source_version_or_etag": response.headers.get("etag"),
    }


def _bounded_response_bytes(response: Any, max_bytes: int) -> bytes:
    content = bytearray()
    for chunk in response.iter_bytes():
        if len(content) + len(chunk) > max_bytes:
            raise ValueError("Nominatim response exceeds the byte budget")
        content.extend(chunk)
    return bytes(content)


def _labeled_events(times: Any, states: Any, labels: Any) -> list[dict[str, object]]:
    return [
        {
            "event": str(labels[int(state)]),
            "occurred_at": timestamp,
            "state_code": int(state),
        }
        for timestamp, state in zip(times.utc_iso(), states, strict=True)
    ]


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("time must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("time must include a timezone")
    return parsed.astimezone(timezone.utc)


def _bounded_number(
    request: ScientificSkillRequest,
    key: str,
    *,
    default: float,
    lower: float,
    upper: float,
) -> float:
    value = optional_number(request.parameters, key, default=default)
    if not lower < value <= upper:
        raise ValueError(f"{key} must be within ({lower}, {upper}]")
    return value


def _bounded_integer(
    request: ScientificSkillRequest,
    key: str,
    *,
    default: int,
    lower: int,
    upper: int,
) -> int:
    return optional_integer(
        request.parameters,
        key,
        default=default,
        lower=lower,
        upper=upper,
    )


def _read_image(request: ScientificSkillRequest) -> Any:
    if "image" in request.parameters:
        image = request.parameters["image"]
        if not isinstance(image, list) or not image:
            raise ValueError("image must be a non-empty 2D array")
        return image
    encoded = require_string(request.parameters, "fits_base64")
    try:
        content = b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("fits_base64 is not valid base64") from error
    if not content or len(content) > request.budget.max_input_bytes:
        raise ValueError("FITS content is empty or exceeds the byte budget")
    from astropy.io import fits

    try:
        with fits.open(BytesIO(content), memmap=False) as document:
            return document[0].data
    except Exception as error:
        raise ValueError("FITS content cannot be decoded") from error


def _table_rows(table: Any, max_rows: int) -> list[dict[str, object]]:
    if table is None:
        return []
    result: list[dict[str, object]] = []
    for row in table[:max_rows]:
        result.append({name: _json_scalar(row[name]) for name in table.colnames})
    return result


def _json_scalar(value: Any) -> object:
    if bool(getattr(value, "mask", False)):
        return None
    if hasattr(value, "value"):
        value = value.value
    item = value.item() if hasattr(value, "item") else value
    if isinstance(item, bytes):
        return item.decode("utf-8", errors="replace")
    if isinstance(item, int | float | bool | str) or item is None:
        return item
    return str(item)


def _sortable_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return float("-inf")
    return float(value)


__all__ = [
    "analyze_fits_image",
    "build_wwt_scene",
    "calculate_ephemeris",
    "find_celestial_events",
    "get_celestial_body_radius",
    "query_simbad",
    "retrieve_skyview_fits",
]
