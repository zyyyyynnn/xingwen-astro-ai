from __future__ import annotations

from base64 import b64decode, b64encode
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from math import exp, pi, sin
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ResearchContract,
    ResearchContractInput,
    ScientificSkillId,
    ScientificTaskInput,
    compute_research_contract_content_hash,
)
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    LightCurveArtifactContent,
    ModelArtifactContent,
    ModelEvaluationArtifactContent,
    SpectrumArtifactContent,
    VisualizationArtifactContent,
)
from app.services.content_storage import sha256_content_hash
from app.services.public_presentation import build_artifact_presentation
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from app.workflow.scientific_admission import (
    _validate_source_table_admission_cardinality,
)
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
from services.scientific_skills.execution import (
    _admit_gaia_output,
    _normalize_gaia_data_fields,
    _publication_source_mode,
)


PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())
SNAPSHOT_ID = str(uuid4())
SECOND_SNAPSHOT_ID = str(uuid4())
EVIDENCE_ID = str(uuid4())
DATASET_VERSION_ID = str(uuid4())
MODEL_VERSION_ID = str(uuid4())
HASH = "sha256:" + "a" * 64
SECOND_HASH = "sha256:" + "b" * 64


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


def _image_training_parameters(count: int = 20) -> dict[str, object]:
    return {
        "images": [
            {
                "image_id": f"images/sample-{index:02d}.png",
                "label": "bright" if index >= count / 2 else "dim",
                "pixels": [index / count] * (32 * 32 * 3),
            }
            for index in range(count)
        ],
        "image_count": count,
        "source_total_pixels": count * 12 * 8,
        "image_shape": [32, 32, 3],
        "preprocessing": {
            "schema_version": "1.0.0",
            "color_mode": "RGB",
            "exif_transpose": True,
            "resize_height": 32,
            "resize_width": 32,
            "resize_mode": "contain_pad",
            "resampling": "bilinear",
            "normalization": "uint8_to_unit_interval",
        },
        "label_schema": [
            {"class_index": 0, "label": "bright", "sample_count": count // 2},
            {"class_index": 1, "label": "dim", "sample_count": count // 2},
        ],
    }


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


def test_data_profile_distinguishes_absent_fields_from_explicit_nulls() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.data_profile,
            {
                "rows": [
                    {"star.temperature": 3600},
                    {"planet.period": 2.616235},
                    {"planet.period": None},
                ]
            },
        )
    )
    fields = {item["field"]: item for item in result.output["fields"]}
    period = fields["planet.period"]
    assert period["null_count"] == 1
    assert period["non_null_count"] == 1
    assert period["present_count"] == 2
    assert period["absent_count"] == 1
    assert period["numeric_summary"]["count"] == 1
    assert period["numeric_summary"]["mean"] == 2.616235
    assert fields["star.temperature"]["null_count"] == 0
    assert fields["star.temperature"]["absent_count"] == 2


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
            {
                "view": {
                    "kind": "coordinates",
                    "center": {"ra_hours": 0.7, "dec_degrees": 41.2},
                    "field_of_view_degrees": 2,
                },
                "text_alternative": "A narrow WWT field centered on Andromeda Galaxy.",
            },
            "view",
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
            ScientificSkillId.time_series_classification,
            {
                "rows": [
                    {
                        "row_id": f"series.{index}",
                        "t0": float(index % 2),
                        "t1": float(index % 2) + 0.1,
                        "t2": float(index % 2) + 0.2,
                        "t3": float(index % 2) + 0.3,
                        "label": "variable" if index % 2 else "stable",
                    }
                    for index in range(40)
                ],
                "series_fields": ["t0", "t1", "t2", "t3"],
                "target_field": "label",
                "algorithm": "random_forest",
            },
            "time_series_classification",
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
            _image_training_parameters(),
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
    model_binary = first.output["model_binary"]
    assert model_binary["media_type"] == "application/onnx"
    content = b64decode(model_binary["content_base64"], validate=True)
    assert sha256_content_hash(content) == model_binary["content_hash"]
    import onnx

    onnx.checker.check_model(onnx.load_model_from_string(content))
    if skill_id in {
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_classification,
    }:
        assert "baseline_metrics" in first.output
    if skill_id is ScientificSkillId.image_classification:
        assert first.output["image_shape"] == [32, 32, 3]
        assert first.output["label_schema"][0]["label"] == "bright"


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
        ("solar_eclipses", {}),
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


