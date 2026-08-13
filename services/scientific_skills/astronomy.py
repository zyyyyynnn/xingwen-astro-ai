"""Astronomy adapters derived from MAVIS tasks without generated-code execution."""

from __future__ import annotations

from base64 import b64decode, b64encode
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
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
        },
    )
    target_name = require_string(request.parameters, "target").casefold()
    _require_solar_system_target(target_name)
    observed_at = _parse_utc(require_string(request.parameters, "observed_at"))
    latitude = require_number(request.parameters, "latitude_degrees")
    longitude = require_number(request.parameters, "longitude_degrees")
    elevation = optional_number(request.parameters, "elevation_meters", default=0)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("observer coordinates are outside their valid range")

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
        "conjunctions_oppositions",
    }:
        raise ValueError("celestial event type is not supported")
    start_at = _parse_utc(require_string(request.parameters, "start_at"))
    end_at = _parse_utc(require_string(request.parameters, "end_at"))
    if end_at <= start_at or (end_at - start_at).days > 3660:
        raise ValueError("event interval must be positive and no longer than 10 years")

    from skyfield import almanac

    with _open_ephemeris(request) as (planets, ts):
        start = ts.from_datetime(start_at)
        end = ts.from_datetime(end_at)
        if event_type == "rise_set_transit":
            target_name = require_string(request.parameters, "target").casefold()
            _require_solar_system_target(target_name)
            observer = _observer(planets, request)
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

            latitude, longitude, elevation = _observer_coordinates(request)
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
    return {
        "event_type": event_type,
        "target": request.parameters.get("target"),
        "events": events[: request.budget.max_output_rows],
        "truncated": len(events) > request.budget.max_output_rows,
    }


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
            "ra_hours",
            "dec_degrees",
            "field_of_view_degrees",
            "observed_at",
            "background",
            "coordinate_grid",
            "fits_layers",
            "annotations",
        },
    )
    from app.schemas.scientific_skills import WwtSceneVisualizationSpec

    payload = {
        "mode": "wwt_scene",
        "center": {
            "ra_hours": require_number(request.parameters, "ra_hours"),
            "dec_degrees": require_number(request.parameters, "dec_degrees"),
        },
        "field_of_view_degrees": optional_number(
            request.parameters, "field_of_view_degrees", default=2
        ),
        "observed_at": optional_string(request.parameters, "observed_at"),
        "background": optional_string(
            request.parameters, "background", default="digitized_sky_survey"
        ),
        "coordinate_grid": optional_string(
            request.parameters, "coordinate_grid", default="equatorial"
        ),
        "fits_layers": request.parameters.get("fits_layers", []),
        "annotations": request.parameters.get("annotations", []),
    }
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


def _observer(planets: Any, request: ScientificSkillRequest) -> Any:
    from skyfield.api import wgs84

    latitude, longitude, elevation = _observer_coordinates(request)
    return planets["earth"] + wgs84.latlon(latitude, longitude, elevation_m=elevation)


def _observer_coordinates(
    request: ScientificSkillRequest,
) -> tuple[float, float, float]:
    latitude = require_number(request.parameters, "latitude_degrees")
    longitude = require_number(request.parameters, "longitude_degrees")
    elevation = optional_number(request.parameters, "elevation_meters", default=0)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("observer coordinates are outside their valid range")
    return latitude, longitude, elevation


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
    "query_simbad",
    "retrieve_skyview_fits",
]
