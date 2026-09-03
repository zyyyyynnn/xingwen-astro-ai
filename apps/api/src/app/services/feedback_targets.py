"""Version-pinned domain admission for immutable Feedback targets."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactKind, ExportArtifactContent
from app.schemas.literature_relation import (
    LiteratureRelationReviewReason,
    LiteratureRelationStatus,
)
from app.schemas.revision import (
    CreateUserFeedbackRequest,
    FeedbackCategory,
    FeedbackTargetType,
)
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.data_artifacts import DataArtifactReadService
from app.services.graph_artifacts import GraphArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService
from app.services.paper_collections import PaperCollectionReadService
from app.services.paper_summaries import PaperSummaryReadPort, PaperSummaryReadService
from app.services.scientific_artifacts import ScientificArtifactReadService


class ArtifactVersionTargetReadPort(Protocol):
    """Validate one exact ArtifactVersion through its domain read boundary."""

    async def validate_version(
        self, *, version_id: str, artifact_kind: str, session_id: str
    ) -> None: ...


class ArtifactVersionTargetReadService:
    """Dispatch whole-version Feedback targets to the existing typed readers."""

    def __init__(
        self,
        artifacts: ArtifactReadService,
        *,
        paper_summary_reader: PaperSummaryReadPort,
    ) -> None:
        self._artifacts = artifacts
        self._data = DataArtifactReadService(artifacts)
        self._papers = PaperCollectionReadService(artifacts)
        self._summaries = paper_summary_reader
        self._literature = LiteratureArtifactReadService(
            artifacts, paper_summary_reader=paper_summary_reader
        )
        self._graph = GraphArtifactReadService(
            artifacts, literature_reader=self._literature
        )
        self._scientific = ScientificArtifactReadService(artifacts)

    async def validate_version(
        self, *, version_id: str, artifact_kind: str, session_id: str
    ) -> None:
        kind = ArtifactKind(artifact_kind)
        if kind is ArtifactKind.dataset:
            self._data.get_dataset(version_id=version_id, session_id=session_id)
        elif kind is ArtifactKind.field_dictionary:
            self._data.get_field_dictionary(
                version_id=version_id, session_id=session_id
            )
        elif kind is ArtifactKind.source_collection:
            self._data.get_source_collection(
                version_id=version_id, session_id=session_id
            )
        elif kind is ArtifactKind.paper_collection:
            self._papers.get_collection(version_id=version_id, session_id=session_id)
        elif kind is ArtifactKind.paper_summary:
            await self._summaries.get_summary(
                version_id=version_id, session_id=session_id
            )
        elif kind is ArtifactKind.literature_claims:
            await self._literature.list_claims(
                version_id=version_id,
                session_id=session_id,
                status=None,
                cursor=None,
                limit=1,
            )
        elif kind is ArtifactKind.literature_relations:
            await self._literature.list_relations(
                version_id=version_id,
                session_id=session_id,
                status=None,
                cursor=None,
                limit=1,
            )
        elif kind is ArtifactKind.graph:
            self._graph.get_graph(version_id=version_id, session_id=session_id)
        elif kind in {
            ArtifactKind.analysis_report,
            ArtifactKind.visualization,
            ArtifactKind.spectrum,
            ArtifactKind.light_curve,
            ArtifactKind.model_evaluation,
            ArtifactKind.model_artifact,
        }:
            self._scientific.get_scientific_artifact(
                version_id=version_id, session_id=session_id
            )
        elif kind is ArtifactKind.export:
            self._validate_export(version_id=version_id, session_id=session_id)
        else:
            raise ValueError(f"unsupported ArtifactVersion target kind: {kind}")

    def _validate_export(self, *, version_id: str, session_id: str) -> None:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        candidate = ExportArtifactContent.model_validate(version.content)
        if (
            artifact.kind is not ArtifactKind.export
            or version.schema_version != candidate.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.source_snapshot_ids
            or version.evidence_ids
        ):
            raise ValueError("invalid Export ArtifactVersion")
        for referenced_version_id in candidate.artifact_version_ids:
            referenced = self._artifacts.get_version(
                version_id=referenced_version_id,
                session_id=session_id,
            )
            if referenced.project_id != version.project_id:
                raise ValueError("cross-project Export reference")

class FeedbackTargetAuthority:
    """Resolve one Feedback target through its version-pinned read authority."""

    def __init__(
        self,
        artifacts: ArtifactReadService,
        *,
        paper_summary_reader: PaperSummaryReadPort | None = None,
        artifact_version_reader: ArtifactVersionTargetReadPort | None = None,
    ) -> None:
        self._data = DataArtifactReadService(artifacts)
        self._papers = PaperCollectionReadService(artifacts)
        self._summaries = paper_summary_reader or PaperSummaryReadService(artifacts)
        self._literature = LiteratureArtifactReadService(
            artifacts, paper_summary_reader=self._summaries
        )
        self._graph = GraphArtifactReadService(
            artifacts, literature_reader=self._literature
        )
        self._artifact_versions = (
            artifact_version_reader
            or ArtifactVersionTargetReadService(
                artifacts,
                paper_summary_reader=self._summaries,
            )
        )

    async def validate(
        self,
        *,
        version_id: str,
        artifact_id: str,
        artifact_kind: str,
        session_id: str,
        request: CreateUserFeedbackRequest,
    ) -> None:
        target_type = request.target_type
        target_id = request.target_id

        if target_type is FeedbackTargetType.artifact:
            self._require_locator(request, {"artifact_id": artifact_id})
            if target_id != artifact_id:
                raise _invalid_target()
            await self._validate_artifact_version(
                version_id=version_id,
                artifact_kind=artifact_kind,
                session_id=session_id,
            )
            return
        if target_type is FeedbackTargetType.artifact_version:
            self._require_locator(
                request,
                {
                    "artifact_id": artifact_id,
                    "artifact_version_id": version_id,
                },
            )
            if target_id != version_id:
                raise _invalid_target()
            await self._validate_artifact_version(
                version_id=version_id,
                artifact_kind=artifact_kind,
                session_id=session_id,
            )
            return

        locator_key = {
            FeedbackTargetType.dataset_field: "field_id",
            FeedbackTargetType.dataset_row: "row_id",
            FeedbackTargetType.paper: "candidate_id",
            FeedbackTargetType.paper_summary: "summary_id",
            FeedbackTargetType.claim: "claim_id",
            FeedbackTargetType.relation: "relation_id",
            FeedbackTargetType.trace: "trace_id",
            FeedbackTargetType.graph_node: "node_id",
            FeedbackTargetType.graph_edge: "edge_id",
        }[target_type]
        self._require_locator(
            request,
            {"artifact_version_id": version_id, locator_key: target_id},
        )

        try:
            if target_type in {
                FeedbackTargetType.dataset_field,
                FeedbackTargetType.dataset_row,
            }:
                self._require_kind(artifact_kind, "dataset")
                dataset = self._data.get_dataset(
                    version_id=version_id, session_id=session_id
                ).dataset
                resolved_ids = (
                    {column.field.field_id for column in dataset.columns}
                    if target_type is FeedbackTargetType.dataset_field
                    else {item.row_id for item in dataset.rows}
                )
                if target_id not in resolved_ids:
                    raise _invalid_target()
            elif target_type is FeedbackTargetType.paper:
                self._require_kind(artifact_kind, "paper_collection")
                self._papers.get_candidate(
                    version_id=version_id,
                    candidate_id=target_id,
                    session_id=session_id,
                )
            elif target_type is FeedbackTargetType.paper_summary:
                self._require_kind(artifact_kind, "paper_summary")
                summary = (
                    await self._summaries.get_summary(
                        version_id=version_id, session_id=session_id
                    )
                ).summary
                if summary.summary_id != target_id:
                    raise _invalid_target()
            elif target_type is FeedbackTargetType.claim:
                self._require_kind(artifact_kind, "literature_claims")
                await self._literature.get_claim(
                    version_id=version_id,
                    claim_id=target_id,
                    session_id=session_id,
                )
            elif target_type is FeedbackTargetType.relation:
                self._require_kind(artifact_kind, "literature_relations")
                relation = await self._literature.get_relation(
                    version_id=version_id,
                    relation_id=target_id,
                    session_id=session_id,
                )
                if request.category is FeedbackCategory.adjudication and (
                    relation.relation.status is not LiteratureRelationStatus.candidate
                    or relation.relation.review_reason
                    not in {
                        LiteratureRelationReviewReason.confidence_not_evaluable,
                        LiteratureRelationReviewReason.confidence_below_threshold,
                    }
                ):
                    raise _invalid_target()
            elif target_type is FeedbackTargetType.trace:
                self._require_kind(artifact_kind, "literature_relations")
                await self._literature.get_reasoning_trace(
                    version_id=version_id,
                    trace_id=target_id,
                    session_id=session_id,
                )
            elif target_type is FeedbackTargetType.graph_node:
                self._require_kind(artifact_kind, "graph")
                self._graph.get_node(
                    version_id=version_id,
                    node_id=target_id,
                    session_id=session_id,
                )
            else:
                self._require_kind(artifact_kind, "graph")
                await self._graph.get_edge(
                    version_id=version_id,
                    edge_id=target_id,
                    session_id=session_id,
                )
        except SecurityProblem as exc:
            if exc.code == "FEEDBACK_TARGET_INVALID":
                raise
            raise _invalid_target() from exc

    async def _validate_artifact_version(
        self, *, version_id: str, artifact_kind: str, session_id: str
    ) -> None:
        try:
            await self._artifact_versions.validate_version(
                version_id=version_id,
                artifact_kind=artifact_kind,
                session_id=session_id,
            )
        except (SecurityProblem, ValidationError, ValueError) as exc:
            raise _invalid_target() from exc

    @staticmethod
    def _require_locator(
        request: CreateUserFeedbackRequest, expected: dict[str, str]
    ) -> None:
        if request.target_locator != expected:
            raise _invalid_target()

    @staticmethod
    def _require_kind(actual: str, expected: str) -> None:
        if actual != expected:
            raise _invalid_target()


def _invalid_target() -> SecurityProblem:
    return SecurityProblem(
        status=422,
        code="FEEDBACK_TARGET_INVALID",
        title="Feedback target is invalid",
        detail=(
            "The target does not resolve within the supplied baseline ArtifactVersion"
        ),
    )


__all__ = [
    "ArtifactVersionTargetReadPort",
    "ArtifactVersionTargetReadService",
    "FeedbackTargetAuthority",
]
