from __future__ import annotations

from base64 import b64encode
from collections.abc import Sequence
from math import exp
from uuid import UUID, uuid4

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ResearchContractInput,
    ScientificSkillId,
    ScientificTaskInput,
)
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    VisualizationArtifactContent,
)
from app.services.content_storage import sha256_content_hash
from services.scientific_skills import (
    ScientificInputBinding,
    ScientificSkillBudget,
    ScientificSkillDefinition,
    ScientificSkillRegistry,
    ScientificSkillRequest,
    ScientificSourceReference,
    ScientificStepAdapter,
    build_scientific_skill_registry,
)


PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())
SNAPSHOT_ID = str(uuid4())
EVIDENCE_ID = str(uuid4())
DATASET_VERSION_ID = str(uuid4())
HASH = "sha256:" + "a" * 64


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _request(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id=f"request.{skill_id.value}",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        skill_id=skill_id,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=30),
    )


def _rows(count: int = 30) -> list[dict[str, object]]:
    return [
        {
            "row_id": f"row.{index}",
            "x": index,
            "y": index * 2 + (index % 3),
            "label": "high" if index >= count / 2 else "low",
        }
        for index in range(count)
    ]


def _synthetic_star_field(size: int = 49) -> list[list[float]]:
    return [
        [
            0.05 * ((x + y) % 3)
            + 50 * exp(-((x - 12) ** 2 + (y - 12) ** 2) / 4)
            + 30 * exp(-((x - 35) ** 2 + (y - 33) ** 2) / 4)
            for x in range(size)
        ]
        for y in range(size)
    ]


def test_production_registry_is_an_exact_fail_closed_skill_catalog() -> None:
    registry = build_scientific_skill_registry()

    assert set(registry.skill_ids) == set(ScientificSkillId)
    assert len(registry.skill_ids) == len(ScientificSkillId)


@pytest.mark.parametrize(
    ("skill_id", "parameters", "output_key"),
    [
        (ScientificSkillId.data_profile, {"rows": _rows()}, "fields"),
        (
            ScientificSkillId.statistical_analysis,
            {"rows": _rows(), "fields": ["x", "y"]},
            "statistics",
        ),
        (
            ScientificSkillId.correlation_analysis,
            {"rows": _rows(), "fields": ["x", "y"]},
            "correlations",
        ),
        (
            ScientificSkillId.chart_visualization,
            {"rows": _rows(), "x_field": "x", "y_field": "y"},
            "series",
        ),
        (
            ScientificSkillId.fits_image_analysis,
            {
                "operation": "aperture_photometry",
                "image": [[1.0 for _ in range(9)] for _ in range(9)],
                "x": 4,
                "y": 4,
                "radius_pixels": 2,
            },
            "aperture_sum",
        ),
        (
            ScientificSkillId.wwt_scene,
            {"ra_hours": 0.7, "dec_degrees": 41.2},
            "center",
        ),
    ],
)
def test_registered_analysis_and_visualization_skills_return_hashed_typed_results(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
    output_key: str,
) -> None:
    result = build_scientific_skill_registry().execute(_request(skill_id, parameters))

    assert result.status == "completed"
    assert output_key in result.output
    if skill_id is ScientificSkillId.chart_visualization:
        assert result.output["series"][0]["points"] == [
            {"x": row["x"], "y": row["y"]} for row in _rows()
        ]
    assert result.output_hash == compute_canonical_payload_hash(result.output)


@pytest.mark.parametrize(
    ("skill_id", "parameters", "task_kind"),
    [
        (
            ScientificSkillId.tabular_machine_learning,
            {
                "rows": _rows(40),
                "feature_fields": ["x", "y"],
                "target_field": "label",
                "task_kind": "classification",
                "algorithm": "random_forest",
            },
            "classification",
        ),
        (
            ScientificSkillId.tabular_machine_learning,
            {
                "rows": _rows(40),
                "feature_fields": ["x"],
                "target_field": "y",
                "task_kind": "regression",
                "algorithm": "linear_regression",
            },
            "regression",
        ),
        (
            ScientificSkillId.time_series_forecast,
            {
                "rows": _rows(50),
                "time_field": "x",
                "target_field": "y",
                "lags": 4,
                "horizon": 3,
            },
            "forecast",
        ),
        (
            ScientificSkillId.image_classification,
            {
                "images": [
                    {
                        "label": "bright" if index >= 10 else "dim",
                        "pixels": [
                            [float(index), float(index + 1)],
                            [float(index + 2), float(index + 3)],
                        ],
                    }
                    for index in range(20)
                ]
            },
            "image_classification",
        ),
    ],
)
def test_registered_modeling_skills_are_deterministic_and_report_a_baseline(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
    task_kind: str,
) -> None:
    registry = build_scientific_skill_registry()
    first = registry.execute(_request(skill_id, parameters))
    second = registry.execute(_request(skill_id, parameters))

    assert first.output == second.output
    assert first.output["task_kind"] == task_kind
    assert "metrics" in first.output
    if skill_id is ScientificSkillId.tabular_machine_learning:
        assert "baseline_metrics" in first.output


