from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection import (
    PaperBenchmarkReference,
    PaperCollection,
    compute_paper_collection_output_hash,
)
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryEvidence,
    PaperSummaryEvidenceLocator,
    PaperSummaryInputVersions,
    PaperSummaryProducerExecution,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
    compute_paper_summary_output_hash,
)
from app.schemas.paper_summary_api import PaperSummaryRead
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceMode,
    SourceSnapshotDetail,
)
from app.security import SecurityProblem
from app.config import settings
from services.paper_pipeline.demo_fixture import build_demo_collection


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
SUMMARY_VERSION_ID = "summary-version"
COLLECTION_VERSION_ID = "collection-version"
SUMMARY_ARTIFACT_ID = "summary-artifact"
PROJECT_ID = "project-1"
BASE_COLLECTION = build_demo_collection()
TEST_CANDIDATE = next(
    candidate
    for candidate in BASE_COLLECTION.candidates
    if candidate.selected and candidate.raw.synthetic_note is None
)


def _collection(
    source_mode: str = "fixture", *, execution_source_id: str | None = None
) -> PaperCollection:
    payload = BASE_COLLECTION.model_dump(mode="json", exclude_none=True)
    for execution in payload["source_executions"]:
        execution["source_id"] = execution_source_id or execution["source_id"]
        if source_mode == "cached":
            execution.update(
                {
                    "source_mode": "cached",
                    "data_level": "real_run_cache",
                    "cache_applicability": "same normalized query",
                    "live_failure_class": "timeout",
                    "live_failure_code": "CROSSREF_TIMEOUT",
                }
            )
    for snapshot in payload["source_snapshots"]:
        if source_mode == "cached":
            snapshot["cache_version"] = "cache-v1"
            snapshot["request_metadata"] = {
                **snapshot["request_metadata"],
                "origin_run_id": "origin-run",
                "origin_artifact_version_id": "origin-version",
            }
    output_hash = compute_paper_collection_output_hash(deepcopy(payload))
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    return PaperCollection.model_validate(payload)


def _input_versions(
    *, with_snapshot: bool, collection: PaperCollection
) -> PaperSummaryInputVersions:
    snapshot = collection.source_snapshots[0]
    snapshots = (
        (
            PaperSummarySourceSnapshotReference(
                source_snapshot_id=snapshot.snapshot_id,
                source_id=snapshot.source_id,
                source_version=(
                    snapshot.source_version_or_etag
                    or snapshot.cache_version
                    or snapshot.content_hash
                ),
                content_hash=snapshot.content_hash,
            ),
        )
        if with_snapshot
        else ()
    )
    return PaperSummaryInputVersions(
        paper_collection_version_id=COLLECTION_VERSION_ID,
        paper_collection_schema_version=collection.schema_version,
        paper_collection_output_hash=collection.output_hash,
        source_snapshots=snapshots,
    )


