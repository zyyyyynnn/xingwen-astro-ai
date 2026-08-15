"""Persistent Worker orchestration for Claim, Relation, and Evidence Graph."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.core import ArtifactKind, ResearchContract
from app.schemas.literature_claim import LiteratureClaimsCandidate
from app.schemas.literature_relation import LiteratureRelationsCandidate
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.services.artifacts import ArtifactReadService
from app.services.graph_inputs import (
    ArtifactVersionGraphInputReadAdapter,
    DatabaseEvidenceRestrictionReadAdapter,
)
from app.services.literature_reasoning import LiteratureReasoningService
from app.services.model_execution import ModelExecutionError, ModelExecutionPort
from app.workflow.literature_pipeline_runtime import LiteraturePipelineRuntime
from app.workflow.publisher import (
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    normalize_producer_parameters,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.claim import PaperSummaryArtifactVersionInput
from services.paper_pipeline.constants import (
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    RELATION_PRODUCER_NAME,
    RELATION_PRODUCER_VERSION,
)
from services.paper_pipeline.relation import LiteratureClaimsArtifactVersionInput


@dataclass(frozen=True, slots=True)
class _ArtifactTarget:
    artifact_id: UUID
    supersedes_version_id: UUID | None


class LiteratureWorkflowRuntime:
    """Close version-pinned literature stages inside one durable Run."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        model_port: ModelExecutionPort,
        model_name: str,
        model_revision: str,
    ) -> None:
        self._session_factory = session_factory
        self._model_name = model_name
        self._reasoning = LiteratureReasoningService(
            model_port,
            provider="qwen",
            model=model_name,
            model_revision=model_revision,
        )
        self._pipelines = LiteraturePipelineRuntime(model_provider="qwen")
        self._producers = ProducerExecutionStore(session_factory)
        self._publisher = ArtifactPublisher(session_factory)

    async def prepare_reasoning_publications(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        contract: ResearchContract,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> tuple[ArtifactPublication, ...]:
        """Publish exact Claim inputs, then prepare final Relation output if needed."""

        require_relations = bool(
            set(contract.output_requirements)
            & {
                ArtifactKind.literature_relations,
                ArtifactKind.reasoning_traces,
                ArtifactKind.graph,
            }
        )
        summaries = self._load_paper_summaries(project_id=project_id, run_id=run_id)
        if not summaries:
            raise PublicationAdmissionError(
                "Literature reasoning requires persisted PaperSummary ArtifactVersions"
            )

        claim_versions = self._load_claim_versions(project_id=project_id, run_id=run_id)
        if not claim_versions:
            claim_publications, candidates = await self._prepare_claim_publications(
                project_id=project_id,
                run_id=run_id,
                summaries=summaries,
                attempt=attempt,
                lease=lease,
            )
            if not require_relations:
                return claim_publications
            published = await asyncio.to_thread(
                self._publisher.publish_intermediate_outputs,
                run_id,
                step_key="reasoning_literature",
                attempt_id=attempt.attempt_id,
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
                publications=claim_publications,
            )
            candidate_by_artifact = {
                publication.artifact_id: candidate
                for publication, candidate in zip(
                    claim_publications, candidates, strict=True
                )
            }
            claim_versions = tuple(
                LiteratureClaimsArtifactVersionInput(
                    artifact_version_id=str(version.id),
                    schema_version=candidate_by_artifact[
                        version.artifact_id
                    ].schema_version,
                    content_hash=version.content_hash,
                    project_id=str(project_id),
                    content=candidate_by_artifact[version.artifact_id],
                )
                for version in published.versions
            )

        if not require_relations:
            raise PublicationAdmissionError(
                "A retried Claim-only step cannot finalize an earlier intermediate set"
            )
        relation_publication = await self._prepare_relation_publication(
            project_id=project_id,
            run_id=run_id,
            claim_versions=claim_versions,
            attempt=attempt,
            lease=lease,
        )
        return (relation_publication,)

    async def prepare_graph_publication(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> ArtifactPublication:
        relation_version_id, relations = self._load_latest_relations(
            project_id=project_id,
            run_id=run_id,
        )
        target = self._ensure_target(
            project_id=project_id,
            kind="graph",
            logical_key=f"graph.{run_id}",
            title="研究证据图谱",
        )
        session_id = self._project_session_id(project_id)
        reader = ArtifactVersionGraphInputReadAdapter(
            artifacts=ArtifactReadService(self._session_factory),
            session_id=session_id,
            evidence_restrictions=DatabaseEvidenceRestrictionReadAdapter(
                self._session_factory
            ),
        )
        prepared = await asyncio.to_thread(
            self._pipelines.prepare_graph,
            project_id=project_id,
            run_id=run_id,
            attempt_id=attempt.attempt_id,
            artifact_id=target.artifact_id,
            literature_relations=relations,
            literature_relations_artifact_version_id=relation_version_id,
            source_mode="live",
            supersedes_version_id=target.supersedes_version_id,
            graph_reader=reader,
        )
        execution = self._producers.start_producer_execution(
            prepared.publication.producer_request,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )
        try:
            self._producers.finish_producer_execution(
                execution.id,
                status="completed",
                output_hash=prepared.publication.candidate.content_hash,
            )
            return prepared.publication.bind_producer_execution(execution.id)
        except Exception:
            self._finish_failed(execution.id, "GRAPH_PUBLICATION_PREPARATION_FAILED")
            raise

    async def _prepare_claim_publications(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        summaries: Sequence[PaperSummaryArtifactVersionInput],
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> tuple[
        tuple[ArtifactPublication, ...],
        tuple[LiteratureClaimsCandidate, ...],
    ]:
        publications: list[ArtifactPublication] = []
        candidates: list[LiteratureClaimsCandidate] = []
        for summary in summaries:
            target = self._ensure_target(
                project_id=project_id,
                kind="literature_claims",
                logical_key=f"literature_claims.{summary.artifact_version_id}",
                title=f"{summary.content.paper.title} · Claims"[:240],
            )
            prepared = self._reasoning.prepare_claim(
                paper_summary_version=summary,
                run_id=str(run_id),
            )
            execution = self._start_model_producer(
                run_id=run_id,
                attempt=attempt,
                lease=lease,
                artifact_id=target.artifact_id,
                kind="literature_claims",
                producer_name=CLAIM_PRODUCER_NAME,
                producer_version=CLAIM_PRODUCER_VERSION,
                plan=prepared.plan,
            )
            try:
                executed = await asyncio.to_thread(
                    self._reasoning.execute_prepared_claim,
                    prepared,
                    producer_execution_id=_pipeline_execution_id(execution.id),
                )
                candidate = executed.admission.publisher_candidate
                if candidate is None:
                    self._producers.finish_producer_execution(
                        execution.id,
                        status="rejected",
                        error_code="LITERATURE_CLAIM_ADMISSION_REJECTED",
                    )
                    raise PublicationAdmissionError(
                        "LiteratureClaim Pipeline rejected every model candidate"
                    )
                persisted_snapshots = _persisted_snapshot_map(
                    candidate.source_snapshot_ids
                )
                publication = self._pipelines.prepare_admitted_claims(
                    project_id=project_id,
                    run_id=run_id,
                    attempt_id=attempt.attempt_id,
                    artifact_id=target.artifact_id,
                    claims=candidate,
                    parameters=prepared.plan.parameters,
                    persisted_source_snapshot_ids=persisted_snapshots,
                    source_mode="live",
                    supersedes_version_id=target.supersedes_version_id,
                ).publication
                self._producers.finish_producer_execution(
                    execution.id,
                    status="completed",
                    output_hash=publication.candidate.content_hash,
                    token_usage=executed.token_usage,
                    latency_ms=executed.latency_ms,
                )
                publications.append(publication.bind_producer_execution(execution.id))
                candidates.append(candidate)
            except Exception as exc:
                if not isinstance(exc, PublicationAdmissionError):
                    self._finish_failed(execution.id, _error_code(exc, "CLAIM_FAILED"))
                raise
        return tuple(publications), tuple(candidates)

    async def _prepare_relation_publication(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        claim_versions: Sequence[LiteratureClaimsArtifactVersionInput],
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> ArtifactPublication:
        target = self._ensure_target(
            project_id=project_id,
            kind="literature_relations",
            logical_key=f"literature_relations.{run_id}",
            title="文献证据关系",
        )
        prepared = self._reasoning.prepare_relation(
            project_id=str(project_id),
            claim_versions=claim_versions,
            run_id=str(run_id),
        )
        execution = self._start_model_producer(
            run_id=run_id,
            attempt=attempt,
            lease=lease,
            artifact_id=target.artifact_id,
            kind="literature_relations",
            producer_name=RELATION_PRODUCER_NAME,
            producer_version=RELATION_PRODUCER_VERSION,
            plan=prepared.plan,
        )
        try:
            executed = await asyncio.to_thread(
                self._reasoning.execute_prepared_relation,
                prepared,
                producer_execution_id=_pipeline_execution_id(execution.id),
            )
            candidate = executed.admission.publisher_candidate
            if candidate is None:
                self._producers.finish_producer_execution(
                    execution.id,
                    status="rejected",
                    error_code="LITERATURE_RELATION_ADMISSION_REJECTED",
                )
                raise PublicationAdmissionError(
                    "LiteratureRelation Pipeline rejected every model candidate"
                )
            publication = self._pipelines.prepare_admitted_relations(
                project_id=project_id,
                run_id=run_id,
                attempt_id=attempt.attempt_id,
                artifact_id=target.artifact_id,
                relations=candidate,
                parameters=prepared.plan.parameters,
                persisted_source_snapshot_ids=_persisted_snapshot_map(
                    candidate.source_snapshot_ids
                ),
                source_mode="live",
                supersedes_version_id=target.supersedes_version_id,
            ).publication
            self._producers.finish_producer_execution(
                execution.id,
                status="completed",
                output_hash=publication.candidate.content_hash,
                token_usage=executed.token_usage,
                latency_ms=executed.latency_ms,
            )
            return publication.bind_producer_execution(execution.id)
        except Exception as exc:
            if not isinstance(exc, PublicationAdmissionError):
                self._finish_failed(execution.id, _error_code(exc, "RELATION_FAILED"))
            raise

    def _start_model_producer(
        self,
        *,
        run_id: UUID,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        artifact_id: UUID,
        kind: str,
        producer_name: str,
        producer_version: str,
        plan: Any,
    ):
        request = ProducerExecutionRequest(
            run_id=run_id,
            step_key="reasoning_literature",
            attempt_id=attempt.attempt_id,
            idempotency_key=(
                f"run:{run_id}:step:reasoning_literature:attempt:"
                f"{attempt.attempt_number}:artifact:{artifact_id}:input:{plan.input_hash}"
            ),
            producer_type="model",
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=plan.input_hash,
            parameters=normalize_producer_parameters(
                plan.parameters,
                parameters_version=plan.parameters_version,
            ),
            model_provider="qwen",
            model_name=self._model_name,
            prompt_name=plan.prompt_name,
            prompt_version=plan.prompt_version,
            prompt_hash=plan.prompt_hash,
        )
        return self._producers.start_producer_execution(
            request,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )

    def _load_paper_summaries(
        self, *, project_id: UUID, run_id: UUID
    ) -> tuple[PaperSummaryArtifactVersionInput, ...]:
        with self._session_factory() as session:
            rows: tuple[ArtifactVersionModel, ...] = ()
            for lineage_run_id in self._lineage_run_ids(
                session, project_id=project_id, run_id=run_id
            ):
                rows = tuple(
                    session.scalars(
                    select(ArtifactVersionModel)
                    .join(
                        ResearchArtifactModel,
                        ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                    )
                    .where(
                        ArtifactVersionModel.project_id == project_id,
                        ArtifactVersionModel.created_by_run_id == lineage_run_id,
                        ResearchArtifactModel.kind == "paper_summary",
                    )
                    .order_by(ArtifactVersionModel.id)
                    )
                )
                if rows:
                    break
        return tuple(
            PaperSummaryArtifactVersionInput(
                artifact_version_id=str(row.id),
                schema_version=row.schema_version,
                content=PaperSummaryArtifactContent.model_validate(row.content),
            )
            for row in rows
        )

    def _load_claim_versions(
        self, *, project_id: UUID, run_id: UUID
    ) -> tuple[LiteratureClaimsArtifactVersionInput, ...]:
        with self._session_factory() as session:
            rows: tuple[ArtifactVersionModel, ...] = ()
            for lineage_run_id in self._lineage_run_ids(
                session, project_id=project_id, run_id=run_id
            ):
                rows = tuple(
                    session.scalars(
                    select(ArtifactVersionModel)
                    .join(
                        ResearchArtifactModel,
                        ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                    )
                    .where(
                        ArtifactVersionModel.project_id == project_id,
                        ArtifactVersionModel.created_by_run_id == lineage_run_id,
                        ResearchArtifactModel.kind == "literature_claims",
                    )
                    .order_by(ArtifactVersionModel.id)
                    )
                )
                if rows:
                    break
        return tuple(
            LiteratureClaimsArtifactVersionInput(
                artifact_version_id=str(row.id),
                schema_version=row.schema_version,
                content_hash=row.content_hash,
                project_id=str(project_id),
                content=LiteratureClaimsCandidate.model_validate(row.content),
            )
            for row in rows
        )

    def _load_latest_relations(
        self, *, project_id: UUID, run_id: UUID
    ) -> tuple[UUID, LiteratureRelationsCandidate]:
        with self._session_factory() as session:
            row: ArtifactVersionModel | None = None
            for lineage_run_id in self._lineage_run_ids(
                session, project_id=project_id, run_id=run_id
            ):
                row = session.scalar(
                    select(ArtifactVersionModel)
                    .join(
                        ResearchArtifactModel,
                        ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                    )
                    .where(
                        ArtifactVersionModel.project_id == project_id,
                        ArtifactVersionModel.created_by_run_id == lineage_run_id,
                        ResearchArtifactModel.kind == "literature_relations",
                    )
                    .order_by(ArtifactVersionModel.created_at.desc())
                    .limit(1)
                )
                if row is not None:
                    break
        if row is None:
            raise PublicationAdmissionError(
                "Graph preparation requires a persisted LiteratureRelations version"
            )
        return row.id, LiteratureRelationsCandidate.model_validate(row.content)

    @staticmethod
    def _lineage_run_ids(
        session: Session, *, project_id: UUID, run_id: UUID
    ) -> tuple[UUID, ...]:
        lineage: list[UUID] = []
        current_id: UUID | None = run_id
        while current_id is not None:
            if current_id in lineage or len(lineage) >= 32:
                raise PublicationAdmissionError("ResearchRun lineage is invalid")
            row = session.scalar(
                select(ResearchRunModel).where(
                    ResearchRunModel.id == current_id,
                    ResearchRunModel.project_id == project_id,
                )
            )
            if row is None:
                raise PublicationAdmissionError("ResearchRun lineage is incomplete")
            lineage.append(row.id)
            current_id = row.parent_run_id
        return tuple(lineage)

    def _ensure_target(
        self,
        *,
        project_id: UUID,
        kind: str,
        logical_key: str,
        title: str,
    ) -> _ArtifactTarget:
        artifact_id = uuid5(NAMESPACE_URL, f"xingwen:{project_id}:{logical_key}")
        with self._session_factory() as session, session.begin():
            artifact = session.get(ResearchArtifactModel, artifact_id)
            if artifact is None:
                artifact = ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind=kind,
                    title=title[:240],
                    logical_key=logical_key,
                )
                session.add(artifact)
                session.flush()
            elif (
                artifact.project_id != project_id
                or artifact.kind != kind
                or artifact.logical_key != logical_key
            ):
                raise PublicationAdmissionError(
                    "ResearchArtifact identity was reused with another meaning"
                )
            return _ArtifactTarget(
                artifact_id=artifact.id,
                supersedes_version_id=artifact.latest_version_id,
            )

    def _project_session_id(self, project_id: UUID) -> str:
        with self._session_factory() as session:
            session_id = session.scalar(
                select(ResearchProjectModel.session_id).where(
                    ResearchProjectModel.id == project_id
                )
            )
        if not session_id:
            raise PublicationAdmissionError("Research Project owner was not found")
        return session_id

    def _finish_failed(self, execution_id: UUID, error_code: str) -> None:
        try:
            self._producers.finish_producer_execution(
                execution_id,
                status="failed",
                error_code=error_code[:128],
            )
        except Exception:
            # Preserve the original pipeline error if another path already closed it.
            pass


def _persisted_snapshot_map(snapshot_ids: Sequence[str]) -> Mapping[str, UUID]:
    try:
        return {value: UUID(value) for value in snapshot_ids}
    except (AttributeError, TypeError, ValueError) as exc:
        raise PublicationAdmissionError(
            "Live literature provenance requires persisted UUID SourceSnapshots"
        ) from exc


def _error_code(error: Exception, fallback: str) -> str:
    if isinstance(error, ModelExecutionError):
        return error.code
    return fallback


def _pipeline_execution_id(execution_id: UUID) -> str:
    """Encode a persisted UUID as the pipeline's stable Identifier shape."""

    return f"producer.{execution_id}"


__all__ = ["LiteratureWorkflowRuntime"]
