"""Domain-specific reads over immutable PaperCollection ArtifactVersions."""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import PaperSourceExecutionStatus, UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import PaperCollection, PaperCollectionCandidate
from app.schemas.paper_collection_api import (
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from app.schemas.core import ArtifactVersionDetail, SourceSnapshotDetail
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService


_MAX_PAGE_SIZE = 100
_UNSAFE_HTML = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)


class PaperCollectionReadService:
    """Validate and project Paper Acquisition Pipeline content without repeating its algorithms."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def get_collection(
        self, *, version_id: str, session_id: str
    ) -> PaperCollectionRead:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        if artifact.kind.value != "paper_collection":
            raise _problem(
                409,
                "ARTIFACT_KIND_MISMATCH",
                "Artifact kind mismatch",
                "The ArtifactVersion is not a paper_collection",
            )
        collection = self._validated_collection(version)
        self._require_available(collection)
        return PaperCollectionRead(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            source_mode=version.source_mode,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            created_at=version.created_at,
            collection=collection,
            producer_execution=version.producer_execution,
            source_snapshots=version.source_snapshots,
        )

    def list_candidates(
        self,
        *,
        version_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[PaperCollectionCandidateRead, ...], str | None, bool]:
        if not 1 <= limit <= _MAX_PAGE_SIZE:
            raise _problem(
                422,
                "SCHEMA_VALIDATION_FAILED",
                "Request validation failed",
                "limit must be between 1 and 100",
            )
        detail = self.get_collection(version_id=version_id, session_id=session_id)
        candidates = detail.collection.candidates
        keys = tuple(_candidate_key(item) for item in candidates)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise _schema_problem()

        start = 0
        if cursor is not None:
            cursor_key = _decode_cursor(cursor, version_id=detail.artifact_version_id)
            try:
                start = keys.index(cursor_key) + 1
            except ValueError as exc:
                raise _invalid_cursor() from exc

        selected = candidates[start : start + limit]
        has_more = start + len(selected) < len(candidates)
        next_cursor = (
            _encode_cursor(
                version_id=detail.artifact_version_id, key=_candidate_key(selected[-1])
            )
            if selected and has_more
            else None
        )
        groups = {
            item.duplicate_group_id: item for item in detail.collection.duplicate_groups
        }
        snapshots = _snapshot_projection_map(detail)
        result: list[PaperCollectionCandidateRead] = []
        for candidate in selected:
            group = groups.get(candidate.duplicate_group_id)
            snapshot = snapshots.get(candidate.raw.source_snapshot_id)
            if group is None or snapshot is None:
                raise _provenance_problem()
            result.append(
                PaperCollectionCandidateRead(
                    paper_collection_version_id=detail.artifact_version_id,
                    paper_collection_input_hash=detail.input_hash,
                    candidate=candidate,
                    duplicate_group=group,
                    source_snapshot=snapshot,
                )
            )
        return tuple(result), next_cursor, has_more

    def get_candidate(
        self, *, version_id: str, candidate_id: str, session_id: str
    ) -> PaperCollectionCandidateRead:
        detail = self.get_collection(version_id=version_id, session_id=session_id)
        candidate = next(
            (
                item
                for item in detail.collection.candidates
                if item.candidate_id == candidate_id
            ),
            None,
        )
        if candidate is None:
            raise _problem(
                404,
                "PAPER_CANDIDATE_NOT_FOUND",
                "Paper candidate not found",
                "The PaperCandidate does not belong to this PaperCollection",
            )
        groups = {
            item.duplicate_group_id: item for item in detail.collection.duplicate_groups
        }
        snapshot = _snapshot_projection_map(detail).get(
            candidate.raw.source_snapshot_id
        )
        group = groups.get(candidate.duplicate_group_id)
        if group is None or snapshot is None:
            raise _provenance_problem()
        return PaperCollectionCandidateRead(
            paper_collection_version_id=detail.artifact_version_id,
            paper_collection_input_hash=detail.input_hash,
            candidate=candidate,
            duplicate_group=group,
            source_snapshot=snapshot,
        )

    @staticmethod
    def _validated_collection(version: ArtifactVersionDetail) -> PaperCollection:
        try:
            collection = PaperCollection.model_validate(version.content)
        except ValidationError as exc:
            raise _schema_problem() from exc
        if (
            version.schema_version != collection.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.input_hash != collection.input_hash
            or version.producer_execution.parameters_hash
            != collection.producer.parameters_hash
            or version.producer_execution.input_hash != collection.input_hash
            or version.producer_execution.output_hash != version.content_hash
            or version.producer_execution.producer.name
            != collection.producer.producer_name
            or version.producer_execution.producer.version
            != collection.producer.producer_version
        ):
            raise _schema_problem()
        if (
            collection.producer.run_id is not None
            and collection.producer.run_id != version.created_by_run_id
        ):
            raise _schema_problem()
        _snapshot_projection_map_from(collection, version.source_snapshots)
        if any(
            item.source_mode.value != version.source_mode.value
            for item in collection.source_executions
        ):
            raise _schema_problem()
        if version.evidence_ids or version.evidence:
            raise _schema_problem()
        if _contains_unsafe_html(collection.model_dump(mode="json")):
            raise _schema_problem()
        return collection

    @staticmethod
    def _require_available(collection: PaperCollection) -> None:
        if collection.acquisition_run.status == "failed":
            failures = tuple(
                item
                for item in collection.source_executions
                if item.status is PaperSourceExecutionStatus.failed
            )
            if any(
                item.failure_class is UpstreamFailureClass.rate_limited
                for item in failures
            ):
                raise _problem(
                    429,
                    "PAPER_SOURCE_RATE_LIMITED",
                    "Paper source rate limited",
                    "The paper source rate limit prevented this collection",
                )
            raise _problem(
                502,
                "PAPER_SOURCE_FAILED",
                "Paper source failed",
                "The paper source did not produce a publishable collection",
            )
        if not collection.candidates:
            raise _problem(
                404,
                "PAPER_COLLECTION_EMPTY",
                "Paper collection is empty",
                "The paper collection contains no candidates",
            )


def _candidate_key(candidate: PaperCollectionCandidate) -> tuple[str, str, str]:
    return candidate.ranking_key, candidate.canonical_paper_id, candidate.candidate_id


def _snapshot_projection_map(
    detail: PaperCollectionRead,
) -> dict[str, SourceSnapshotDetail]:
    return _snapshot_projection_map_from(detail.collection, detail.source_snapshots)


def _snapshot_projection_map_from(
    collection: PaperCollection, snapshots: Sequence[SourceSnapshotDetail]
) -> dict[str, SourceSnapshotDetail]:
    """Map pipeline snapshot identifiers to persisted UUID projections by provenance."""

    persisted_by_fingerprint: dict[tuple[Any, ...], SourceSnapshotDetail] = {}
    for snapshot in snapshots:
        fingerprint = _persisted_snapshot_fingerprint(snapshot)
        if fingerprint in persisted_by_fingerprint:
            raise _provenance_problem()
        persisted_by_fingerprint[fingerprint] = snapshot
    result: dict[str, SourceSnapshotDetail] = {}
    for snapshot in collection.source_snapshots:
        persisted = persisted_by_fingerprint.get(
            _content_snapshot_fingerprint(snapshot)
        )
        if persisted is None:
            raise _provenance_problem()
        result[snapshot.snapshot_id] = persisted
    if len(result) != len(persisted_by_fingerprint):
        raise _provenance_problem()
    return result


def _content_snapshot_fingerprint(snapshot: SourceSnapshotRecord) -> tuple[Any, ...]:
    return (
        snapshot.source_id,
        snapshot.source_type,
        snapshot.query_hash,
        snapshot.content_hash,
        snapshot.retrieved_at,
    )


def _persisted_snapshot_fingerprint(snapshot: SourceSnapshotDetail) -> tuple[Any, ...]:
    return (
        snapshot.source_id,
        snapshot.source_type,
        snapshot.query_hash,
        snapshot.content_hash,
        snapshot.retrieved_at,
    )


def _encode_cursor(*, version_id: str, key: tuple[str, str, str]) -> str:
    payload = json.dumps(
        {
            "version_id": version_id,
            "ranking_key": key[0],
            "canonical_paper_id": key[1],
            "candidate_id": key[2],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str, *, version_id: str) -> tuple[str, str, str]:
    try:
        if len(value) > 4096:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if set(payload) != {
            "version_id",
            "ranking_key",
            "canonical_paper_id",
            "candidate_id",
        }:
            raise ValueError
        if payload["version_id"] != version_id:
            raise ValueError
        key = (
            payload["ranking_key"],
            payload["canonical_paper_id"],
            payload["candidate_id"],
        )
        if not all(isinstance(item, str) and item for item in key):
            raise ValueError
        return key
    except (
        binascii.Error,
        TypeError,
        ValueError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise _invalid_cursor() from exc


def _contains_unsafe_html(value: Any) -> bool:
    if isinstance(value, str):
        return _UNSAFE_HTML.search(value) is not None
    if isinstance(value, Mapping):
        return any(_contains_unsafe_html(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_unsafe_html(item) for item in value)
    return False


def _invalid_cursor() -> SecurityProblem:
    return _problem(
        400,
        "INVALID_CURSOR",
        "Invalid cursor",
        "The cursor is invalid for this PaperCollection",
    )


def _schema_problem() -> SecurityProblem:
    return _problem(
        422,
        "PAPER_COLLECTION_SCHEMA_INVALID",
        "PaperCollection Schema invalid",
        "The ArtifactVersion content is not a valid PaperCollection",
    )


def _provenance_problem() -> SecurityProblem:
    return _problem(
        403,
        "PROVENANCE_SCOPE_VIOLATION",
        "Provenance access denied",
        "The PaperCollection provenance graph is incomplete or outside the authorized project",
    )


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)
