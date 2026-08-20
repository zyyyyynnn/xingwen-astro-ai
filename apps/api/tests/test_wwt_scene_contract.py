from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.core import ScientificSkillId
from app.schemas.scientific_skills import WwtSceneVisualizationSpec
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    build_scientific_skill_registry,
)
from services.scientific_skills.wwt_capabilities import WWT_CAPABILITY_MATRIX


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _request(parameters: dict[str, object]) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id="request.wwt.full-scene",
        project_id=str(uuid4()),
        run_id=str(uuid4()),
        skill_id=ScientificSkillId.wwt_scene,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=30),
    )


def _full_scene_parameters() -> dict[str, object]:
    return {
        "view": {
            "kind": "coordinates",
            "center": {"ra_hours": 1.25, "dec_degrees": 2.25},
            "field_of_view_degrees": 12,
            "roll_degrees": 8,
            "transition_seconds": 3,
        },
        "time": {
            "mode": "playback",
            "observed_at": "2026-08-14T12:00:00Z",
            "rate": 120,
        },
        "observer": {
            "latitude_degrees": 31.2304,
            "longitude_degrees": 121.4737,
            "elevation_meters": 12,
            "local_horizon_mode": True,
        },
        "background": "digitized_sky_survey",
        "foreground": {"image_set": "wise", "opacity": 0.35},
        "solar_system": None,
        "coordinate_grids": [
            {"system": "equatorial", "labels": True},
            {"system": "altaz", "labels": True},
        ],
        "constellations": {
            "boundaries": True,
            "figures": True,
            "pictures": False,
            "labels": True,
        },
        "precession_chart": True,
        "fits_layers": [
            {
                "layer_id": "layer.fits",
                "source_snapshot_id": "snapshot.fits",
                "content_ref": "content.fits",
                "content_hash": HASH_A,
                "opacity": 0.8,
                "stretch": "sqrt",
                "color_map": "viridis",
                "vmin": 1.5,
                "vmax": 42.0,
            }
        ],
        "table_layers": [
            {
                "layer_id": "layer.catalog",
                "source_snapshot_id": "snapshot.catalog",
                "content_ref": "content.catalog",
                "content_hash": HASH_B,
                "media_type": "text/csv",
                "coordinates": {
                    "kind": "spherical",
                    "frame": "sky",
                    "longitude_field": "ra",
                    "latitude_field": "dec",
                    "longitude_unit": "hours",
                },
                "time_series": {
                    "time_field": "observed_at",
                    "decay_days": 3,
                },
                "size_field": "magnitude",
                "size_scale": 1.25,
                "color_token": "information",
                "color_field": "temperature",
                "marker_scale": "screen",
                "opacity": 0.75,
            }
        ],
        "annotations": [
            {
                "annotation_id": "annotation.path",
                "kind": "line",
                "points": [
                    {"ra_hours": 1.0, "dec_degrees": 2.0},
                    {"ra_hours": 1.5, "dec_degrees": 2.5},
                ],
                "line_width": 2.5,
                "color_token": "brand",
            },
            {
                "annotation_id": "annotation.point",
                "kind": "point",
                "points": [{"ra_hours": 1.25, "dec_degrees": 2.25}],
                "color_token": "warning",
            },
        ],
        "tour_steps": [
            {
                "step_id": "step.first-field",
                "view": {
                    "kind": "coordinates",
                    "center": {"ra_hours": 1.0, "dec_degrees": 2.0},
                    "field_of_view_degrees": 12,
                    "roll_degrees": 0,
                    "transition_seconds": 1,
                },
                "observed_at": "2026-08-14T12:00:00Z",
                "hold_seconds": 1,
            },
            {
                "step_id": "step.second-field",
                "view": {
                    "kind": "coordinates",
                    "center": {"ra_hours": 1.5, "dec_degrees": 2.5},
                    "field_of_view_degrees": 12,
                    "roll_degrees": 0,
                    "transition_seconds": 1,
                },
                "observed_at": "2026-08-15T12:00:00Z",
                "hold_seconds": 1,
            },
        ],
        "readbacks": ["center_coordinates", "field_of_view", "current_time"],
        "text_alternative": (
            "Mars is tracked from Shanghai at 2026-08-14 12:00 UTC with solar "
            "system overlays, two coordinate grids, a FITS image, and a catalog."
        ),
    }


