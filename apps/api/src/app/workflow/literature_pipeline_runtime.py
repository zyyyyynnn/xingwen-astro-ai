"""Prepare the production literature pipeline for the persistent Worker.

This module is deliberately a preparation boundary.  The paper pipelines and the
Evidence Graph pipeline own validation and publication authority; this module only
adapts their sealed candidates to the application's Publisher ports.  In
particular, it never calls a source adapter, a benchmark runner, or a model client,
and it never invents a persisted ProducerExecution or ArtifactVersion id.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import SourceMode
from app.schemas.graph_artifact import (
    GraphArtifactCandidate,
    GraphBuildRequest,
    GraphBuildScope,
    GraphEdgeType,
    GraphLayoutHint,
    GraphPolicySet,
    GraphStructuralEdgeRequest,
    graph_algorithm_parameters,
)
from app.schemas.literature_claim import (
    LiteratureClaimStatus,
    LiteratureClaimsCandidate,
)
from app.schemas.literature_relation import (
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationStatus,
    LiteratureRelationsCandidate,
)
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.workflow.publisher import (
    AdmittedArtifactCandidate,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    ProducerParameter,
    ProducerExecutionRequest,
    admit_artifact_candidate,
    normalize_producer_parameters,
)
from services.graph_pipeline import GraphPipeline, build_complete_progressive_input
from services.graph_pipeline.ports import VersionedGraphInputReadPort
from services.paper_pipeline.claim import (
    LiteratureClaimPipeline,
    PaperSummaryArtifactVersionInput,
)
from services.paper_pipeline.relation import (
    LiteratureClaimsArtifactVersionInput,
    LiteratureRelationPipeline,
)


PublicationSourceMode = Literal["fixture", "live", "cached"]
_NAMESPACE = "https://xingwen.example/literature-pipeline-runtime"


class LiteraturePipelinePreparationError(ValueError):
    """Raised when a pipeline handoff cannot be closed without guessing."""


@dataclass(frozen=True, slots=True)
class PreparedArtifactPublication:
    """A sealed candidate plus the request needed to create its ProducerExecution.

    ``ArtifactPublication`` intentionally requires the id of an already-created
    ProducerExecution.  The Worker owns that transaction and lease, so this value
    cannot manufacture the id.  ``bind_producer_execution`` is the only handoff
    from this pure preparation boundary to the Publisher publication value.
    """

    kind: Literal["paper_summary", "literature_claims", "literature_relations", "graph"]
    artifact_id: UUID
    publication_key: str
    producer_request: ProducerExecutionRequest
    candidate: AdmittedArtifactCandidate
    source_mode: PublicationSourceMode
    supersedes_version_id: UUID | None = None

    def bind_producer_execution(self, producer_execution_id: UUID | str) -> ArtifactPublication:
        """Attach the exact persisted ProducerExecution created by the Worker."""

        return ArtifactPublication(
            artifact_id=self.artifact_id,
            publication_key=self.publication_key,
            producer_execution_id=_uuid(producer_execution_id, "producer_execution_id"),
            candidate=self.candidate,
            source_mode=self.source_mode,
            supersedes_version_id=self.supersedes_version_id,
        )


@dataclass(frozen=True, slots=True)
class PaperSummaryPreparation:
    summary: PaperSummaryArtifactContent
    publication: PreparedArtifactPublication


@dataclass(frozen=True, slots=True)
class LiteratureClaimsPreparation:
    admission: object | None
    claims: LiteratureClaimsCandidate
    publication: PreparedArtifactPublication


@dataclass(frozen=True, slots=True)
class LiteratureRelationsPreparation:
    admission: object | None
    relations: LiteratureRelationsCandidate
    publication: PreparedArtifactPublication


@dataclass(frozen=True, slots=True)
class GraphPreparation:
    request: GraphBuildRequest
    candidate: GraphArtifactCandidate
    publication: PreparedArtifactPublication


class LiteraturePipelineRuntime:
    """Adapt sealed literature/graph candidates to Worker publication requests.

    The runtime is intentionally stateless.  A caller supplies the exact immutable
    upstream version used by the next pipeline stage and the persisted provenance
    ids already allocated by the application.  This makes retries deterministic
    while keeping database leases, ProducerExecution rows, and ArtifactVersion
    creation in ``PersistentWorkflowStore``/``ArtifactPublisher``.
    """

    def __init__(
        self,
        *,
        graph_reader: VersionedGraphInputReadPort | None = None,
        model_provider: str | None = None,
    ) -> None:
        self._graph_reader = graph_reader
        self._model_provider = model_provider

    def prepare_paper_summary(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        summary: PaperSummaryArtifactContent,
        persisted_source_snapshot_ids: Mapping[str, UUID | str],
        parameters: Mapping[str, ProducerParameter],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
        model_provider: str | None = None,
    ) -> PaperSummaryPreparation:
        """Prepare a previously admitted PaperSummary for Publisher handoff.

        Summary admission remains owned by ``PaperSummaryPipeline`` (including its
        process-local seal).  This method does not accept a raw model response and
        therefore cannot turn an unadmitted model payload into a publication.
        """

        if type(summary) is not PaperSummaryArtifactContent:
            raise LiteraturePipelinePreparationError(
                "PaperSummary preparation requires the exact admitted content model"
            )
        source_mode_value = _source_mode(source_mode)
        _reject_fixture_as_live(summary, source_mode_value)
        snapshot_ids = tuple(
            sorted(item.source_snapshot_id for item in summary.input_versions.source_snapshots)
        )
        source_bindings = _source_bindings(
            snapshot_ids,
            persisted_source_snapshot_ids,
        )
        evidence_bindings = tuple(
            ArtifactEvidenceBinding(
                target_type="paper_summary",
                target_id=summary.summary_id,
                pipeline_evidence_id=item.evidence_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=_stable_uuid(
                    project_id,
                    run_id,
                    "paper_summary",
                    f"evidence:{item.evidence_id}:{item.source_snapshot_id}",
                ),
                persisted_source_snapshot_id=_persisted_snapshot_for(
                    source_bindings,
                    item.source_snapshot_id,
                ),
            )
            for item in sorted(summary.evidence, key=lambda value: value.evidence_id)
        )
        admitted = _admit(
            summary,
            schema_version=summary.schema_version,
            source_snapshot_ids=snapshot_ids,
            evidence_ids=tuple(sorted(summary.evidence_ids)),
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="paper_summary",
            project_id=project_id,
            run_id=run_id,
            attempt_id=attempt_id,
            artifact_id=artifact_id,
            step_key="summarizing_papers",
            candidate=admitted,
            producer=summary.producer,
            parameters=parameters,
            source_mode=source_mode,
            supersedes_version_id=supersedes_version_id,
            model_provider=model_provider,
        )
        return PaperSummaryPreparation(summary=summary, publication=publication)

    def prepare_claims(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        paper_summary_version: PaperSummaryArtifactVersionInput,
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ProducerParameter],
        persisted_source_snapshot_ids: Mapping[str, UUID | str],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
    ) -> LiteratureClaimsPreparation:
        """Run authoritative Claim admission and prepare its publication.

        ``paper_summary_version.artifact_version_id`` must be the actual persisted
        Summary version.  It is deliberately not derived from ``run_id``.
        """

        if type(paper_summary_version) is not PaperSummaryArtifactVersionInput:
            raise LiteraturePipelinePreparationError(
                "Claims require the exact PaperSummary artifact-version input"
            )
        source_mode_value = _source_mode(source_mode)
        _reject_fixture_as_live(paper_summary_version.content, source_mode_value)
        project_uuid = _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        admission = LiteratureClaimPipeline().admit(
            paper_summary_artifact_version_id=paper_summary_version.artifact_version_id,
            paper_id=paper_summary_version.content.paper_id,
            paper_summary_versions={
                paper_summary_version.artifact_version_id: paper_summary_version
            },
            model_response=model_response,
            model_name=model_name,
            parameters=parameters,
            run_id=str(run_uuid),
            available_evidence_ids=frozenset(paper_summary_version.content.evidence_ids),
            available_source_snapshot_ids=frozenset(
                item.source_snapshot_id
                for item in paper_summary_version.content.input_versions.source_snapshots
            ),
        )
        claims = admission.publisher_candidate
        if claims is None:
            raise LiteraturePipelinePreparationError(
                "LiteratureClaim Pipeline did not produce a publisher candidate"
            )
        source_bindings = _source_bindings(
            claims.source_snapshot_ids,
            persisted_source_snapshot_ids,
        )
        evidence_bindings = _literature_evidence_bindings(
            candidate=claims,
            kind="literature_claims",
            project_id=project_uuid,
            run_id=run_uuid,
            persisted_source_snapshot_ids=persisted_source_snapshot_ids,
        )
        admitted = _admit(
            claims,
            schema_version=claims.schema_version,
            source_snapshot_ids=claims.source_snapshot_ids,
            evidence_ids=claims.evidence_ids,
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="literature_claims",
            project_id=project_uuid,
            run_id=run_uuid,
            attempt_id=attempt_uuid,
            artifact_id=artifact_id,
            step_key="reasoning_literature",
            candidate=admitted,
            producer=claims.producer,
            parameters=parameters,
            source_mode=source_mode_value,
            supersedes_version_id=supersedes_version_id,
        )
        return LiteratureClaimsPreparation(
            admission=admission,
            claims=claims,
            publication=publication,
        )

    def prepare_admitted_claims(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        claims: LiteratureClaimsCandidate,
        parameters: Mapping[str, ProducerParameter],
        persisted_source_snapshot_ids: Mapping[str, UUID | str],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
    ) -> LiteratureClaimsPreparation:
        """Prepare an already sealed Claim candidate for publication.

        The Claim Pipeline must have produced and sealed ``claims`` before this
        boundary is called.  This method only closes persisted provenance and
        creates the Publisher request; it never invokes the Claim Pipeline.
        """

        project_uuid = _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        source_mode_value = _source_mode(source_mode)
        _validate_admitted_literature_candidate(
            claims,
            kind="literature_claims",
            project_id=project_uuid,
            run_id=run_uuid,
            source_mode=source_mode_value,
        )
        source_bindings = _source_bindings(
            claims.source_snapshot_ids,
            persisted_source_snapshot_ids,
        )
        evidence_bindings = _literature_evidence_bindings(
            candidate=claims,
            kind="literature_claims",
            project_id=project_uuid,
            run_id=run_uuid,
            persisted_source_snapshot_ids=persisted_source_snapshot_ids,
        )
        admitted = _admit(
            claims,
            schema_version=claims.schema_version,
            source_snapshot_ids=claims.source_snapshot_ids,
            evidence_ids=claims.evidence_ids,
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="literature_claims",
            project_id=project_uuid,
            run_id=run_uuid,
            attempt_id=attempt_uuid,
            artifact_id=artifact_id,
            step_key="reasoning_literature",
            candidate=admitted,
            producer=claims.producer,
            parameters=parameters,
            source_mode=source_mode_value,
            supersedes_version_id=supersedes_version_id,
        )
        return LiteratureClaimsPreparation(
            admission=None,
            claims=claims,
            publication=publication,
        )

    def prepare_relations(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        literature_claim_versions: Sequence[LiteratureClaimsArtifactVersionInput],
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ProducerParameter],
        confidence_assessments: Mapping[str, LiteratureRelationConfidenceAssessment],
        persisted_source_snapshot_ids: Mapping[str, UUID | str],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
    ) -> LiteratureRelationsPreparation:
        """Run authoritative Relation admission against the actual Claim version."""

        claim_versions = tuple(literature_claim_versions)
        if not claim_versions or any(
            type(item) is not LiteratureClaimsArtifactVersionInput
            for item in claim_versions
        ):
            raise LiteraturePipelinePreparationError(
                "Relations require one or more exact LiteratureClaims artifact-version inputs"
            )
        source_mode_value = _source_mode(source_mode)
        project_uuid = _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        claim_version_by_id = {
            item.artifact_version_id: item for item in claim_versions
        }
        if len(claim_version_by_id) != len(claim_versions):
            raise LiteraturePipelinePreparationError(
                "LiteratureClaims artifact-version ids must be unique"
            )
        claims = tuple(item.content for item in claim_versions)
        comparable = tuple(
            item
            for content in claims
            for item in content.claims
            if item.status is not LiteratureClaimStatus.rejected and item.evidence_ids
        )
        if len(comparable) < 2:
            raise LiteraturePipelinePreparationError(
                "at least two non-rejected Evidence-backed Claims are required for Relation admission"
            )
        admission = LiteratureRelationPipeline().admit(
            literature_claim_artifact_version_ids=tuple(
                sorted(claim_version_by_id)
            ),
            literature_claim_versions=claim_version_by_id,
            project_id=str(project_uuid),
            model_response=model_response,
            model_name=model_name,
            parameters=parameters,
            confidence_assessments=confidence_assessments,
            run_id=str(run_uuid),
            available_evidence_ids=frozenset(
                evidence_id
                for content in claims
                for evidence_id in content.evidence_ids
            ),
            available_source_snapshot_ids=frozenset(
                snapshot_id
                for content in claims
                for snapshot_id in content.source_snapshot_ids
            ),
            available_paper_summary_artifact_version_ids=frozenset(
                {
                    item.source_paper_summary_artifact_version_id
                    for content in claims
                    for item in content.claims
                }
            ),
        )
        relations = admission.publisher_candidate
        if relations is None:
            raise LiteraturePipelinePreparationError(
                "LiteratureRelation Pipeline did not produce a publisher candidate"
            )
        source_bindings = _source_bindings(
            relations.source_snapshot_ids,
            persisted_source_snapshot_ids,
        )
        evidence_bindings = _literature_evidence_bindings(
            candidate=relations,
            kind="literature_relations",
            project_id=project_uuid,
            run_id=run_uuid,
            persisted_source_snapshot_ids=persisted_source_snapshot_ids,
        )
        admitted = _admit(
            relations,
            schema_version=relations.schema_version,
            source_snapshot_ids=relations.source_snapshot_ids,
            evidence_ids=relations.evidence_ids,
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="literature_relations",
            project_id=project_uuid,
            run_id=run_uuid,
            attempt_id=attempt_uuid,
            artifact_id=artifact_id,
            step_key="reasoning_literature",
            candidate=admitted,
            producer=relations.producer,
            parameters=parameters,
            source_mode=source_mode_value,
            supersedes_version_id=supersedes_version_id,
        )
        return LiteratureRelationsPreparation(
            admission=admission,
            relations=relations,
            publication=publication,
        )

    def prepare_admitted_relations(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        relations: LiteratureRelationsCandidate,
        parameters: Mapping[str, ProducerParameter],
        persisted_source_snapshot_ids: Mapping[str, UUID | str],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
    ) -> LiteratureRelationsPreparation:
        """Prepare an already sealed Relation candidate for publication.

        Relation admission and model execution are owned by
        ``LiteratureRelationPipeline``.  The runtime only verifies the sealed
        handoff, materializes persisted provenance, and builds the Publisher
        request with the candidate's versioned parameter hash.
        """

        project_uuid = _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        source_mode_value = _source_mode(source_mode)
        _validate_admitted_literature_candidate(
            relations,
            kind="literature_relations",
            project_id=project_uuid,
            run_id=run_uuid,
            source_mode=source_mode_value,
        )
        source_bindings = _source_bindings(
            relations.source_snapshot_ids,
            persisted_source_snapshot_ids,
        )
        evidence_bindings = _literature_evidence_bindings(
            candidate=relations,
            kind="literature_relations",
            project_id=project_uuid,
            run_id=run_uuid,
            persisted_source_snapshot_ids=persisted_source_snapshot_ids,
        )
        admitted = _admit(
            relations,
            schema_version=relations.schema_version,
            source_snapshot_ids=relations.source_snapshot_ids,
            evidence_ids=relations.evidence_ids,
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="literature_relations",
            project_id=project_uuid,
            run_id=run_uuid,
            attempt_id=attempt_uuid,
            artifact_id=artifact_id,
            step_key="reasoning_literature",
            candidate=admitted,
            producer=relations.producer,
            parameters=parameters,
            source_mode=source_mode_value,
            supersedes_version_id=supersedes_version_id,
        )
        return LiteratureRelationsPreparation(
            admission=None,
            relations=relations,
            publication=publication,
        )

    def prepare_graph(
        self,
        *,
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        literature_relations: LiteratureRelationsCandidate,
        literature_relations_artifact_version_id: UUID | str,
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None = None,
        graph_reader: VersionedGraphInputReadPort | None = None,
    ) -> GraphPreparation:
        """Build and admit Graph from one exact persisted Relations version."""

        if type(literature_relations) is not LiteratureRelationsCandidate:
            raise LiteraturePipelinePreparationError(
                "Graph preparation requires the exact LiteratureRelations candidate"
            )
        source_mode_value = _source_mode(source_mode)
        project_uuid = _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        relation_version_uuid = _uuid(
            literature_relations_artifact_version_id,
            "literature_relations_artifact_version_id",
        )
        accepted_claims = tuple(
            sorted(
                (
                    item
                    for item in literature_relations.claims
                    if item.status is LiteratureClaimStatus.accepted
                ),
                key=lambda item: item.claim_id,
            )
        )
        accepted_relations = tuple(
            sorted(
                (
                    item
                    for item in literature_relations.relations
                    if item.status is LiteratureRelationStatus.accepted
                ),
                key=lambda item: item.relation_id,
            )
        )
        if not accepted_claims or not accepted_relations:
            raise LiteraturePipelinePreparationError(
                "Graph preparation requires accepted Claims and Relations"
            )
        scope = GraphBuildScope(
            literature_paper_ids=tuple(sorted({item.paper_id for item in accepted_claims})),
            literature_claim_ids=tuple(item.claim_id for item in accepted_claims),
            accepted_relation_ids=tuple(item.relation_id for item in accepted_relations),
            structural_edges=tuple(
                GraphStructuralEdgeRequest(
                    edge_type=GraphEdgeType.supports_finding,
                    source_paper_id=item.paper_id,
                    target_claim_id=item.claim_id,
                )
                for item in accepted_claims
            ),
        )
        progressive = build_complete_progressive_input(
            progressive_id=(
                f"progressive.{run_uuid.hex}.{relation_version_uuid.hex}"
            ),
            literature_relations_artifact_version_id=str(relation_version_uuid),
            dataset_artifact_version_id=None,
            field_dictionary_artifact_version_id=None,
            scope=scope,
        )
        request = GraphBuildRequest(
            project_id=str(project_uuid),
            literature_relations_artifact_version_id=str(relation_version_uuid),
            scope=scope,
            policies=GraphPolicySet(),
            progressive=progressive,
            layout_hint=GraphLayoutHint(strategy="group_by_node_type"),
        )
        reader = graph_reader or self._graph_reader
        if reader is None:
            raise LiteraturePipelinePreparationError(
                "Graph preparation requires the exact versioned input read port"
            )
        result = GraphPipeline(reader).admit(request)
        candidate = result.candidate
        if candidate is None:
            failure = result.report.first_rejection_reason
            detail = result.report.findings[0] if result.report.findings else None
            raise LiteraturePipelinePreparationError(
                "Evidence Graph Pipeline rejected the exact Relations version"
                + (f": {failure.value}" if failure is not None else "")
                + (
                    f" at {detail.path} ({detail.message})"
                    if detail is not None
                    else ""
                )
            )
        source_bindings = tuple(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_source_snapshot_id=item.persisted_source_snapshot_id,
            )
            for item in sorted(candidate.source_snapshots, key=lambda value: value.source_snapshot_id)
        )
        persisted_by_pipeline = {
            item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
            for item in source_bindings
        }
        evidence_bindings = tuple(
            ArtifactEvidenceBinding(
                target_type="graph_edge",
                target_id=item.graph_edge_id,
                pipeline_evidence_id=item.evidence_use_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=_stable_uuid(
                    project_uuid,
                    run_uuid,
                    "graph",
                    f"evidence:{item.evidence_use_id}",
                ),
                persisted_source_snapshot_id=persisted_by_pipeline[
                    item.source_snapshot_id
                ],
            )
            for item in sorted(candidate.evidence_uses, key=lambda value: value.evidence_use_id)
        )
        upstream_evidence_ids = {
            item.upstream_evidence_id for item in candidate.evidence_uses
        }
        if any(item.persisted_evidence_id in upstream_evidence_ids for item in evidence_bindings):
            raise LiteraturePipelinePreparationError(
                "Graph-owned Evidence ids must not reuse upstream Evidence ids"
            )
        admitted = _admit(
            candidate,
            schema_version=candidate.schema_version,
            source_snapshot_ids=tuple(
                item.pipeline_source_snapshot_id for item in source_bindings
            ),
            evidence_ids=tuple(item.evidence_use_id for item in candidate.evidence_uses),
            source_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        publication = self._publication(
            kind="graph",
            project_id=project_uuid,
            run_id=run_uuid,
            attempt_id=attempt_uuid,
            artifact_id=artifact_id,
            step_key="building_graph",
            candidate=admitted,
            producer=candidate.producer,
            parameters=graph_algorithm_parameters(candidate.policies, candidate.taxonomy),
            source_mode=source_mode_value,
            supersedes_version_id=supersedes_version_id,
            model_provider=None,
        )
        return GraphPreparation(
            request=request,
            candidate=candidate,
            publication=publication,
        )

    def _publication(
        self,
        *,
        kind: Literal["paper_summary", "literature_claims", "literature_relations", "graph"],
        project_id: UUID | str,
        run_id: UUID | str,
        attempt_id: UUID | str,
        artifact_id: UUID | str,
        step_key: str,
        candidate: AdmittedArtifactCandidate,
        producer: object,
        parameters: Mapping[str, ProducerParameter],
        source_mode: SourceMode | PublicationSourceMode,
        supersedes_version_id: UUID | str | None,
        model_provider: str | None = None,
    ) -> PreparedArtifactPublication:
        _uuid(project_id, "project_id")
        run_uuid = _uuid(run_id, "run_id")
        attempt_uuid = _uuid(attempt_id, "attempt_id")
        artifact_uuid = _uuid(artifact_id, "artifact_id")
        source_mode_value = _source_mode(source_mode)
        content = candidate.content
        producer_input_hash = content.get("input_hash")
        declared_producer_input_hash = getattr(producer, "input_hash", None)
        if (
            not isinstance(producer_input_hash, str)
            or not producer_input_hash.startswith("sha256:")
            or (
                declared_producer_input_hash is not None
                and declared_producer_input_hash != producer_input_hash
            )
        ):
            raise LiteraturePipelinePreparationError(
                f"{kind} candidate input_hash is not canonical"
            )
        producer_type = _producer_text(producer, "producer_type", default="algorithm")
        producer_name = _producer_text(producer, "producer_name", default=f"{kind}-pipeline")
        producer_version = _producer_text(producer, "producer_version", default="1.0.0")
        parameters_version = _optional_producer_text(producer, "parameters_version")
        try:
            normalized_parameters = _parameters(
                parameters,
                parameters_version=parameters_version,
            )
        except ValueError as exc:
            raise LiteraturePipelinePreparationError(
                f"{kind} producer parameters are not bounded JSON"
            ) from exc
        declared_parameters_hash = getattr(producer, "parameters_hash", None)
        if (
            isinstance(declared_parameters_hash, str)
            and compute_canonical_payload_hash(normalized_parameters)
            != declared_parameters_hash
        ):
            raise LiteraturePipelinePreparationError(
                f"{kind} producer parameters_hash does not match the ledger payload"
            )
        provider = None
        if producer_type == "model":
            provider = (
                model_provider
                if model_provider is not None
                else self._model_provider
                or _optional_producer_text(producer, "provider")
            )
        request = ProducerExecutionRequest(
            run_id=run_uuid,
            step_key=step_key,
            attempt_id=attempt_uuid,
            idempotency_key=(
                f"run:{run_uuid}:producer:{step_key}:artifact:{artifact_uuid}:"
                f"input:{producer_input_hash}"
            ),
            producer_type=producer_type,
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=str(producer_input_hash),
            parameters=normalized_parameters,
            model_provider=provider,
            model_name=_optional_producer_text(producer, "model_name"),
            prompt_name=_optional_producer_text(producer, "prompt_name"),
            prompt_version=_optional_producer_text(producer, "prompt_version"),
            prompt_hash=_optional_producer_text(producer, "prompt_hash"),
        )
        return PreparedArtifactPublication(
            kind=kind,
            artifact_id=artifact_uuid,
            publication_key=(
                f"run:{run_uuid}:step:{step_key}:artifact:{artifact_uuid}:"
                f"input:{producer_input_hash}"
            ),
            producer_request=request,
            candidate=candidate,
            source_mode=source_mode_value,
            supersedes_version_id=(
                None
                if supersedes_version_id is None
                else _uuid(supersedes_version_id, "supersedes_version_id")
            ),
        )


def _admit(
    candidate: object,
    *,
    schema_version: str,
    source_snapshot_ids: Sequence[str],
    evidence_ids: Sequence[str],
    source_bindings: Sequence[ArtifactSourceSnapshotBinding],
    evidence_bindings: Sequence[ArtifactEvidenceBinding],
) -> AdmittedArtifactCandidate:
    if not isinstance(candidate, BaseModel):
        raise LiteraturePipelinePreparationError("pipeline candidate must be a Pydantic model")
    return admit_artifact_candidate(
        candidate,  # type: ignore[arg-type]
        schema_version=schema_version,
        source_snapshot_ids=source_snapshot_ids,
        evidence_ids=evidence_ids,
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )


def _literature_evidence_bindings(
    *,
    candidate: LiteratureClaimsCandidate | LiteratureRelationsCandidate,
    kind: Literal["literature_claims", "literature_relations"],
    project_id: UUID,
    run_id: UUID,
    persisted_source_snapshot_ids: Mapping[str, UUID | str],
) -> tuple[ArtifactEvidenceBinding, ...]:
    target_type = "claim" if kind == "literature_claims" else "relation"
    expected: dict[tuple[str, str, str, str], object] = {}
    for reference in candidate.evidence_references:
        target_id = (
            reference.claim_id
            if kind == "literature_claims"
            else reference.relation_id
        )
        key = (
            target_type,
            target_id,
            reference.evidence_id,
            reference.source_snapshot_id,
        )
        # Relation Evidence can legitimately be referenced from both endpoint
        # claims. The persisted Evidence target is the relation itself, so one
        # (relation, Evidence, SourceSnapshot) row closes both side references.
        expected.setdefault(key, reference)
    declared = set(candidate.evidence_ids)
    referenced = {key[2] for key in expected}
    if declared != referenced:
        raise LiteraturePipelinePreparationError(
            "literature Evidence registry does not close its references"
        )
    missing_persisted = tuple(
        sorted(
            {
                key[3]
                for key in expected
                if key[3] not in persisted_source_snapshot_ids
            }
        )
    )
    if missing_persisted:
        raise LiteraturePipelinePreparationError(
            "literature Evidence bindings have no persisted SourceSnapshot: "
            + ", ".join(missing_persisted)
        )
    bindings = tuple(
        ArtifactEvidenceBinding(
            target_type=key[0],
            target_id=key[1],
            pipeline_evidence_id=key[2],
            pipeline_source_snapshot_id=key[3],
            persisted_evidence_id=_stable_uuid(
                project_id,
                run_id,
                kind,
                f"evidence:{key[1]}:{key[2]}:{key[3]}",
            ),
            persisted_source_snapshot_id=str(
                _uuid(
                    persisted_source_snapshot_ids[key[3]],
                    f"persisted_source_snapshot_ids[{key[3]}]",
                )
            ),
        )
        for key in sorted(expected)
    )
    # Fill SourceSnapshot ids only after checking that every reference points at a
    # candidate-declared snapshot.  Keeping this as a separate pass makes the
    # provenance closure explicit and deterministic.
    snapshot_ids = set(candidate.source_snapshot_ids)
    if any(item.pipeline_source_snapshot_id not in snapshot_ids for item in bindings):
        raise LiteraturePipelinePreparationError(
            "literature Evidence references an undeclared SourceSnapshot"
        )
    return bindings


def _source_bindings(
    pipeline_ids: Sequence[str],
    persisted_ids: Mapping[str, UUID | str],
) -> tuple[ArtifactSourceSnapshotBinding, ...]:
    required = tuple(sorted(set(pipeline_ids)))
    missing = tuple(item for item in required if item not in persisted_ids)
    if missing:
        raise LiteraturePipelinePreparationError(
            "persisted SourceSnapshot bindings are incomplete: " + ", ".join(missing)
        )
    bindings = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=item,
            persisted_source_snapshot_id=str(
                _uuid(persisted_ids[item], f"persisted_source_snapshot_ids[{item}]")
            ),
        )
        for item in required
    )
    persisted = tuple(item.persisted_source_snapshot_id for item in bindings)
    if len(persisted) != len(set(persisted)):
        raise LiteraturePipelinePreparationError(
            "persisted SourceSnapshot bindings must be unique"
        )
    return bindings


def _persisted_snapshot_for(
    bindings: Sequence[ArtifactSourceSnapshotBinding],
    pipeline_id: str,
) -> str:
    for binding in bindings:
        if binding.pipeline_source_snapshot_id == pipeline_id:
            return binding.persisted_source_snapshot_id
    raise LiteraturePipelinePreparationError(
        f"persisted SourceSnapshot binding is missing: {pipeline_id}"
    )


def _validate_admitted_literature_candidate(
    candidate: LiteratureClaimsCandidate | LiteratureRelationsCandidate,
    *,
    kind: Literal["literature_claims", "literature_relations"],
    project_id: UUID,
    run_id: UUID,
    source_mode: PublicationSourceMode,
) -> None:
    expected_type = (
        LiteratureClaimsCandidate
        if kind == "literature_claims"
        else LiteratureRelationsCandidate
    )
    if type(candidate) is not expected_type:
        raise LiteraturePipelinePreparationError(
            f"{kind} preparation requires the exact Pipeline candidate model"
        )
    admission_check = getattr(expected_type, "__artifact_publication_is_admitted__", None)
    try:
        is_admitted = callable(admission_check) and admission_check(candidate) is True
    except Exception as exc:
        raise LiteraturePipelinePreparationError(
            f"{kind} candidate admission seal cannot be verified"
        ) from exc
    if not is_admitted:
        raise LiteraturePipelinePreparationError(
            f"{kind} candidate must be sealed by its authoritative Pipeline"
        )

    producer = candidate.producer
    execution_id = getattr(producer, "execution_id", None)
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise LiteraturePipelinePreparationError(
            f"{kind} candidate ProducerExecution execution_id is not bound"
        )
    producer_run_id = getattr(producer, "run_id", None)
    if producer_run_id != str(run_id):
        raise LiteraturePipelinePreparationError(
            f"{kind} candidate ProducerExecution run_id is not closed to this run"
        )
    declared_project_id = getattr(candidate.input_versions, "project_id", None)
    if declared_project_id is not None and declared_project_id != str(project_id):
        raise LiteraturePipelinePreparationError(
            f"{kind} candidate project_id is not closed to this project"
        )

    if kind == "literature_claims":
        input_snapshot_ids = {
            item.source_snapshot_id
            for item in candidate.input_versions.source_snapshots
        }
        if not set(candidate.source_snapshot_ids).issubset(input_snapshot_ids):
            raise LiteraturePipelinePreparationError(
                "literature_claims candidate SourceSnapshots are outside its input Summary"
            )
    else:
        input_versions = candidate.input_versions.claim_artifact_versions
        input_version_ids = {item.artifact_version_id for item in input_versions}
        input_snapshot_ids = {
            source_snapshot_id
            for item in input_versions
            for source_snapshot_id in item.source_snapshot_ids
        }
        if any(item.project_id != str(project_id) for item in input_versions):
            raise LiteraturePipelinePreparationError(
                "literature_relations input Claim versions are not closed to this project"
            )
        for relation in candidate.relations:
            endpoint_version_ids = {
                item
                for item in (
                    relation.source_claim_artifact_version_id,
                    relation.target_claim_artifact_version_id,
                )
                if item is not None
            }
            if not endpoint_version_ids.issubset(input_version_ids):
                raise LiteraturePipelinePreparationError(
                    "literature_relations candidate endpoint is outside its input Claim versions"
                )
        if not set(candidate.source_snapshot_ids).issubset(input_snapshot_ids):
            raise LiteraturePipelinePreparationError(
                "literature_relations candidate SourceSnapshots are outside its input Claims"
            )

    _reject_fixture_as_live(candidate, source_mode)


def _stable_uuid(
    project_id: UUID | str,
    run_id: UUID | str,
    kind: str,
    value: str,
) -> str:
    project = _uuid(project_id, "project_id")
    run = _uuid(run_id, "run_id")
    return str(uuid5(NAMESPACE_URL, f"{_NAMESPACE}:{project}:{run}:{kind}:{value}"))


def _uuid(value: UUID | str, label: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or not value.strip():
        raise LiteraturePipelinePreparationError(f"{label} must be a UUID")
    try:
        return UUID(value)
    except ValueError as exc:
        raise LiteraturePipelinePreparationError(f"{label} must be a UUID") from exc


def _source_mode(value: SourceMode | PublicationSourceMode) -> PublicationSourceMode:
    try:
        normalized = SourceMode(value).value
    except (TypeError, ValueError) as exc:
        raise LiteraturePipelinePreparationError(
            "source_mode must be fixture, live, or cached"
        ) from exc
    return normalized  # type: ignore[return-value]


def _reject_fixture_as_live(
    candidate: (
        PaperSummaryArtifactContent
        | LiteratureClaimsCandidate
        | LiteratureRelationsCandidate
    ),
    source_mode: PublicationSourceMode,
) -> None:
    if source_mode != "live":
        return
    if isinstance(candidate, PaperSummaryArtifactContent) and candidate.benchmark is not None:
        raise LiteraturePipelinePreparationError(
            "Benchmark PaperSummary cannot be published with source_mode=live"
        )
    producer = getattr(candidate, "producer", None)
    model_name = getattr(producer, "model_name", None)
    evidence = getattr(candidate, "evidence", ())
    if model_name == "paper_benchmark-approved-label-replay" or any(
        getattr(item, "source_id", None) == "paper_benchmark" for item in evidence
    ):
        raise LiteraturePipelinePreparationError(
            "Benchmark literature candidate cannot be published with source_mode=live"
        )


def _parameters(
    values: Mapping[str, ProducerParameter],
    *,
    parameters_version: str | None = None,
) -> dict[str, ProducerParameter]:
    return normalize_producer_parameters(
        values,
        parameters_version=parameters_version,
    )


def _producer_text(producer: object, name: str, *, default: str) -> str:
    value = getattr(producer, name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _optional_producer_text(producer: object, name: str) -> str | None:
    value = getattr(producer, name, None)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LiteraturePipelinePreparationError(
            f"Producer field {name} must be nonempty text when supplied"
        )
    return value.strip()


def _accept(_: object) -> None:
    return None


__all__ = [
    "GraphPreparation",
    "LiteratureClaimsPreparation",
    "LiteraturePipelinePreparationError",
    "LiteraturePipelineRuntime",
    "LiteratureRelationsPreparation",
    "PaperSummaryPreparation",
    "PreparedArtifactPublication",
]
