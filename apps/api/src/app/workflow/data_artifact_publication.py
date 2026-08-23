"""Shared Data Artifact build, quality, and publication orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.schemas.core import ArtifactKind
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    compute_data_quality_input_hash,
)
from app.schemas.enums import SourceMode
from app.workflow.publisher import (
    ArtifactPublication,
    ProducerExecutionSnapshot,
    admit_artifact_candidate,
)
from app.workflow.step_publication import RunStepContext, StepPublicationFactory
from app.workflow.store import AttemptHandle, LeaseGrant
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.admission import QualityAdmittedDataArtifacts
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set


@dataclass(frozen=True, slots=True)
class DataArtifactPublicationConfig:
    """Step-specific bindings for the shared Data Artifact publication seam."""

    publish_kinds: tuple[ArtifactKind, ...]
    operation_key_prefix: str
    producer_error_code: str
    producer_version: str
    quality_failure_message: str
    source_mode: SourceMode = SourceMode.live
    snapshot_bindings_override: dict[str, str] | None = None
    source_snapshots: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedDataArtifacts:
    """Immutable handoff between quality admission and publication."""

    build_result: DataArtifactBuildResult
    quality: QualityAdmittedDataArtifacts
    executions: dict[str, ProducerExecutionSnapshot]


class DataArtifactPublicationService:
    """Own the common Data Artifact lifecycle for all producing RunSteps."""

    def __init__(self, publications: StepPublicationFactory) -> None:
        self._publications = publications

    def prepare(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        data_input: DataArtifactBuildInput,
        config: DataArtifactPublicationConfig,
    ) -> PreparedDataArtifacts:
        if not config.publish_kinds:
            raise ValueError("Data Artifact publication requires at least one kind")

        executions = {
            kind.value: self._publications.start_producer(
                context,
                step_key=step_key,
                operation_key=f"{config.operation_key_prefix}:{kind.value}",
                producer_type="algorithm",
                producer_name=f"data-artifact-{kind.value}",
                producer_version=config.producer_version,
                input_hash=data_input.input_hash,
                parameters={},
                attempt=attempt,
                lease=lease,
            )
            for kind in config.publish_kinds
        }
        try:
            build_result = build_data_artifact_candidates(data_input)
            quality_payload = {
                "data_artifact_input": data_input,
                "dataset_candidate": build_result.dataset,
                "field_dictionary_candidate": build_result.field_dictionary,
                "source_collection_candidate": build_result.source_collection,
                "research_contract": context.contract,
                "quality_rule_set": load_frozen_quality_rule_set(),
            }
            quality_unhashed = DataQualityEvaluationInput.model_construct(
                **quality_payload,
                input_hash="sha256:" + "0" * 64,
            )
            quality_payload["input_hash"] = compute_data_quality_input_hash(
                quality_unhashed
            )
            quality_input = DataQualityEvaluationInput.model_validate(quality_payload)
            quality_result = evaluate_data_quality(quality_input)
            if not isinstance(quality_result, DataQualityEvaluationResult):
                raise ValueError(config.quality_failure_message)
            quality = admit_data_artifact_quality(
                build_result=build_result,
                evaluation_input=quality_input,
                evaluation_result=quality_result,
            )
        except Exception:
            self._finish_failed(executions, config.producer_error_code)
            raise

        return PreparedDataArtifacts(
            build_result=build_result,
            quality=quality,
            executions=executions,
        )

    def publish(
        self,
        context: RunStepContext,
        *,
        prepared: PreparedDataArtifacts,
        config: DataArtifactPublicationConfig,
    ) -> tuple[ArtifactPublication, ...]:
        if config.source_snapshots:
            self._publications.ensure_source_snapshots(context, config.source_snapshots)

        candidates = {
            "dataset": prepared.build_result.dataset,
            "field_dictionary": prepared.build_result.field_dictionary,
            "source_collection": prepared.build_result.source_collection,
        }
        completed_kinds: set[str] = set()
        publications: list[ArtifactPublication] = []
        try:
            for kind in config.publish_kinds:
                kind_value = kind.value
                candidate = candidates[kind_value]
                source_bindings, evidence_bindings = self._publications.data_bindings(
                    context,
                    kind=kind_value,
                    candidate=prepared.build_result.dataset,
                    snapshot_bindings_override=config.snapshot_bindings_override,
                )
                admitted = admit_artifact_candidate(
                    candidate,
                    schema_version=candidate.schema_version,
                    source_snapshot_ids=candidate.source_snapshot_ids,
                    evidence_ids=candidate.evidence_ids,
                    evidence_validator=validate_data_artifact_evidence,
                    domain_validator=validate_data_artifact_domain,
                    quality_validator=build_data_quality_publication_validator(
                        prepared.quality,
                        candidate_kind=kind_value,
                    ),
                    source_snapshot_bindings=source_bindings,
                    evidence_bindings=evidence_bindings,
                    data_provenance_candidate=(
                        None
                        if kind is ArtifactKind.dataset
                        else prepared.build_result.dataset
                    ),
                )
                execution = prepared.executions[kind_value]
                self._publications.finish_producer(
                    execution.id,
                    status="completed",
                    input_hash=candidate.input_hash,
                    output_hash=admitted.content_hash,
                )
                completed_kinds.add(kind_value)
                publications.append(
                    self._publications.publication(
                        context,
                        kind=kind_value,
                        candidate=admitted,
                        producer_execution_id=execution.id,
                        source_mode=config.source_mode,
                    )
                )
        except Exception:
            for kind, execution in prepared.executions.items():
                if kind not in completed_kinds:
                    self._publications.finish_producer(
                        execution.id,
                        status="failed",
                        error_code=config.producer_error_code,
                    )
            raise

        context.data_result = prepared.build_result
        return tuple(publications)

    def _finish_failed(
        self,
        executions: Mapping[str, ProducerExecutionSnapshot],
        error_code: str,
    ) -> None:
        for execution in executions.values():
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code=error_code,
            )
