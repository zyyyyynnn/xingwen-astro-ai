"""Domain-specific reads over immutable PaperSummary ArtifactVersions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.schemas.paper_summary_api import PaperSummaryRead
from app.schemas.v2 import ArtifactVersionDetail, SourceSnapshotDetail
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService


class PaperSummaryReadService:
    """Validate and project D-03 content without repeating pipeline logic."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def get_summary(self, *, version_id: str, session_id: str) -> PaperSummaryRead:
        version = self._artifacts.get_version(version_id=version_id, session_id=session_id)
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        if artifact.kind.value != "paper_summary":
            raise _problem(
                409,
                "ARTIFACT_KIND_MISMATCH",
                "Artifact kind mismatch",
                "The ArtifactVersion is not a paper_summary",
            )

        summary = self._validated_summary(version)
        self._validate_input_collection(version, summary, session_id)
        self._validate_snapshots_and_evidence(version, summary)
        return PaperSummaryRead(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            source_mode=version.source_mode,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            created_at=version.created_at,
            summary=summary,
            producer_execution=version.producer_execution,
            source_snapshots=version.source_snapshots,
            evidence=version.evidence,
        )

    def _validated_summary(
        self, version: ArtifactVersionDetail
    ) -> PaperSummaryArtifactContent:
        try:
            summary = PaperSummaryArtifactContent.model_validate(version.content)
        except ValidationError as exc:
            raise _schema_problem() from exc

        producer = summary.producer
        runtime_producer = version.producer_execution
        if (
            version.schema_version != summary.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.input_hash != summary.input_hash
            or runtime_producer.run_id != version.created_by_run_id
            or runtime_producer.step_key != producer.step_key
            or runtime_producer.producer.type != producer.producer_type
            or runtime_producer.parameters_hash != producer.parameters_hash
            or runtime_producer.input_hash != summary.input_hash
            or runtime_producer.output_hash != version.content_hash
            or runtime_producer.status != "completed"
            or runtime_producer.producer.name != producer.producer_name
            or runtime_producer.producer.version != producer.producer_version
            or runtime_producer.producer.model_name != producer.model_name
            or runtime_producer.producer.prompt_name != producer.prompt_name
            or runtime_producer.producer.prompt_version != producer.prompt_version
            or runtime_producer.producer.prompt_hash != producer.prompt_hash
            or runtime_producer.producer.parameters_hash != producer.parameters_hash
            or version.producer != runtime_producer.producer
        ):
            raise _schema_problem()
        if (
            producer.run_id is not None
            and producer.run_id != version.created_by_run_id
        ):
            raise _schema_problem()
        return summary

    def _validate_input_collection(
        self,
        version: ArtifactVersionDetail,
        summary: PaperSummaryArtifactContent,
        session_id: str,
    ) -> None:
        try:
            collection_version = self._artifacts.get_version(
                version_id=summary.input_versions.paper_collection_version_id,
                session_id=session_id,
            )
            collection_artifact = self._artifacts.get_artifact(
                artifact_id=collection_version.artifact_id, session_id=session_id
            )
        except SecurityProblem as exc:
            raise _provenance_problem() from exc
        if collection_artifact.kind.value != "paper_collection":
            raise _provenance_problem()
        reference = summary.input_versions
        if (
            collection_version.project_id != version.project_id
            or collection_version.schema_version
            != reference.paper_collection_schema_version
            or collection_version.content_hash
            != compute_canonical_payload_hash(collection_version.content)
            or collection_version.content.get("schema_version")
            != reference.paper_collection_schema_version
            or collection_version.content.get("output_hash")
            != reference.paper_collection_output_hash
        ):
            raise _provenance_problem()

    @staticmethod
    def _validate_snapshots_and_evidence(
        version: ArtifactVersionDetail,
        summary: PaperSummaryArtifactContent,
    ) -> None:
        persisted_snapshots = _snapshot_map(version.source_snapshots)
        if set(version.source_snapshot_ids) != {
            item.id for item in version.source_snapshots
        }:
            raise _provenance_problem()
        snapshot_ids: dict[str, str] = {}
        for reference in summary.input_versions.source_snapshots:
            key = (reference.source_id, reference.source_version, reference.content_hash)
            persisted = persisted_snapshots.get(key)
            if persisted is None:
                raise _provenance_problem()
            snapshot_ids[reference.source_snapshot_id] = persisted.id

        evidence_by_id = {item.evidence_id: item for item in summary.evidence}
        if set(summary.evidence_ids) != set(evidence_by_id):
            raise _schema_problem()

        generic_evidence = tuple(version.evidence)
        statement_targets = {
            item.evidence_id: {
                statement.statement_id
                for statement in summary.statements()
                if item.evidence_id in statement.evidence_ids
            }
            for item in summary.evidence
        }
        for item in summary.evidence:
            persisted_snapshot_id = snapshot_ids.get(item.source_snapshot_id)
            if persisted_snapshot_id is None:
                raise _provenance_problem()
            matches = tuple(
                evidence.paper_id == item.paper_id
                and evidence.artifact_version_id == version.id
                and evidence.target_type == "paper_summary"
                and evidence.target_id in statement_targets[item.evidence_id]
                and evidence.source_snapshot_id == persisted_snapshot_id
                and _locator_source_record_id(evidence.locator) == item.source_record_id
                for evidence in generic_evidence
            )
            if sum(matches) != 1:
                raise _provenance_problem()

        if set(version.evidence_ids) != {item.id for item in generic_evidence}:
            raise _provenance_problem()


def _snapshot_map(
    snapshots: tuple[SourceSnapshotDetail, ...],
) -> dict[tuple[str, str | None, str], SourceSnapshotDetail]:
    result: dict[tuple[str, str | None, str], SourceSnapshotDetail] = {}
    for snapshot in snapshots:
        key = (snapshot.source_id, snapshot.source_version_or_etag, snapshot.content_hash)
        if key in result:
            raise _provenance_problem()
        result[key] = snapshot
    return result


def _locator_source_record_id(locator: Mapping[str, Any]) -> str | None:
    value = locator.get("source_record_id")
    return value if isinstance(value, str) else None


def _schema_problem() -> SecurityProblem:
    return _problem(
        422,
        "PAPER_SUMMARY_SCHEMA_INVALID",
        "PaperSummary Schema invalid",
        "The ArtifactVersion content is not a valid PaperSummary",
    )


def _provenance_problem() -> SecurityProblem:
    return _problem(
        403,
        "PROVENANCE_SCOPE_VIOLATION",
        "Provenance access denied",
        "The PaperSummary provenance graph is incomplete or outside the authorized project",
    )


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = ["PaperSummaryReadService"]