def _summary(
    *,
    with_evidence: bool = True,
    source_mode: str = "fixture",
    collection: PaperCollection | None = None,
) -> PaperSummaryArtifactContent:
    collection = collection or _collection(source_mode)
    input_versions = _input_versions(with_snapshot=with_evidence, collection=collection)
    source_snapshot = collection.source_snapshots[0]
    producer = PaperSummaryProducerExecution(
        execution_id="pipeline-execution",
        run_id=None,
        producer_name="xingwen.paper_summary",
        producer_version="1.0.0",
        model_name="fixture-model",
        prompt_name="paper_summary",
        prompt_version="v2",
        prompt_hash=HASH_A,
        parameters_version="1.0.0",
        parameters_hash=HASH_B,
        input_versions=input_versions,
        input_hash=HASH_C,
        model_response_hash=HASH_A,
        output_hash=HASH_A,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=1,
    )
    evidence = ()
    findings = ()
    if with_evidence:
        evidence = (
            PaperSummaryEvidence(
                evidence_id="pipeline-evidence",
                paper_id=TEST_CANDIDATE.canonical_paper_id,
                candidate_id=TEST_CANDIDATE.candidate_id,
                source_id=TEST_CANDIDATE.raw.source_id,
                source_record_id=TEST_CANDIDATE.raw.source_record_id,
                source_snapshot_id=source_snapshot.snapshot_id,
                source_snapshot_version=(
                    source_snapshot.source_version_or_etag
                    or source_snapshot.cache_version
                    or source_snapshot.content_hash
                ),
                source_snapshot_content_hash=source_snapshot.content_hash,
                locator=PaperSummaryEvidenceLocator(
                    kind="paper_metadata",
                    source_url=TEST_CANDIDATE.raw.url,
                    metadata_field="title",
                ),
                quote_or_value=TEST_CANDIDATE.title,
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            ),
        )
        findings = (
            PaperSummaryStatement(
                statement_id="finding-1",
                text=TEST_CANDIDATE.title,
                evidence_ids=("pipeline-evidence",),
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            ),
        )
    normalized = PaperSummaryArtifactContent.model_construct(
        kind="paper_summary",
        schema_version="1.0.0",
        summary_id="summary-1",
        paper_id=TEST_CANDIDATE.canonical_paper_id,
        benchmark=PaperBenchmarkReference.model_validate(
            collection.benchmark.model_dump(mode="json")
        ),
        input_versions=input_versions,
        research_goal=None,
        method=None,
        dataset=None,
        findings=findings,
        limitations=(),
        future_work=(),
        evidence_ids=tuple(item.evidence_id for item in evidence),
        evidence=evidence,
        source_conflicts=(),
        producer=producer,
        input_hash=HASH_C,
        output_hash=HASH_A,
    )
    payload = normalized.model_dump(mode="json")
    output_hash = compute_paper_summary_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    return PaperSummaryArtifactContent.model_validate(payload)


def _summary_with_two_evidence() -> PaperSummaryArtifactContent:
    summary = _summary()
    second_evidence = summary.evidence[0].model_copy(
        update={"evidence_id": "pipeline-evidence-2"}
    )
    second_finding = summary.findings[0].model_copy(
        update={
            "statement_id": "finding-2",
            "evidence_ids": (second_evidence.evidence_id,),
        }
    )
    payload = summary.model_dump(mode="json")
    payload["evidence"].append(second_evidence.model_dump(mode="json"))
    payload["evidence_ids"].append(second_evidence.evidence_id)
    payload["findings"].append(second_finding.model_dump(mode="json"))
    output_hash = compute_paper_summary_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    return PaperSummaryArtifactContent.model_validate(payload)


