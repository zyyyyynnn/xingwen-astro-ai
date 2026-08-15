"""Numerical reference cases for MAVIS-derived astronomy capabilities.

Each case pins one representative capability against a published almanac
value (tolerances cover DE421 ephemeris error plus the skill's search step).
These tests assert real numbers, not just schema validity.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.core import ScientificSkillId
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
)

GREENWICH = {"latitude_degrees": 51.4779, "longitude_degrees": 0.0}


def _request(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id="request.astronomy-reference",
        project_id="project.astronomy-reference",
        run_id="run.astronomy-reference",
        skill_id=skill_id,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=120, max_output_rows=10_000),
    )


def _events(parameters: dict[str, object]) -> list[dict[str, object]]:
    result = build_scientific_skill_registry().execute(
        _request(ScientificSkillId.celestial_events, parameters)
    )
    return list(result.output["events"])


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize(
    ("label", "expected_utc", "event_label"),
    [
        ("Spring", "2024-03-20T03:06:00Z", "Vernal Equinox"),
        ("Summer", "2024-06-20T20:51:00Z", "Summer Solstice"),
        ("Autumn", "2024-09-22T12:44:00Z", "Autumnal Equinox"),
        ("Winter", "2024-12-21T09:20:00Z", "Winter Solstice"),
    ],
)
def test_seasons_match_published_almanac_times(label: str, expected_utc: str, event_label: str) -> None:
    events = _events(
        {"event_type": "seasons", "start_at": "2024-01-01T00:00:00Z", "end_at": "2025-01-01T00:00:00Z"}
    )
    matches = [event for event in events if event["event"] == event_label]
    assert matches, f"missing {event_label} in {events}"
    occurred = _parse_utc(str(matches[0]["occurred_at"]))
    expected = _parse_utc(expected_utc)
    assert abs((occurred - expected).total_seconds()) <= 15 * 60


def test_full_moon_matches_published_phase_time() -> None:
    # Full Moon: 2024-04-23 23:49 UTC (published almanac value).
    events = _events(
        {"event_type": "moon_phases", "start_at": "2024-04-01T00:00:00Z", "end_at": "2024-05-01T00:00:00Z"}
    )
    fulls = [event for event in events if event["event"] == "Full Moon"]
    assert fulls
    occurred = _parse_utc(str(fulls[0]["occurred_at"]))
    expected = _parse_utc("2024-04-23T23:49:00Z")
    assert abs((occurred - expected).total_seconds()) <= 30 * 60


def test_mars_opposition_2025_matches_published_date() -> None:
    # Mars opposition: 2025-01-16 (published almanac value).
    events = _events(
        {
            "event_type": "conjunctions_oppositions",
            "target": "mars",
            "start_at": "2025-01-01T00:00:00Z",
            "end_at": "2025-02-01T00:00:00Z",
        }
    )
    assert events
    for event in events:
        occurred = _parse_utc(str(event["occurred_at"]))
        assert abs((occurred - _parse_utc("2025-01-16T00:00:00Z")).days) <= 1


def test_lunar_eclipse_march_2025_is_found() -> None:
    # Total lunar eclipse: 2025-03-14 (published almanac value).
    events = _events(
        {"event_type": "lunar_eclipses", "start_at": "2025-03-01T00:00:00Z", "end_at": "2025-04-01T00:00:00Z"}
    )
    assert events
    occurred = _parse_utc(str(events[0]["occurred_at"]))
    assert abs((occurred - _parse_utc("2025-03-14T06:00:00Z")).days) <= 1


def test_solar_eclipse_april_2024_is_found() -> None:
    # Total solar eclipse: 2024-04-08 (published almanac value).
    events = _events(
        {"event_type": "solar_eclipses", "start_at": "2024-04-01T00:00:00Z", "end_at": "2024-05-01T00:00:00Z"}
    )
    assert events
    occurred = _parse_utc(str(events[0]["occurred_at"]))
    assert abs((occurred - _parse_utc("2024-04-08T18:00:00Z")).days) <= 1


def test_venus_greatest_elongation_january_2025() -> None:
    # Venus greatest eastern elongation: 2025-01-10, about 47.2 degrees.
    events = _events(
        {"event_type": "venus_elongations", "start_at": "2025-01-01T00:00:00Z", "end_at": "2025-02-01T00:00:00Z"}
    )
    assert events
    eastern = [event for event in events if event["direction"] == "east"]
    assert eastern
    occurred = _parse_utc(str(eastern[0]["occurred_at"]))
    assert abs((occurred - _parse_utc("2025-01-10T00:00:00Z")).days) <= 2
    assert abs(float(eastern[0]["elongation_degrees"]) - 47.2) <= 1.5


def test_sun_transit_at_greenwich_near_local_noon() -> None:
    # Apparent solar transit at Greenwich is within ~4 minutes of 12:00 UTC.
    events = _events(
        {
            "event_type": "rise_set_transit",
            "target": "sun",
            "start_at": "2024-06-01T00:00:00Z",
            "end_at": "2024-06-02T00:00:00Z",
            **GREENWICH,
        }
    )
    transits = [event for event in events if event["event"] == "transit"]
    assert transits
    occurred = _parse_utc(str(transits[0]["occurred_at"]))
    noon = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert abs((occurred - noon).total_seconds()) <= 4 * 60


def test_sunrise_at_greenwich_on_equinox_matches_almanac() -> None:
    # Sunrise at Greenwich around the 2024 vernal equinox: ~06:00 UTC.
    events = _events(
        {
            "event_type": "rise_set_transit",
            "target": "sun",
            "start_at": "2024-03-20T00:00:00Z",
            "end_at": "2024-03-21T00:00:00Z",
            **GREENWICH,
        }
    )
    rises = [event for event in events if event["event"] == "rise"]
    assert rises
    occurred = _parse_utc(str(rises[0]["occurred_at"]))
    expected = datetime(2024, 3, 20, 6, 0, tzinfo=timezone.utc)
    assert abs((occurred - expected).total_seconds()) <= 10 * 60


def test_sun_ra_dec_at_vernal_equinox_is_coordinate_origin() -> None:
    # At the instant of the 2024 vernal equinox the apparent Sun sits at
    # ecliptic longitude 0 by definition: RA 0h, Dec 0 degrees.
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.ephemeris,
            {
                "target": "sun",
                "observed_at": "2024-03-20T03:06:00Z",
                **GREENWICH,
            },
        )
    )
    output = result.output
    ra_hours = float(output["ra_hours"]) % 24.0
    circular_distance = min(ra_hours, 24.0 - ra_hours)
    assert circular_distance <= 2 / 60
    assert abs(float(output["dec_degrees"])) <= 1.0
    ecliptic = float(output["ecliptic_longitude_degrees"]) % 360.0
    assert min(ecliptic, 360.0 - ecliptic) <= 0.5


def test_ephemeris_output_carries_explicit_frame_epoch_and_units() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.ephemeris,
            {
                "target": "mars",
                "observed_at": "2025-01-16T00:00:00Z",
                "latitude_degrees": 39.9042,
                "longitude_degrees": 116.4074,
            },
        )
    )
    output = result.output
    assert output["frame"] == "gcrs_apparent_epoch_of_date"
    assert output["time_scale"] == "UTC"
    assert output["ephemeris"] == "jpl_de421"
    assert output["observer_latitude_degrees"] == pytest.approx(39.9042)
    assert output["observer_longitude_degrees"] == pytest.approx(116.4074)
    # Unit-bearing field names: RA in hours, Dec/alt/az in degrees, distance in AU.
    assert 0.0 <= float(output["ra_hours"]) < 24.0
    assert -90.0 <= float(output["dec_degrees"]) <= 90.0
    assert 0.3 < float(output["distance_au"]) < 3.0


def test_mars_distance_at_opposition_is_close_to_published_value() -> None:
    # Mars near its 2025 opposition was about 0.64 AU from Earth (0.96 AU
    # from the Sun minus Earth's 1.0 AU, within the eccentricity range).
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.ephemeris,
            {
                "target": "mars",
                "observed_at": "2025-01-16T00:00:00Z",
                "latitude_degrees": 0.0,
                "longitude_degrees": 0.0,
            },
        )
    )
    assert abs(float(result.output["distance_au"]) - 0.65) <= 0.05
