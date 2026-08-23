"""Workflow adapter and Artifact assembler for registered scientific skills.

The contract stores only bounded configuration and immutable input references.
This module resolves those references at execution time, runs the registered
algorithm behind one seam, materializes binary outputs through the existing
content-addressed store, and emits canonical Artifact candidates.
"""

from __future__ import annotations

import asyncio
from base64 import b64decode
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import version
from time import monotonic
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from app.schemas.core import (
    ArtifactKind,
    ResearchContract,
    ScientificSkillId,
    ScientificTaskInput,
)
from app.schemas.enums import SourceMode
from app.schemas.source_table import SourceTableAdmission
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    ChartVisualizationSpec,
    FitsImageVisualizationSpec,
    ImageTrainingSpecification,
    LightCurveArtifactContent,
    ModelArtifactContent,
    ModelBinaryReference,
    ModelEvaluationArtifactContent,
    ModelSplitReference,
    ScientificMetric,
    ScientificEvidence,
    ScientificResultBlock,
    ScientificSkillExecution,
    SpectrumArtifactContent,
    VisualizationArtifactContent,
    WwtSceneVisualizationSpec,
    scientific_artifact_output_hash,
)
from app.schemas.scientific_capabilities import (
    capability_for,
    produced_artifact_kinds as _capability_produced_kinds,
    produces_source_snapshot as _capability_produces_snapshot,
    scientific_skill_phase,
)
from app.services.content_storage import ContentStorage
from services.data_pipeline.source_table import (
    GAIA_SOURCE_ID,
    admit_source_table,
    gaia_source_contract,
)
from .registry import ScientificSkillRegistry
from .types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    ScientificSkillResult,
    ScientificSourceReference,
)


InputKind = Literal["artifact_version", "source_snapshot", "content_blob"]