def _version(
    *,
    summary: PaperSummaryArtifactContent,
    kind: str = "paper_summary",
    tamper_hash: bool = False,
    source_mode: str = "fixture",
    collection: PaperCollection | None = None,
) -> ArtifactVersionDetail:
    collection = collection or _collection(source_mode)
    content = (
        summary.model_dump(mode="json")
        if kind == "paper_summary"
        else collection.model_dump(mode="json", exclude_none=True)
    )
    content_hash = compute_canonical_payload_hash(content)
    if tamper_hash:
        content_hash = HASH_A
    producer = ProducerReference(
        type="model" if kind == "paper_summary" else "algorithm",
        name=(
            "xingwen.paper_summary"
            if kind == "paper_summary"
            else collection.producer.producer_name
        ),
        version=(
            "1.0.0" if kind == "paper_summary" else collection.producer.producer_version
        ),
        model_name="fixture-model" if kind == "paper_summary" else None,
        prompt_name="paper_summary" if kind == "paper_summary" else None,
        prompt_version="v2" if kind == "paper_summary" else None,
        prompt_hash=HASH_A if kind == "paper_summary" else None,
        parameters_hash=(
            HASH_B if kind == "paper_summary" else collection.producer.parameters_hash
        ),
    )
    runtime_producer = ProducerExecutionDetail(
        id="producer-1",
        run_id="run-1",
        step_key=(
            "summarizing_papers" if kind == "paper_summary" else "searching_papers"
        ),
        step_attempt_id="attempt-1",
        producer=producer,
        parameters={},
        parameters_hash=(
            HASH_B if kind == "paper_summary" else collection.producer.parameters_hash
        ),
        input_hash=summary.input_hash
        if kind == "paper_summary"
        else collection.input_hash,
        output_hash=content_hash,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=1,
    )
    reference = (
        summary.input_versions.source_snapshots[0]
        if summary.input_versions.source_snapshots
        else None
    )
    pipeline_snapshot = (
        next(
            item
            for item in collection.source_snapshots
            if reference is not None
            and item.snapshot_id == reference.source_snapshot_id
        )
        if reference is not None
        else None
    )
    snapshots = (
        (
            SourceSnapshotDetail(
                id="snapshot-db",
                source_id=pipeline_snapshot.source_id,
                source_type=pipeline_snapshot.source_type,
                retrieved_at=pipeline_snapshot.retrieved_at,
                query=pipeline_snapshot.query,
                query_hash=pipeline_snapshot.query_hash,
                source_version_or_etag=reference.source_version,
                content_hash=pipeline_snapshot.content_hash,
                license_note=pipeline_snapshot.license_note,
                cache_version=pipeline_snapshot.cache_version,
                request_metadata=pipeline_snapshot.request_metadata,
            ),
        )
        if kind == "paper_summary" and pipeline_snapshot is not None
        else ()
    )
    evidence = (
        (
            EvidenceDetail(
                id="evidence-db",
                artifact_version_id=SUMMARY_VERSION_ID,
                target_type="paper_summary",
                target_id="finding-1",
                evidence_type="paper_metadata",
                source_snapshot_id="snapshot-db",
                paper_id=TEST_CANDIDATE.canonical_paper_id,
                locator={
                    "source_record_id": TEST_CANDIDATE.raw.source_record_id,
                    "summary_evidence_id": "pipeline-evidence",
                },
                quote_or_value=TEST_CANDIDATE.title,
                extraction_method="paper_summary",
                confidence=1.0,
                created_at=NOW,
            ),
        )
        if snapshots
        else ()
    )
    return ArtifactVersionDetail(
        id=SUMMARY_VERSION_ID if kind == "paper_summary" else COLLECTION_VERSION_ID,
        artifact_id=SUMMARY_ARTIFACT_ID
        if kind == "paper_summary"
        else "collection-artifact",
        project_id=PROJECT_ID,
        created_by_run_id="run-1",
        version_number=1,
        schema_version="1.0.0",
        content=content,
        content_hash=content_hash,
        input_hash=summary.input_hash
        if kind == "paper_summary"
        else collection.input_hash,
        source_mode=source_mode,
        producer=producer,
        source_snapshot_ids=tuple(item.id for item in snapshots),
        evidence_ids=tuple(item.id for item in evidence),
        supersedes_version_id=None,
        created_at=NOW,
        producer_execution=runtime_producer,
        source_snapshots=snapshots,
        evidence=evidence,
    )