def _inference_model_parameters() -> dict[str, object]:
    trained = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.tabular_machine_learning,
            {
                "rows": _rows(40),
                "feature_fields": ["x", "y"],
                "target_field": "label",
                "task_kind": "classification",
                "algorithm": "random_forest",
            },
        )
    )
    binary = trained.output["model_binary"]
    assert isinstance(binary, dict)
    return {
        "model_artifact_version_id": MODEL_VERSION_ID,
        "model_id": "model.primary",
        "task_kind": "classification",
        "feature_fields": ["x", "y"],
        "target_field": "label",
        "content_base64": binary["content_base64"],
        "content_hash": binary["content_hash"],
        "media_type": binary["media_type"],
        "input_name": binary["input_name"],
        "output_names": binary["output_names"],
        "input_shape": binary["input_shape"],
        "opset_imports": binary["opset_imports"],
    }


def test_model_inference_runs_only_the_frozen_onnx_contract_on_cpu() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.model_inference,
            {
                "model": _inference_model_parameters(),
                "rows": _rows(5),
                "dataset_artifact_version_id": DATASET_VERSION_ID,
            },
        )
    )

    assert result.output["model_artifact_version_id"] == MODEL_VERSION_ID
    assert result.output["dataset_artifact_version_id"] == DATASET_VERSION_ID
    assert result.output["prediction_count"] == 5
    assert len(result.output["predictions"]) == 5