@dataclass(frozen=True, slots=True)
class ScientificInputBinding:
    """Resolved immutable input plus parameters injected into one task."""

    ref_id: str
    kind: InputKind
    parameters: Mapping[str, object]
    source_references: tuple[ScientificSourceReference, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScientificTaskExecutionOutcome:
    task: ScientificTaskInput
    result: ScientificSkillResult
    materialized_output: Mapping[str, object]
    duration_ms: int
    source_snapshot_ids: tuple[str, ...]
    produced_source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    artifact_version_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScientificStepOutput:
    task_id: str
    skill_id: ScientificSkillId
    source_mode: SourceMode
    artifact_candidates: tuple[
        AnalysisReportArtifactContent
        | VisualizationArtifactContent
        | SpectrumArtifactContent
        | LightCurveArtifactContent
        | ModelEvaluationArtifactContent
        | ModelArtifactContent,
        ...,
    ]
    source_snapshot_ids: tuple[str, ...] = ()
    source_table_admissions: tuple[SourceTableAdmission, ...] = ()


def _publication_source_mode(
    outcome: ScientificTaskExecutionOutcome,
) -> SourceMode:
    acquisition = outcome.result.output.get("acquisition")
    if not isinstance(acquisition, Mapping):
        if outcome.task.skill_id is ScientificSkillId.gaia_cone_search:
            raise ValueError("Gaia acquisition provenance is missing")
        return SourceMode.live
    source_mode = acquisition.get("source_mode")
    try:
        return SourceMode(source_mode)
    except ValueError as error:
        raise ValueError("scientific acquisition source_mode is unknown") from error


class ScientificProducedSourceRecorder(Protocol):
    async def record(
        self,
        *,
        project_id: str,
        run_id: str,
        task: ScientificTaskInput,
        request: ScientificSkillRequest,
        result: ScientificSkillResult,
    ) -> tuple[ScientificSourceReference, ...]:
        """Persist each physical source response and return its snapshot identities."""


ScientificInputResolver = Callable[
    [ScientificTaskInput], Awaitable[Sequence[ScientificInputBinding]]
]


class ScientificSkillExecutor(Protocol):
    async def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        """Execute one validated request and return its bounded result."""


_GAIA_DATA_ARTIFACT_KINDS = frozenset(
    {
        ArtifactKind.dataset,
        ArtifactKind.field_dictionary,
        ArtifactKind.source_collection,
    }
)


def _normalize_gaia_data_fields(
    task: ScientificTaskInput,
    contract: ResearchContract,
) -> ScientificTaskInput:
    """Translate Contract canonical fields into the Gaia adapter's raw projection."""

    if (
        task.skill_id is not ScientificSkillId.gaia_cone_search
        or not _GAIA_DATA_ARTIFACT_KINDS.intersection(contract.output_requirements)
    ):
        return task
    raw_by_canonical = {
        item.canonical_field_id: item.raw_field for item in gaia_source_contract()
    }
    unsupported = tuple(
        field_id
        for field_id in contract.requested_fields
        if field_id not in raw_by_canonical
    )
    if unsupported:
        raise ValueError(
            "Gaia Data Artifact requested fields are not admitted by the source contract: "
            + ", ".join(unsupported)
        )
    explicit = task.parameters.get("fields")
    if explicit is None:
        analysis_fields: tuple[str, ...] = ()
    elif isinstance(explicit, (list, tuple)) and all(
        isinstance(field, str) for field in explicit
    ):
        analysis_fields = tuple(explicit)
    else:
        raise ValueError("Gaia fields must be a list of raw source field names")
    requested_raw_fields = tuple(
        raw_by_canonical[field_id] for field_id in contract.requested_fields
    )
    normalized_fields = list(dict.fromkeys((*analysis_fields, *requested_raw_fields)))
    return task.model_copy(
        update={
            "parameters": {
                **task.parameters,
                "fields": normalized_fields,
            }
        }
    )


class InProcessScientificSkillExecutor:
    """Injectable executor for deterministic unit tests and local composition."""

    def __init__(self, registry: ScientificSkillRegistry) -> None:
        self._registry = registry

    async def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        return await asyncio.to_thread(self._registry.execute, request)


def _produced_kinds(skill_id: ScientificSkillId) -> frozenset[ArtifactKind]:
    """Descriptor-driven Artifact kinds one skill may publish."""

    return frozenset(
        ArtifactKind(kind) for kind in _capability_produced_kinds(skill_id.value)
    )


def _produces_model_artifact(skill_id: ScientificSkillId) -> bool:
    """Whether the skill must materialize a model binary through storage."""

    return ArtifactKind.model_artifact in _produced_kinds(skill_id)


def _produces_source_snapshot(skill_id: ScientificSkillId) -> bool:
    """Whether the skill outcome must be persisted as a SourceSnapshot."""

    return _capability_produces_snapshot(skill_id.value)


class ScientificStepAdapter:
    """Execute exactly one task-owned frozen Workflow step."""

    def __init__(
        self,
        registry: ScientificSkillRegistry | None = None,
        *,
        executor: ScientificSkillExecutor | None = None,
        content_storage: ContentStorage,
        source_recorder: ScientificProducedSourceRecorder,
        budget: ScientificSkillBudget | None = None,
    ) -> None:
        if (registry is None) == (executor is None):
            raise ValueError(
                "provide exactly one scientific skill executor or registry"
            )
        self._executor = executor or InProcessScientificSkillExecutor(registry)
        self._content_storage = content_storage
        self._source_recorder = source_recorder
        self._budget = budget or ScientificSkillBudget()

    async def execute(
        self,
        *,
        task_id: str,
        project_id: str,
        run_id: str,
        contract: ResearchContract,
        resolve_inputs: ScientificInputResolver,
    ) -> ScientificStepOutput:
        tasks = tuple(
            task for task in contract.scientific_tasks if task.task_id == task_id
        )
        if len(tasks) != 1:
            raise ValueError(
                f"scientific Workflow step must resolve exactly one task: {task_id!r}"
            )
        task = tasks[0]
        scientific_skill_phase(task.skill_id.value)
        outcome = await self._execute_task(
            task=task,
            project_id=project_id,
            run_id=run_id,
            contract=contract,
            resolve_inputs=resolve_inputs,
        )
        candidates = tuple(
            candidate
            for candidate in _assemble_candidates(
                outcome,
                requested_outputs=frozenset(contract.output_requirements),
            )
        )
        return ScientificStepOutput(
            task_id=task.task_id,
            skill_id=task.skill_id,
            source_mode=_publication_source_mode(outcome),
            artifact_candidates=candidates,
            source_snapshot_ids=outcome.source_snapshot_ids,
            source_table_admissions=_source_table_admissions(outcome),
        )

    async def _execute_task(
        self,
        *,
        task: ScientificTaskInput,
        project_id: str,
        run_id: str,
        contract: ResearchContract,
        resolve_inputs: ScientificInputResolver,
    ) -> ScientificTaskExecutionOutcome:
        task = _normalize_gaia_data_fields(task, contract)
        bindings = tuple(await resolve_inputs(task))
        _validate_bindings(task, bindings)
        parameters = dict(task.parameters)
        for binding in bindings:
            overlap = set(parameters) & set(binding.parameters)
            if overlap:
                raise ValueError(
                    "resolved scientific inputs cannot override contract parameters: "
                    + ", ".join(sorted(overlap))
                )
            parameters.update(binding.parameters)
        sources = _unique_sources(
            reference for binding in bindings for reference in binding.source_references
        )
        request = ScientificSkillRequest(
            request_id=_stable_id("request", run_id, task.task_id),
            project_id=project_id,
            run_id=run_id,
            skill_id=task.skill_id,
            parameters=parameters,
            source_references=sources,
            budget=self._budget,
        )
        started = monotonic()
        result = await self._executor.execute(request)
        duration_ms = max(0, round((monotonic() - started) * 1000))
        produced_sources: tuple[ScientificSourceReference, ...] = ()
        if _produces_source_snapshot(task.skill_id):
            produced_sources = await self._source_recorder.record(
                project_id=project_id,
                run_id=run_id,
                task=task,
                request=request,
                result=result,
            )
        materialized = await _materialize_output(
            task.skill_id,
            result.output,
            self._content_storage,
        )
        if task.skill_id is ScientificSkillId.gaia_cone_search:
            materialized = _admit_gaia_output(
                materialized,
                produced_sources=produced_sources,
                evidence_scope_id=request.request_id,
                contract=contract,
            )
        all_sources = _unique_sources((*sources, *produced_sources))
        return ScientificTaskExecutionOutcome(
            task=task,
            result=result,
            materialized_output=materialized,
            duration_ms=duration_ms,
            source_snapshot_ids=tuple(
                sorted(reference.source_snapshot_id for reference in all_sources)
            ),
            produced_source_snapshot_ids=tuple(
                reference.source_snapshot_id for reference in produced_sources
            ),
            evidence_ids=tuple(
                sorted(
                    {
                        evidence_id
                        for binding in bindings
                        for evidence_id in binding.evidence_ids
                    }
                )
            ),
            artifact_version_ids=tuple(
                binding.ref_id
                for binding in bindings
                if binding.kind == "artifact_version"
            ),
        )


def _admit_gaia_output(
    output: Mapping[str, object],
    *,
    produced_sources: tuple[ScientificSourceReference, ...],
    evidence_scope_id: str,
    contract: ResearchContract,
) -> Mapping[str, object]:
    if len(produced_sources) != 1:
        raise ValueError("Gaia admission requires exactly one physical SourceSnapshot")
    source = produced_sources[0]
    if (
        source.source_id != GAIA_SOURCE_ID
        or source.query_hash is None
        or source.retrieved_at is None
    ):
        raise ValueError("Gaia SourceSnapshot facts are incomplete")
    raw_fields = output.get("fields")
    raw_rows = output.get("rows")
    if (
        not isinstance(raw_fields, list)
        or not all(isinstance(field, str) for field in raw_fields)
        or not isinstance(raw_rows, list)
        or not all(isinstance(row, Mapping) for row in raw_rows)
    ):
        raise ValueError("Gaia result has no bounded source-table payload")
    status = output.get("result_status")
    truncated = output.get("truncated")
    if status not in {"complete", "empty", "truncated"} or not isinstance(
        truncated, bool
    ):
        raise ValueError("Gaia result completion status is invalid")
    if (
        (status == "empty") != (not raw_rows)
        or (status == "truncated") != truncated
    ):
        raise ValueError(
            "Gaia result completion status is inconsistent with rows and truncated"
        )
    admission = admit_source_table(
        source_id=source.source_id,
        fields=raw_fields,
        rows=raw_rows,
        result_status=status,
        source_snapshot_id=source.source_snapshot_id,
        source_snapshot_content_hash=source.content_hash,
        query_hash=source.query_hash,
        retrieved_at=source.retrieved_at,
        evidence_scope_id=evidence_scope_id,
        contract=contract,
    )
    return {
        key: value for key, value in output.items() if key != "source_table_admission"
    } | {"source_table_admission": admission.model_dump(mode="json")}


async def _materialize_output(
    skill_id: ScientificSkillId,
    output: Mapping[str, object],
    content_storage: ContentStorage,
) -> Mapping[str, object]:
    if _produces_model_artifact(skill_id):
        raw_binary = output.get("model_binary")
        if not isinstance(raw_binary, dict):
            raise ValueError("model skill output has no model binary")
        encoded = raw_binary.get("content_base64")
        content_hash = raw_binary.get("content_hash")
        media_type = raw_binary.get("media_type")
        if (
            not isinstance(encoded, str)
            or not isinstance(content_hash, str)
            or media_type != "application/onnx"
        ):
            raise ValueError("model binary identity or media type is invalid")
        content = b64decode(encoded, validate=True)
        content_ref = await content_storage.store(content, content_hash)
        materialized_binary = {
            key: value for key, value in raw_binary.items() if key != "content_base64"
        } | {"content_ref": content_ref}
        return {**output, "model_binary": materialized_binary}
    if skill_id is not ScientificSkillId.skyview_fits:
        return dict(output)
    raw_documents = output.get("documents")
    if not isinstance(raw_documents, list):
        raise ValueError("SkyView output has no FITS document registry")
    documents: list[dict[str, object]] = []
    for raw in raw_documents:
        if not isinstance(raw, dict):
            raise ValueError("SkyView FITS document must be an object")
        encoded = raw.get("content_base64")
        content_hash = raw.get("content_hash")
        if not isinstance(encoded, str) or not isinstance(content_hash, str):
            raise ValueError("SkyView FITS document is missing content identity")
        content = b64decode(encoded, validate=True)
        content_ref = await content_storage.store(content, content_hash)
        documents.append(
            {key: value for key, value in raw.items() if key != "content_base64"}
            | {"content_ref": content_ref}
        )
    return {**output, "documents": documents}


def _assemble_candidates(
    outcome: ScientificTaskExecutionOutcome,
    *,
    requested_outputs: frozenset[ArtifactKind],
) -> tuple[
    AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | SpectrumArtifactContent
    | LightCurveArtifactContent
    | ModelEvaluationArtifactContent
    | ModelArtifactContent,
    ...,
]:
    # Candidate assembly is descriptor-driven: the capability table decides
    # which Artifact kinds a skill may publish, the contract decides which of
    # them this Run requested. No parallel per-skill allowlist may drift here.
    produced = _produced_kinds(outcome.task.skill_id)
    candidates: list[
        AnalysisReportArtifactContent
        | VisualizationArtifactContent
        | SpectrumArtifactContent
        | LightCurveArtifactContent
        | ModelEvaluationArtifactContent
        | ModelArtifactContent
    ] = []
    if ArtifactKind.spectrum in produced and ArtifactKind.spectrum in requested_outputs:
        candidates.append(_spectrum(outcome))
    if (
        ArtifactKind.light_curve in produced
        and ArtifactKind.light_curve in requested_outputs
    ):
        candidates.append(_light_curve(outcome))
    if (
        ArtifactKind.analysis_report in produced
        and ArtifactKind.analysis_report in requested_outputs
    ):
        candidates.append(_analysis_report(outcome))
    if (
        ArtifactKind.model_evaluation in produced
        and ArtifactKind.model_evaluation in requested_outputs
    ):
        candidates.append(_model_evaluation(outcome))
    if (
        ArtifactKind.model_artifact in produced
        and ArtifactKind.model_artifact in requested_outputs
    ):
        candidates.append(_model_artifact(outcome))
    if (
        ArtifactKind.visualization in produced
        and ArtifactKind.visualization in requested_outputs
    ):
        candidates.extend(_visualization_candidates(outcome))
    return tuple(candidates)


def _visualization_candidates(
    outcome: ScientificTaskExecutionOutcome,
) -> tuple[VisualizationArtifactContent, ...]:
    """Dispatch the concrete declarative visualization for one skill."""

    skill_id = outcome.task.skill_id
    if skill_id is ScientificSkillId.chart_visualization:
        return (_chart_visualization(outcome),)
    if skill_id is ScientificSkillId.wwt_scene:
        return (_wwt_visualization(outcome),)
    if skill_id is ScientificSkillId.skyview_fits:
        return _fits_visualizations(outcome)
    if skill_id in {
        ScientificSkillId.clustering_analysis,
        ScientificSkillId.anomaly_detection,
    }:
        return (_projection_visualization(outcome),)
    raise ValueError(
        f"skill declares visualization output without an assembler: {skill_id.value}"
    )


def _spectrum(outcome: ScientificTaskExecutionOutcome) -> SpectrumArtifactContent:
    spectrum_id = _stable_id("spectrum", outcome.task.task_id)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="spectrum",
        target_id=spectrum_id,
    )
    raw = outcome.materialized_output
    payload = {
        "kind": "spectrum",
        "schema_version": "1.0.0",
        "spectrum_id": spectrum_id,
        "title": f"{raw['object_name']} 光谱",
        "object_name": raw["object_name"],
        "wavelength_unit": raw["wavelength_unit"],
        "flux_unit": raw["flux_unit"],
        "sample_count": raw["sample_count"],
        "points": raw["points"],
        "signal_to_noise": raw["signal_to_noise"],
        "detected_lines": raw["detected_lines"],
        "rest_wavelength": raw["rest_wavelength"],
        "radial_velocity_km_s": raw["radial_velocity_km_s"],
        "skill_executions": [_skill_execution(outcome).model_dump(mode="json")],
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(SpectrumArtifactContent, payload)


def _light_curve(
    outcome: ScientificTaskExecutionOutcome,
) -> LightCurveArtifactContent:
    light_curve_id = _stable_id("light_curve", outcome.task.task_id)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="light_curve",
        target_id=light_curve_id,
    )
    raw = outcome.materialized_output
    payload = {
        "kind": "light_curve",
        "schema_version": "1.0.0",
        "light_curve_id": light_curve_id,
        "title": f"{raw['object_name']} 光变曲线",
        "object_name": raw["object_name"],
        "time_scale": raw["time_scale"],
        "time_unit": raw["time_unit"],
        "value_unit": raw["value_unit"],
        "value_kind": raw["value_kind"],
        "normalization": raw["normalization"],
        "sample_count": raw["sample_count"],
        "accepted_sample_count": raw["accepted_sample_count"],
        "rejected_sample_count": raw["rejected_sample_count"],
        "duration": raw["duration"],
        "median_cadence": raw["median_cadence"],
        "best_period": raw["best_period"],
        "best_power": raw["best_power"],
        "false_alarm_probability": raw["false_alarm_probability"],
        "period_peaks": raw["period_peaks"],
        "points": raw["points"],
        "skill_executions": [_skill_execution(outcome).model_dump(mode="json")],
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(LightCurveArtifactContent, payload)


def _analysis_report(
    outcome: ScientificTaskExecutionOutcome,
) -> AnalysisReportArtifactContent:
    descriptor = capability_for(outcome.task.skill_id.value)
    result_blocks, scientific_evidence, evidence_ids = _result_blocks(outcome)
    source_table_admissions = _source_table_admissions(outcome)
    metrics = _metrics_from_output(outcome, evidence_ids=evidence_ids)
    payload: dict[str, object] = {
        "kind": "analysis_report",
        "schema_version": "1.0.0",
        "report_id": _stable_id("report", outcome.task.task_id),
        "title": str(descriptor["label"]),
        "summary": str(descriptor["description"]),
        "skill_executions": [_skill_execution(outcome).model_dump(mode="json")],
        "result_blocks": [item.model_dump(mode="json") for item in result_blocks],
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "findings": [],
        "limitations": list(outcome.result.warnings),
        "human_required": [],
        "related_artifact_version_ids": list(outcome.artifact_version_ids),
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_table_admissions": [
            item.model_dump(mode="json") for item in source_table_admissions
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(AnalysisReportArtifactContent, payload)


def _chart_visualization(
    outcome: ScientificTaskExecutionOutcome,
) -> VisualizationArtifactContent:
    data_identity = _chart_data_identity(outcome)
    output = outcome.materialized_output
    x_field = _text(output, "x_field")
    y_field = _text(output, "y_field")
    raw_series = output.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise ValueError("chart task produced no series")
    colors = ("brand", "information", "success", "warning", "error", "neutral")
    spec = ChartVisualizationSpec.model_validate(
        {
            "mode": "chart",
            **data_identity,
            "x_axis": {"field": x_field, "label": x_field},
            "y_axis": {"field": y_field, "label": y_field},
            "series": [
                {
                    "series_id": _text(item, "series_id"),
                    "label": _text(item, "label"),
                    "x_field": x_field,
                    "y_field": y_field,
                    "mark": _text(item, "mark"),
                    "color_token": colors[index % len(colors)],
                    "points": item.get("points"),
                }
                for index, item in enumerate(raw_series)
                if isinstance(item, dict)
            ],
        }
    )
    return _visualization(outcome, spec=spec, title=_text(output, "title"))


_PROJECTION_COLORS = ("brand", "information", "success", "warning", "error", "neutral")


def _projection_visualization(
    outcome: ScientificTaskExecutionOutcome,
) -> VisualizationArtifactContent:
    """Map PCA projection, cluster assignment or anomaly score onto the
    existing declarative chart contract instead of a renderer-specific
    Artifact."""

    data_identity = _chart_data_identity(outcome)
    output = outcome.materialized_output
    algorithm = _text(output, "algorithm")
    series_payloads: list[dict[str, object]] = []
    if outcome.task.skill_id is ScientificSkillId.clustering_analysis:
        raw_assignments = output.get("assignments")
        if not isinstance(raw_assignments, list) or not raw_assignments:
            raise ValueError("clustering task produced no assignments")
        by_cluster: dict[int, list[dict[str, object]]] = {}
        for item in raw_assignments:
            if not isinstance(item, dict):
                raise ValueError("clustering assignment must be an object")
            by_cluster.setdefault(int(item["cluster"]), []).append(item)
        for index, cluster in enumerate(sorted(by_cluster)):
            label = "噪声（未分组）" if cluster < 0 else f"簇 {cluster}"
            series_id = "cluster.noise" if cluster < 0 else f"cluster.{cluster}"
            series_payloads.append(
                {
                    "series_id": series_id,
                    "label": label,
                    "points": [
                        {"x": item["pca_x"], "y": item["pca_y"]}
                        for item in by_cluster[cluster]
                    ],
                    "color_token": _PROJECTION_COLORS[index % len(_PROJECTION_COLORS)],
                }
            )
        title = f"{algorithm} 聚类投影"
    else:
        raw_ranked = output.get("ranked_observations")
        if not isinstance(raw_ranked, list) or not raw_ranked:
            raise ValueError("anomaly task produced no ranked observations")
        partitions: dict[bool, list[dict[str, object]]] = {False: [], True: []}
        for item in raw_ranked:
            if not isinstance(item, dict):
                raise ValueError("anomaly observation must be an object")
            partitions[bool(item["is_anomaly"])].append(item)
        series_payloads = [
            {
                "series_id": "anomaly.normal",
                "label": "正常观测",
                "points": [
                    {"x": item["pca_x"], "y": item["pca_y"]}
                    for item in partitions[False]
                ],
                "color_token": "brand",
            },
            {
                "series_id": "anomaly.flagged",
                "label": "异常观测",
                "points": [
                    {"x": item["pca_x"], "y": item["pca_y"]}
                    for item in partitions[True]
                ],
                "color_token": "warning",
            },
        ]
        title = f"{algorithm} 异常检测投影"
    spec = ChartVisualizationSpec.model_validate(
        {
            "mode": "chart",
            **data_identity,
            "x_axis": {"field": "pca_x", "label": "PCA 第一主成分"},
            "y_axis": {"field": "pca_y", "label": "PCA 第二主成分"},
            "series": [
                {
                    "series_id": payload["series_id"],
                    "label": payload["label"],
                    "x_field": "pca_x",
                    "y_field": "pca_y",
                    "mark": "point",
                    "color_token": payload["color_token"],
                    "points": payload["points"],
                }
                for payload in series_payloads
                if payload["points"]
            ],
        }
    )
    return _visualization(outcome, spec=spec, title=title)


def _wwt_visualization(
    outcome: ScientificTaskExecutionOutcome,
) -> VisualizationArtifactContent:
    spec = WwtSceneVisualizationSpec.model_validate(outcome.materialized_output)
    return _visualization(
        outcome,
        spec=spec,
        title="WWT 天图场景",
    )


def _fits_visualizations(
    outcome: ScientificTaskExecutionOutcome,
) -> tuple[VisualizationArtifactContent, ...]:
    if not outcome.source_snapshot_ids:
        raise ValueError("SkyView visualization requires a persisted SourceSnapshot")
    documents = outcome.materialized_output.get("documents")
    if not isinstance(documents, list):
        raise ValueError("SkyView task produced no document registry")
    return tuple(
        _visualization(
            outcome,
            spec=FitsImageVisualizationSpec.model_validate(
                {
                    "mode": "fits_image",
                    "source_snapshot_id": outcome.source_snapshot_ids[-1],
                    "content_ref": _text(document, "content_ref"),
                    "content_hash": _text(document, "content_hash"),
                }
            ),
            title=f"{outcome.materialized_output.get('survey', 'SkyView')} FITS 图像",
            suffix=str(index + 1),
        )
        for index, document in enumerate(documents)
        if isinstance(document, dict)
    )


def _visualization(
    outcome: ScientificTaskExecutionOutcome,
    *,
    spec: ChartVisualizationSpec
    | FitsImageVisualizationSpec
    | WwtSceneVisualizationSpec,
    title: str,
    suffix: str = "primary",
) -> VisualizationArtifactContent:
    visualization_id = _stable_id("visualization", outcome.task.task_id, suffix)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="visualization",
        target_id=visualization_id,
    )
    payload: dict[str, object] = {
        "kind": "visualization",
        "schema_version": "1.0.0",
        "visualization_id": visualization_id,
        "title": title,
        "description": f"{capability_for(outcome.task.skill_id.value)['label']}生成的声明式科学视图。",
        "spec": spec.model_dump(mode="json"),
        "skill_executions": [_skill_execution(outcome).model_dump(mode="json")],
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(VisualizationArtifactContent, payload)


_MODEL_SPLIT_STRATEGIES = frozenset({"random", "stratified", "group", "entity", "time"})


def _model_evaluation(
    outcome: ScientificTaskExecutionOutcome,
) -> ModelEvaluationArtifactContent:
    output = outcome.materialized_output
    training_input = _model_training_input(outcome)
    raw_split = output.get("split")
    if not isinstance(raw_split, dict):
        raise ValueError("model task produced no split metadata")
    train_count = _positive_int(raw_split, "train_count")
    test_count = _positive_int(raw_split, "test_count")
    total = train_count + test_count
    raw_strategy = _text(raw_split, "strategy")
    if raw_strategy not in _MODEL_SPLIT_STRATEGIES:
        raise ValueError(f"unknown split strategy: {raw_strategy}")
    random_seed = raw_split.get("random_seed")
    split = ModelSplitReference(
        strategy=raw_strategy,
        field=raw_split.get("field"),
        random_seed=(
            int(random_seed)
            if raw_strategy != "time" and random_seed is not None
            else None
        ),
        train_fraction=train_count / total,
        validation_fraction=0,
        test_fraction=test_count / total,
        cross_validation_folds=raw_split.get("cross_validation_folds"),
        train_cutoff=raw_split.get("train_cutoff"),
    )
    evaluation_id = _stable_id("evaluation", outcome.task.task_id)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="evaluation",
        target_id=evaluation_id,
    )
    metrics = _named_metrics(
        outcome, output.get("metrics"), prefix="metric", evidence_ids=evidence_ids
    )
    baseline = _named_metrics(
        outcome,
        output.get("baseline_metrics"),
        prefix="baseline",
        evidence_ids=evidence_ids,
    )
    feature_fields = _model_feature_fields(outcome)
    image_training = _model_image_training(outcome)
    raw_model_binary = output.get("model_binary")
    if not isinstance(raw_model_binary, dict):
        raise ValueError("model task produced no materialized model binary")
    model_binary = ModelBinaryReference.model_validate(
        {
            "content_ref": raw_model_binary.get("content_ref"),
            "content_hash": raw_model_binary.get("content_hash"),
            "media_type": raw_model_binary.get("media_type"),
        }
    )
    payload: dict[str, object] = {
        "kind": "model_evaluation",
        "schema_version": "1.0.0",
        "evaluation_id": evaluation_id,
        "title": f"{capability_for(outcome.task.skill_id.value)['label']}评估",
        "task_kind": _text(output, "task_kind"),
        "algorithm": _text(output, "algorithm"),
        "algorithm_version": _text(output, "algorithm_version"),
        "training_input": training_input,
        "image_training": (
            image_training.model_dump(mode="json")
            if image_training is not None
            else None
        ),
        "feature_fields": feature_fields,
        "target_field": _text(output, "target_field", fallback=outcome.task.parameters),
        "split": split.model_dump(mode="json"),
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "baseline_metrics": [item.model_dump(mode="json") for item in baseline],
        "skill_execution": _skill_execution(outcome).model_dump(mode="json"),
        "model_binary": model_binary.model_dump(mode="json"),
        "diagnostic_visualization_ids": [],
        "limitations": _model_limitations(outcome),
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(ModelEvaluationArtifactContent, payload)


def _model_artifact(
    outcome: ScientificTaskExecutionOutcome,
) -> ModelArtifactContent:
    output = outcome.materialized_output
    training_input = _model_training_input(outcome)
    feature_fields = _model_feature_fields(outcome)
    image_training = _model_image_training(outcome)
    raw_model_binary = output.get("model_binary")
    if not isinstance(raw_model_binary, dict):
        raise ValueError("model task produced no materialized model binary")
    model_binary = ModelBinaryReference.model_validate(
        {
            "content_ref": raw_model_binary.get("content_ref"),
            "content_hash": raw_model_binary.get("content_hash"),
            "media_type": raw_model_binary.get("media_type"),
        }
    )
    model_id = _stable_id("model", outcome.task.task_id)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="model",
        target_id=model_id,
    )
    payload: dict[str, object] = {
        "kind": "model_artifact",
        "schema_version": "1.0.0",
        "model_id": model_id,
        "title": f"{capability_for(outcome.task.skill_id.value)['label']}模型",
        "status": "active",
        "task_kind": _text(output, "task_kind"),
        "algorithm": _text(output, "algorithm"),
        "algorithm_version": _text(output, "algorithm_version"),
        "training_input": training_input,
        "image_training": (
            image_training.model_dump(mode="json")
            if image_training is not None
            else None
        ),
        "evaluation_id": _stable_id("evaluation", outcome.task.task_id),
        "feature_fields": feature_fields,
        "target_field": _text(output, "target_field", fallback=outcome.task.parameters),
        "model_binary": model_binary.model_dump(mode="json"),
        "input_name": _text(raw_model_binary, "input_name"),
        "output_names": _string_list(raw_model_binary, "output_names"),
        "input_shape": _input_shape(raw_model_binary),
        "opset_imports": _opset_imports(raw_model_binary),
        "dependency_revisions": _model_dependency_revisions(outcome),
        "skill_execution": _skill_execution(outcome).model_dump(mode="json"),
        "limitations": _model_limitations(outcome),
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(ModelArtifactContent, payload)


def _model_limitations(outcome: ScientificTaskExecutionOutcome) -> list[str]:
    raw_limitations = outcome.materialized_output.get("limitations")
    runtime_limitations = (
        [item for item in raw_limitations if isinstance(item, str) and item.strip()]
        if isinstance(raw_limitations, list)
        else []
    )
    return list(dict.fromkeys((*runtime_limitations, *outcome.result.warnings)))


def _model_feature_fields(outcome: ScientificTaskExecutionOutcome) -> list[str]:
    raw_binary = outcome.materialized_output.get("model_binary")
    if outcome.task.skill_id is ScientificSkillId.image_classification:
        if isinstance(raw_binary, dict):
            shape = raw_binary.get("input_shape")
            if (
                isinstance(shape, list)
                and len(shape) == 2
                and isinstance(shape[1], int)
                and not isinstance(shape[1], bool)
                and shape[1] > 0
            ):
                return [f"pixel_{index}" for index in range(shape[1])]
    raw = outcome.materialized_output.get("feature_fields")
    if isinstance(raw, list) and raw and all(isinstance(item, str) for item in raw):
        return list(raw)
    if outcome.task.skill_id is ScientificSkillId.time_series_forecast:
        raw_lags = outcome.materialized_output.get("split")
        if isinstance(raw_lags, dict):
            lags = raw_lags.get("lags")
            if isinstance(lags, int) and lags > 0:
                return [f"lag_{offset}" for offset in range(lags, 0, -1)]
    raise ValueError("model task produced no feature field registry")


def _model_image_training(
    outcome: ScientificTaskExecutionOutcome,
) -> ImageTrainingSpecification | None:
    if outcome.task.skill_id is not ScientificSkillId.image_classification:
        return None
    output = outcome.materialized_output
    return ImageTrainingSpecification.model_validate(
        {
            "manifest_schema_version": "1.0.0",
            "preprocessing": output.get("preprocessing"),
            "image_shape": output.get("image_shape"),
            "image_count": output.get("image_count"),
            "source_total_pixels": output.get("source_total_pixels"),
            "label_schema": output.get("label_schema"),
        }
    )


def _model_training_input(outcome: ScientificTaskExecutionOutcome) -> dict[str, str]:
    if len(outcome.artifact_version_ids) == 1:
        return {
            "kind": "dataset_artifact_version",
            "ref_id": outcome.artifact_version_ids[0],
        }
    if not outcome.artifact_version_ids and len(outcome.source_snapshot_ids) == 1:
        return {
            "kind": "source_snapshot",
            "ref_id": outcome.source_snapshot_ids[0],
        }
    raise ValueError(
        "model task requires exactly one Dataset ArtifactVersion or SourceSnapshot input"
    )


def _string_list(value: Mapping[str, object], key: str) -> list[str]:
    raw = value.get(key)
    if (
        not isinstance(raw, list)
        or not raw
        or not all(isinstance(item, str) for item in raw)
    ):
        raise ValueError(f"model binary {key} must be a non-empty string list")
    return list(raw)


def _input_shape(value: Mapping[str, object]) -> list[int | None]:
    raw = value.get("input_shape")
    if (
        not isinstance(raw, list)
        or len(raw) < 2
        or raw[0] is not None
        or any(isinstance(item, bool) or not isinstance(item, int) for item in raw[1:])
    ):
        raise ValueError("model binary input_shape is invalid")
    return list(raw)


def _opset_imports(value: Mapping[str, object]) -> dict[str, int]:
    raw = value.get("opset_imports")
    if not isinstance(raw, dict) or not raw:
        raise ValueError("model binary has no ONNX opset registry")
    if any(
        not isinstance(domain, str)
        or not domain
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        for domain, revision in raw.items()
    ):
        raise ValueError("model binary ONNX opset registry is invalid")
    return dict(raw)


def _model_dependency_revisions(
    outcome: ScientificTaskExecutionOutcome,
) -> list[str]:
    distributions = ["scikit-learn", "onnx", "onnxruntime", "skl2onnx"]
    if outcome.task.skill_id is ScientificSkillId.image_classification:
        distributions.append("pillow")
    return [
        f"{distribution}=={version(distribution)}" for distribution in distributions
    ]


def _skill_execution(
    outcome: ScientificTaskExecutionOutcome,
) -> ScientificSkillExecution:
    return ScientificSkillExecution(
        execution_id=_stable_id("execution", outcome.result.request_id),
        skill_id=outcome.result.skill_id,
        skill_revision=outcome.result.skill_revision,
        status=outcome.result.status,
        input_hash=outcome.result.input_hash,
        output_hash=outcome.result.output_hash,
        duration_ms=outcome.duration_ms,
        warnings=outcome.result.warnings,
    )


def _metrics_from_output(
    outcome: ScientificTaskExecutionOutcome,
    *,
    evidence_ids: tuple[str, ...],
) -> tuple[ScientificMetric, ...]:
    definitions = _DECISION_METRICS.get(outcome.task.skill_id, ())
    return tuple(
        ScientificMetric(
            metric_id=_stable_id("metric", outcome.task.task_id, path),
            label=label,
            value=value,
            unit=unit,
            evidence_ids=evidence_ids,
        )
        for path, label, unit in definitions
        if (value := _metric_value(outcome.materialized_output, path)) is not None
    )


_DECISION_METRICS: dict[ScientificSkillId, tuple[tuple[str, str, str | None], ...]] = {
    ScientificSkillId.data_profile: (
        ("row_count", "记录数", "行"),
        ("field_count", "字段数", "列"),
    ),
    ScientificSkillId.simbad_lookup: (("row_count", "返回记录", "行"),),
    ScientificSkillId.gaia_cone_search: (("row_count", "返回记录", "行"),),
    ScientificSkillId.vizier_tap: (("row_count", "返回记录", "行"),),
    ScientificSkillId.clustering_analysis: (
        ("sample_count", "有效样本", "个"),
        ("cluster_count", "聚类数量", "个"),
        ("noise_count", "噪声样本", "个"),
        ("silhouette_score", "轮廓系数", None),
    ),
    ScientificSkillId.anomaly_detection: (
        ("sample_count", "有效样本", "个"),
        ("anomaly_count", "异常样本", "个"),
    ),
    ScientificSkillId.spectrum_analysis: (
        ("sample_count", "光谱采样点", "个"),
        ("signal_to_noise", "信噪比", None),
        ("radial_velocity_km_s", "径向速度", "km/s"),
    ),
    ScientificSkillId.light_curve_analysis: (
        ("accepted_sample_count", "有效采样点", "个"),
        ("rejected_sample_count", "剔除采样点", "个"),
        ("best_period", "最佳周期", None),
        ("false_alarm_probability", "虚警概率", None),
    ),
}


def _metric_value(output: Mapping[str, object], path: str) -> float | int | str | None:
    value: object = output
    for key in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    return value


def _named_metrics(
    outcome: ScientificTaskExecutionOutcome,
    raw: object,
    *,
    prefix: str,
    evidence_ids: tuple[str, ...],
) -> tuple[ScientificMetric, ...]:
    if not isinstance(raw, dict) or not raw:
        if prefix == "metric":
            raise ValueError("model task produced no evaluation metrics")
        return ()
    return tuple(
        ScientificMetric(
            metric_id=_stable_id(prefix, outcome.task.task_id, str(name)),
            label=_model_metric_label(str(name)),
            value=value,
            evidence_ids=evidence_ids,
        )
        for name, value in sorted(raw.items())
        if isinstance(value, int | float | str) and not isinstance(value, bool)
    )


def _model_metric_label(name: str) -> str:
    labels = {
        "accuracy": "准确率",
        "precision": "精确率",
        "recall": "召回率",
        "f1": "F1 分数",
        "roc_auc": "ROC AUC",
        "mae": "平均绝对误差",
        "mse": "均方误差",
        "rmse": "均方根误差",
        "r2": "决定系数 R²",
    }
    return labels.get(name, name.upper())


def _evidence_for_target(
    outcome: ScientificTaskExecutionOutcome,
    *,
    target_type: Literal[
        "result_block",
        "metric",
        "visualization",
        "spectrum",
        "light_curve",
        "evaluation",
        "model",
    ],
    target_id: str,
) -> tuple[tuple[ScientificEvidence, ...], tuple[str, ...]]:
    sources = outcome.produced_source_snapshot_ids or outcome.source_snapshot_ids
    evidence = tuple(
        ScientificEvidence(
            evidence_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"evidence:{outcome.result.request_id}:{target_type}:{target_id}:{source_id}",
                )
            ),
            target_type=target_type,
            target_id=target_id,
            source_snapshot_id=source_id,
            evidence_type=(
                "service_response"
                if source_id in outcome.produced_source_snapshot_ids
                else "input_snapshot"
            ),
            locator={
                "kind": "scientific_computation",
                "task_id": outcome.task.task_id,
                "skill_id": outcome.task.skill_id.value,
                "output_hash": outcome.result.output_hash,
                "upstream_evidence_ids": list(outcome.evidence_ids),
            },
            quote_or_value=None,
        )
        for source_id in sources
    )
    return evidence, tuple(sorted(item.evidence_id for item in evidence))


