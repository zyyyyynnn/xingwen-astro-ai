"""Shared Data Artifact build, quality, and publication orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.schemas.core import ArtifactKind
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    compute_data_artifact_public_payload_hash,
)
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationResult,
    compute_data_quality_input_hash,
)
from app.schemas.enums import SourceMode
from app.services.data_artifact_build_inputs import DataArtifactBuildInputRepository
from app.workflow.publisher import (
    ArtifactPublication,
    ProducerExecutionSnapshot,
    admit_artifact_candidate,
)
from app.workflow.step_publication import RunStepContext, StepPublicationFactory
from app.workflow.store import AttemptHandle, LeaseGrant
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.revision import (
    DataRevisionPublicationTarget,
    data_revision_publication_targets,
)
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

    def __init__(
        self,
        publications: StepPublicationFactory,
        build_inputs: DataArtifactBuildInputRepository,
    ) -> None:
        self._publications = publications
        self._build_inputs = build_inputs

    def prepare(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        data_input: DataArtifactBuildInput,
        config: DataArtifactPublicationConfig,
        build_result: DataArtifactBuildResult | None = None,
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
            build_result = build_result or build_data_artifact_candidates(data_input)
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
            self._build_inputs.put(
                project_id=context.project_id,
                input_value=data_input,
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
        publication_targets: tuple[DataRevisionPublicationTarget, ...] | None = None,
    ) -> tuple[ArtifactPublication, ...]:
        if config.source_snapshots:
            self._publications.ensure_source_snapshots(context, config.source_snapshots)

        candidates = {
            "dataset": prepared.build_result.dataset,
            "field_dictionary": prepared.build_result.field_dictionary,
            "source_collection": prepared.build_result.source_collection,
        }
        if publication_targets is None and context.data_revision is not None:
            publication_targets = data_revision_publication_targets(
                context.data_revision.baselines,
                prepared.build_result,
            )
        target_by_kind = (
            {item.artifact_kind: item for item in publication_targets}
            if publication_targets is not None
            else {}
        )
        if publication_targets is not None and set(target_by_kind) != {
            item.value for item in config.publish_kinds
        }:
            raise ValueError("revision publication targets do not match publish kinds")
        completed_kinds: set[str] = set()
        publications: list[ArtifactPublication] = []
        try:
            for kind in config.publish_kinds:
                kind_value = kind.value
                candidate = candidates[kind_value]
                target = target_by_kind.get(kind_value)
                if target is not None and (
                    target.candidate_id != candidate.candidate_id
                    or target.candidate_content_hash
                    != compute_data_artifact_public_payload_hash(candidate)
                ):
                    raise ValueError(
                        "revision publication target does not match admitted candidate"
                    )
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
                publication = (
                    self._publications.publication(
                        context,
                        kind=kind_value,
                        candidate=admitted,
                        producer_execution_id=execution.id,
                        artifact_id=target.artifact_id,
                        supersedes_version_id=target.supersedes_version_id,
                        source_mode=config.source_mode,
                    )
                    if target is not None
                    else self._publications.publication(
                        context,
                        kind=kind_value,
                        candidate=admitted,
                        producer_execution_id=execution.id,
                        source_mode=config.source_mode,
                    )
                )
                publications.append(publication)
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
