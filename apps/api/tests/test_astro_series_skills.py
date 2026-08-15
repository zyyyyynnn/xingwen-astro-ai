from __future__ import annotations

from collections.abc import Sequence
from math import exp, pi, sin
from uuid import uuid4

import pytest

from app.schemas.core import (
    ResearchContractInput,
    ScientificSkillId,
    ScientificTaskInput,
)
from app.schemas.scientific_skills import (
    LightCurveArtifactContent,
    SpectrumArtifactContent,
)
from services.scientific_skills import (
    ScientificInputBinding,
    ScientificSkillRequest,
    ScientificSourceReference,
    ScientificStepAdapter,
    build_scientific_skill_registry,
)


PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())
DATASET_VERSION_ID = str(uuid4())
SNAPSHOT_ID = str(uuid4())
EVIDENCE_ID = str(uuid4())
HASH = "sha256:" + "a" * 64


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Storage:
    async def store(self, _content: bytes, _content_hash: str) -> str:
        raise AssertionError("series analysis must not materialize binary content")


class _Recorder:
    async def record(self, **_: object) -> tuple[ScientificSourceReference, ...]:
        raise AssertionError(
            "dataset-backed series analysis creates no remote snapshot"
        )


def _spectrum_rows() -> list[dict[str, object]]:
    return [
        {
            "wavelength": 5000.0 + index,
            "flux": (10.0 + index * 0.002)
            * (1.0 - 0.35 * exp(-((index - 50) ** 2) / 8.0)),
        }
        for index in range(101)
    ]


def _light_curve_rows(period: float = 2.5) -> list[dict[str, object]]:
    return [
        {
            "time": index * 0.1,
            "flux": 1.0 + 0.15 * sin(2.0 * pi * index * 0.1 / period),
        }
        for index in range(200)
    ]


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
    )


def _contract(
    skill_id: ScientificSkillId,
    output: str,
    parameters: dict[str, object],
) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": "Analyze a bounded astronomical series",
            "target_objects": ["observed_target"],
            "data_requirements": {},
            "requested_fields": ["series.value"],
            "source_scope": {"allowed_sources": ["uploaded_dataset"]},
            "paper_search_scope": {},
            "scientific_tasks": [
                {
                    "task_id": "task.series",
                    "skill_id": skill_id,
                    "parameters": parameters,
                    "input_refs": [DATASET_VERSION_ID],
                }
            ],
            "output_requirements": [output],
            "evidence_requirements": {},
            "quality_constraints": {},
        }
    )


async def _execute_artifact(
    skill_id: ScientificSkillId,
    output: str,
    parameters: dict[str, object],
    rows: list[dict[str, object]],
) -> object:
    adapter = ScientificStepAdapter(
        build_scientific_skill_registry(),
        content_storage=_Storage(),
        source_recorder=_Recorder(),
    )

    async def resolve(_: ScientificTaskInput) -> Sequence[ScientificInputBinding]:
        return (
            ScientificInputBinding(
                ref_id=DATASET_VERSION_ID,
                kind="artifact_version",
                parameters={"rows": rows},
                source_references=(
                    ScientificSourceReference(
                        source_snapshot_id=SNAPSHOT_ID,
                        content_hash=HASH,
                    ),
                ),
                evidence_ids=(EVIDENCE_ID,),
            ),
        )

    result = await adapter.execute(
        task_id="task.series",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        contract=_contract(skill_id, output, parameters),
        resolve_inputs=resolve,
    )
    return result.artifact_candidates[0]


@pytest.mark.anyio
async def test_spectrum_analysis_detects_a_line_and_builds_a_typed_artifact() -> None:
    parameters = {
        "wavelength_field": "wavelength",
        "flux_field": "flux",
        "object_name": "Synthetic star",
        "rest_wavelength": 5050.0,
    }
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.spectrum_analysis,
            {"rows": _spectrum_rows()} | parameters,
        )
    )
    assert result.output["detected_lines"]
    assert result.output["detected_lines"][0]["kind"] == "absorption"
    assert abs(float(result.output["radial_velocity_km_s"])) < 1

    artifact = await _execute_artifact(
        ScientificSkillId.spectrum_analysis,
        "spectrum",
        parameters,
        _spectrum_rows(),
    )
    assert isinstance(artifact, SpectrumArtifactContent)
    assert artifact.sample_count == 101
    assert artifact.detected_lines
    assert artifact.source_snapshot_ids == (SNAPSHOT_ID,)
    assert EVIDENCE_ID in artifact.evidence_ids


@pytest.mark.anyio
async def test_light_curve_analysis_recovers_period_and_builds_a_typed_artifact() -> (
    None
):
    parameters = {
        "time_field": "time",
        "value_field": "flux",
        "object_name": "Synthetic variable",
        "minimum_period": 1.0,
        "maximum_period": 5.0,
    }
    result = build_scientific_skill_registry().execute(
        _request(
            ScientificSkillId.light_curve_analysis,
            {"rows": _light_curve_rows()} | parameters,
        )
    )
    assert float(result.output["best_period"]) == pytest.approx(2.5, rel=0.03)
    assert result.output["rejected_sample_count"] == 0

    artifact = await _execute_artifact(
        ScientificSkillId.light_curve_analysis,
        "light_curve",
        parameters,
        _light_curve_rows(),
    )
    assert isinstance(artifact, LightCurveArtifactContent)
    assert artifact.best_period == pytest.approx(2.5, rel=0.03)
    assert artifact.accepted_sample_count == 200
    assert artifact.points[0].phase == pytest.approx(0)