def test_model_inference_rejects_python_object_serialization() -> None:
    model = _inference_model_parameters()
    model["media_type"] = "application/vnd.sklearn"

    with pytest.raises(ValueError, match="only ONNX"):
        build_scientific_skill_registry().execute(
            _request(
                ScientificSkillId.model_inference,
                {
                    "model": model,
                    "rows": _rows(2),
                    "dataset_artifact_version_id": DATASET_VERSION_ID,
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
    async def record(self, **_: object) -> tuple[ScientificSourceReference, ...]:
        return (
            ScientificSourceReference(
                source_snapshot_id=SNAPSHOT_ID,
                content_hash=HASH,
            ),
        )


class _TwoSourceRecorder:
    async def record(self, **_: object) -> tuple[ScientificSourceReference, ...]:
        return (
            ScientificSourceReference(
                source_snapshot_id=SNAPSHOT_ID,
                content_hash=HASH,
            ),
            ScientificSourceReference(
                source_snapshot_id=SECOND_SNAPSHOT_ID,
                content_hash=SECOND_HASH,
            ),
        )


class _GaiaSourceRecorder:
    async def record(self, **_: object) -> tuple[ScientificSourceReference, ...]:
        return (
            ScientificSourceReference(
                source_snapshot_id=SNAPSHOT_ID,
                content_hash=HASH,
                source_id="esa_gaia_dr3.gaiadr3.gaia_source",
                query_hash="sha256:" + "b" * 64,
                retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
            ),
        )


def _contract(
    *,
    skill_id: ScientificSkillId,
    output: str | Sequence[str],
    input_refs: Sequence[str] = (),
    parameters: dict[str, object] | None = None,
    requested_fields: Sequence[str] | None = None,
) -> ResearchContract:
    contract_input = ResearchContractInput.model_validate(
        {
            "research_goal": "Execute a bounded scientific analysis",
            "target_objects": ["host_star"],
            "data_requirements": {
                "unit_policy": "canonical",
                "document_source_policy": "disabled",
            },
            "requested_fields": list(
                requested_fields
                or (
                    [
                        "star.gaia_dr3_id",
                        "system.right_ascension",
                        "system.declination",
                    ]
                    if skill_id is ScientificSkillId.gaia_cone_search
                    else ["star.mass"]
                )
            ),
            "source_scope": {
                "allowed_sources": [
                    "esa_gaia_dr3"
                    if skill_id is ScientificSkillId.gaia_cone_search
                    else "nasa_exoplanet_archive"
                ]
            },
            "paper_search_scope": {},
            "scientific_tasks": [
                {
                    "task_id": "task.primary",
                    "skill_id": skill_id,
                    "parameters": parameters or {},
                    "input_refs": list(input_refs),
                }
            ],
            "output_requirements": [output]
            if isinstance(output, str)
            else list(output),
            "evidence_requirements": {},
            "quality_constraints": {},
        }
    )

    return ResearchContract.model_validate(
        contract_input.model_dump(mode="json")
        | {
            "id": "contract.scientific-test",
            "project_id": PROJECT_ID,
            "version": 1,
            "created_from_draft_id": "draft.scientific-test",
            "created_at": datetime(2026, 8, 20, tzinfo=UTC),
            "content_hash": compute_research_contract_content_hash(contract_input),
        }
    )


@pytest.mark.parametrize(
    ("source_mode", "expected"),
    [
        ("live", "live"),
        ("cached", "cached"),
        ("recorded", "recorded"),
        ("fixture", "fixture"),
    ],
)
def test_scientific_publication_source_mode_preserves_non_live_origins(
    source_mode: str, expected: str
) -> None:
    outcome = SimpleNamespace(
        task=SimpleNamespace(skill_id=ScientificSkillId.data_profile),
        result=SimpleNamespace(output={"acquisition": {"source_mode": source_mode}}),
    )

    assert _publication_source_mode(outcome) == expected


def test_scientific_publication_source_mode_rejects_unknown_origin() -> None:
    outcome = SimpleNamespace(
        task=SimpleNamespace(skill_id=ScientificSkillId.data_profile),
        result=SimpleNamespace(output={"acquisition": {"source_mode": "mock"}}),
    )

    with pytest.raises(ValueError, match="source_mode is unknown"):
        _publication_source_mode(outcome)


def test_scientific_publication_source_mode_rejects_missing_gaia_provenance() -> None:
    outcome = SimpleNamespace(
        task=SimpleNamespace(skill_id=ScientificSkillId.gaia_cone_search),
        result=SimpleNamespace(output={}),
    )

    with pytest.raises(ValueError, match="Gaia acquisition provenance is missing"):
        _publication_source_mode(outcome)


@pytest.mark.anyio
async def test_gaia_unsupported_dataset_field_rejects_before_resolver_or_executor() -> (
    None
):
    class _NeverCalledExecutor:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, _: ScientificSkillRequest) -> object:
            self.calls += 1
            raise AssertionError("Gaia executor must not be called")

    executor = _NeverCalledExecutor()
    adapter = ScientificStepAdapter(
        executor=executor,
        content_storage=_MemoryStorage(),
        source_recorder=_GaiaSourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.gaia_cone_search,
        output="dataset",
        parameters={
            "ra_degrees": 10.0,
            "dec_degrees": 20.0,
            "radius_degrees": 0.1,
        },
        requested_fields=("star.mass",),
    )
    resolver_calls = 0

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        nonlocal resolver_calls
        resolver_calls += 1
        return ()

    with pytest.raises(ValueError, match="not admitted by the source contract"):
        await adapter.execute(
            task_id="task.primary",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            contract=contract,
            resolve_inputs=resolve,
        )

    assert resolver_calls == 0
    assert executor.calls == 0


def test_gaia_data_artifact_fields_are_raw_json_array_union() -> None:
    task = ScientificTaskInput(
        task_id="task.primary",
        skill_id=ScientificSkillId.gaia_cone_search,
        parameters={"fields": ["teff_gspphot"], "ra_degrees": 10.0},
    )
    contract = _contract(
        skill_id=ScientificSkillId.gaia_cone_search,
        output="dataset",
        parameters={"ra_degrees": 10.0, "dec_degrees": 20.0},
        requested_fields=("system.right_ascension",),
    )

    normalized = _normalize_gaia_data_fields(task, contract)

    assert normalized.parameters["fields"] == ["teff_gspphot", "ra", "dec"]


@pytest.mark.parametrize(
    ("status", "truncated", "rows"),
    [
        (
            "complete",
            True,
            [{"source_id": "65214061869072512", "ra": 56.7, "dec": 24.1}],
        ),
        (
            "truncated",
            False,
            [{"source_id": "65214061869072512", "ra": 56.7, "dec": 24.1}],
        ),
        (
            "empty",
            False,
            [{"source_id": "65214061869072512", "ra": 56.7, "dec": 24.1}],
        ),
    ],
)
def test_gaia_admission_rejects_inconsistent_completion_attestation(
    status: str, truncated: bool, rows: list[dict[str, object]]
) -> None:
    output = {
        "fields": ["source_id", "ra", "dec"],
        "rows": rows,
        "result_status": status,
        "truncated": truncated,
    }

    with pytest.raises(ValueError, match="completion status is inconsistent"):
        _admit_gaia_output(
            output,
            produced_sources=(
                ScientificSourceReference(
                    source_snapshot_id=SNAPSHOT_ID,
                    content_hash=HASH,
                    source_id="esa_gaia_dr3.gaiadr3.gaia_source",
                    query_hash="sha256:" + "b" * 64,
                    retrieved_at=datetime(2026, 8, 20, tzinfo=UTC),
                ),
            ),
            evidence_scope_id="evidence.gaia-status-test",
            contract=_contract(
                skill_id=ScientificSkillId.gaia_cone_search,
                output="dataset",
                parameters={
                    "ra_degrees": 10.0,
                    "dec_degrees": 20.0,
                    "radius_degrees": 0.1,
                },
            ),
        )


@pytest.mark.anyio
async def test_gaia_source_table_is_readmitted_and_emits_cell_evidence() -> None:
    def handler(_: ScientificSkillRequest) -> dict[str, object]:
        return {
            "service": "gaia_archive",
            "fields": ["source_id", "ra", "dec"],
            "rows": [{"source_id": "65214061869072512", "ra": 56.7, "dec": 24.1}],
            "row_count": 1,
            "truncated": False,
            "result_status": "complete",
            "source_table_admission": {"overall_status": "pass"},
            "acquisition": {"source_mode": "cached"},
        }

    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(gaia_handler=handler),
        content_storage=_MemoryStorage(),
        source_recorder=_GaiaSourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.gaia_cone_search,
        output="analysis_report",
        parameters={"ra_degrees": 56.7, "dec_degrees": 24.1},
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    report = output.artifact_candidates[0]
    assert isinstance(report, AnalysisReportArtifactContent)
    admission = report.source_table_admissions[0]
    assert admission.overall_status.value == "pass"
    assert admission.research_contract_content_hash == contract.content_hash
    assert report.result_blocks[0].payload["column_metadata"][0]["field"] == "column_1"
    assert {item.locator["raw_field"] for item in report.scientific_evidence} == {
        "source_id",
        "ra",
        "dec",
    }
    assert all(
        item.locator["source_role"] == "single" for item in report.scientific_evidence
    )
    missing_attestation = report.model_copy(update={"source_table_admissions": ()})
    with pytest.raises(PublicationAdmissionError, match="cardinality"):
        _validate_source_table_admission_cardinality(
            replace(output, artifact_candidates=(missing_attestation,))
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
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    assert output.task_id == "task.primary"
    assert output.skill_id is ScientificSkillId.data_profile
    candidate = output.artifact_candidates[0]
    assert isinstance(candidate, AnalysisReportArtifactContent)
    assert candidate.related_artifact_version_ids == (DATASET_VERSION_ID,)
    assert candidate.result_blocks[0].payload["row_count"] == 30
    assert set(candidate.evidence_ids) == {
        item.evidence_id for item in candidate.scientific_evidence
    }
    assert candidate.scientific_evidence[0].locator["upstream_evidence_ids"] == [
        EVIDENCE_ID
    ]
    admitted = admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=lambda _context: None,
        domain_validator=lambda _context: None,
        quality_validator=lambda _context: None,
    )
    assert {
        item.persisted_evidence_id for item in admitted.owned_evidence_materializations
    } == set(candidate.evidence_ids)
    assert {
        item.persisted_source_snapshot_id
        for item in admitted.owned_evidence_materializations
    } == set(candidate.source_snapshot_ids)


@pytest.mark.anyio
async def test_analysis_assembly_exposes_each_structured_scientific_result() -> None:
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
            ),
        )

    cases = (
        (ScientificSkillId.data_profile, {}, {"分析摘要", "字段概览"}),
        (
            ScientificSkillId.statistical_analysis,
            {
                "fields": ["x", "y"],
                "hypothesis_tests": [
                    {"kind": "one_sample_t", "field": "x", "expected_mean": 0}
                ],
            },
            {"分析摘要", "描述统计", "假设检验"},
        ),
        (
            ScientificSkillId.correlation_analysis,
            {"fields": ["x", "y"]},
            {"相关系数"},
        ),
    )
    for skill_id, parameters, expected_labels in cases:
        adapter = ScientificStepAdapter(
            build_scientific_skill_registry(),
            content_storage=_MemoryStorage(),
            source_recorder=_SourceRecorder(),
        )
        output = await adapter.execute(
            task_id="task.primary",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            contract=_contract(
                skill_id=skill_id,
                output="analysis_report",
                input_refs=[DATASET_VERSION_ID],
                parameters=parameters,
            ),
            resolve_inputs=resolve,
        )

        report = output.artifact_candidates[0]
        assert isinstance(report, AnalysisReportArtifactContent)
        assert {block.label for block in report.result_blocks} == expected_labels
        assert skill_id.value not in report.title
        assert skill_id.value not in report.summary


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("skill_id", "parameters"),
    (
        (
            ScientificSkillId.clustering_analysis,
            {"feature_fields": ["x", "y"], "cluster_count": 3},
        ),
        (
            ScientificSkillId.anomaly_detection,
            {"feature_fields": ["x", "y"], "contamination": 0.1},
        ),
    ),
)
async def test_descriptor_drives_unsupervised_report_and_chart_candidates(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> None:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=skill_id,
        output=("analysis_report", "visualization"),
        input_refs=[DATASET_VERSION_ID],
        parameters=parameters,
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={"rows": _rows(40)},
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID,
                        content_hash=HASH,
                    ),
                ),
            ),
        )

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    assert tuple(candidate.kind for candidate in output.artifact_candidates) == (
        "analysis_report",
        "visualization",
    )
    visualization = output.artifact_candidates[1]
    assert isinstance(visualization, VisualizationArtifactContent)
    assert visualization.spec.mode == "chart"
    assert visualization.spec.x_axis.field == "pca_x"
    assert visualization.spec.y_axis.field == "pca_y"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("skill_id", "parameters"),
    (
        (
            ScientificSkillId.clustering_analysis,
            {"feature_fields": ["x", "y"], "cluster_count": 3},
        ),
        (
            ScientificSkillId.anomaly_detection,
            {"feature_fields": ["x", "y"], "contamination": 0.1},
        ),
    ),
)
async def test_direct_research_input_pins_chart_to_its_source_snapshot(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> None:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=skill_id,
        output=("analysis_report", "visualization"),
        input_refs=[SECOND_SNAPSHOT_ID],
        parameters=parameters,
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=SECOND_SNAPSHOT_ID,
                kind="content_blob",
                parameters={"rows": _rows(40)},
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID,
                        content_hash=HASH,
                    ),
                ),
            ),
        )

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    visualization = output.artifact_candidates[1]
    assert isinstance(visualization, VisualizationArtifactContent)
    assert visualization.spec.dataset_artifact_version_id is None
    assert visualization.spec.source_snapshot_id == SNAPSHOT_ID