_RESULT_METADATA_FIELDS = frozenset(
    {
        "catalog",
        "column_metadata",
        "coordinate_frame",
        "data_release",
        "ephemeris",
        "frame",
        "provider_uri",
        "qualified_table",
        "service",
        "time_scale",
    }
)

_RESULT_PRESENTATIONS: dict[str, tuple[str, str]] = {
    "acquisition": ("数据来源", "record"),
    "assignments": ("聚类分组", "table"),
    "center": ("检索中心", "record"),
    "correlations": ("相关系数", "matrix"),
    "detected_lines": ("谱线检测", "table"),
    "documents": ("数据产品", "catalog"),
    "events": ("天象事件", "timeseries"),
    "fields": ("字段概览", "table"),
    "forecast": ("预测结果", "timeseries"),
    "hypothesis_tests": ("假设检验", "statistics"),
    "matches": ("交叉匹配结果", "catalog"),
    "period_peaks": ("周期候选", "timeseries"),
    "points": ("观测序列", "timeseries"),
    "predictions": ("推理结果", "table"),
    "parameters": ("分析参数", "record"),
    "ranked_observations": ("异常排序", "table"),
    "records": ("检索结果", "catalog"),
    "resolved_location": ("观测地点", "record"),
    "rows": ("数据记录", "catalog"),
    "sources": ("检测源", "catalog"),
    "statistics": ("描述统计", "statistics"),
}

