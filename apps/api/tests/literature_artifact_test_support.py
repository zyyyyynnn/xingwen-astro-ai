from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_payload
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.schemas.literature_claim import LiteratureClaimsCandidate
from app.schemas.paper_summary_api import (
    PaperSummaryPaperMetadata,
    PaperSummaryRead,
)
from app.schemas.literature_relation import (
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
)
from app.schemas.paper_summary import PaperSummaryArtifactContent
from app.security import SecurityProblem

from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim_benchmark_cases import _build_claim_fixture
from services.paper_pipeline.relation_benchmark_cases import (
    _claim_inputs,
    build_frozen_relation_benchmark_cases,
)

NOW = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
PROJECT_ID = "project.literature_relation_benchmark"
RUN_ID = "run-literature"


@dataclass(frozen=True, slots=True)
class LiteratureFixture:
    artifacts: FixtureArtifactReads
    claim_version_ids: tuple[str, ...]
    relation_version_id: str
    accepted_relation_id: str
    trace_id: str


class FixtureArtifactReads:
    def __init__(
        self,
        *,
        versions: dict[str, ArtifactVersionDetail],
        artifacts: dict[str, ResearchArtifactDetail],
    ) -> None:
        self.versions = versions
        self.artifacts = artifacts
        self.full_content_requests: list[bool] = []
        self.paper_summary_reader = FixturePaperSummaryReads(self)

    def get_version(
        self,
        *,
        version_id: str,
        session_id: str,
        full_content: bool = False,
    ) -> ArtifactVersionDetail:
        self.full_content_requests.append(full_content)
        if session_id != "owner" or version_id not in self.versions:
            raise _not_found("ARTIFACT_VERSION_NOT_FOUND")
        return self.versions[version_id]

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        if session_id != "owner" or artifact_id not in self.artifacts:
            raise _not_found("ARTIFACT_NOT_FOUND")
        return self.artifacts[artifact_id]



class FixturePaperSummaryReads:
    """Test-only Summary envelope validator for frozen paper acquisition benchmark inputs."""

    def __init__(self, artifacts: FixtureArtifactReads) -> None:
        self._artifacts = artifacts

    def get_summary(self, *, version_id: str, session_id: str) -> PaperSummaryRead:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=True,
        )
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        summary = PaperSummaryArtifactContent.model_validate(version.content)
        producer = summary.producer
        runtime = version.producer_execution
        if (
            artifact.kind.value != "paper_summary"
            or artifact.project_id != version.project_id
            or version.schema_version != summary.schema_version
            or version.content_hash
            != compute_canonical_payload_hash(version.content)
            or version.input_hash != summary.input_hash
            or runtime.run_id != version.created_by_run_id
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
            or runtime.input_hash != summary.input_hash
            or runtime.output_hash != version.content_hash
            or runtime.status != "completed"
            or version.producer != runtime.producer
        ):
            raise _not_found("PAPER_SUMMARY_INVALID")
        if producer.run_id is not None and producer.run_id != version.created_by_run_id:
            raise _not_found("PAPER_SUMMARY_INVALID")
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
            paper=PaperSummaryPaperMetadata(
                paper_id=summary.paper_id,
                title=summary.paper_id,
            ),
            summary=summary,
            producer_execution=runtime,
            source_snapshots=version.source_snapshots,
            evidence=version.evidence,
        )


