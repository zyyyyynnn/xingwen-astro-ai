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
    ResearchContractInput,
    ScientificSkillId,
    ScientificTaskInput,
)
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
from app.services.content_storage import ContentStorage

from .planning import scientific_skill_phase
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
    artifact_candidates: tuple[
        AnalysisReportArtifactContent
        | VisualizationArtifactContent
        | SpectrumArtifactContent
        | LightCurveArtifactContent
        | ModelEvaluationArtifactContent
        | ModelArtifactContent,
        ...,
    ]


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


class InProcessScientificSkillExecutor:
    """Injectable executor for deterministic unit tests and local composition."""

    def __init__(self, registry: ScientificSkillRegistry) -> None:
        self._registry = registry

    async def execute(self, request: ScientificSkillRequest) -> ScientificSkillResult:
        return await asyncio.to_thread(self._registry.execute, request)


_SNAPSHOT_PRODUCING_SKILLS = frozenset(
    {
        ScientificSkillId.simbad_lookup,
        ScientificSkillId.skyview_fits,
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
        ScientificSkillId.gaia_cone_search,
        ScientificSkillId.vizier_tap,
        ScientificSkillId.spectrum_acquisition,
        ScientificSkillId.light_curve_acquisition,
    }
)
_ANALYSIS_SKILLS = frozenset(
    {
        ScientificSkillId.catalog_crossmatch,
        ScientificSkillId.data_profile,
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.correlation_analysis,
        ScientificSkillId.clustering_analysis,
        ScientificSkillId.anomaly_detection,
        ScientificSkillId.simbad_lookup,
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
        ScientificSkillId.fits_image_analysis,
        ScientificSkillId.spectrum_analysis,
        ScientificSkillId.light_curve_analysis,
        ScientificSkillId.gaia_cone_search,
        ScientificSkillId.vizier_tap,
        ScientificSkillId.model_inference,
    }
)
_MODEL_SKILLS = frozenset(
    {
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_classification,
        ScientificSkillId.time_series_forecast,
        ScientificSkillId.image_classification,
    }
)


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
        contract: ResearchContractInput,
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
        scientific_skill_phase(task.skill_id)
        outcome = await self._execute_task(
            task=task,
            project_id=project_id,
            run_id=run_id,
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
            artifact_candidates=candidates,
        )

    async def _execute_task(
        self,
        *,
        task: ScientificTaskInput,
        project_id: str,
        run_id: str,
        resolve_inputs: ScientificInputResolver,
    ) -> ScientificTaskExecutionOutcome:
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
        if task.skill_id in _SNAPSHOT_PRODUCING_SKILLS:
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