_PRESENTATION_HIDDEN_FIELDS = frozenset(
    {
        "algorithm_version",
        "dataset_artifact_version_id",
        "model_artifact_version_id",
        "model_content_hash",
        "raw_content_hash",
        "response_content_hash",
    }
)


def _result_blocks(
    outcome: ScientificTaskExecutionOutcome,
) -> tuple[
    tuple[ScientificResultBlock, ...],
    tuple[ScientificEvidence, ...],
    tuple[str, ...],
]:
    """Turn one typed handler result into explicit presentation-owned blocks."""

    admissions = _source_table_admissions(outcome)
    if admissions:
        return _source_table_result_blocks(outcome, admissions[0])

    output = dict(outcome.materialized_output)
    metadata = {
        key: value for key, value in output.items() if key in _RESULT_METADATA_FIELDS
    }
    scalar_values: dict[str, object] = {}
    block_values: list[tuple[str, str, str, object]] = []
    for key, value in output.items():
        if key in _RESULT_METADATA_FIELDS:
            continue
        if isinstance(value, list):
            label, representation = _RESULT_PRESENTATIONS.get(
                key, ("结构化结果", "table")
            )
            block_values.append(
                (
                    key,
                    label,
                    representation,
                    {**metadata, "rows": _presentation_rows(value)},
                )
            )
        elif isinstance(value, dict):
            label, _representation = _RESULT_PRESENTATIONS.get(
                key, ("结果明细", "record")
            )
            block_values.append((key, label, "record", _presentation_mapping(value)))
        else:
            if key not in _PRESENTATION_HIDDEN_FIELDS:
                scalar_values[key] = value
    if scalar_values or not block_values:
        block_values.insert(
            0,
            (
                "summary",
                "分析摘要",
                "record",
                {**metadata, **scalar_values},
            ),
        )

    blocks: list[ScientificResultBlock] = []
    all_scientific_evidence: list[ScientificEvidence] = []
    all_evidence_ids: set[str] = set()
    for key, label, representation, payload in block_values:
        block_id = _stable_id("result", outcome.task.task_id, key)
        scientific_evidence, evidence_ids = _evidence_for_target(
            outcome,
            target_type="result_block",
            target_id=block_id,
        )
        blocks.append(
            ScientificResultBlock(
                block_id=block_id,
                label=label,
                representation=representation,  # type: ignore[arg-type]
                payload=payload,  # type: ignore[arg-type]
                content_hash=compute_canonical_payload_hash(payload),
                evidence_ids=evidence_ids,
            )
        )
        all_scientific_evidence.extend(scientific_evidence)
        all_evidence_ids.update(evidence_ids)
    return (
        tuple(blocks),
        tuple(all_scientific_evidence),
        tuple(sorted(all_evidence_ids)),
    )


