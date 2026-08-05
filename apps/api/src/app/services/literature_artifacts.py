"""B-08 version-pinned Claim, Relation, and ReasoningTrace reads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import ValidationError

from app.config import settings
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    SourceSnapshotDetail,
)
from app.schemas.literature_artifact_api import (
    LiteratureArtifactVersionContext,
    LiteratureClaimRead,
    LiteraturePaperSummaryReference,
    LiteratureReasoningTraceRead,
    LiteratureRelationRead,
)
from app.schemas.literature_claim import (
    LiteratureClaimCandidate,
    LiteratureClaimsCandidate,
    LiteratureClaimStatus,
)
from app.schemas.literature_relation import (
    LiteratureReasoningTraceCandidate,
    LiteratureRelationCandidate,
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
)
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService

_MAX_PAGE_SIZE = 100
_MAX_CONTENT_BYTES = 10 * 1024 * 1024
_MAX_DOMAIN_ITEMS = 10_000
_ORDERING = "stable_id.asc.v1"
_CURSOR_VERSION = 1
_Item = TypeVar("_Item")


@dataclass(frozen=True, slots=True)
class _ClaimsContext:
    version: ArtifactVersionDetail
    candidate: LiteratureClaimsCandidate
    version_context: LiteratureArtifactVersionContext
    reads: Mapping[str, LiteratureClaimRead]


@dataclass(frozen=True, slots=True)
class _RelationsContext:
    version: ArtifactVersionDetail
    candidate: LiteratureRelationsCandidate
    version_context: LiteratureArtifactVersionContext
    claim_reads: Mapping[str, LiteratureClaimRead]
    evidence_by_relation: Mapping[str, tuple[EvidenceDetail, ...]]
    snapshots_by_relation: Mapping[str, tuple[SourceSnapshotDetail, ...]]


class LiteratureArtifactReadService:
    """Project D-07/D-08 content without rerunning scientific admission."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def list_claims(
        self,
        *,
        version_id: str,
        session_id: str,
        status: LiteratureClaimStatus | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[LiteratureClaimRead, ...], str | None, bool]:
        context = self._claims_context(version_id=version_id, session_id=session_id)
        items = tuple(
            item
            for item in context.reads.values()
            if status is None or item.claim.status is status
        )
        return _page(
            items,
            key=lambda item: item.claim.claim_id,
            version_id=context.version.id,
            collection="literature_claims",
            status=status.value if status is not None else None,
            cursor=cursor,
            limit=limit,
        )

    def get_claim(
        self, *, version_id: str, claim_id: str, session_id: str
    ) -> LiteratureClaimRead:
        context = self._claims_context(version_id=version_id, session_id=session_id)
        item = context.reads.get(claim_id)
        if item is None:
            raise _not_found("LITERATURE_CLAIM_NOT_FOUND")
        return item

    def list_relations(
        self,
        *,
        version_id: str,
        session_id: str,
        status: LiteratureRelationStatus | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[LiteratureRelationRead, ...], str | None, bool]:
        context = self._relations_context(version_id=version_id, session_id=session_id)
        items = tuple(
            self._relation_read(context, relation)
            for relation in context.candidate.relations
            if status is None or relation.status is status
        )
        return _page(
            items,
            key=lambda item: item.relation.relation_id,
            version_id=context.version.id,
            collection="literature_relations",
            status=status.value if status is not None else None,
            cursor=cursor,
            limit=limit,
        )

    def get_relation(
        self, *, version_id: str, relation_id: str, session_id: str
    ) -> LiteratureRelationRead:
        context = self._relations_context(version_id=version_id, session_id=session_id)
        relation = next(
            (
                item
                for item in context.candidate.relations
                if item.relation_id == relation_id
            ),
            None,
        )
        if relation is None:
            raise _not_found("LITERATURE_RELATION_NOT_FOUND")
        return self._relation_read(context, relation)

    def list_reasoning_traces(
        self,
        *,
        version_id: str,
        session_id: str,
        status: LiteratureRelationStatus | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[LiteratureReasoningTraceRead, ...], str | None, bool]:
        context = self._relations_context(version_id=version_id, session_id=session_id)
        relations = {item.relation_id: item for item in context.candidate.relations}
        items = tuple(
            self._trace_read(context, trace, relations[trace.relation_id])
            for trace in context.candidate.reasoning_traces
            if status is None or relations[trace.relation_id].status is status
        )
        return _page(
            items,
            key=lambda item: item.trace.trace_id,
            version_id=context.version.id,
            collection="reasoning_traces",
            status=status.value if status is not None else None,
            cursor=cursor,
            limit=limit,
        )

    def get_reasoning_trace(
        self, *, version_id: str, trace_id: str, session_id: str
    ) -> LiteratureReasoningTraceRead:
        context = self._relations_context(version_id=version_id, session_id=session_id)
        trace = next(
            (
                item
                for item in context.candidate.reasoning_traces
                if item.trace_id == trace_id
            ),
            None,
        )
        if trace is None:
            raise _not_found("REASONING_TRACE_NOT_FOUND")
        relation = next(
            item
            for item in context.candidate.relations
            if item.relation_id == trace.relation_id
        )
        return self._trace_read(context, trace, relation)

    def _claims_context(self, *, version_id: str, session_id: str) -> _ClaimsContext:
        version = self._version(version_id=version_id, session_id=session_id)
        self._require_kind(version, "literature_claims", session_id=session_id)
        candidate = _validated_candidate(
            version, LiteratureClaimsCandidate, "LITERATURE_CLAIMS_SCHEMA_INVALID"
        )
        if len(candidate.claims) > _MAX_DOMAIN_ITEMS:
            raise _capacity_problem("LiteratureClaim")
        _validate_runtime_producer(version, candidate)

        reference = candidate.input_versions
        try:
            summary_version = self._artifacts.get_version(
                version_id=reference.paper_summary_artifact_version_id,
                session_id=session_id,
                full_content=True,
            )
            summary_artifact = self._artifacts.get_artifact(
                artifact_id=summary_version.artifact_id,
                session_id=session_id,
            )
            summary = PaperSummaryArtifactContent.model_validate(
                summary_version.content
            )
        except (SecurityProblem, ValidationError) as exc:
            raise _provenance_problem() from exc
        if (
            summary_version.id != reference.paper_summary_artifact_version_id
            or summary_artifact.kind.value != "paper_summary"
            or summary_artifact.project_id != version.project_id
            or summary_version.project_id != version.project_id
            or summary_version.schema_version != summary.schema_version
            or summary_version.content_hash
            != compute_canonical_payload_hash(summary_version.content)
            or summary.schema_version != reference.paper_summary_schema_version
            or summary.output_hash != reference.paper_summary_output_hash
            or summary.summary_id != reference.summary_id
            or summary.paper_id != reference.paper_id
        ):
            raise _provenance_problem()
        summary_snapshots = {
            (
                item.source_snapshot_id,
                item.source_id,
                item.source_version,
                item.content_hash,
            )
            for item in summary.input_versions.source_snapshots
        }
        claim_snapshots = {
            (
                item.source_snapshot_id,
                item.source_id,
                item.source_version,
                item.content_hash,
            )
            for item in reference.source_snapshots
        }
        if claim_snapshots != summary_snapshots:
            raise _provenance_problem()
        summary_evidence = {item.evidence_id: item for item in summary.evidence}
        if any(
            summary_evidence.get(item.evidence_id) != item
            for item in candidate.evidence
        ):
            raise _provenance_problem()

        snapshot_map = _snapshot_projection_map(
            version,
            candidate.source_snapshot_ids,
            {
                item.source_snapshot_id: (
                    item.source_id,
                    item.source_version,
                    item.content_hash,
                )
                for item in reference.source_snapshots
            },
        )
        evidence_by_pipeline_id = {
            item.evidence_id: item for item in candidate.evidence
        }
        evidence_by_claim: dict[str, list[EvidenceDetail]] = {}
        used_evidence: set[str] = set()
        for item in candidate.evidence_references:
            pipeline_evidence = evidence_by_pipeline_id.get(item.evidence_id)
            persisted_snapshot = snapshot_map.get(item.source_snapshot_id)
            if pipeline_evidence is None or persisted_snapshot is None:
                raise _provenance_problem()
            matches = tuple(
                evidence
                for evidence in version.evidence
                if evidence.target_type == "claim"
                and evidence.target_id == item.claim_id
                and evidence.paper_id == item.paper_id
                and evidence.artifact_version_id == version.id
                and evidence.source_snapshot_id == persisted_snapshot.id
                and _locator_value(evidence.locator, "summary_evidence_id")
                == item.evidence_id
                and _locator_value(evidence.locator, "source_record_id")
                == pipeline_evidence.source_record_id
            )
            if len(matches) != 1 or matches[0].id in used_evidence:
                raise _provenance_problem()
            used_evidence.add(matches[0].id)
            evidence_by_claim.setdefault(item.claim_id, []).append(matches[0])
        _require_exact_persisted_provenance(
            version,
            used_evidence=used_evidence,
            used_snapshots={item.id for item in snapshot_map.values()},
        )

        version_context = _version_context(version, candidate.output_hash)
        summary_reference = LiteraturePaperSummaryReference(
            artifact_version_id=summary_version.id,
            summary_id=summary.summary_id,
            paper_id=summary.paper_id,
            schema_version=summary.schema_version,
            content_hash=summary_version.content_hash,
            output_hash=summary.output_hash,
        )
        reads: dict[str, LiteratureClaimRead] = {}
        for claim in candidate.claims:
            evidence = tuple(
                sorted(
                    evidence_by_claim.get(claim.claim_id, ()), key=lambda item: item.id
                )
            )
            snapshot_ids = {item.source_snapshot_id for item in evidence}
            snapshots = tuple(
                sorted(
                    (item for item in snapshot_map.values() if item.id in snapshot_ids),
                    key=lambda item: item.id,
                )
            )
            if claim.status is not LiteratureClaimStatus.rejected and (
                not evidence or not snapshots
            ):
                raise _provenance_problem()
            reads[claim.claim_id] = LiteratureClaimRead(
                version=version_context,
                claim=claim,
                paper_summary=summary_reference,
                source_snapshots=snapshots,
                evidence=evidence,
            )
        return _ClaimsContext(
            version=version,
            candidate=candidate,
            version_context=version_context,
            reads=dict(sorted(reads.items())),
        )

    def _relations_context(
        self, *, version_id: str, session_id: str
    ) -> _RelationsContext:
        version = self._version(version_id=version_id, session_id=session_id)
        self._require_kind(version, "literature_relations", session_id=session_id)
        candidate = _validated_candidate(
            version,
            LiteratureRelationsCandidate,
            "LITERATURE_RELATIONS_SCHEMA_INVALID",
        )
        if (
            max(len(candidate.relations), len(candidate.reasoning_traces))
            > _MAX_DOMAIN_ITEMS
        ):
            raise _capacity_problem("LiteratureRelation")
        _validate_runtime_producer(version, candidate)

        claim_reads: dict[str, LiteratureClaimRead] = {}
        upstream_claims: dict[str, LiteratureClaimCandidate] = {}
        for reference in candidate.input_versions.claim_artifact_versions:
            try:
                context = self._claims_context(
                    version_id=reference.artifact_version_id,
                    session_id=session_id,
                )
            except SecurityProblem as exc:
                raise _provenance_problem() from exc
            expected_summary_versions = tuple(
                sorted(
                    {
                        item.source_paper_summary_artifact_version_id
                        for item in context.candidate.claims
                    }
                )
            )
            if (
                context.version.id != reference.artifact_version_id
                or context.version.project_id != version.project_id
                or reference.project_id != version.project_id
                or reference.schema_version != context.candidate.schema_version
                or reference.content_hash != context.version.content_hash
                or reference.output_hash != context.candidate.output_hash
                or reference.claim_ids
                != tuple(sorted(item.claim_id for item in context.candidate.claims))
                or reference.paper_summary_artifact_version_ids
                != expected_summary_versions
                or reference.source_snapshot_ids
                != tuple(sorted(context.candidate.source_snapshot_ids))
            ):
                raise _provenance_problem()
            for claim_id, read in context.reads.items():
                if claim_id in claim_reads:
                    raise _provenance_problem()
                claim_reads[claim_id] = read
                upstream_claims[claim_id] = read.claim
        if set(upstream_claims) != {item.claim_id for item in candidate.claims}:
            raise _provenance_problem()
        if any(upstream_claims.get(item.claim_id) != item for item in candidate.claims):
            raise _provenance_problem()

        evidence_by_pipeline_id = {
            item.evidence_id: item for item in candidate.evidence
        }
        snapshot_references = _relation_snapshot_references(candidate)
        snapshot_map = _snapshot_projection_map(
            version, candidate.source_snapshot_ids, snapshot_references
        )
        evidence_by_relation: dict[str, list[EvidenceDetail]] = {}
        used_evidence: set[str] = set()
        seen_relation_evidence: set[tuple[str, str]] = set()
        for item in candidate.evidence_references:
            pair = (item.relation_id, item.evidence_id)
            if pair in seen_relation_evidence:
                continue
            seen_relation_evidence.add(pair)
            pipeline_evidence = evidence_by_pipeline_id.get(item.evidence_id)
            persisted_snapshot = snapshot_map.get(item.source_snapshot_id)
            if pipeline_evidence is None or persisted_snapshot is None:
                raise _provenance_problem()
            matches = tuple(
                evidence
                for evidence in version.evidence
                if evidence.target_type == "relation"
                and evidence.target_id == item.relation_id
                and evidence.paper_id == item.paper_id
                and evidence.artifact_version_id == version.id
                and evidence.source_snapshot_id == persisted_snapshot.id
                and _locator_value(evidence.locator, "summary_evidence_id")
                == item.evidence_id
                and _locator_value(evidence.locator, "source_record_id")
                == pipeline_evidence.source_record_id
            )
            if len(matches) != 1 or matches[0].id in used_evidence:
                raise _provenance_problem()
            used_evidence.add(matches[0].id)
            evidence_by_relation.setdefault(item.relation_id, []).append(matches[0])
        _require_exact_persisted_provenance(
            version,
            used_evidence=used_evidence,
            used_snapshots={item.id for item in snapshot_map.values()},
        )
        snapshots_by_relation = {
            relation.relation_id: tuple(
                sorted(
                    (
                        snapshot_map[item]
                        for item in relation.source_snapshot_ids
                        if item in snapshot_map
                    ),
                    key=lambda item: item.id,
                )
            )
            for relation in candidate.relations
        }
        return _RelationsContext(
            version=version,
            candidate=candidate,
            version_context=_version_context(version, candidate.output_hash),
            claim_reads=claim_reads,
            evidence_by_relation={
                key: tuple(sorted(items, key=lambda item: item.id))
                for key, items in evidence_by_relation.items()
            },
            snapshots_by_relation=snapshots_by_relation,
        )

    @staticmethod
    def _relation_read(
        context: _RelationsContext, relation: LiteratureRelationCandidate
    ) -> LiteratureRelationRead:
        traces = {item.trace_id: item for item in context.candidate.reasoning_traces}
        trace = (
            traces.get(relation.reasoning_trace_id)
            if relation.reasoning_trace_id is not None
            else None
        )
        source_claim = context.claim_reads.get(relation.source_claim_id)
        target_claim = context.claim_reads.get(relation.target_claim_id)
        evidence = context.evidence_by_relation.get(relation.relation_id, ())
        snapshots = context.snapshots_by_relation.get(relation.relation_id, ())
        graph_eligible = relation.status is LiteratureRelationStatus.accepted
        if graph_eligible and (
            source_claim is None
            or target_claim is None
            or source_claim.claim.status is not LiteratureClaimStatus.accepted
            or target_claim.claim.status is not LiteratureClaimStatus.accepted
            or trace is None
            or not evidence
            or not snapshots
        ):
            raise _provenance_problem()
        return LiteratureRelationRead(
            version=context.version_context,
            relation=relation,
            source_claim=source_claim,
            target_claim=target_claim,
            reasoning_trace=trace,
            source_snapshots=snapshots,
            evidence=evidence,
            graph_eligible=graph_eligible,
        )

    @staticmethod
    def _trace_read(
        context: _RelationsContext,
        trace: LiteratureReasoningTraceCandidate,
        relation: LiteratureRelationCandidate,
    ) -> LiteratureReasoningTraceRead:
        source_claim = context.claim_reads.get(relation.source_claim_id)
        target_claim = context.claim_reads.get(relation.target_claim_id)
        evidence = context.evidence_by_relation.get(relation.relation_id, ())
        snapshots = context.snapshots_by_relation.get(relation.relation_id, ())
        if (
            source_claim is None
            or target_claim is None
            or not evidence
            or not snapshots
        ):
            raise _provenance_problem()
        return LiteratureReasoningTraceRead(
            version=context.version_context,
            trace=trace,
            relation=relation,
            source_claim=source_claim,
            target_claim=target_claim,
            source_snapshots=snapshots,
            evidence=evidence,
        )

    def _version(self, *, version_id: str, session_id: str) -> ArtifactVersionDetail:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        content_size = len(
            json.dumps(
                version.content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if content_size > _MAX_CONTENT_BYTES:
            raise _problem(
                413,
                "LITERATURE_ARTIFACT_SIZE_LIMIT_EXCEEDED",
                "Literature artifact size limit exceeded",
                "The ArtifactVersion exceeds the literature read size limit",
            )
        return version

    def _require_kind(
        self,
        version: ArtifactVersionDetail,
        expected: str,
        *,
        session_id: str,
    ) -> None:
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id,
            session_id=session_id,
        )
        if artifact.project_id != version.project_id:
            raise _provenance_problem()
        if artifact.kind.value != expected:
            raise _problem(
                409,
                "ARTIFACT_KIND_MISMATCH",
                "Artifact kind mismatch",
                f"The ArtifactVersion is not {expected}",
            )


def _validated_candidate(
    version: ArtifactVersionDetail,
    model: type[_Item],
    error_code: str,
) -> _Item:
    try:
        candidate = model.model_validate(version.content)  # type: ignore[attr-defined]
    except ValidationError as exc:
        raise _schema_problem(error_code) from exc
    if (
        version.schema_version != candidate.schema_version  # type: ignore[attr-defined]
        or version.content_hash != compute_canonical_payload_hash(version.content)
        or version.input_hash != candidate.input_hash  # type: ignore[attr-defined]
    ):
        raise _schema_problem(error_code)
    return candidate


def _validate_runtime_producer(
    version: ArtifactVersionDetail,
    candidate: LiteratureClaimsCandidate | LiteratureRelationsCandidate,
) -> None:
    producer = candidate.producer
    runtime = version.producer_execution
    if (
        runtime.run_id != version.created_by_run_id
        or runtime.step_key != producer.step_key
        or runtime.producer.type != producer.producer_type
        or runtime.producer.name != producer.producer_name
        or runtime.producer.version != producer.producer_version
        or runtime.producer.model_name != producer.model_name
        or runtime.producer.prompt_name != producer.prompt_name
        or runtime.producer.prompt_version != producer.prompt_version
        or runtime.producer.prompt_hash != producer.prompt_hash
        or runtime.parameters_hash != producer.parameters_hash
        or runtime.producer.parameters_hash != producer.parameters_hash
        or runtime.input_hash != candidate.input_hash
        or runtime.output_hash != version.content_hash
        or runtime.status != "completed"
        or version.producer != runtime.producer
    ):
        raise _schema_problem(
            "LITERATURE_CLAIMS_SCHEMA_INVALID"
            if candidate.kind == "literature_claims"
            else "LITERATURE_RELATIONS_SCHEMA_INVALID"
        )
    if producer.run_id is not None and producer.run_id != version.created_by_run_id:
        raise _schema_problem(
            "LITERATURE_CLAIMS_SCHEMA_INVALID"
            if candidate.kind == "literature_claims"
            else "LITERATURE_RELATIONS_SCHEMA_INVALID"
        )


def _snapshot_projection_map(
    version: ArtifactVersionDetail,
    pipeline_ids: Iterable[str],
    references: Mapping[str, tuple[str, str, str]],
) -> dict[str, SourceSnapshotDetail]:
    persisted_by_key: dict[tuple[str, str, str], SourceSnapshotDetail] = {}
    for snapshot in version.source_snapshots:
        key = (
            snapshot.source_id,
            snapshot.source_version_or_etag
            or snapshot.cache_version
            or snapshot.content_hash,
            snapshot.content_hash,
        )
        if key in persisted_by_key:
            raise _provenance_problem()
        persisted_by_key[key] = snapshot
    result: dict[str, SourceSnapshotDetail] = {}
    for pipeline_id in pipeline_ids:
        reference = references.get(pipeline_id)
        persisted = persisted_by_key.get(reference) if reference is not None else None
        if persisted is None:
            raise _provenance_problem()
        result[pipeline_id] = persisted
    if set(version.source_snapshot_ids) != {
        item.id for item in version.source_snapshots
    }:
        raise _provenance_problem()
    if {item.id for item in result.values()} != set(version.source_snapshot_ids):
        raise _provenance_problem()
    return result


def _relation_snapshot_references(
    candidate: LiteratureRelationsCandidate,
) -> dict[str, tuple[str, str, str]]:
    references: dict[str, tuple[str, str, str]] = {}
    for item in candidate.evidence:
        reference = (
            item.source_id,
            item.source_snapshot_version,
            item.source_snapshot_content_hash,
        )
        existing = references.get(item.source_snapshot_id)
        if existing is not None and existing != reference:
            raise _provenance_problem()
        references[item.source_snapshot_id] = reference
    return references


def _require_exact_persisted_provenance(
    version: ArtifactVersionDetail,
    *,
    used_evidence: set[str],
    used_snapshots: set[str],
) -> None:
    if (
        len({item.id for item in version.evidence}) != len(version.evidence)
        or set(version.evidence_ids) != {item.id for item in version.evidence}
        or used_evidence != set(version.evidence_ids)
        or used_snapshots != set(version.source_snapshot_ids)
    ):
        raise _provenance_problem()


def _version_context(
    version: ArtifactVersionDetail, output_hash: str
) -> LiteratureArtifactVersionContext:
    return LiteratureArtifactVersionContext(
        artifact_version_id=version.id,
        artifact_id=version.artifact_id,
        project_id=version.project_id,
        version_number=version.version_number,
        supersedes_version_id=version.supersedes_version_id,
        source_mode=version.source_mode,
        schema_version=version.schema_version,
        content_hash=version.content_hash,
        input_hash=version.input_hash,
        output_hash=output_hash,
        created_at=version.created_at,
        producer_execution=version.producer_execution,
    )


def _locator_value(locator: Mapping[str, Any], key: str) -> str | None:
    value = locator.get(key)
    return value if isinstance(value, str) and value else None


def _page(
    items: tuple[_Item, ...],
    *,
    key: Any,
    version_id: str,
    collection: str,
    status: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[tuple[_Item, ...], str | None, bool]:
    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise _problem(
            422,
            "SCHEMA_VALIDATION_FAILED",
            "Request validation failed",
            "limit must be between 1 and 100",
        )
    ordered = tuple(sorted(items, key=key))
    keys = tuple(key(item) for item in ordered)
    if len(keys) != len(set(keys)):
        raise _provenance_problem()
    start = 0
    if cursor is not None:
        last_id = _decode_cursor(
            cursor,
            version_id=version_id,
            collection=collection,
            status=status,
        )
        try:
            start = keys.index(last_id) + 1
        except ValueError as exc:
            raise _invalid_cursor(collection) from exc
    selected = ordered[start : start + limit]
    has_more = start + len(selected) < len(ordered)
    next_cursor = (
        _encode_cursor(
            version_id=version_id,
            collection=collection,
            status=status,
            last_id=key(selected[-1]),
        )
        if selected and has_more
        else None
    )
    return selected, next_cursor, has_more


def _encode_cursor(
    *, version_id: str, collection: str, status: str | None, last_id: str
) -> str:
    payload: dict[str, Any] = {
        "v": _CURSOR_VERSION,
        "version_id": version_id,
        "collection": collection,
        "status": status,
        "ordering": _ORDERING,
        "last_id": last_id,
    }
    payload["signature"] = _cursor_signature(payload)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    value: str, *, version_id: str, collection: str, status: str | None
) -> str:
    try:
        if len(value) > 4096:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if (
            set(payload)
            != {
                "v",
                "version_id",
                "collection",
                "status",
                "ordering",
                "last_id",
                "signature",
            }
            or payload["v"] != _CURSOR_VERSION
            or payload["version_id"] != version_id
            or payload["collection"] != collection
            or payload["status"] != status
            or payload["ordering"] != _ORDERING
            or not isinstance(payload["last_id"], str)
            or not payload["last_id"]
            or not isinstance(payload["signature"], str)
            or not hmac.compare_digest(
                payload["signature"],
                _cursor_signature(
                    {key: item for key, item in payload.items() if key != "signature"}
                ),
            )
        ):
            raise ValueError
        return payload["last_id"]
    except (
        binascii.Error,
        json.JSONDecodeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        raise _invalid_cursor(collection) from exc


def _cursor_signature(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    key = settings.CURSOR_SIGNING_KEY.get_secret_value().encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _schema_problem(code: str) -> SecurityProblem:
    title = (
        "LiteratureClaims Schema invalid"
        if code == "LITERATURE_CLAIMS_SCHEMA_INVALID"
        else "LiteratureRelations Schema invalid"
    )
    return _problem(
        422,
        code,
        title,
        "The ArtifactVersion content is not a valid admitted literature artifact",
    )


def _provenance_problem() -> SecurityProblem:
    return _problem(
        403,
        "PROVENANCE_SCOPE_VIOLATION",
        "Provenance access denied",
        "The literature provenance graph is incomplete or outside the authorized project",
    )


def _capacity_problem(item: str) -> SecurityProblem:
    return _problem(
        413,
        "LITERATURE_ARTIFACT_ITEM_LIMIT_EXCEEDED",
        "Literature artifact item limit exceeded",
        f"The ArtifactVersion exceeds the {item} item limit",
    )


def _invalid_cursor(collection: str) -> SecurityProblem:
    return _problem(
        400,
        "INVALID_CURSOR",
        "Invalid cursor",
        f"The cursor is invalid for this {collection} collection",
    )


def _not_found(code: str) -> SecurityProblem:
    return _problem(404, code, "Resource not found", "Resource not found")


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = ["LiteratureArtifactReadService"]