@pytest.mark.anyio
async def test_acquisition_skills_publish_the_typed_artifacts_they_declare() -> None:
    production = build_scientific_skill_registry()
    spectrum_output = production.execute(
        _request(
            ScientificSkillId.spectrum_analysis,
            {
                "rows": [
                    {
                        "wavelength": 5000 + index,
                        "flux": 1.5 if index == 16 else 1 + 0.01 * (index % 3),
                    }
                    for index in range(32)
                ],
                "wavelength_field": "wavelength",
                "flux_field": "flux",
                "object_name": "SDSS target",
            },
        )
    ).output
    light_curve_output = production.execute(
        _request(
            ScientificSkillId.light_curve_analysis,
            {
                "rows": [
                    {
                        "time": index * 0.1,
                        "flux": 1 + 0.05 * sin(2 * pi * index / 10),
                    }
                    for index in range(40)
                ],
                "time_field": "time",
                "value_field": "flux",
                "object_name": "TIC target",
            },
        )
    ).output

    def acquire_spectrum(_: ScientificSkillRequest) -> dict[str, object]:
        return {
            **spectrum_output,
            "acquisition": {"source_mode": "cached"},
        }

    def acquire_light_curve(_: ScientificSkillRequest) -> dict[str, object]:
        return dict(light_curve_output)

    registry = ScientificSkillRegistry(
        [
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.spectrum_acquisition,
                revision="1.0.0",
                phase="acquiring_observations",
                accepted_input_kinds=("sky_coordinates",),
                produced_artifact_kinds=("spectrum", "analysis_report"),
                workload_class="network",
                handler=acquire_spectrum,
            ),
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.light_curve_acquisition,
                revision="1.0.0",
                phase="acquiring_observations",
                accepted_input_kinds=("target_name",),
                produced_artifact_kinds=("light_curve", "analysis_report"),
                workload_class="network",
                handler=acquire_light_curve,
            ),
        ]
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    cases = (
        (
            ScientificSkillId.spectrum_acquisition,
            ("spectrum", "analysis_report"),
            {"plate": 1234, "mjd": 59_000, "fiber": 42},
            SpectrumArtifactContent,
        ),
        (
            ScientificSkillId.light_curve_acquisition,
            ("light_curve", "analysis_report"),
            {"tic_id": "123", "product_filename": "tess-lightcurve.fits"},
            LightCurveArtifactContent,
        ),
    )
    for skill_id, outputs, parameters, expected_type in cases:
        adapter = ScientificStepAdapter(
            registry,
            content_storage=_MemoryStorage(),
            source_recorder=_SourceRecorder(),
        )
        output = await adapter.execute(
            task_id="task.primary",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            contract=_contract(
                skill_id=skill_id,
                output=outputs,
                parameters=parameters,
            ),
            resolve_inputs=resolve,
        )

        typed_candidate = output.artifact_candidates[0]
        assert isinstance(typed_candidate, expected_type)
        assert typed_candidate.skill_executions[0].skill_id is skill_id
        assert output.source_mode == (
            "cached" if skill_id is ScientificSkillId.spectrum_acquisition else "live"
        )


