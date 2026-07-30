from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
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
from app.schemas.paper_collection import PaperBenchmarkReference
from app.schemas.paper_summary_api import PaperSummaryRead
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.security import SecurityProblem
from app.services.paper_summaries import PaperSummaryReadService
from app.config import settings


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
SUMMARY_VERSION_ID = "summary-version"
COLLECTION_VERSION_ID = "collection-version"
SUMMARY_ARTIFACT_ID = "summary-artifact"
PROJECT_ID = "project-1"


def _input_versions(*, with_snapshot: bool) -> PaperSummaryInputVersions:
    snapshots = (
        (
            PaperSummarySourceSnapshotReference(
                source_snapshot_id="pipeline-snapshot",
                source_id="crossref",
                source_version="crossref-v1",
                content_hash=HASH_A,
            ),
        )
        if with_snapshot
        else ()
    )
    return PaperSummaryInputVersions(
        paper_collection_version_id=COLLECTION_VERSION_ID,
        paper_collection_schema_version="1.0.0",
        paper_collection_output_hash=HASH_B,
        source_snapshots=snapshots,
    )


def _summary(*, with_evidence: bool = True) -> PaperSummaryArtifactContent:
    input_versions = _input_versions(with_snapshot=with_evidence)
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
                paper_id="paper-1",
                candidate_id="candidate-1",
                source_id="crossref",
                source_record_id="record-1",
                source_snapshot_id="pipeline-snapshot",
                source_snapshot_version="crossref-v1",
                source_snapshot_content_hash=HASH_A,
                locator=PaperSummaryEvidenceLocator(
                    kind="paper_metadata",
                    source_url="https://example.org/paper",
                    metadata_field="title",
                ),
                quote_or_value="A validated paper",
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            ),
        )
        findings = (
            PaperSummaryStatement(
                statement_id="finding-1",
                text="A validated paper",
                evidence_ids=("pipeline-evidence",),
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            ),
        )
    normalized = PaperSummaryArtifactContent.model_construct(
        kind="paper_summary",
        schema_version="1.0.0",
        summary_id="summary-1",
        paper_id="paper-1",
        benchmark=PaperBenchmarkReference(
            benchmark_id="exoplanet_host_star.paper_reasoning",
            schema_version="1.3.0",
            benchmark_version="1.3.0",
            scientific_payload_hash=HASH_A,
            content_hash=HASH_B,
            scenario_id="search.tess_mission_and_catalogs",
            x00_main_sha="eb7e23f6d0c14555627c602c6e5a2b84210ba833",
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


def _version(
    *,
    summary: PaperSummaryArtifactContent,
    kind: str = "paper_summary",
    tamper_hash: bool = False,
) -> ArtifactVersionDetail:
    content = (
        summary.model_dump(mode="json")
        if kind == "paper_summary"
        else {
            "schema_version": summary.input_versions.paper_collection_schema_version,
            "output_hash": summary.input_versions.paper_collection_output_hash,
        }
    )
    content_hash = compute_canonical_payload_hash(content)
    if tamper_hash:
        content_hash = HASH_A
    producer = ProducerReference(
        type="model",
        name="xingwen.paper_summary" if kind == "paper_summary" else "fixture",
        version="1.0.0",
        model_name="fixture-model" if kind == "paper_summary" else None,
        prompt_name="paper_summary" if kind == "paper_summary" else None,
        prompt_version="v2" if kind == "paper_summary" else None,
        prompt_hash=HASH_A if kind == "paper_summary" else None,
        parameters_hash=HASH_B if kind == "paper_summary" else None,
    )
    runtime_producer = ProducerExecutionDetail(
        id="producer-1",
        run_id="run-1",
        step_key="summarizing_papers" if kind == "paper_summary" else "planning",
        step_attempt_id="attempt-1",
        producer=producer,
        parameters={},
        parameters_hash=HASH_B,
        input_hash=HASH_C,
        output_hash=content_hash,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=1,
    )
    snapshots = (
        (
            SourceSnapshotDetail(
                id="snapshot-db",
                source_id="crossref",
                source_type="paper_metadata",
                retrieved_at=NOW,
                query="query",
                query_hash=HASH_A,
                source_version_or_etag="crossref-v1",
                content_hash=HASH_A,
                license_note="Public metadata",
                request_metadata={},
            ),
        )
        if kind == "paper_summary" and summary.input_versions.source_snapshots
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
                paper_id="paper-1",
                locator={"source_record_id": "record-1"},
                quote_or_value="A validated paper",
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
        input_hash=HASH_C,
        source_mode="fixture",
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
    def __init__(self, summary_version: ArtifactVersionDetail) -> None:
        self.summary_version = summary_version
        self.collection_version = _version(
            summary=_summary(with_evidence=False), kind="paper_collection"
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
    assert PaperSummaryRead.model_validate(data).summary.paper_id == "paper-1"
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