def _source_table_admissions(
    outcome: ScientificTaskExecutionOutcome,
) -> tuple[SourceTableAdmission, ...]:
    raw = outcome.materialized_output.get("source_table_admission")
    if raw is None:
        return ()
    if outcome.task.skill_id is not ScientificSkillId.gaia_cone_search:
        raise ValueError("only the Gaia source-table task may carry this admission")
    return (SourceTableAdmission.model_validate(raw),)


def _source_table_result_blocks(
    outcome: ScientificTaskExecutionOutcome,
    admission: SourceTableAdmission,
) -> tuple[
    tuple[ScientificResultBlock, ...],
    tuple[ScientificEvidence, ...],
    tuple[str, ...],
]:
    block_id = _stable_id("result", outcome.task.task_id, "source_table")
    payload = source_table_result_payload(admission)
    evidence = tuple(
        ScientificEvidence(
            evidence_id=cell.evidence_id,
            target_type="result_block",
            target_id=block_id,
            source_snapshot_id=admission.source_snapshot_id,
            evidence_type="service_response",
            locator=cell.locator.model_dump(mode="json"),
            quote_or_value=cell.canonical_value,
        )
        for cell in admission.cells
    )
    evidence_ids = tuple(sorted(item.evidence_id for item in evidence))
    block = ScientificResultBlock(
        block_id=block_id,
        label="Gaia DR3 单源数据",
        representation="table",
        payload=payload,
        content_hash=compute_canonical_payload_hash(payload),
        evidence_ids=evidence_ids,
    )
    return (block,), evidence, evidence_ids