@pytest.mark.anyio
async def test_step_adapter_materializes_an_onnx_model_binary() -> None:
    storage = _MemoryStorage()
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=storage,
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.tabular_machine_learning,
        output=("model_evaluation", "model_artifact"),
        input_refs=[DATASET_VERSION_ID],
        parameters={
            "feature_fields": ["x", "y"],
            "target_field": "label",
            "task_kind": "classification",
            "algorithm": "random_forest",
            "split_strategy": "entity",
            "entity_field": "object_id",
        },
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={
                    "rows": [
                        {**row, "object_id": f"star.{index % 8}"}
                        for index, row in enumerate(_rows(40))
                    ]
                },
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
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    evaluation, model = output.artifact_candidates
    assert isinstance(evaluation, ModelEvaluationArtifactContent)
    assert isinstance(model, ModelArtifactContent)
    assert evaluation.model_binary is not None
    assert evaluation.model_binary == model.model_binary
    assert model.model_binary.media_type == "application/onnx"
    assert model.status == "active"
    assert evaluation.split.strategy == "entity"
    assert evaluation.split.field == "object_id"
    assert evaluation.split.cross_validation_folds == 5
    assert evaluation.split.train_cutoff is None
    assert evaluation.diagnostics is not None
    assert evaluation.diagnostics.confusion_matrix is not None
    assert (
        sum(sum(row) for row in evaluation.diagnostics.confusion_matrix.rows)
        == evaluation.diagnostics.evaluated_sample_count
    )
    assert not evaluation.diagnostics.regression_predictions
    metric_by_key = {metric.metric_key: metric for metric in evaluation.metrics}
    assert metric_by_key["accuracy"].category == "holdout"
    assert metric_by_key["cv_accuracy_mean"].category == "cross_validation"
    assert metric_by_key["cv_accuracy_mean"].label == "准确率 · 均值"
    assert any(metric.category == "feature_importance" for metric in evaluation.metrics)
    baseline_by_key = {
        metric.metric_key: metric for metric in evaluation.baseline_metrics
    }
    for metric in evaluation.metrics:
        if metric.metric_key in baseline_by_key:
            assert baseline_by_key[metric.metric_key].metric_id != metric.metric_id
            assert (
                baseline_by_key[metric.metric_key].optimization == metric.optimization
            )
    assert any(
        "never cross the train/test boundary" in item for item in evaluation.limitations
    )
    assert model.limitations == evaluation.limitations
    assert model.input_shape[0] is None
    assert model.input_dtype == "FLOAT"
    assert set(model.output_metadata) == set(model.output_names)
    label_metadata = model.output_metadata[model.output_names[0]]
    probability_metadata = model.output_metadata[model.output_names[1]]
    assert label_metadata is not None
    assert label_metadata.value_kind == "tensor"
    assert label_metadata.dtype == "STRING"
    assert label_metadata.shape == (None,)
    assert probability_metadata is not None
    assert probability_metadata.value_kind == "sequence"
    assert probability_metadata.dtype is None
    assert probability_metadata.shape is None
    assert model.opset_imports
    assert storage.content[model.model_binary.content_hash]

    evaluation_presentation = build_artifact_presentation(
        ArtifactKind.model_evaluation,
        evaluation.model_dump(mode="json"),
        (),
    )
    evaluation_facts = {
        fact.label: fact.values for fact in evaluation_presentation.facts
    }
    assert evaluation_facts["算法"] == ("random_forest",)
    assert evaluation_facts["训练数据"] == ("研究数据集",)
    assert evaluation_facts["划分方式"] == ("实体隔离划分",)
    assert {"算法版本", "训练输入", "随机种子"}.isdisjoint(evaluation_facts)
    assert evaluation_presentation.tables[0].title.startswith("混淆矩阵")
    assert (
        sum(int(row.cells[1].value) for row in evaluation_presentation.tables[0].rows)
        == evaluation.diagnostics.evaluated_sample_count
    )

    model_presentation = build_artifact_presentation(
        ArtifactKind.model_artifact,
        model.model_dump(mode="json"),
        (),
    )
    model_facts = {fact.label: fact.values for fact in model_presentation.facts}
    assert model_facts["算法"] == ("random_forest",)
    assert {"状态", "算法版本", "运行依赖"}.isdisjoint(model_facts)


