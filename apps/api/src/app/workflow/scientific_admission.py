"""Narrow scientific candidate admission for task-owned Workflow steps.

This module validates the scientific candidate set (task binding, contract
binding, Evidence/SourceSnapshot registry closure, cross-ArtifactVersion
ownership, Evidence coverage and execution status) and resolves stable
ResearchArtifact identities. The single ArtifactVersion publication
transaction remains owned by ``ArtifactPublisher``; this admission layer
never writes ArtifactVersion rows itself.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
)
from app.schemas.core import ArtifactKind, ResearchContract, ScientificSkillId
from app.schemas.data_quality import QualityGateStatus
from app.schemas.enums import SourceMode
from app.schemas.source_table import SourceTableAdmission
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    ChartVisualizationSpec,
    LightCurveArtifactContent,
    ModelArtifactContent,
    ModelDiagnosticVisualizationSpec,
    ModelEvaluationArtifactContent,
    SpectrumArtifactContent,
    VisualizationArtifactContent,
)
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactPublication,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    admit_artifact_candidate,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.scientific_skills.execution import (
    ScientificStepOutput,
    source_table_result_payload,
)
from services.data_pipeline.source_table import replay_source_table_admission


ScientificCandidate = (
    AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | SpectrumArtifactContent
    | LightCurveArtifactContent
    | ModelEvaluationArtifactContent
    | ModelArtifactContent
)


@dataclass(frozen=True, slots=True)
class _ArtifactTarget:
    artifact_id: UUID
    publication_key: str
    supersedes_version_id: UUID | None


class ScientificStepAdmission:
    """Admit one complete scientific Step output set before publication."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._producers = ProducerExecutionStore(session_factory)

    def prepare_publications(
        self,
        *,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        step_key: str,
        contract: ResearchContract,
        output: ScientificStepOutput,
        source_mode: SourceMode,
    ) -> tuple[ArtifactPublication, ...]:
        """Admit the candidate set and bind ProducerExecutions.

        Returns the publications for the single ArtifactPublisher transaction;
        this layer never commits ArtifactVersion rows itself.
        """
        self._require_task_binding(
            attempt=attempt,
            step_key=step_key,
            task_id=output.task_id,
            skill_id=output.skill_id.value,
        )
        task = next(
            (
                item
                for item in contract.scientific_tasks
                if item.task_id == output.task_id
            ),
            None,
        )
        if task is None or task.skill_id != output.skill_id:
            raise PublicationAdmissionError(
                "Scientific task output is not bound to the frozen contract"
            )
        if not output.artifact_candidates and not (
            output.skill_id is ScientificSkillId.gaia_cone_search
            and output.source_table_admissions
            and set(contract.output_requirements)
            & {
                ArtifactKind.dataset,
                ArtifactKind.field_dictionary,
                ArtifactKind.source_collection,
            }
        ):
            raise PublicationAdmissionError(
                "A scientific Workflow step must publish its complete output set"
            )
        _validate_source_table_admission_cardinality(output)
        project_id = self._project_id(attempt.run_id)
        publications: list[ArtifactPublication] = []
        for candidate in output.artifact_candidates:
            admitted = admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=_evidence_validator(candidate),
                domain_validator=_domain_validator(
                    self._session_factory,
                    candidate,
                    project_id=project_id,
                ),
                quality_validator=_quality_validator(candidate, contract),
            )
            target = self._ensure_artifact_target(project_id, candidate, step_key)
            execution = self._producers.start_producer_execution(
                ProducerExecutionRequest(
                    run_id=attempt.run_id,
                    step_key=step_key,
                    attempt_id=attempt.attempt_id,
                    idempotency_key=f"scientific-assembly:{target.publication_key}",
                    producer_type="algorithm",
                    producer_name="scientific_artifact_assembler",
                    producer_version="1.0.0",
                    input_hash=candidate.input_hash,
                    parameters={
                        "artifact_kind": candidate.kind.value,
                        "schema_version": candidate.schema_version,
                    },
                ),
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
            )
            self._producers.finish_producer_execution(
                execution.id,
                status="completed",
                output_hash=admitted.content_hash,
                latency_ms=0,
            )
            publications.append(
                ArtifactPublication(
                    artifact_id=target.artifact_id,
                    publication_key=target.publication_key,
                    producer_execution_id=execution.id,
                    candidate=admitted,
                    source_mode=SourceMode(source_mode),
                    supersedes_version_id=target.supersedes_version_id,
                )
            )
        return tuple(publications)

    def _require_task_binding(
        self,
        *,
        attempt: AttemptHandle,
        step_key: str,
        task_id: str,
        skill_id: str,
    ) -> None:
        with self._session_factory() as session:
            step = session.get(RunStepModel, attempt.run_step_id)
            if (
                step is None
                or step.run_id != attempt.run_id
                or step.key != step_key
                or step.task_id != task_id
                or step.skill_id != skill_id
            ):
                raise PublicationAdmissionError(
                    "Scientific task output is not bound to the active RunStep"
                )

    def _project_id(self, run_id: UUID) -> UUID:
        with self._session_factory() as session:
            project_id = session.scalar(
                select(ResearchRunModel.project_id).where(ResearchRunModel.id == run_id)
            )
        if project_id is None:
            raise PublicationAdmissionError("Scientific Run was not found")
        return project_id

    def _ensure_artifact_target(
        self,
        project_id: UUID,
        candidate: ScientificCandidate,
        step_key: str,
    ) -> _ArtifactTarget:
        candidate_id = _candidate_id(candidate)
        logical_key = f"scientific.{candidate.kind.value}.{candidate_id}"
        artifact_id = uuid5(NAMESPACE_URL, f"xingwen:{project_id}:{logical_key}")
        publication_key = str(
            uuid5(
                NAMESPACE_URL,
                f"xingwen:{project_id}:{step_key}:{logical_key}:{candidate.input_hash}",
            )
        )
        with self._session_factory() as session, session.begin():
            artifact = session.get(ResearchArtifactModel, artifact_id)
            if artifact is None:
                artifact = ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind=candidate.kind.value,
                    title=candidate.title,
                    logical_key=logical_key,
                )
                session.add(artifact)
                session.flush()
            elif (
                artifact.project_id != project_id
                or artifact.kind != candidate.kind.value
                or artifact.logical_key != logical_key
            ):
                raise PublicationAdmissionError(
                    "Scientific ResearchArtifact identity was reused with another domain meaning"
                )
            existing = session.scalar(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.artifact_id == artifact.id,
                    ArtifactVersionModel.publication_key == publication_key,
                )
            )
            supersedes = (
                existing.supersedes_version_id
                if existing is not None
                else artifact.latest_version_id
            )
            return _ArtifactTarget(
                artifact_id=artifact.id,
                publication_key=publication_key,
                supersedes_version_id=supersedes,
            )


