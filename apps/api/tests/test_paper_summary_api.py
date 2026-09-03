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
    ArtifactKind,
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    PublicArtifactPresentation,
    ResearchArtifactDetail,
    SourceMode,
    SourceSnapshotDetail,
)
from app.services.public_presentation import build_artifact_presentation
from app.security import SecurityProblem
from app.services.paper_candidate_inputs import (
    AcceptedPaperInput,
    PaperCandidateInputReadService,
)
from app.services.research_input_store import ResearchInputRecord
from app.config import settings
from services.paper_pipeline.demo_fixture import build_demo_collection


NOW = datetime(2026, 7, 29, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
SUMMARY_VERSION_ID = "summary-version"
COLLECTION_VERSION_ID = "11111111-1111-4111-8111-111111111111"
SUMMARY_ARTIFACT_ID = "summary-artifact"
PROJECT_ID = "project-1"
BASE_COLLECTION = build_demo_collection()
TEST_CANDIDATE = next(
    candidate
    for candidate in BASE_COLLECTION.candidates
    if candidate.selected and candidate.raw.synthetic_note is None
)


def _collection(source_mode: str = "fixture") -> PaperCollection:
    payload = BASE_COLLECTION.model_dump(mode="json", exclude_none=True)
    if source_mode == "cached":
        for execution in payload["source_executions"]:
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
            snapshot["cache_version"] = "cache-fixture"
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
        prompt_version="3.0.0",
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
    experiments = ()
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
        experiments = (
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
        schema_version="2.0.0",
        summary_id="summary-1",
        paper_id=TEST_CANDIDATE.canonical_paper_id,
        benchmark=PaperBenchmarkReference.model_validate(
            collection.benchmark.model_dump(mode="json")
        ),
        input_versions=input_versions,
        background=(),
        methodology=(),
        dataset=(),
        experiments=experiments,
        discussion=(),
        limitations=(),
        research_questions=(),
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
    second_finding = summary.experiments[0].model_copy(
        update={
            "statement_id": "finding-2",
            "evidence_ids": (second_evidence.evidence_id,),
        }
    )
    payload = summary.model_dump(mode="json")
    payload["evidence"].append(second_evidence.model_dump(mode="json"))
    payload["evidence_ids"].append(second_evidence.evidence_id)
    payload["experiments"].append(second_finding.model_dump(mode="json"))
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
        requested_model="fixture-model" if kind == "paper_summary" else None,
        prompt_name="paper_summary" if kind == "paper_summary" else None,
        prompt_version="3.0.0" if kind == "paper_summary" else None,
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
    evidence_by_id = {item.evidence_id: item for item in summary.evidence}
    target_by_evidence_id: dict[str, str] = {}
    for statement in summary.statements():
        for evidence_id in statement.evidence_ids:
            target_by_evidence_id.setdefault(evidence_id, statement.statement_id)
    evidence = (
        tuple(
            EvidenceDetail(
                id="evidence-db" if index == 1 else f"evidence-db-{index}",
                artifact_version_id=SUMMARY_VERSION_ID,
                target_type="paper_summary",
                target_id=target_by_evidence_id[evidence_id],
                evidence_type=item.locator.kind,
                source_snapshot_id="snapshot-db",
                paper_id=item.paper_id,
                locator={
                    "source_record_id": item.source_record_id,
                    "summary_evidence_id": item.evidence_id,
                },
                quote_or_value=item.quote_or_value,
                extraction_method="paper_summary",
                confidence=1.0,
                created_at=NOW,
            )
            for index, (evidence_id, item) in enumerate(
                (
                    (evidence_id, evidence_by_id[evidence_id])
                    for evidence_id in summary.evidence_ids
                ),
                start=1,
            )
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
        schema_version=(
            collection.schema_version if kind == "paper_collection" else "2.0.0"
        ),
        content=content,
        presentation=(
            build_artifact_presentation(ArtifactKind(kind), content, evidence)
            if kind in {"paper_summary", "paper_collection"}
            else PublicArtifactPresentation(kind=ArtifactKind(kind))
        ),
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

    def get_version(
        self, *, version_id: str, session_id: str, full_content: bool = False
    ) -> ArtifactVersionDetail:
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
    assert artifacts.collection_version.content["kind"] == "paper_collection"
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
            "cache_version": "cache-fixture",
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
    collection = _collection("cached")
    summary = _summary(source_mode="cached", collection=collection)
    version = _version(summary=summary, source_mode="cached", collection=collection)
    artifacts = _Artifacts(version, collection=collection)
    content = dict(artifacts.collection_version.content)
    executions = [dict(item) for item in content["source_executions"]]
    executions[0]["source_id"] = "semantic-scholar"
    content["source_executions"] = executions
    output_hash = compute_paper_collection_output_hash(deepcopy(content))
    content["output_hash"] = output_hash
    content["producer"]["output_hash"] = output_hash
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


class _FakePaperInputReader:
    """Stands in for the authorized PaperCandidate input bridge read seam."""

    def __init__(self, record: ResearchInputRecord | None) -> None:
        self.record = record
        self.calls: list[dict[str, str]] = []

    def accepted_research_input(self, **kwargs: str) -> ResearchInputRecord | None:
        self.calls.append(kwargs)
        return self.record


def _pdf_input_record():
    from app.schemas.research_input import ResearchInputStatus, ResearchInputType
    from app.services.research_input_store import ResearchInputRecord

    return ResearchInputRecord(
        id="input-pdf-1",
        session_id="owner",
        project_id=PROJECT_ID,
        type=ResearchInputType.pdf,
        source_type="url_fetch",
        content_hash=HASH_A,
        storage_ref="local:input-pdf-1",
        filename="paper.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        status=ResearchInputStatus.accepted,
        source_snapshot_id=None,
        url=None,
        created_at=NOW,
        expires_at=None,
    )


def test_paper_summary_pdf_source_returns_authorized_research_input() -> None:
    client = _client(_Artifacts(_version(summary=_summary())))
    service = _FakePaperInputReader(_pdf_input_record())
    client.app.state.paper_candidate_input_reader = service

    response = client.get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["research_input"]["id"] == "input-pdf-1"
    assert data["research_input"]["type"] == "pdf"
    assert data["research_input"]["content_hash"] == HASH_A
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == [
        {
            "session_id": "owner",
            "project_id": PROJECT_ID,
            "paper_collection_version_id": COLLECTION_VERSION_ID,
            "canonical_paper_id": TEST_CANDIDATE.canonical_paper_id,
        }
    ]


class _AcceptedInputRepository:
    def accepted_input_for_paper(self, **_kwargs: str) -> AcceptedPaperInput:
        return AcceptedPaperInput(
            research_input_id="input-document-1",
            research_input_content_hash=HASH_A,
        )


class _BoundResearchInputs:
    def __init__(self, record: ResearchInputRecord) -> None:
        self._record = record

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        assert session_id == "owner"
        assert input_id == "input-document-1"
        return self._record


@pytest.mark.parametrize(
    ("input_type", "mime_type", "supported"),
    (
        ("pdf", "text/plain", False),
        ("image", "image/gif", False),
        ("text", "application/pdf", False),
        ("url", "application/pdf", True),
        ("url", "image/png", True),
        ("url", "text/html", False),
    ),
)
def test_paper_candidate_reader_requires_supported_document_content(
    input_type: str, mime_type: str, supported: bool
) -> None:
    from app.schemas.research_input import ResearchInputStatus, ResearchInputType
    from app.services.research_input_store import ResearchInputRecord

    record = ResearchInputRecord(
        id="input-document-1",
        session_id="owner",
        project_id=PROJECT_ID,
        type=ResearchInputType(input_type),
        source_type="url_fetch" if input_type == "url" else "upload",
        content_hash=HASH_A,
        storage_ref="local:input-document-1",
        filename="paper.bin",
        mime_type=mime_type,
        size_bytes=1024,
        status=ResearchInputStatus.accepted,
        source_snapshot_id=None,
        url=None,
        created_at=NOW,
        expires_at=None,
    )
    reader = PaperCandidateInputReadService(
        research_inputs=_BoundResearchInputs(record),
        repository=_AcceptedInputRepository(),
    )

    resolved = reader.accepted_research_input(
        session_id="owner",
        project_id=PROJECT_ID,
        paper_collection_version_id=COLLECTION_VERSION_ID,
        canonical_paper_id=TEST_CANDIDATE.canonical_paper_id,
    )

    assert resolved == (record if supported else None)


def test_paper_summary_hash_uses_current_document_parse_family() -> None:
    summary = _summary()
    current = summary.model_dump(mode="json")
    without_document_family = deepcopy(current)
    without_document_family["input_versions"].pop("document_parses")
    without_document_family["producer"]["input_versions"].pop("document_parses")

    assert compute_paper_summary_output_hash(
        current
    ) != compute_paper_summary_output_hash(without_document_family)


def test_paper_summary_document_source_rejects_collection_provenance_drift() -> None:
    version = _version(summary=_summary()).model_copy(update={"evidence": ()})
    client = _client(_Artifacts(version))
    service = _FakePaperInputReader(_pdf_input_record())
    client.app.state.paper_candidate_input_reader = service

    response = client.get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    assert service.calls == []


def test_paper_summary_pdf_source_is_null_without_authorized_binding() -> None:
    client = _client(_Artifacts(_version(summary=_summary())))
    client.app.state.paper_candidate_input_reader = _FakePaperInputReader(None)

    response = client.get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"research_input": None}


def test_paper_summary_pdf_source_is_null_when_bridge_is_unconfigured() -> None:
    client = _client(_Artifacts(_version(summary=_summary())))
    assert client.app.state.paper_candidate_input_reader is None

    response = client.get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"research_input": None}


def test_paper_summary_pdf_source_rejects_kind_mismatch_and_foreign_session() -> None:
    response = _client(_Artifacts(_version(summary=_summary(), kind="dataset"))).get(
        f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ARTIFACT_KIND_MISMATCH"

    app = create_app()
    app.state.artifact_read_service = _Artifacts(_version(summary=_summary()))  # type: ignore[assignment]
    assert (
        TestClient(app)
        .get(
            f"/api/artifact-versions/{SUMMARY_VERSION_ID}/paper-summary/document-source"
        )
        .status_code
        == 401
    )