@pytest.mark.anyio
async def test_forecast_publishes_cutoff_baseline_and_original_test_rows() -> None:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    rows = [
        {"row_id": f"epoch.{index}", "time": index, "flux": 1 + 0.01 * sin(index)}
        for index in range(50)
    ]

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={"rows": rows},
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID, content_hash=HASH
                    ),
                ),
                evidence_ids=(EVIDENCE_ID,),
            ),
        )

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=_contract(
            skill_id=ScientificSkillId.time_series_forecast,
            output=("model_evaluation", "model_artifact"),
            input_refs=[DATASET_VERSION_ID],
            parameters={
                "time_field": "time",
                "target_field": "flux",
                "lags": 4,
                "horizon": 3,
            },
        ),
        resolve_inputs=resolve,
    )
    evaluation, model = output.artifact_candidates
    assert isinstance(evaluation, ModelEvaluationArtifactContent)
    assert isinstance(model, ModelArtifactContent)
    assert evaluation.split.strategy == "time"
    assert evaluation.split.field == "time"
    assert evaluation.split.train_cutoff == 39
    assert evaluation.split.random_seed is None
    assert evaluation.feature_fields == ("lag_4", "lag_3", "lag_2", "lag_1")
    diagnostics = evaluation.diagnostics
    assert diagnostics is not None
    assert diagnostics.evaluated_sample_count == 10
    assert diagnostics.confusion_matrix is None
    assert [point.row_id for point in diagnostics.regression_predictions] == [
        row["row_id"] for row in rows[40:]
    ]
    assert [point.actual for point in diagnostics.regression_predictions] == [
        row["flux"] for row in rows[40:]
    ]
    assert [point.step for point in diagnostics.forecast] == [1, 2, 3]
    baseline = {metric.metric_key: metric for metric in evaluation.baseline_metrics}
    expected_mae = (
        sum(
            abs(rows[index]["flux"] - rows[index - 1]["flux"])
            for index in range(40, 50)
        )
        / 10
    )
    assert baseline["mean_absolute_error"].value == pytest.approx(expected_mae)
    assert baseline["mean_absolute_error"].optimization == "minimize"
    assert model.input_shape == (None, 4)
    presentation = build_artifact_presentation(
        ArtifactKind.model_evaluation, evaluation.model_dump(mode="json"), ()
    )
    assert [table.total_row_count for table in presentation.tables] == [10, 3]