def _candidate_id(candidate: ScientificCandidate) -> str:
    if isinstance(candidate, AnalysisReportArtifactContent):
        return candidate.report_id
    if isinstance(candidate, VisualizationArtifactContent):
        return candidate.visualization_id
    if isinstance(candidate, SpectrumArtifactContent):
        return candidate.spectrum_id
    if isinstance(candidate, LightCurveArtifactContent):
        return candidate.light_curve_id
    if isinstance(candidate, ModelArtifactContent):
        return candidate.model_id
    return candidate.evaluation_id


def _evidence_validator(candidate: ScientificCandidate):
    def validate(context: ArtifactAdmissionContext) -> None:
        if context.candidate is not candidate:
            raise ValueError("scientific Evidence validator received another candidate")
        if tuple(candidate.source_snapshot_ids) != context.source_snapshot_ids:
            raise ValueError("scientific SourceSnapshot registry drifted")
        if tuple(candidate.evidence_ids) != context.evidence_ids:
            raise ValueError("scientific Evidence registry drifted")

    return validate


def _domain_validator(
    session_factory: Callable[[], Session],
    candidate: ScientificCandidate,
    *,
    project_id: UUID,
):
    referenced = tuple(_referenced_artifact_versions(candidate))

    def validate(context: ArtifactAdmissionContext) -> None:
        if context.candidate is not candidate:
            raise ValueError("scientific domain validator received another candidate")
        version_ids: tuple[UUID, ...] = ()
        if referenced:
            try:
                version_ids = tuple(UUID(item) for item in referenced)
            except ValueError as exc:
                raise ValueError(
                    "scientific ArtifactVersion references must use UUID identities"
                ) from exc
        admissions = (
            candidate.source_table_admissions
            if isinstance(candidate, AnalysisReportArtifactContent)
            else ()
        )
        with session_factory() as session:
            rows = (
                tuple(
                    session.scalars(
                        select(ArtifactVersionModel).where(
                            ArtifactVersionModel.id.in_(version_ids),
                            ArtifactVersionModel.project_id == project_id,
                        )
                    )
                )
                if version_ids
                else ()
            )
            snapshot_ids = tuple(UUID(item.source_snapshot_id) for item in admissions)
            snapshots = (
                tuple(
                    session.scalars(
                        select(SourceSnapshotModel).where(
                            SourceSnapshotModel.id.in_(snapshot_ids),
                            SourceSnapshotModel.project_id == project_id,
                        )
                    )
                )
                if snapshot_ids
                else ()
            )
        if {row.id for row in rows} != set(version_ids):
            raise ValueError(
                "scientific ArtifactVersion references must resolve in the Run Project"
            )
        if (
            isinstance(candidate, ModelEvaluationArtifactContent | ModelArtifactContent)
            and candidate.training_input.kind == "dataset_artifact_version"
        ):
            row = next(
                item for item in rows if str(item.id) == candidate.training_input.ref_id
            )
            if row.content.get("kind") != "dataset":
                raise ValueError("model input must be a Dataset ArtifactVersion")
        snapshots_by_id = {str(row.id): row for row in snapshots}
        for admission in admissions:
            snapshot = snapshots_by_id.get(admission.source_snapshot_id)
            if snapshot is None or (
                snapshot.source_id != admission.source_id
                or snapshot.content_hash != admission.source_snapshot_content_hash
                or snapshot.query_hash != admission.query_hash
                or snapshot.retrieved_at != admission.retrieved_at
            ):
                raise ValueError(
                    "source-table admission is not bound to its persisted SourceSnapshot"
                )

    return validate


