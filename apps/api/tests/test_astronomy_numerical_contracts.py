"""Representative astronomical numerical contracts through the public API.

Every assertion carries a real physical tolerance instead of only checking
field existence.  Reference values are the published JPL/USNO-style event
times for the DE421 ephemeris the skill bundles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.schemas.core import ScientificSkillId
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    build_scientific_skill_registry,
)

PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())

LIGHT_TIME_MINUTES_PER_AU = 499.00478384 / 60.0


def _execute(skill_id: ScientificSkillId, parameters: dict[str, object]) -> dict:
    result = build_scientific_skill_registry().execute(
        ScientificSkillRequest(
            request_id=f"request.{skill_id.value}",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            skill_id=skill_id,
            parameters=parameters,
            source_references=(),
            budget=ScientificSkillBudget(timeout_seconds=60),
        )
    )
    return result.output


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def test_2024_vernal_equinox_matches_published_time() -> None:
    output = _execute(
        ScientificSkillId.celestial_events,
        {
            "event_type": "seasons",
            "start_at": "2024-01-01T00:00:00Z",
            "end_at": "2024-12-31T00:00:00Z",
        },
    )
    equinoxes = [
        event
        for event in output["events"]
        if "equinox" in str(event["event"]).lower()
        and _parse_iso(str(event["occurred_at"])).month == 3
    ]
    assert len(equinoxes) == 1
    occurred = _parse_iso(str(equinoxes[0]["occurred_at"]))
    # Published value: 2024-03-20 03:06 UTC.
    published = datetime(2024, 3, 20, 3, 6, tzinfo=timezone.utc)
    assert abs((occurred - published).total_seconds()) < 2 * 3600


def test_2024_january_full_moon_matches_published_time() -> None:
    output = _execute(
        ScientificSkillId.celestial_events,
        {
            "event_type": "moon_phases",
            "start_at": "2024-01-01T00:00:00Z",
            "end_at": "2024-02-01T00:00:00Z",
        },
    )
    full_moons = [
        event
        for event in output["events"]
        if "full" in str(event["event"]).lower()
    ]
    assert len(full_moons) == 1
    occurred = _parse_iso(str(full_moons[0]["occurred_at"]))
    # Published value: 2024-01-25 17:54 UTC.
    published = datetime(2024, 1, 25, 17, 54, tzinfo=timezone.utc)
    assert abs((occurred - published).total_seconds()) < 2 * 3600


def test_2025_mars_opposition_falls_on_the_published_date() -> None:
    output = _execute(
        ScientificSkillId.celestial_events,
        {
            "event_type": "conjunctions_oppositions",
            "target": "mars",
            "start_at": "2025-01-01T00:00:00Z",
            "end_at": "2025-12-31T00:00:00Z",
        },
    )
    oppositions = [
        event
        for event in output["events"]
        if str(event["event"]) == "opposition"
    ]
    assert len(oppositions) == 1
    occurred = _parse_iso(str(oppositions[0]["occurred_at"]))
    # Published value: 2025-01-16 (approximately 02:38 UTC).
    published = datetime(2025, 1, 16, 2, 38, tzinfo=timezone.utc)
    assert abs((occurred - published).total_seconds()) < 12 * 3600


def test_greenwich_solar_transit_is_within_the_equation_of_time() -> None:
    output = _execute(
        ScientificSkillId.celestial_events,
        {
            "event_type": "rise_set_transit",
            "target": "sun",
            "start_at": "2024-06-21T00:00:00Z",
            "end_at": "2024-06-22T00:00:00Z",
            "latitude_degrees": 51.4778,
            "longitude_degrees": 0.0,
            "elevation_meters": 0,
        },
    )
    transits = [
        event for event in output["events"] if str(event["event"]) == "transit"
    ]
    assert len(transits) == 1
    occurred = _parse_iso(str(transits[0]["occurred_at"]))
    mean_noon = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)
    delta_minutes = abs((occurred - mean_noon).total_seconds()) / 60.0
    # Apparent solar noon at Greenwich deviates from 12:00 UTC only by the
    # equation of time (about -1.7 minutes on the June solstice).
    assert delta_minutes < 10.0


def test_ephemeris_metadata_carries_frame_time_scale_observer_and_units() -> None:
    output = _execute(
        ScientificSkillId.ephemeris,
        {
            "target": "mars",
            "reference_target": "sun",
            "observed_at": "2026-08-14T00:00:00Z",
            "latitude_degrees": 51.4778,
            "longitude_degrees": 0.0,
            "elevation_meters": 0,
        },
    )

    assert output["frame"] == "gcrs_apparent_epoch_of_date"
    assert output["time_scale"] == "UTC"
    assert output["ephemeris"] == "jpl_de421"
    assert float(output["observer_latitude_degrees"]) == pytest.approx(51.4778)
    assert float(output["observer_longitude_degrees"]) == pytest.approx(0.0)

    ra_hours = float(output["ra_hours"])
    dec_degrees = float(output["dec_degrees"])
    distance_au = float(output["distance_au"])
    assert 0 <= ra_hours < 24
    assert -90 <= dec_degrees <= 90
    # Mars-Earth distance is physically bounded by the two orbital radii.
    assert 0.35 <= distance_au <= 2.7

    light_time_minutes = float(output["light_time_minutes"])
    assert light_time_minutes == pytest.approx(
        distance_au * LIGHT_TIME_MINUTES_PER_AU, rel=1e-3
    )