class _Artifacts:
    def __init__(
        self,
        summary_version: ArtifactVersionDetail,
        *,
        collection: PaperCollection | None = None,
    ) -> None:
        self.summary_version = summary_version
        self.collection = collection or _collection(summary_version.source_mode.value)
        self.collection_version = _version(
            summary=_summary(with_evidence=False, collection=self.collection),
            kind="paper_collection",
            source_mode=summary_version.source_mode.value,
            collection=self.collection,
        )

    def get_version(self, *, version_id: str, session_id: str) -> ArtifactVersionDetail:
        if session_id != "owner":
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_VERSION_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        if version_id == SUMMARY_VERSION_ID:
            return self.summary_version
        if version_id == COLLECTION_VERSION_ID:
            return self.collection_version
        raise SecurityProblem(
            status=404,
            code="ARTIFACT_VERSION_NOT_FOUND",
            title="Resource not found",
            detail="Resource not found",
        )

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        if session_id != "owner":
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        if artifact_id == SUMMARY_ARTIFACT_ID:
            return ResearchArtifactDetail(
                id=SUMMARY_ARTIFACT_ID,
                project_id=PROJECT_ID,
                kind="paper_summary",
                title="Paper summary",
                logical_key="paper_summary.primary",
                created_at=NOW,
                latest_version_id=SUMMARY_VERSION_ID,
                versions=(),
            )
        if artifact_id == "collection-artifact":
            return ResearchArtifactDetail(
                id="collection-artifact",
                project_id=PROJECT_ID,
                kind="paper_collection",
                title="Paper collection",
                logical_key="paper_collection.primary",
                created_at=NOW,
                latest_version_id=COLLECTION_VERSION_ID,
                versions=(),
            )
        raise SecurityProblem(
            status=404,
            code="ARTIFACT_NOT_FOUND",
            title="Resource not found",
            detail="Resource not found",
        )