def _quality_validator(
    candidate: ScientificCandidate,
    contract: ResearchContract,
):
    def validate(context: ArtifactAdmissionContext) -> None:
        if context.candidate is not candidate:
            raise ValueError("scientific quality validator received another candidate")
        required = contract.evidence_requirements.minimum_coverage
        covered, total = _evidence_coverage(candidate)
        coverage = 1.0 if total == 0 else covered / total
        if coverage < required:
            raise ValueError(
                f"scientific Evidence coverage {coverage:.3f} is below {required:.3f}"
            )
        executions = (
            candidate.skill_executions
            if not isinstance(
                candidate, ModelEvaluationArtifactContent | ModelArtifactContent
            )
            else (candidate.skill_execution,)
        )
        if any(item.status not in {"completed", "partial"} for item in executions):
            raise ValueError("scientific Artifact contains a non-publishable execution")
        if isinstance(candidate, AnalysisReportArtifactContent):
            for admission in candidate.source_table_admissions:
                _validate_source_table_admission(candidate, contract, admission)

    return validate


def _validate_source_table_admission_cardinality(
    output: ScientificStepOutput,
) -> None:
    admissions = output.source_table_admissions
    report_admissions = tuple(
        admission
        for candidate in output.artifact_candidates
        if isinstance(candidate, AnalysisReportArtifactContent)
        for admission in candidate.source_table_admissions
    )
    has_report = any(
        isinstance(candidate, AnalysisReportArtifactContent)
        for candidate in output.artifact_candidates
    )
    if has_report and report_admissions != admissions:
        raise PublicationAdmissionError(
            "scientific source-table admission cardinality is not closed across the output"
        )
    expected = 1 if output.skill_id is ScientificSkillId.gaia_cone_search else 0
    if len(admissions) != expected:
        raise PublicationAdmissionError(
            "scientific source-table admission cardinality disagrees with the skill"
        )


