"""Evidence graph building step service for Research Runs."""

from __future__ import annotations

from collections.abc import Callable
from sqlalchemy.orm import Session

from app.schemas.enums import GraphNodeType
from app.schemas.literature_relation import (
    LiteratureRelationStatus,
    LiteratureRelationsCandidate,
)
from app.schemas.graph_artifact import (
    compute_graph_algorithm_parameters_hash,
    graph_algorithm_parameters,
    GraphBuildRequest,
    GraphBuildScope,
    GraphIntegrityStatus,
    GraphLayoutHint,
    GraphPolicySet,
)
from app.security import canonical_request_hash
from app.services.artifacts import ArtifactReadService
from app.services.graph_inputs import (
    ArtifactVersionGraphInputReadAdapter,
    PostgresEvidenceRestrictionReadAdapter,
)
from app.workflow.publisher import (
    ArtifactEvidenceBinding,
    ArtifactSourceSnapshotBinding,
    admit_artifact_candidate,
)
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepPublicationFactory,
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.graph_pipeline import (
    GraphPipeline,
    build_complete_progressive_input,
)
from services.graph_pipeline.pipeline import build_graph_taxonomy


class GraphStepService:
    """Build an admitted Graph from the exact published Relation version."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        publications: StepPublicationFactory,
    ) -> None:
        self._factory = factory
        self._publications = publications

    def build(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        relations_version_id = context.versions.get("literature_relations")
        relations = context.literature_relations
        if relations is None and relations_version_id is not None:
            version = ArtifactReadService(self._factory).get_version(
                version_id=str(relations_version_id),
                session_id=context.session_id,
            )
            relations = LiteratureRelationsCandidate.model_validate(version.content)
            context.literature_relations = relations
        if relations_version_id is None or relations is None:
            raise ValueError("literature_relations must be published before graph build")

        claim_ids = tuple(sorted(item.claim_id for item in relations.claims))
        paper_ids = tuple(sorted({item.paper_id for item in relations.evidence_references}))
        relation_ids = tuple(
            sorted(
                item.relation_id
                for item in relations.relations
                if item.status is LiteratureRelationStatus.accepted
            )
        )
        if not relation_ids:
            raise ValueError("evidence graph requires at least one accepted Relation")

        scope = GraphBuildScope(
            literature_paper_ids=paper_ids,
            literature_claim_ids=claim_ids,
            accepted_relation_ids=relation_ids,
            structural_edges=(),
            include_data=False,
        )
        progressive = build_complete_progressive_input(
            progressive_id=f"progressive.{str(context.run_id).replace('-', '')[:24]}",
            literature_relations_artifact_version_id=str(relations_version_id),
            dataset_artifact_version_id=None,
            field_dictionary_artifact_version_id=None,
            scope=scope,
        )
        request = GraphBuildRequest(
            project_id=str(context.project_id),
            literature_relations_artifact_version_id=str(relations_version_id),
            scope=scope,
            policies=GraphPolicySet(),
            progressive=progressive,
            layout_hint=GraphLayoutHint(
                strategy="group_by_node_type",
                group_order=(GraphNodeType.claim, GraphNodeType.paper),
            ),
        )
        request_hash = canonical_request_hash(
            request.model_dump(mode="json", exclude_none=True)
        )
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="graph",
            producer_type="algorithm",
            producer_name="evidence-graph-pipeline",
            producer_version="2.0.0",
            input_hash=request_hash,
            parameters=graph_algorithm_parameters(
                request.policies, build_graph_taxonomy()
            ),
            parameters_hash=compute_graph_algorithm_parameters_hash(
                request.policies, build_graph_taxonomy()
            ),
            attempt=attempt,
            lease=lease,
        )
        reader = ArtifactVersionGraphInputReadAdapter(
            artifacts=ArtifactReadService(self._factory),
            session_id=context.session_id,
            evidence_restrictions=PostgresEvidenceRestrictionReadAdapter(self._factory),
        )
        try:
            result = GraphPipeline(reader).admit(request)
        except Exception:
            self._publications.finish_producer(
                execution.id, status="failed", error_code="GRAPH_PIPELINE_FAILED"
            )
            raise
        if result.status is not GraphIntegrityStatus.passed or result.candidate is None:
            self._publications.finish_producer(
                execution.id, status="rejected", error_code="GRAPH_ADMISSION_REJECTED"
            )
            finding = result.report.findings[0] if result.report.findings else None
            detail = (
                f"{result.report.first_rejection_reason.value}: {finding.message} "
                f"({finding.path})"
                if finding is not None and result.report.first_rejection_reason
                else "unknown graph admission failure"
            )
            raise ValueError(f"证据图谱未通过准入: {detail}")
        graph = result.candidate
        snapshot_bindings_override = {
            item.source_snapshot_id: str(item.persisted_source_snapshot_id)
            for item in graph.source_snapshots
        }
        source_bindings = tuple(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_source_snapshot_id=str(item.persisted_source_snapshot_id),
            )
            for item in graph.source_snapshots
        )
        evidence_bindings = tuple(
            ArtifactEvidenceBinding(
                target_type="graph_edge",
                target_id=item.graph_edge_id,
                pipeline_evidence_id=item.evidence_use_id,
                pipeline_source_snapshot_id=item.source_snapshot_id,
                persisted_evidence_id=str(
                    step_uuid(
                        str(context.run_id),
                        f"graph:evidence:{item.evidence_use_id}",
                    )
                ),
                persisted_source_snapshot_id=snapshot_bindings_override[
                    item.source_snapshot_id
                ],
            )
            for item in graph.evidence_uses
        )
        admitted = admit_artifact_candidate(
            graph,
            schema_version=graph.schema_version,
            source_snapshot_ids=graph.source_snapshot_ids,
            evidence_ids=graph.evidence_ids,
            evidence_validator=lambda _context: None,
            domain_validator=lambda _context: None,
            quality_validator=lambda _context: None,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        self._publications.finish_producer(
            execution.id,
            status="completed",
            input_hash=graph.input_hash,
            output_hash=admitted.content_hash,
        )
        publication = self._publications.publication(
            context,
            kind="graph",
            candidate=admitted,
            producer_execution_id=execution.id,
        )
        return PreparedStep(
            publications=(publication,),
            activity_result_summary=(
                f"已构建科学证据图谱，包含 {len(graph.nodes)} 个节点与 "
                f"{len(graph.edges)} 条证据关系"
            ),
        )


__all__ = ["GraphStepService"]