def source_table_result_payload(
    admission: SourceTableAdmission,
) -> dict[str, object]:
    """Project one admitted source table into its only public result payload."""

    public_columns = [
        {
            "field": f"column_{index + 1}",
            "label": column.label_zh,
            "unit": column.canonical_unit_symbol,
        }
        for index, column in enumerate(admission.columns)
    ]
    evidence_by_cell = {
        (cell.row_id, cell.canonical_field_id): cell.evidence_id
        for cell in admission.cells
    }
    return {
        "column_metadata": public_columns,
        "rows": [
            {
                **{
                    public_columns[index]["field"]: row.values[
                        column.canonical_field_id
                    ]
                    for index, column in enumerate(admission.columns)
                },
                "cell_evidence_ids": {
                    public_columns[index]["field"]: evidence_by_cell[
                        (row.row_id, column.canonical_field_id)
                    ]
                    for index, column in enumerate(admission.columns)
                },
            }
            for row in admission.rows
        ],
        "quality": {
            "status": admission.overall_status.value,
            "source_status": admission.source_result_status,
            "metrics": [
                {
                    "label": label,
                    "status": metric.status.value,
                    "value": str(metric.value) if metric.value is not None else None,
                }
                for metric, label in zip(
                    admission.metrics,
                    ("来源完整性", "单位一致性", "证据覆盖率"),
                    strict=True,
                )
            ],
        },
    }