def test_bundled_jpl_ephemeris_executes_without_runtime_download() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.ephemeris,
            {
                "target": "mars",
                "reference_target": "sun",
                "observed_at": "2026-08-14T00:00:00Z",
                "latitude_degrees": 31.2,
                "longitude_degrees": 121.5,
            },
        )
    )

    assert result.output["target"] == "mars"
    assert 0 <= float(result.output["ra_hours"]) < 24
    assert result.output["reference_target"] == "sun"
    assert 0 <= float(result.output["angular_separation_degrees"]) <= 180
    assert float(result.output["light_time_minutes"]) > 0


@pytest.mark.parametrize(
    ("operation", "parameters", "result_key"),
    [
        ("background_statistics", {}, "background_stddev"),
        ("centroid", {}, "x_centroid"),
        ("source_detection", {"threshold_sigma": 3}, "sources"),
        ("segmentation", {"threshold_sigma": 3}, "segments"),
        (
            "aperture_photometry",
            {"x": 12, "y": 12, "radius_pixels": 4},
            "aperture_sum",
        ),
    ],
)
def test_fits_image_analysis_exposes_bounded_photutils_operations(
    operation: str,
    parameters: dict[str, object],
    result_key: str,
) -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.fits_image_analysis,
            {"operation": operation, "image": _synthetic_star_field()} | parameters,
        )
    )

    assert result.output["operation"] == operation
    assert result.output["image_shape"] == [49, 49]
    assert result_key in result.output
    if operation == "source_detection":
        assert int(result.output["source_count"]) >= 2
    if operation == "segmentation":
        assert int(result.output["segment_count"]) >= 2


@pytest.mark.parametrize(
    ("event_type", "extra"),
    [
        ("moon_phases", {}),
        ("seasons", {}),
        ("lunar_eclipses", {}),
        (
            "twilight",
            {"latitude_degrees": 31.2, "longitude_degrees": 121.5},
        ),
        ("conjunctions_oppositions", {"target": "mars"}),
    ],
)
def test_celestial_events_uses_bundled_ephemeris_for_supported_event_families(
    event_type: str,
    extra: dict[str, object],
) -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.celestial_events,
            {
                "event_type": event_type,
                "start_at": "2026-01-01T00:00:00Z",
                "end_at": "2027-01-01T00:00:00Z",
            }
            | extra,
        )
    )

    assert result.output["event_type"] == event_type
    assert result.output["events"]


def test_modeling_rejects_a_split_that_cannot_represent_every_class() -> None:
    rows = [{"x": index, "label": f"class.{index}"} for index in range(10)]
    with pytest.raises(ValueError, match="represent every class"):
        build_scientific_skill_registry().execute(
            _request(
                ScientificSkillId.tabular_machine_learning,
                {
                    "rows": rows,
                    "feature_fields": ["x"],
                    "target_field": "label",
                },
            )
        )


def test_scientific_requests_reject_non_finite_and_chart_rejects_non_scalars() -> None:
    registry = build_scientific_skill_registry()
    with pytest.raises(ValueError, match="finite_number"):
        _request(ScientificSkillId.data_profile, {"rows": [{"x": float("nan")}]})
    with pytest.raises(ValueError, match="non-scalar"):
        registry.execute(
            _request(
                ScientificSkillId.chart_visualization,
                {
                    "rows": [{"x": 1, "y": [2]}],
                    "x_field": "x",
                    "y_field": "y",
                },
            )
        )


def test_modeling_rejects_fractional_integer_parameters_and_duplicate_times() -> None:
    registry = build_scientific_skill_registry()
    with pytest.raises(ValueError, match="lags must be an integer"):
        registry.execute(
            _request(
                ScientificSkillId.time_series_forecast,
                {
                    "rows": _rows(30),
                    "time_field": "x",
                    "target_field": "y",
                    "lags": 4.5,
                },
            )
        )
    rows = _rows(30)
    rows[1]["x"] = rows[0]["x"]
    with pytest.raises(ValueError, match="duplicate"):
        registry.execute(
            _request(
                ScientificSkillId.time_series_forecast,
                {
                    "rows": rows,
                    "time_field": "x",
                    "target_field": "y",
                    "lags": 4,
                },
            )
        )