def _validate_source_table_admission(
    candidate: AnalysisReportArtifactContent,
    contract: ResearchContract,
    admission: SourceTableAdmission,
) -> None:
    if admission.overall_status is not QualityGateStatus.pass_:
        raise ValueError(
            "source table did not pass the Contract quality gate: "
            + admission.source_result_status
        )
    if (
        admission.research_contract_id != contract.id
        or admission.research_contract_version != contract.version
        or admission.research_contract_content_hash != contract.content_hash
    ):
        raise ValueError("source-table admission is not bound to this Contract")
    replay_source_table_admission(admission, contract=contract)
    if admission.source_snapshot_id not in candidate.source_snapshot_ids:
        raise ValueError("source-table admission snapshot is outside the Artifact")
    cell_evidence_ids = tuple(cell.evidence_id for cell in admission.cells)
    if not cell_evidence_ids or not set(cell_evidence_ids) <= set(
        candidate.evidence_ids
    ):
        raise ValueError("source-table cell Evidence is incomplete")
    blocks = tuple(
        block
        for block in candidate.result_blocks
        if block.evidence_ids == tuple(sorted(cell_evidence_ids))
    )
    if len(blocks) != 1:
        raise ValueError("source-table admission does not close one result table")
    if blocks[0].payload != source_table_result_payload(admission):
        raise ValueError("source-table result payload drifted from its admission")
    evidence_by_id = {item.evidence_id: item for item in candidate.scientific_evidence}
    for cell in admission.cells:
        evidence = evidence_by_id.get(cell.evidence_id)
        if evidence is None or (
            evidence.target_id != blocks[0].block_id
            or evidence.source_snapshot_id != admission.source_snapshot_id
            or evidence.locator != cell.locator.model_dump(mode="json")
            or evidence.quote_or_value != cell.canonical_value
        ):
            raise ValueError("source-table cell Evidence locator drifted")


def _referenced_artifact_versions(candidate: ScientificCandidate) -> Iterable[str]:
    if isinstance(candidate, AnalysisReportArtifactContent):
        yield from candidate.related_artifact_version_ids
    elif isinstance(candidate, ModelEvaluationArtifactContent):
        if candidate.training_input.kind == "dataset_artifact_version":
            yield candidate.training_input.ref_id
        yield from candidate.diagnostic_visualization_ids
    elif isinstance(candidate, ModelArtifactContent):
        if candidate.training_input.kind == "dataset_artifact_version":
            yield candidate.training_input.ref_id
    elif isinstance(candidate, VisualizationArtifactContent):
        if isinstance(candidate.spec, ChartVisualizationSpec):
            if candidate.spec.dataset_artifact_version_id is not None:
                yield candidate.spec.dataset_artifact_version_id
        elif isinstance(candidate.spec, ModelDiagnosticVisualizationSpec):
            yield candidate.spec.model_evaluation_artifact_version_id


def _evidence_coverage(candidate: ScientificCandidate) -> tuple[int, int]:
    if isinstance(candidate, AnalysisReportArtifactContent):
        items = (*candidate.result_blocks, *candidate.metrics, *candidate.findings)
        return sum(bool(item.evidence_ids) for item in items), len(items)
    if isinstance(candidate, ModelEvaluationArtifactContent):
        items = (*candidate.metrics, *candidate.baseline_metrics)
        return sum(bool(item.evidence_ids) for item in items), len(items)
    if isinstance(candidate, ModelArtifactContent):
        return (1 if candidate.evidence_ids else 0), 1
    if candidate.source_snapshot_ids:
        return (1 if candidate.evidence_ids else 0), 1
    return 0, 0


__all__ = ["ScientificStepAdmission"]