def build_literature_fixture() -> LiteratureFixture:
    benchmark = load_frozen_benchmark()
    relation_case = next(
        item
        for item in build_frozen_relation_benchmark_cases(benchmark)
        if item.admission.publisher_candidate is not None
        and item.admission.records[0].status is LiteratureRelationStatus.accepted
    )
    relation_candidate = relation_case.admission.publisher_candidate
    assert relation_candidate is not None
    claim_inputs = _claim_inputs(benchmark)
    claim_versions_by_id = {
        item.version.artifact_version_id: item.version for item in claim_inputs.values()
    }

    summary_contents: dict[str, PaperSummaryArtifactContent] = {}
    for claim in benchmark.claims:
        fixture = _build_claim_fixture(benchmark, claim)
        for summary_input in fixture["versions"].values():
            summary_contents[summary_input.artifact_version_id] = summary_input.content

    versions: dict[str, ArtifactVersionDetail] = {}
    artifacts: dict[str, ResearchArtifactDetail] = {}
    for summary_version_id, summary in summary_contents.items():
        version = _summary_version(summary_version_id, summary)
        versions[version.id] = version
        artifacts[version.artifact_id] = _artifact(version, "paper_summary")

    claim_version_ids: list[str] = []
    for reference in relation_candidate.input_versions.claim_artifact_versions:
        pipeline_version = claim_versions_by_id[reference.artifact_version_id]
        version = _claim_version(
            reference.artifact_version_id,
            pipeline_version.content,
        )
        versions[version.id] = version
        artifacts[version.artifact_id] = _artifact(version, "literature_claims")
        claim_version_ids.append(version.id)

    relation_version_id = "artifact-version-literature-relations"
    relation_version = _relation_version(relation_version_id, relation_candidate)
    versions[relation_version.id] = relation_version
    artifacts[relation_version.artifact_id] = _artifact(
        relation_version, "literature_relations"
    )
    accepted = next(
        item
        for item in relation_candidate.relations
        if item.status is LiteratureRelationStatus.accepted
    )
    assert accepted.reasoning_trace_id is not None
    return LiteratureFixture(
        artifacts=FixtureArtifactReads(versions=versions, artifacts=artifacts),
        claim_version_ids=tuple(sorted(claim_version_ids)),
        relation_version_id=relation_version.id,
        accepted_relation_id=accepted.relation_id,
        trace_id=accepted.reasoning_trace_id,
    )


def _summary_version(
    version_id: str, summary: PaperSummaryArtifactContent
) -> ArtifactVersionDetail:
    return _version(
        version_id=version_id,
        kind="paper_summary",
        candidate=summary,
        snapshots=(),
        evidence=(),
    )


def _claim_version(
    version_id: str, candidate: LiteratureClaimsCandidate
) -> ArtifactVersionDetail:
    snapshot_specs = {
        item.source_snapshot_id: (
            item.source_id,
            item.source_version,
            item.content_hash,
        )
        for item in candidate.input_versions.source_snapshots
        if item.source_snapshot_id in candidate.source_snapshot_ids
    }
    snapshots = _snapshots(snapshot_specs)
    persisted_by_pipeline_id = {
        pipeline_id: snapshot
        for pipeline_id, snapshot in zip(sorted(snapshot_specs), snapshots, strict=True)
    }
    pipeline_evidence = {item.evidence_id: item for item in candidate.evidence}
    evidence: list[EvidenceDetail] = []
    for reference in candidate.evidence_references:
        item = pipeline_evidence[reference.evidence_id]
        evidence.append(
            _evidence(
                version_id=version_id,
                target_type="claim",
                target_id=reference.claim_id,
                pipeline_evidence_id=reference.evidence_id,
                source_record_id=item.source_record_id,
                paper_summary_locator=item.locator.model_dump(
                    mode="json", exclude_none=True
                ),
                snapshot_id=persisted_by_pipeline_id[reference.source_snapshot_id].id,
                paper_id=reference.paper_id,
            )
        )
    return _version(
        version_id=version_id,
        kind="literature_claims",
        candidate=candidate,
        snapshots=snapshots,
        evidence=tuple(evidence),
    )


def _relation_version(
    version_id: str, candidate: LiteratureRelationsCandidate
) -> ArtifactVersionDetail:
    snapshot_specs = {
        item.source_snapshot_id: (
            item.source_id,
            item.source_snapshot_version,
            item.source_snapshot_content_hash,
        )
        for item in candidate.evidence
        if item.source_snapshot_id in candidate.source_snapshot_ids
    }
    snapshots = _snapshots(snapshot_specs)
    persisted_by_pipeline_id = {
        pipeline_id: snapshot
        for pipeline_id, snapshot in zip(sorted(snapshot_specs), snapshots, strict=True)
    }
    pipeline_evidence = {item.evidence_id: item for item in candidate.evidence}
    evidence: list[EvidenceDetail] = []
    seen: set[tuple[str, str]] = set()
    for reference in candidate.evidence_references:
        pair = (reference.relation_id, reference.evidence_id)
        if pair in seen:
            continue
        seen.add(pair)
        item = pipeline_evidence[reference.evidence_id]
        evidence.append(
            _evidence(
                version_id=version_id,
                target_type="relation",
                target_id=reference.relation_id,
                pipeline_evidence_id=reference.evidence_id,
                source_record_id=item.source_record_id,
                paper_summary_locator=item.locator.model_dump(
                    mode="json", exclude_none=True
                ),
                snapshot_id=persisted_by_pipeline_id[reference.source_snapshot_id].id,
                paper_id=reference.paper_id,
            )
        )
    return _version(
        version_id=version_id,
        kind="literature_relations",
        candidate=candidate,
        snapshots=snapshots,
        evidence=tuple(evidence),
    )