def test_wwt_skill_emits_the_complete_bounded_declarative_scene() -> None:
    parameters = _full_scene_parameters()

    result = build_scientific_skill_registry().execute(_request(parameters))

    scene = WwtSceneVisualizationSpec.model_validate(result.output)
    assert scene.view.kind == "coordinates"
    assert scene.view.roll_degrees == 8
    assert scene.time.mode == "playback"
    assert scene.time.rate == 120
    assert scene.observer is not None
    assert scene.observer.local_horizon_mode is True
    assert [grid.system for grid in scene.coordinate_grids] == [
        "equatorial",
        "altaz",
    ]
    assert scene.foreground is not None
    assert scene.foreground.image_set == "wise"
    assert scene.constellations.boundaries is True
    assert scene.precession_chart is True
    assert scene.fits_layers[0].vmax == 42
    assert scene.table_layers[0].coordinates.kind == "spherical"
    assert [step.step_id for step in scene.tour_steps] == [
        "step.first-field",
        "step.second-field",
    ]
    assert scene.readbacks == (
        "center_coordinates",
        "field_of_view",
        "current_time",
    )
    assert "WebSocket" not in scene.model_dump_json()


def test_wwt_skill_emits_a_bounded_tracked_solar_system_scene() -> None:
    parameters: dict[str, object] = {
        "view": {
            "kind": "tracked_object",
            "target": "mars",
            "field_of_view_degrees": 12,
            "transition_seconds": 3,
        },
        "time": {
            "mode": "paused",
            "observed_at": "2026-08-14T12:00:00Z",
        },
        "background": "solar_system",
        "solar_system": {
            "cosmos": True,
            "lighting": True,
            "milky_way": True,
            "minor_planets": False,
            "minor_orbits": True,
            "orbits": True,
            "planets": True,
            "scale": 50,
            "stars": True,
        },
        "coordinate_grids": [],
        "text_alternative": (
            "Mars is tracked in the solar-system view at the fixed UTC time."
        ),
    }

    result = build_scientific_skill_registry().execute(_request(parameters))
    scene = WwtSceneVisualizationSpec.model_validate(result.output)

    assert scene.view.kind == "tracked_object"
    assert scene.view.target == "mars"
    assert scene.solar_system is not None
    assert scene.solar_system.scale == 50


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload.update(text_alternative=""),
            "at least 1 character",
        ),
        (
            lambda payload: payload["time"].update(rate=0),
            "playback rate must be non-zero",
        ),
        (
            lambda payload: payload.update(observer=None),
            "altaz grid requires an observer",
        ),
        (
            lambda payload: payload["fits_layers"][0].update(vmin=50, vmax=40),
            "vmin must be lower than vmax",
        ),
        (
            lambda payload: payload.update(background="solar_system"),
            "overlays require a sky background",
        ),
    ],
)
def test_wwt_scene_rejects_ambiguous_or_non_reproducible_intent(
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    payload = _full_scene_parameters()
    mutate(payload)

    with pytest.raises((ValidationError, ValueError), match=message):
        build_scientific_skill_registry().execute(_request(payload))


def test_wwt_scene_rejects_arbitrary_remote_control_or_layer_urls() -> None:
    payload = _full_scene_parameters()
    payload["websocket_url"] = "ws://127.0.0.1:8001/wwt"

    with pytest.raises(ValueError, match="websocket_url"):
        build_scientific_skill_registry().execute(_request(payload))

    payload = _full_scene_parameters()
    payload["fits_layers"][0]["url"] = "https://example.invalid/image.fits"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        build_scientific_skill_registry().execute(_request(payload))


def test_wwt_scene_support_matrix_tracks_contract_engine_and_renderer_truthfully() -> None:
    assert WWT_CAPABILITY_MATRIX["center_on_coordinates"] == {
        "contract": "supported",
        "engine": "supported",
        "renderer": "supported",
    }
    assert WWT_CAPABILITY_MATRIX["observer_location"] == {
        "contract": "supported",
        "engine": "supported",
        "renderer": "supported",
    }
    assert WWT_CAPABILITY_MATRIX["table_layer"] == {
        "contract": "supported",
        "engine": "supported",
        "renderer": "supported",
    }
    assert WWT_CAPABILITY_MATRIX["text_alternative"] == {
        "contract": "supported",
        "engine": "unsupported",
        "renderer": "supported",
    }
    assert WWT_CAPABILITY_MATRIX["arbitrary_websocket_command"] == {
        "contract": "unsupported",
        "engine": "unsupported",
        "renderer": "unsupported",
    }
    assert WWT_CAPABILITY_MATRIX["automatic_screenshot_upload"] == {
        "contract": "unsupported",
        "engine": "unsupported",
        "renderer": "unsupported",
    }
    for rejected_despite_engine_primitive in (
        "screenshot_polling",
        "unbounded_remote_layer_url",
    ):
        assert WWT_CAPABILITY_MATRIX[rejected_despite_engine_primitive] == {
            "contract": "unsupported",
            "engine": "supported",
            "renderer": "unsupported",
        }
