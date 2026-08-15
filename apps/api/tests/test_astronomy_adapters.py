from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.schemas.core import ScientificSkillId
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificTaskInput
from app.workflow.scientific_provenance import _produced_sources, _source_metadata
from services.scientific_skills import astronomy
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
)
from services.scientific_skills.types import ScientificSkillResult


def _request(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=str(uuid4()),
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        skill_id=skill_id,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=120, max_output_rows=10_000),
    )


@pytest.mark.parametrize(
    ("name", "radius_km"),
    [("Sun", 696_340.0), (" moon ", 1_737.4), ("MERCURY", 2_439.7)],
)
def test_reference_body_radii_are_normalized_and_bounded(
    name: str, radius_km: float
) -> None:
    assert astronomy.get_celestial_body_radius(name) == radius_km


def test_reference_body_radius_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unsupported celestial body"):
        astronomy.get_celestial_body_radius("ceres")


def test_nominatim_recorded_transport_returns_only_bounded_location_facts() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            json=[
                {
                    "lat": "26.646694",
                    "lon": "106.628201",
                    "display_name": "Guiyang, Guizhou, China",
                    "extraneous": "not persisted",
                }
            ],
            request=request,
        )

    result = astronomy._geocode_location(
        "Guiyang",
        timeout_seconds=5,
        max_bytes=4096,
        transport=httpx.MockTransport(handler),
    )

    assert seen_urls == [
        "https://nominatim.openstreetmap.org/search?q=Guiyang&format=jsonv2&limit=1"
    ]
    assert {
        key: result[key]
        for key in (
            "query",
            "display_name",
            "latitude_degrees",
            "longitude_degrees",
            "source",
            "source_host",
        )
    } == {
        "query": "Guiyang",
        "display_name": "Guiyang, Guizhou, China",
        "latitude_degrees": 26.646694,
        "longitude_degrees": 106.628201,
        "source": "nominatim",
        "source_host": "nominatim.openstreetmap.org",
    }
    assert result["response_uri"] == "https://nominatim.openstreetmap.org/search"
    assert result["response_content_hash"].startswith("sha256:")
    assert result["source_version_or_etag"] is None


def test_nominatim_rejects_redirects_and_oversized_recorded_responses() -> None:
    redirect = httpx.MockTransport(
        lambda request: httpx.Response(
            302,
            headers={"location": "https://evil.example/"},
            request=request,
        )
    )
    with pytest.raises(ValueError, match="bounded success"):
        astronomy._geocode_location("Guiyang", transport=redirect)

    oversized = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 128, request=request)
    )
    with pytest.raises(ValueError, match="byte budget"):
        astronomy._geocode_location("Guiyang", max_bytes=64, transport=oversized)


def test_observer_location_requires_exactly_one_coordinate_form(monkeypatch) -> None:
    explicit = _request(
        ScientificSkillId.ephemeris,
        {"latitude_degrees": 26.6, "longitude_degrees": 106.6},
    )
    assert astronomy._observer_coordinates(explicit)[:3] == (26.6, 106.6, 0)

    monkeypatch.setattr(
        astronomy,
        "_geocode_location",
        lambda *_args, **_kwargs: {
            "query": "Guiyang",
            "display_name": "Guiyang",
            "latitude_degrees": 26.6,
            "longitude_degrees": 106.6,
            "source": "nominatim",
            "source_host": "nominatim.openstreetmap.org",
        },
    )
    named = _request(ScientificSkillId.ephemeris, {"location_name": "Guiyang"})
    assert astronomy._observer_coordinates(named)[:3] == (26.6, 106.6, 0)

    with pytest.raises(ValueError, match="exactly one observer location"):
        astronomy._observer_coordinates(
            _request(
                ScientificSkillId.ephemeris,
                {
                    "location_name": "Guiyang",
                    "latitude_degrees": 26.6,
                    "longitude_degrees": 106.6,
                },
            )
        )
    with pytest.raises(ValueError, match="provided together"):
        astronomy._observer_coordinates(
            _request(ScientificSkillId.ephemeris, {"latitude_degrees": 26.6})
        )


def test_celestial_events_persist_resolved_location_fact(monkeypatch) -> None:
    monkeypatch.setattr(
        astronomy,
        "_geocode_location",
        lambda *_args, **_kwargs: {
            "query": "Guiyang",
            "display_name": "Guiyang",
            "latitude_degrees": 26.6,
            "longitude_degrees": 106.6,
            "source": "nominatim",
            "source_host": "nominatim.openstreetmap.org",
        },
    )
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.celestial_events,
            {
                "event_type": "moon_phases",
                "start_at": "2026-01-01T00:00:00Z",
                "end_at": "2026-02-01T00:00:00Z",
                "location_name": "Guiyang",
            },
        )
    )

    assert result.output["resolved_location"]["display_name"] == "Guiyang"
    assert result.output["resolved_location"]["latitude_degrees"] == 26.6