@pytest.mark.anyio
async def test_image_dataset_publishes_source_pinned_training_specification() -> None:
    storage = _MemoryStorage()
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=storage,
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.image_classification,
        output=("model_evaluation", "model_artifact"),
        input_refs=[SNAPSHOT_ID],
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=SNAPSHOT_ID,
                kind="content_blob",
                parameters=_image_training_parameters(),
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID,
                        content_hash=HASH,
                    ),
                ),
            ),
        )

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    evaluation, model = output.artifact_candidates
    assert isinstance(evaluation, ModelEvaluationArtifactContent)
    assert isinstance(model, ModelArtifactContent)
    assert evaluation.training_input.kind == "source_snapshot"
    assert evaluation.training_input.ref_id == SNAPSHOT_ID
    assert evaluation.image_training is not None
    assert model.image_training == evaluation.image_training
    assert model.image_training.image_shape == (32, 32, 3)
    assert model.image_training.label_schema[0].label == "bright"
    assert any(item.startswith("pillow==") for item in model.dependency_revisions)


@pytest.mark.anyio
async def test_step_adapter_publishes_version_pinned_model_predictions() -> None:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.model_inference,
        output="analysis_report",
        input_refs=[MODEL_VERSION_ID, DATASET_VERSION_ID],
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        source = ScientificSourceReference(
            source_snapshot_id=SNAPSHOT_ID,
            content_hash=HASH,
        )
        return (
            ScientificInputBinding(
                ref_id=MODEL_VERSION_ID,
                kind="artifact_version",
                parameters={"model": _inference_model_parameters()},
                source_references=(source,),
                evidence_ids=(EVIDENCE_ID,),
            ),
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={
                    "rows": _rows(5),
                    "dataset_artifact_version_id": DATASET_VERSION_ID,
                },
                source_references=(source,),
                evidence_ids=(EVIDENCE_ID,),
            ),
        )

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    candidate = output.artifact_candidates[0]
    assert isinstance(candidate, AnalysisReportArtifactContent)
    assert candidate.related_artifact_version_ids == (
        MODEL_VERSION_ID,
        DATASET_VERSION_ID,
    )
    assert candidate.result_blocks[0].payload["prediction_count"] == 5


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
                phase="acquiring_observations",
                accepted_input_kinds=("sky_coordinates",),
                produced_artifact_kinds=("fits_image",),
                workload_class="network",
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
        task_id="task.primary",
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