def _client(artifacts: _Artifacts) -> TestClient:
    app = create_app()
    app.state.artifact_read_service = artifacts  # type: ignore[assignment]
    owner, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(owner, id="owner"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    return client


def test_paper_summary_read_returns_typed_summary_and_provenance() -> None:
    summary = _summary()
    version = _version(summary=summary)
    assert version.content_hash != summary.output_hash
    assert version.producer_execution.output_hash == version.content_hash
    artifacts = _Artifacts(version)
    assert "kind" not in artifacts.collection_version.content
    client = _client(artifacts)
    response = client.get(f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary")

    assert response.status_code == 200
    data = response.json()["data"]
    assert (
        PaperSummaryRead.model_validate(data).summary.paper_id
        == TEST_CANDIDATE.canonical_paper_id
    )
    assert data["paper"] == {
        "paper_id": TEST_CANDIDATE.canonical_paper_id,
        "title": TEST_CANDIDATE.title,
        "authors": list(TEST_CANDIDATE.authors),
        "year": TEST_CANDIDATE.year,
    }
    assert data["version_number"] == 1
    assert data["supersedes_version_id"] is None
    assert data["cache_audits"] == []
    assert data["evidence"][0]["artifact_version_id"] == SUMMARY_VERSION_ID
    assert data["source_snapshots"][0]["id"] == "snapshot-db"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("version", "status", "code"),
    [
        (_version(summary=_summary(), kind="dataset"), 409, "ARTIFACT_KIND_MISMATCH"),
        (
            _version(summary=_summary(), tamper_hash=True),
            422,
            "PAPER_SUMMARY_SCHEMA_INVALID",
        ),
    ],
)
def test_paper_summary_invalid_content_uses_problem_details(
    version: ArtifactVersionDetail, status: int, code: str
) -> None:
    response = _client(_Artifacts(version)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
    assert response.json()["request_id"]


def test_paper_summary_requires_session_and_hides_other_projects() -> None:
    app = create_app()
    artifacts = _Artifacts(_version(summary=_summary()))
    app.state.artifact_read_service = artifacts  # type: ignore[assignment]
    assert (
        TestClient(app)
        .get(f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary")
        .status_code
        == 401
    )

    owner, _owner_credential, _ = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    app.state.session_service.store.put(replace(owner, id="owner"))
    other, other_credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(other, id="other"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, other_credential, path="/api")
    response = client.get(f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary")
    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_paper_summary_rejects_missing_persisted_evidence() -> None:
    summary = _summary()
    version = _version(summary=summary).model_copy(
        update={"evidence": (), "evidence_ids": ()}
    )
    response = _client(_Artifacts(version)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


def test_paper_summary_rejects_swapped_persisted_evidence_identity() -> None:
    summary = _summary()
    version = _version(summary=summary)
    evidence = version.evidence[0].model_copy(
        update={
            "locator": {
                **version.evidence[0].locator,
                "summary_evidence_id": "another-pipeline-evidence",
            }
        }
    )
    response = _client(
        _Artifacts(
            version.model_copy(
                update={"evidence": (evidence,), "evidence_ids": (evidence.id,)}
            )
        )
    ).get(f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary")

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


def test_paper_summary_exposes_complete_cached_source_audit() -> None:
    version = _version(summary=_summary(source_mode="cached"), source_mode="cached")
    response = _client(_Artifacts(version)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )

    assert response.status_code == 200
    assert response.json()["data"]["cache_audits"] == [
        {
            "source_id": "crossref",
            "source_snapshot_id": "snapshot-db",
            "cache_version": "cache-v1",
            "cache_applicability": "same normalized query",
            "live_failure_class": "timeout",
            "live_failure_code": "CROSSREF_TIMEOUT",
            "origin_run_id": "origin-run",
            "origin_artifact_version_id": "origin-version",
        }
    ]


def test_paper_summary_rejects_unreferenced_persisted_evidence() -> None:
    version = _version(summary=_summary())
    extra = version.evidence[0].model_copy(
        update={
            "id": "evidence-extra",
            "locator": {
                **version.evidence[0].locator,
                "summary_evidence_id": "pipeline-evidence-extra",
            },
        }
    )
    response = _client(
        _Artifacts(
            version.model_copy(
                update={
                    "evidence": (*version.evidence, extra),
                    "evidence_ids": (*version.evidence_ids, extra.id),
                }
            )
        )
    ).get(f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary")

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


def test_paper_summary_rejects_duplicate_persisted_evidence_ids() -> None:
    summary = _summary_with_two_evidence()
    version = _version(summary=summary)
    first = version.evidence[0]
    second = first.model_copy(
        update={
            "target_id": "finding-2",
            "locator": {
                **first.locator,
                "summary_evidence_id": "pipeline-evidence-2",
            },
        }
    )
    version = version.model_copy(
        update={
            "evidence": (first, second),
            "evidence_ids": (first.id,),
        }
    )

    response = _client(_Artifacts(version)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


def test_paper_summary_rejects_self_consistent_artifact_hash_over_stale_collection_hash() -> (
    None
):
    collection = _collection()
    version = _version(summary=_summary(collection=collection), collection=collection)
    artifacts = _Artifacts(version, collection=collection)
    content = dict(artifacts.collection_version.content)
    candidates = [dict(item) for item in content["candidates"]]
    candidates[0]["title"] = "Tampered title with stale collection output hash"
    content["candidates"] = candidates
    artifacts.collection_version = artifacts.collection_version.model_copy(
        update={
            "content": content,
            "content_hash": compute_canonical_payload_hash(content),
        }
    )

    response = _client(artifacts).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


@pytest.mark.parametrize(
    ("collection_mode", "version_mode"),
    [("fixture", SourceMode.cached), ("cached", SourceMode.fixture)],
)
def test_paper_summary_rejects_source_mode_without_matching_cache_audit(
    collection_mode: str, version_mode: SourceMode
) -> None:
    collection = _collection(collection_mode)
    summary = _summary(source_mode=collection_mode, collection=collection)
    version = _version(
        summary=summary,
        source_mode=collection_mode,
        collection=collection,
    ).model_copy(update={"source_mode": version_mode})

    response = _client(_Artifacts(version, collection=collection)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"


def test_paper_summary_rejects_cached_execution_attributed_to_another_source() -> None:
    collection = _collection("cached", execution_source_id="semantic-scholar")
    summary = _summary(source_mode="cached", collection=collection)
    version = _version(summary=summary, source_mode="cached", collection=collection)

    response = _client(_Artifacts(version, collection=collection)).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
