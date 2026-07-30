"""Domain-specific reads over immutable PaperSummary ArtifactVersions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.schemas.enums import SourceMode as PaperSourceMode
from app.schemas.paper_collection import PaperCollection
from app.schemas.paper_summary_api import (
    PaperSummaryCacheAudit,
    PaperSummaryPaperMetadata,
    PaperSummaryRead,
)
from app.schemas.core import ArtifactVersionDetail, SourceMode, SourceSnapshotDetail
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService


class PaperSummaryReadService:
    """Validate and project D-03 content without repeating pipeline logic."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def get_summary(self, *, version_id: str, session_id: str) -> PaperSummaryRead:
        version = self._artifacts.get_version(
            version_id=version_id, session_id=session_id
        )
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
        collection = self._validate_input_collection(version, summary, session_id)
        snapshot_ids = self._validate_snapshots_and_evidence(version, summary)
        cache_audits = _cache_audits(
            collection,
            snapshot_ids,
            version.source_snapshots,
            source_mode=version.source_mode,
        )
        return PaperSummaryRead(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            version_number=version.version_number,
            supersedes_version_id=version.supersedes_version_id,
            source_mode=version.source_mode,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            created_at=version.created_at,
            paper=_paper_metadata(collection, summary.paper_id),
            summary=summary,
            cache_audits=cache_audits,
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
        if producer.run_id is not None and producer.run_id != version.created_by_run_id:
            raise _schema_problem()
        return summary

    def _validate_input_collection(
        self,
        version: ArtifactVersionDetail,
        summary: PaperSummaryArtifactContent,
        session_id: str,
    ) -> PaperCollection:
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
        try:
            return PaperCollection.model_validate(collection_version.content)
        except ValidationError as exc:
            raise _provenance_problem() from exc

    @staticmethod
    def _validate_snapshots_and_evidence(
        version: ArtifactVersionDetail,
        summary: PaperSummaryArtifactContent,
    ) -> dict[str, str]:
        persisted_snapshots = _snapshot_map(version.source_snapshots)
        if set(version.source_snapshot_ids) != {
            item.id for item in version.source_snapshots
        }:
            raise _provenance_problem()
        snapshot_ids: dict[str, str] = {}
        for reference in summary.input_versions.source_snapshots:
            key = (
                reference.source_id,
                reference.source_version,
                reference.content_hash,
            )
            persisted = persisted_snapshots.get(key)
            if persisted is None:
                raise _provenance_problem()
            snapshot_ids[reference.source_snapshot_id] = persisted.id

        evidence_by_id = {item.evidence_id: item for item in summary.evidence}
        if set(summary.evidence_ids) != set(evidence_by_id):
            raise _schema_problem()

        generic_evidence = tuple(version.evidence)
        if len(generic_evidence) != len(summary.evidence):
            raise _provenance_problem()
        if len({item.id for item in generic_evidence}) != len(generic_evidence):
            raise _provenance_problem()
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
                and _locator_summary_evidence_id(evidence.locator) == item.evidence_id
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
        return snapshot_ids


def _snapshot_map(
    snapshots: tuple[SourceSnapshotDetail, ...],
) -> dict[tuple[str, str | None, str], SourceSnapshotDetail]:
    result: dict[tuple[str, str | None, str], SourceSnapshotDetail] = {}
    for snapshot in snapshots:
        key = (
            snapshot.source_id,
            snapshot.source_version_or_etag,
            snapshot.content_hash,
        )
        if key in result:
            raise _provenance_problem()
        result[key] = snapshot
    return result


def _locator_source_record_id(locator: Mapping[str, Any]) -> str | None:
    value = locator.get("source_record_id")
    return value if isinstance(value, str) else None


def _locator_summary_evidence_id(locator: Mapping[str, Any]) -> str | None:
    value = locator.get("summary_evidence_id")
    return value if isinstance(value, str) else None


def _paper_metadata(
    collection: PaperCollection, paper_id: str
) -> PaperSummaryPaperMetadata:
    matches = tuple(
        candidate
        for candidate in collection.candidates
        if candidate.canonical_paper_id == paper_id and candidate.selected
    )
    if len(matches) != 1:
        raise _provenance_problem()
    candidate = matches[0]
    try:
        return PaperSummaryPaperMetadata.model_validate(
            {
                "paper_id": paper_id,
                "title": candidate.title,
                "authors": candidate.authors,
                "year": candidate.year,
            }
        )
    except ValidationError as exc:
        raise _provenance_problem() from exc


def _cache_audits(
    collection: PaperCollection,
    snapshot_ids: Mapping[str, str],
    snapshots: tuple[SourceSnapshotDetail, ...],
    *,
    source_mode: SourceMode,
) -> tuple[PaperSummaryCacheAudit, ...]:
    persisted_by_id = {snapshot.id: snapshot for snapshot in snapshots}
    result: list[PaperSummaryCacheAudit] = []
    for execution in collection.source_executions:
        if execution.source_mode is not PaperSourceMode.cached:
            continue
        if (
            execution.source_snapshot_id is None
            or execution.cache_applicability is None
            or execution.live_failure_class is None
            or execution.live_failure_code is None
        ):
            raise _provenance_problem()
        persisted_id = snapshot_ids.get(execution.source_snapshot_id)
        snapshot = persisted_by_id.get(persisted_id) if persisted_id else None
        metadata = snapshot.request_metadata if snapshot else {}
        origin_run_id = metadata.get("origin_run_id")
        origin_version_id = metadata.get("origin_artifact_version_id")
        if (
            snapshot is None
            or snapshot.source_id != execution.source_id
            or not snapshot.cache_version
            or not snapshot.cache_version.strip()
            or not isinstance(origin_run_id, str)
            or not origin_run_id.strip()
            or not isinstance(origin_version_id, str)
            or not origin_version_id.strip()
        ):
            raise _provenance_problem()
        result.append(
            PaperSummaryCacheAudit(
                source_id=execution.source_id,
                source_snapshot_id=snapshot.id,
                cache_version=snapshot.cache_version,
                cache_applicability=execution.cache_applicability,
                live_failure_class=execution.live_failure_class,
                live_failure_code=execution.live_failure_code,
                origin_run_id=origin_run_id,
                origin_artifact_version_id=origin_version_id,
            )
        )
    if (source_mode is SourceMode.cached) != bool(result):
        raise _provenance_problem()
    return tuple(result)


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