@pytest.mark.anyio
async def test_step_adapter_preserves_each_produced_physical_source_snapshot() -> None:
    def fake_ephemeris(_: ScientificSkillRequest) -> dict[str, object]:
        return {"target": "mars", "distance_au": 1.2}

    registry = ScientificSkillRegistry(
        [
            ScientificSkillDefinition(
                skill_id=ScientificSkillId.ephemeris,
                revision="1.0.0",
                phase="acquiring_observations",
                accepted_input_kinds=("target_name", "time_range"),
                produced_artifact_kinds=("ephemeris_coordinates",),
                workload_class="cpu_light",
                handler=fake_ephemeris,
            )
        ]
    )
    adapter = ScientificStepAdapter(
        registry,
        content_storage=_MemoryStorage(),
        source_recorder=_TwoSourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.ephemeris,
        output="analysis_report",
        parameters={"target": "mars", "observed_at": "2026-01-01T00:00:00Z"},
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    output = await adapter.execute(
        task_id="task.primary",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=contract,
        resolve_inputs=resolve,
    )

    candidate = output.artifact_candidates[0]
    assert candidate.source_snapshot_ids == tuple(
        sorted((SNAPSHOT_ID, SECOND_SNAPSHOT_ID))
    )


@pytest.mark.anyio
async def test_step_adapter_rejects_a_task_not_frozen_in_the_contract() -> None:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_MemoryStorage(),
        source_recorder=_SourceRecorder(),
    )
    contract = _contract(
        skill_id=ScientificSkillId.data_profile,
        output="analysis_report",
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return ()

    with pytest.raises(ValueError, match="exactly one task"):
        await adapter.execute(
            task_id="task.not_authorized",
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            contract=contract,
            resolve_inputs=resolve,
        )


def test_input_binding_order_is_part_of_the_frozen_contract() -> None:
    task = ScientificTaskInput(
        task_id="task.profile",
        skill_id=ScientificSkillId.data_profile,
        input_refs=(DATASET_VERSION_ID,),
    )
    assert task.input_refs == (DATASET_VERSION_ID,)
    assert UUID(DATASET_VERSION_ID)