def _presentation_rows(values: Sequence[object]) -> list[object]:
    if all(isinstance(value, Mapping) for value in values):
        return [_presentation_mapping(value) for value in values]  # type: ignore[arg-type]
    if all(isinstance(value, (list, tuple)) for value in values):
        return [
            {f"column_{index + 1}": cell for index, cell in enumerate(value)}
            for value in values  # type: ignore[union-attr]
        ]
    return [{"value": value} for value in values]


def _presentation_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: nested
        for key, nested in value.items()
        if key not in _PRESENTATION_HIDDEN_FIELDS
    }


def _validate_bindings(
    task: ScientificTaskInput, bindings: tuple[ScientificInputBinding, ...]
) -> None:
    resolved = tuple(binding.ref_id for binding in bindings)
    if resolved != task.input_refs:
        raise ValueError(
            "scientific input resolver must return each input_ref once in contract order"
        )
    if any(
        binding.kind not in {"artifact_version", "source_snapshot", "content_blob"}
        for binding in bindings
    ):
        raise ValueError("scientific input binding kind is unsupported")
    for binding in bindings:
        if len(binding.evidence_ids) != len(set(binding.evidence_ids)):
            raise ValueError("scientific input Evidence ids must be unique")


def _unique_sources(
    values: Sequence[ScientificSourceReference]
    | tuple[ScientificSourceReference, ...]
    | object,
) -> tuple[ScientificSourceReference, ...]:
    registry: dict[str, ScientificSourceReference] = {}
    for value in values:  # type: ignore[union-attr]
        existing = registry.get(value.source_snapshot_id)
        if existing is not None and existing != value:
            raise ValueError("SourceSnapshot identity resolved to conflicting content")
        registry[value.source_snapshot_id] = value
    return tuple(registry[key] for key in sorted(registry))