def test_venus_greatest_elongation_uses_bounded_skyfield_maxima() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.celestial_events,
            {
                "event_type": "venus_elongations",
                "start_at": "2026-01-01T00:00:00Z",
                "end_at": "2027-01-01T00:00:00Z",
            },
        )
    )

    assert result.output["event_type"] == "venus_elongations"
    assert result.output["events"]
    assert {event["direction"] for event in result.output["events"]} <= {
        "east",
        "west",
    }
    assert all(
        0 < event["elongation_degrees"] < 50 for event in result.output["events"]
    )


@pytest.mark.parametrize(
    ("event_type", "target", "expected_event"),
    [
        ("transits", "mercury", "mercury_transit"),
        ("transits", "venus", "venus_transit"),
        ("occultations", "jupiter", "moon_occultation_jupiter"),
    ],
)
def test_reference_transit_and_occultation_families_are_strict_disk_overlaps(
    event_type: str, target: str, expected_event: str
) -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.celestial_events,
            {
                "event_type": event_type,
                "target": target,
                "start_at": "2000-01-01T00:00:00Z",
                "end_at": "2010-01-01T00:00:00Z",
            },
        )
    )

    events = result.output["events"]
    assert events
    assert all(event["event"] == expected_event for event in events)
    assert all(
        event["angular_separation_degrees"]
        < event["foreground_angular_radius_degrees"]
        + event["background_angular_radius_degrees"]
        for event in events
    )


def test_transit_and_elongation_parameters_fail_closed() -> None:
    registry = build_scientific_skill_registry()
    base = {
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2027-01-01T00:00:00Z",
    }
    with pytest.raises(ValueError, match="must be mercury or venus"):
        registry.execute(
            _request(
                ScientificSkillId.celestial_events,
                base | {"event_type": "transits", "target": "mars"},
            )
        )
    with pytest.raises(ValueError, match="must be a planet"):
        registry.execute(
            _request(
                ScientificSkillId.celestial_events,
                base | {"event_type": "occultations", "target": "moon"},
            )
        )
    with pytest.raises(ValueError, match="fixes target"):
        registry.execute(
            _request(
                ScientificSkillId.celestial_events,
                base
                | {
                    "event_type": "venus_elongations",
                    "target": "mercury",
                },
            )
        )


def test_provenance_keeps_jpl_and_nominatim_as_distinct_sources() -> None:
    explicit = _source_metadata(
        ScientificSkillId.ephemeris,
        {"latitude_degrees": 26.6, "longitude_degrees": 106.6},
    )
    named = _source_metadata(
        ScientificSkillId.ephemeris,
        {"location_name": "Guiyang"},
    )

    assert [item[0] for item in explicit] == ["jpl_de421"]
    assert [item[0] for item in named] == [
        "jpl_de421",
        "nominatim_openstreetmap",
    ]
    assert all("composite" not in item[1] for item in named)


def test_produced_jpl_and_nominatim_snapshots_have_source_specific_hashes() -> None:
    request = _request(
        ScientificSkillId.ephemeris,
        {
            "target": "mars",
            "observed_at": "2026-01-01T00:00:00Z",
            "location_name": "Guiyang",
        },
    )
    output = {
        "target": "mars",
        "distance_au": 1.2,
        "resolved_location": {
            "query": "Guiyang",
            "display_name": "Guiyang, China",
            "latitude_degrees": 26.6,
            "longitude_degrees": 106.6,
            "source": "nominatim",
            "source_host": "nominatim.openstreetmap.org",
        },
    }
    result = ScientificSkillResult(
        request_id=request.request_id,
        skill_id=request.skill_id,
        skill_revision="1.0.0",
        status="completed",
        output=output,
        source_snapshot_ids=(),
        input_hash=request.input_hash,
        output_hash=compute_canonical_payload_hash(output),
    )
    sources = _produced_sources(
        task=ScientificTaskInput(
            task_id="task.ephemeris",
            skill_id=request.skill_id,
            parameters=request.parameters,
        ),
        request=request,
        result=result,
    )

    assert [source.source_id for source in sources] == [
        "jpl_de421",
        "nominatim_openstreetmap",
    ]
    assert sources[0].content_hash != sources[1].content_hash
    assert sources[1].query == {"location_name": "Guiyang"}
    assert sources[0].source_version_or_etag == "DE421"
    assert sources[1].source_version_or_etag is None
    assert sources[1].request_metadata == {
        "adapter": "nominatim",
        "endpoint_host": "nominatim.openstreetmap.org",
    }