async def _materialize_output(
    skill_id: ScientificSkillId,
    output: Mapping[str, object],
    content_storage: ContentStorage,
) -> Mapping[str, object]:
    if skill_id in _MODEL_SKILLS:
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
    skill_id = outcome.task.skill_id
    if skill_id in {
        ScientificSkillId.spectrum_analysis,
        ScientificSkillId.spectrum_acquisition,
    }:
        spectrum_candidates: list[
            AnalysisReportArtifactContent | SpectrumArtifactContent
        ] = []
        if ArtifactKind.spectrum in requested_outputs:
            spectrum_candidates.append(_spectrum(outcome))
        if ArtifactKind.analysis_report in requested_outputs:
            spectrum_candidates.append(_analysis_report(outcome))
        return tuple(spectrum_candidates)
    if skill_id in {
        ScientificSkillId.light_curve_analysis,
        ScientificSkillId.light_curve_acquisition,
    }:
        light_curve_candidates: list[
            AnalysisReportArtifactContent | LightCurveArtifactContent
        ] = []
        if ArtifactKind.light_curve in requested_outputs:
            light_curve_candidates.append(_light_curve(outcome))
        if ArtifactKind.analysis_report in requested_outputs:
            light_curve_candidates.append(_analysis_report(outcome))
        return tuple(light_curve_candidates)
    if (
        skill_id in _ANALYSIS_SKILLS
        and ArtifactKind.analysis_report in requested_outputs
    ):
        return (_analysis_report(outcome),)
    if skill_id in _MODEL_SKILLS:
        candidates: list[ModelEvaluationArtifactContent | ModelArtifactContent] = []
        if ArtifactKind.model_evaluation in requested_outputs:
            candidates.append(_model_evaluation(outcome))
        if ArtifactKind.model_artifact in requested_outputs:
            candidates.append(_model_artifact(outcome))
        return tuple(candidates)
    if ArtifactKind.visualization not in requested_outputs:
        return ()
    if skill_id is ScientificSkillId.chart_visualization:
        return (_chart_visualization(outcome),)
    if skill_id is ScientificSkillId.wwt_scene:
        return (_wwt_visualization(outcome),)
    if skill_id is ScientificSkillId.skyview_fits:
        return _fits_visualizations(outcome)
    return ()


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
        "title": f"Spectrum of {raw['object_name']}",
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
        "title": f"Light curve of {raw['object_name']}",
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
    result_block_id = _stable_id("result", outcome.task.task_id)
    scientific_evidence, evidence_ids = _evidence_for_target(
        outcome,
        target_type="result_block",
        target_id=result_block_id,
    )
    metrics = _metrics_from_output(outcome, evidence_ids=evidence_ids)
    payload: dict[str, object] = {
        "kind": "analysis_report",
        "schema_version": "1.0.0",
        "report_id": _stable_id("report", outcome.task.task_id),
        "title": f"{outcome.task.skill_id.value.replace('_', ' ').title()} report",
        "summary": (
            f"The registered {outcome.task.skill_id.value} skill completed with "
            f"{len(outcome.materialized_output)} bounded output fields."
        ),
        "skill_executions": [_skill_execution(outcome).model_dump(mode="json")],
        "result_blocks": [
            ScientificResultBlock(
                block_id=result_block_id,
                label=f"{outcome.task.skill_id.value.replace('_', ' ').title()} output",
                representation=_result_representation(outcome.materialized_output),
                payload=dict(outcome.materialized_output),
                content_hash=outcome.result.output_hash,
                evidence_ids=evidence_ids,
            ).model_dump(mode="json")
        ],
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "findings": [],
        "limitations": list(outcome.result.warnings),
        "human_required": [],
        "related_artifact_version_ids": list(outcome.artifact_version_ids),
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
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
    dataset_id = _require_dataset_version(outcome)
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
            "dataset_artifact_version_id": dataset_id,
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


def _wwt_visualization(
    outcome: ScientificTaskExecutionOutcome,
) -> VisualizationArtifactContent:
    spec = WwtSceneVisualizationSpec.model_validate(outcome.materialized_output)
    return _visualization(
        outcome,
        spec=spec,
        title=f"WWT scene: {outcome.task.task_id}",
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
            title=f"{outcome.materialized_output.get('survey', 'SkyView')} FITS image",
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
        "description": (
            f"Declarative visualization produced by {outcome.task.skill_id.value}."
        ),
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
    strategy = _text(raw_split, "strategy")
    random_seed = raw_split.get("random_seed")
    split = ModelSplitReference(
        strategy=strategy,
        random_seed=(
            int(random_seed)
            if strategy != "time_ordered" and random_seed is not None
            else None
        ),
        train_fraction=train_count / total,
        validation_fraction=0,
        test_fraction=test_count / total,
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
        "title": f"{_text(output, 'algorithm').replace('_', ' ').title()} evaluation",
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
        "limitations": list(outcome.result.warnings),
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
        "title": f"{_text(output, 'algorithm').replace('_', ' ').title()} model",
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
        "limitations": list(outcome.result.warnings),
        "scientific_evidence": [
            item.model_dump(mode="json") for item in scientific_evidence
        ],
        "source_snapshot_ids": list(outcome.source_snapshot_ids),
        "evidence_ids": list(evidence_ids),
        "input_hash": outcome.result.input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    return _seal(ModelArtifactContent, payload)


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
        f"{distribution}=={version(distribution)}"
        for distribution in distributions
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
    flattened: list[tuple[str, float | int | str]] = []
    _collect_scalars(outcome.materialized_output, prefix="", target=flattened)
    return tuple(
        ScientificMetric(
            metric_id=_stable_id("metric", outcome.task.task_id, path),
            label=path[-256:],
            value=value,
            evidence_ids=evidence_ids,
        )
        for path, value in flattened[:64]
    )


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
            label=str(name).replace("_", " ").title(),
            value=value,
            evidence_ids=evidence_ids,
        )
        for name, value in sorted(raw.items())
        if isinstance(value, int | float | str) and not isinstance(value, bool)
    )


def _collect_scalars(
    value: object,
    *,
    prefix: str,
    target: list[tuple[str, float | int | str]],
) -> None:
    if len(target) >= 64:
        return
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            _collect_scalars(item, prefix=f"{prefix}.{key}".strip("."), target=target)
    elif isinstance(value, list):
        return
    elif isinstance(value, int | float | str) and not isinstance(value, bool):
        target.append((prefix or "value", value))


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
    return evidence, tuple(
        sorted({*outcome.evidence_ids, *(item.evidence_id for item in evidence)})
    )


def _result_representation(value: Mapping[str, object]) -> str:
    if isinstance(value.get("rows"), list):
        return "catalog"
    if isinstance(value.get("statistics"), list):
        return "statistics"
    if isinstance(value.get("correlations"), list):
        return "matrix"
    if isinstance(value.get("events"), list) or isinstance(value.get("forecast"), list):
        return "timeseries"
    if any(isinstance(item, list) for item in value.values()):
        return "table"
    return "record"


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


def _require_dataset_version(outcome: ScientificTaskExecutionOutcome) -> str:
    if not outcome.artifact_version_ids:
        raise ValueError(
            f"{outcome.task.skill_id.value} requires a Dataset ArtifactVersion input"
        )
    return outcome.artifact_version_ids[0]


__all__ = [
    "ScientificInputBinding",
    "ScientificProducedSourceRecorder",
    "ScientificStepAdapter",
    "ScientificStepOutput",
    "ScientificTaskExecutionOutcome",
]