def _seal(model: type[object], payload: dict[str, object]):
    unsealed = model.model_validate(  # type: ignore[attr-defined]
        payload,
        context={"skip_scientific_output_hash_validation": True},
    )
    payload["output_hash"] = scientific_artifact_output_hash(unsealed)
    return model.model_validate(payload)  # type: ignore[attr-defined,no-any-return]


def _stable_id(*parts: str) -> str:
    return "sci_" + uuid5(NAMESPACE_URL, ":".join(parts)).hex


def _text(
    value: Mapping[str, object],
    key: str,
    *,
    fallback: Mapping[str, object] | None = None,
) -> str:
    raw = value.get(key)
    if raw is None and fallback is not None:
        raw = fallback.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"scientific output requires non-empty {key}")
    return raw.strip()


def _positive_int(value: Mapping[str, object], key: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        raise ValueError(f"scientific output requires positive {key}")
    return raw


def _chart_data_identity(outcome: ScientificTaskExecutionOutcome) -> dict[str, str]:
    if len(outcome.artifact_version_ids) == 1:
        return {"dataset_artifact_version_id": outcome.artifact_version_ids[0]}
    if len(outcome.artifact_version_ids) > 1:
        raise ValueError("chart requires exactly one Dataset ArtifactVersion input")
    if len(outcome.source_snapshot_ids) == 1:
        return {"source_snapshot_id": outcome.source_snapshot_ids[0]}
    raise ValueError("chart requires exactly one immutable data source identity")


__all__ = [
    "ScientificInputBinding",
    "ScientificProducedSourceRecorder",
    "ScientificStepAdapter",
    "ScientificStepOutput",
    "ScientificTaskExecutionOutcome",
]