class _MemoryStorage:
    def __init__(self) -> None:
        self.content: dict[str, bytes] = {}

    async def store(self, content: bytes, content_hash: str) -> str:
        assert sha256_content_hash(content) == content_hash
        self.content[content_hash] = content
        return f"memory/{content_hash.removeprefix('sha256:')}"

    async def retrieve(self, content_hash: str) -> bytes | None:
        return self.content.get(content_hash)

    def exists(self, content_hash: str) -> bool:
        return content_hash in self.content


class _SourceRecorder:
    async def record(self, **_: object) -> ScientificSourceReference:
        return ScientificSourceReference(
            source_snapshot_id=SNAPSHOT_ID,
            content_hash=HASH,
        )


def _contract(
    *,
    skill_id: ScientificSkillId,
    output: str,
    input_refs: Sequence[str] = (),
    parameters: dict[str, object] | None = None,
) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Execute a bounded scientific analysis",
            "target_objects": ["host_star"],
            "data_requirements": {},
            "requested_fields": ["star.mass"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {},
            "scientific_tasks": [
                {
                    "task_id": "task.primary",
                    "skill_id": skill_id,
                    "parameters": parameters or {},
                    "input_refs": list(input_refs),
                }
            ],
            "output_requirements": [output],
            "evidence_requirements": {},
            "quality_constraints": {},
        }
    )


@pytest.mark.anyio
async def test_step_adapter_resolves_dataset_input_and_builds_analysis_artifact() -> (
    None
):
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.data_profile,
        output="analysis_report",
        input_refs=[DATASET_VERSION_ID],
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={"rows": _rows()},
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID,
                        content_hash=HASH,
                    ),
                ),
                evidence_ids=(EVIDENCE_ID,),
            ),
        )

    output = await adapter.execute(
        step_key="analyzing_data",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    assert len(output.outcomes) == 1
    candidate = output.artifact_candidates[0]
    assert isinstance(candidate, AnalysisReportArtifactContent)
    assert candidate.related_artifact_version_ids == (DATASET_VERSION_ID,)
    assert candidate.result_blocks[0].payload["row_count"] == 30
    assert len(candidate.evidence_ids) == 1
    assert candidate.scientific_evidence[0].locator["upstream_evidence_ids"] == [
        EVIDENCE_ID
    ]


@pytest.mark.anyio
async def test_step_adapter_materializes_skyview_fits_and_builds_visualization() -> (
    None
):
    content = b"SIMPLE  =                    T"
    content_hash = sha256_content_hash(content)

    def fake_skyview(_: ScientificSkillRequest) -> dict[str, object]:
        return {
            "service": "skyview",
            "position": "Andromeda Galaxy",
            "survey": "DSS",
            "documents": [
                {
                    "document_id": "fits.1",
                    "media_type": "application/fits",
                    "content_base64": b64encode(content).decode("ascii"),
                    "content_hash": content_hash,
                    "shape": [1, 1],
                    "object": "Andromeda Galaxy",
                    "survey": "DSS",
                }
            ],
        }

    registry = ScientificSkillRegistry(
        [
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.skyview_fits,
                revision="1.0.0",
                handler=fake_skyview,
            )
        ]
    )
    storage = _MemoryStorage()
    adapter = ScientificStepAdapter(
        registry,
        content_storage=storage,
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.skyview_fits,
        output="visualization",
        parameters={"position": "Andromeda Galaxy", "survey": "DSS"},
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    output = await adapter.execute(
        step_key="acquiring_observations",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    candidate = output.artifact_candidates[0]
    assert isinstance(candidate, VisualizationArtifactContent)
    assert candidate.spec.mode == "fits_image"
    assert candidate.spec.content_hash == content_hash
    assert storage.content[content_hash] == content
    assert len(candidate.scientific_evidence) == 1


def test_input_binding_order_is_part_of_the_frozen_contract() -> None:
    task = ScientificTaskInput(
        task_id="task.profile",
        skill_id=ScientificSkillId.data_profile,
        input_refs=(DATASET_VERSION_ID,),
    )
    assert task.input_refs == (DATASET_VERSION_ID,)
    assert UUID(DATASET_VERSION_ID)