def _version(
    *,
    version_id: str,
    kind: str,
    candidate: PaperSummaryArtifactContent
    | LiteratureClaimsCandidate
    | LiteratureRelationsCandidate,
    snapshots: tuple[SourceSnapshotDetail, ...],
    evidence: tuple[EvidenceDetail, ...],
) -> ArtifactVersionDetail:
    content = canonical_artifact_content_payload(candidate)
    content_hash = compute_canonical_payload_hash(content)
    producer = _producer(candidate)
    return ArtifactVersionDetail(
        id=version_id,
        artifact_id=f"artifact-{_token(version_id)}",
        project_id=PROJECT_ID,
        created_by_run_id=RUN_ID,
        version_number=1,
        schema_version=candidate.schema_version,
        content=content,
        content_hash=content_hash,
        input_hash=candidate.input_hash,
        source_mode="fixture",
        producer=producer,
        source_snapshot_ids=tuple(item.id for item in snapshots),
        evidence_ids=tuple(item.id for item in evidence),
        supersedes_version_id=None,
        created_at=NOW,
        producer_execution=ProducerExecutionDetail(
            id=f"producer-{_token(version_id)}",
            run_id=RUN_ID,
            step_key=candidate.producer.step_key,
            step_attempt_id=f"attempt-{_token(version_id)}",
            producer=producer,
            parameters={},
            parameters_hash=candidate.producer.parameters_hash,
            input_hash=candidate.input_hash,
            output_hash=content_hash,
            status="completed",
            started_at=NOW,
            finished_at=NOW,
            latency_ms=1,
        ),
        source_snapshots=snapshots,
        evidence=evidence,
    )


def _producer(
    candidate: PaperSummaryArtifactContent
    | LiteratureClaimsCandidate
    | LiteratureRelationsCandidate,
) -> ProducerReference:
    nested = candidate.producer
    return ProducerReference(
        type=nested.producer_type,
        name=nested.producer_name,
        version=nested.producer_version,
        model_name=nested.model_name,
        prompt_name=nested.prompt_name,
        prompt_version=nested.prompt_version,
        prompt_hash=nested.prompt_hash,
        parameters_hash=nested.parameters_hash,
    )


def _snapshots(
    specs: dict[str, tuple[str, str, str]],
) -> tuple[SourceSnapshotDetail, ...]:
    return tuple(
        SourceSnapshotDetail(
            id=f"snapshot-{_token(pipeline_id)}",
            source_id=source_id,
            source_type="benchmark",
            retrieved_at=NOW,
            query={"fixture": pipeline_id},
            query_hash=compute_canonical_payload_hash({"fixture": pipeline_id}),
            source_version_or_etag=source_version,
            content_hash=content_hash,
            license_note="Benchmark fixture",
            request_metadata={"data_level": "benchmark"},
        )
        for pipeline_id, (source_id, source_version, content_hash) in sorted(
            specs.items()
        )
    )


def _evidence(
    *,
    version_id: str,
    target_type: str,
    target_id: str,
    pipeline_evidence_id: str,
    source_record_id: str,
    paper_summary_locator: dict[str, object],
    snapshot_id: str,
    paper_id: str,
) -> EvidenceDetail:
    identity = f"{version_id}:{target_type}:{target_id}:{pipeline_evidence_id}"
    return EvidenceDetail(
        id=f"evidence-{_token(identity)}",
        artifact_version_id=version_id,
        target_type=target_type,
        target_id=target_id,
        evidence_type="paper_text",
        source_snapshot_id=snapshot_id,
        paper_id=paper_id,
        locator={
            "summary_evidence_id": pipeline_evidence_id,
            "source_record_id": source_record_id,
            "paper_summary_locator": paper_summary_locator,
        },
        quote_or_value="Benchmark evidence",
        extraction_method="literature_admission",
        confidence=1.0,
        created_at=NOW,
    )


def _artifact(version: ArtifactVersionDetail, kind: str) -> ResearchArtifactDetail:
    return ResearchArtifactDetail(
        id=version.artifact_id,
        project_id=version.project_id,
        kind=kind,
        title=kind,
        logical_key=f"{kind}.fixture",
        created_at=NOW,
        latest_version_id=version.id,
        versions=(),
    )


def _token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404,
        code=code,
        title="Resource not found",
        detail="Resource not found",
    )
