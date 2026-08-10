"""Contract and defensive read tests for the PaperCollection API."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from app.main import create_app
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import PaperDataLevel, SourceMode, UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import (
    PaperCollection,
    PaperSourcePage,
    compute_paper_collection_output_hash,
)
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.security import SecurityProblem
from app.services.paper_collections import PaperCollectionReadService
from app.services.artifacts import ArtifactReadService
from app.workflow.publisher import ArtifactAdmissionContext, admit_artifact_candidate
from services.paper_pipeline.benchmark_runner import PaperCollectionBenchmarkRunner
from services.paper_pipeline.sources.base import (
    RawSourceRecord,
    SourceFailure,
    SourceSearchResult,
)


NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
HASH = "sha256:" + "a" * 64
VERSION_ID = "00000000-0000-0000-0000-000000000101"
ARTIFACT_ID = "00000000-0000-0000-0000-000000000102"
PROJECT_ID = "00000000-0000-0000-0000-000000000103"
RUN_ID = "a0000000-0000-0000-0000-000000000104"
SNAPSHOT_ID = "a0000000-0000-0000-0000-000000000105"
SNAPSHOT_RECORD_ID = "snapshot.crossref.paper_collection_api"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


class _FixtureAdapter:
    source_id = "crossref"
    adapter_name = "paper_collection_api_fixture"
    adapter_version = "1.0.0"

    def __init__(self, count: int = 3) -> None:
        self.count = count

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        records = tuple(
            RawSourceRecord(
                source_id="crossref",
                source_record_id=f"record-{index}",
                title=f"TESS host star study {index}",
                authors=("Ada Researcher",),
                year=2020,
                doi=f"10.1000/tess-{index}",
                arxiv_id=None,
                url=f"https://doi.org/10.1000/tess-{index}",
            )
            for index in range(self.count)
        )
        records_hash = compute_canonical_payload_hash(
            [record.hash_payload() for record in records]
        )
        snapshot = SourceSnapshotRecord(
            snapshot_id=SNAPSHOT_RECORD_ID,
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=NOW,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            content_hash=records_hash,
            license_note="Public metadata only.",
            request_metadata={"adapter_name": self.adapter_name},
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=query.pagination.page_size,
            returned_rows=len(records),
            total_results=len(records),
            attempt_count=1,
            status_code=200,
            retrieved_at=NOW,
            request_hash=compute_canonical_payload_hash({"query": query.query_hash}),
            response_hash=records_hash,
        )
        return SourceSearchResult(
            records=records, pages=(page,), snapshot=snapshot, retry_count=0
        )


def _collection(count: int = 3) -> PaperCollection:
    return PaperCollectionBenchmarkRunner(
        adapter=_FixtureAdapter(count), clock=lambda: NOW
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        page_size=20,
        selection_limit=2,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
        run_id=RUN_ID,
    )


class _FailureAdapter(_FixtureAdapter):
    def __init__(self, classification: UpstreamFailureClass) -> None:
        self.classification = classification

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        raise SourceFailure(
            self.classification, "CROSSREF_FAILED", retryable=True, attempt_count=2
        )


def _failed_collection(classification: UpstreamFailureClass) -> PaperCollection:
    return PaperCollectionBenchmarkRunner(
        adapter=_FailureAdapter(classification), clock=lambda: NOW
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
        run_id=RUN_ID,
    )


def _unsafe_collection() -> PaperCollection:
    payload = _collection().model_dump(mode="json", exclude_none=True)
    payload["candidates"][0]["title"] = "<script>alert(1)</script>"
    output_hash = compute_paper_collection_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    return PaperCollection.model_validate(payload)


def _accept(_: ArtifactAdmissionContext) -> None:
    return None


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


class _Artifacts:
    def __init__(self, collection: PaperCollection) -> None:
        self.collection = collection

    def get_version(self, *, version_id: str, session_id: str) -> ArtifactVersionDetail:
        if session_id != "owner" or version_id != VERSION_ID:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_VERSION_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        candidates = self.collection.candidates
        evidence = tuple(
            EvidenceDetail(
                id=f"evidence-{index}",
                artifact_version_id=VERSION_ID,
                target_type="paper_candidate",
                target_id=candidate.candidate_id,
                evidence_type="paper_metadata",
                source_snapshot_id=SNAPSHOT_ID,
                paper_id=candidate.canonical_paper_id,
                locator={"source_record_id": candidate.raw.source_record_id},
                quote_or_value=candidate.title,
                extraction_method="direct_lookup",
                confidence=1.0,
                created_at=NOW,
            )
            for index, candidate in enumerate(candidates)
        )
        source_snapshots = (
            (
                SourceSnapshotDetail(
                    id=SNAPSHOT_ID,
                    source_id="crossref",
                    source_type="paper_metadata",
                    retrieved_at=NOW,
                    query=self.collection.query.normalized_query_string,
                    query_hash=self.collection.query.query_hash,
                    content_hash=self.collection.source_snapshots[0].content_hash,
                    license_note="Public metadata only.",
                    request_metadata={"adapter_name": "paper_collection_api_fixture"},
                ),
            )
            if self.collection.source_snapshots
            else ()
        )
        return ArtifactVersionDetail(
            id=VERSION_ID,
            artifact_id=ARTIFACT_ID,
            project_id=PROJECT_ID,
            created_by_run_id=RUN_ID,
            version_number=1,
            schema_version="2.0.0",
            content=self.collection.model_dump(mode="json", exclude_none=True),
            content_hash=compute_canonical_payload_hash(
                self.collection.model_dump(mode="json", exclude_none=True)
            ),
            input_hash=self.collection.input_hash,
            source_mode="fixture",
            producer=ProducerReference(
                type="algorithm",
                name=self.collection.producer.producer_name,
                version=self.collection.producer.producer_version,
            ),
            source_snapshot_ids=tuple(item.id for item in source_snapshots),
            evidence_ids=tuple(item.id for item in evidence),
            created_at=NOW,
            producer_execution=ProducerExecutionDetail(
                id="producer-1",
                run_id=RUN_ID,
                step_key="searching_papers",
                step_attempt_id="attempt-1",
                producer=ProducerReference(
                    type="algorithm",
                    name=self.collection.producer.producer_name,
                    version=self.collection.producer.producer_version,
                ),
                parameters={},
                parameters_hash=self.collection.producer.parameters_hash,
                input_hash=self.collection.input_hash,
                output_hash=self.collection.output_hash,
                status="completed",
                started_at=NOW,
                finished_at=NOW,
            ),
            source_snapshots=source_snapshots,
            evidence=evidence,
        )

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        if session_id != "owner" or artifact_id != ARTIFACT_ID:
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_NOT_FOUND",
                title="Resource not found",
                detail="Resource not found",
            )
        return ResearchArtifactDetail(
            id=ARTIFACT_ID,
            project_id=PROJECT_ID,
            kind="paper_collection",
            title="Paper collection",
            logical_key="paper_collection.primary",
            created_at=NOW,
            latest_version_id=VERSION_ID,
            versions=(),
        )


@pytest.fixture()
def service() -> PaperCollectionReadService:
    return PaperCollectionReadService(_Artifacts(_collection()))  # type: ignore[arg-type]


def test_detail_exposes_reproducible_typed_collection(
    service: PaperCollectionReadService,
) -> None:
    detail = service.get_collection(version_id=VERSION_ID, session_id="owner")
    assert detail.collection.query.query_hash.startswith("sha256:")
    assert detail.collection.source_executions[0].source_id == "crossref"
    assert detail.collection.duplicate_groups
    assert all(
        item.selection_reason if item.selected else item.exclusion_reason
        for item in detail.collection.candidates
    )
    assert detail.content_hash == compute_canonical_payload_hash(
        detail.collection.model_dump(mode="json", exclude_none=True)
    )
    assert detail.content_hash != detail.collection.output_hash


def test_fixture_uses_atomic_publisher_content_hash_semantics() -> None:
    collection = _collection()
    admitted = admit_artifact_candidate(
        collection,
        schema_version=collection.schema_version,
        source_snapshot_ids=(SNAPSHOT_ID,),
        evidence_ids=("evidence-1",),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )
    version = _Artifacts(collection).get_version(
        version_id=VERSION_ID, session_id="owner"
    )
    assert version.content_hash == admitted.content_hash
    assert version.content_hash != collection.output_hash


def test_candidate_cursor_is_stable_scoped_and_resolves_provenance(
    service: PaperCollectionReadService,
) -> None:
    first, cursor, has_more = service.list_candidates(
        version_id=VERSION_ID, session_id="owner", cursor=None, limit=2
    )
    assert len(first) == 2 and has_more is True and cursor is not None
    second, final_cursor, final_has_more = service.list_candidates(
        version_id=VERSION_ID, session_id="owner", cursor=cursor, limit=2
    )
    assert len(second) == 1 and final_cursor is None and final_has_more is False
    combined = first + second
    assert len({item.candidate.candidate_id for item in combined}) == 3
    assert all(
        item.evidence and item.source_snapshot.id == SNAPSHOT_ID for item in combined
    )

    class _CrossVersion(_Artifacts):
        def get_version(self, **kwargs):  # type: ignore[no-untyped-def]
            return (
                super()
                .get_version(version_id=VERSION_ID, session_id="owner")
                .model_copy(update={"id": "another-version"})
            )

    with pytest.raises(SecurityProblem) as invalid:
        PaperCollectionReadService(_CrossVersion(_collection())).list_candidates(
            version_id=VERSION_ID, session_id="owner", cursor=cursor, limit=2
        )
    assert invalid.value.code == "INVALID_CURSOR"


def test_invalid_schema_unsafe_html_empty_and_source_failures_use_problem_details(
    service: PaperCollectionReadService,
) -> None:
    artifacts = service._artifacts  # noqa: SLF001 - deliberate corruption test seam
    assert isinstance(artifacts, _Artifacts)
    with pytest.raises(SecurityProblem) as invalid:
        PaperCollectionReadService(_Artifacts(_unsafe_collection())).get_collection(
            version_id=VERSION_ID, session_id="owner"
        )
    assert invalid.value.code == "PAPER_COLLECTION_SCHEMA_INVALID"

    with pytest.raises(SecurityProblem) as empty:
        PaperCollectionReadService(_Artifacts(_collection(0))).get_collection(
            version_id=VERSION_ID, session_id="owner"
        )
    assert (empty.value.status, empty.value.code) == (404, "PAPER_COLLECTION_EMPTY")

    with pytest.raises(SecurityProblem) as failed:
        PaperCollectionReadService(
            _Artifacts(_failed_collection(UpstreamFailureClass.timeout))
        ).get_collection(version_id=VERSION_ID, session_id="owner")
    assert (failed.value.status, failed.value.code) == (502, "PAPER_SOURCE_FAILED")

    with pytest.raises(SecurityProblem) as limited:
        PaperCollectionReadService(
            _Artifacts(_failed_collection(UpstreamFailureClass.rate_limited))
        ).get_collection(version_id=VERSION_ID, session_id="owner")
    assert (limited.value.status, limited.value.code) == (
        429,
        "PAPER_SOURCE_RATE_LIMITED",
    )


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "auth_header",
        "private-key",
        "bearerToken",
        "proxy authentication headers",
        "signing_keys",
    ],
)
def test_embedded_source_snapshot_rejects_credential_aliases(
    sensitive_key: str,
) -> None:
    payload = _collection().model_dump(mode="json", exclude_none=True)
    payload["source_snapshots"][0]["request_metadata"] = {
        sensitive_key: "must-not-leak"
    }
    with pytest.raises(
        ValidationError, match="request_metadata contains sensitive keys"
    ):
        PaperCollection.model_validate(payload)


def test_http_contract_authentication_envelopes_and_no_store() -> None:
    app = create_app()
    app.state.artifact_read_service = _Artifacts(_collection())
    owner, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    owner = replace(owner, id="owner")
    app.state.session_service.store.put(owner)
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    detail = client.get(f"/api/artifact-versions/{VERSION_ID}/paper-collection")
    page = client.get(
        f"/api/artifact-versions/{VERSION_ID}/paper-candidates", params={"limit": 2}
    )
    assert detail.status_code == page.status_code == 200
    assert (
        detail.headers["cache-control"] == page.headers["cache-control"] == "no-store"
    )
    assert detail.json()["data"]["collection"]["query"]["query_id"]
    assert page.json()["page"]["has_more"] is True
    assert (
        TestClient(app)
        .get(f"/api/artifact-versions/{VERSION_ID}/paper-collection")
        .status_code
        == 401
    )


def test_genuinely_expired_session_still_returns_401() -> None:
    """Regression: a session whose expiry is in the past must still 401.

    Guards against re-introducing a fixed-past ``NOW`` for the HTTP session:
    the authenticator reads real ``datetime.now(UTC)``, so a session created
    long enough ago that ``expires_at`` has passed must degrade to 401.
    """
    app = create_app()
    app.state.artifact_read_service = _Artifacts(_collection())
    ttl = app.state.session_service.ttl_seconds
    past = datetime.now(UTC) - timedelta(seconds=ttl + 1)
    owner, credential, _ = app.state.session_service.create(now=past)
    app.state.session_service.store.put(replace(owner, id="owner"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    response = client.get(f"/api/artifact-versions/{VERSION_ID}/paper-collection")
    assert response.status_code == 401
    assert response.json()["code"] == "SESSION_REQUIRED"


@pytest.mark.parametrize(
    ("collection", "status", "code"),
    [
        (_collection(0), 404, "PAPER_COLLECTION_EMPTY"),
        (
            _failed_collection(UpstreamFailureClass.timeout),
            502,
            "PAPER_SOURCE_FAILED",
        ),
        (
            _failed_collection(UpstreamFailureClass.rate_limited),
            429,
            "PAPER_SOURCE_RATE_LIMITED",
        ),
        (_unsafe_collection(), 422, "PAPER_COLLECTION_SCHEMA_INVALID"),
    ],
)
def test_http_failures_are_rfc9457_problem_details(
    collection: PaperCollection, status: int, code: str
) -> None:
    app = create_app()
    app.state.artifact_read_service = _Artifacts(collection)
    owner, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.session_service.store.put(replace(owner, id="owner"))
    client = TestClient(app)
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
    response = client.get(f"/api/artifact-versions/{VERSION_ID}/paper-collection")
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    problem = response.json()
    assert problem["code"] == code
    assert problem["request_id"]
    assert problem["detail"]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_postgres_published_collection_reads_with_ownership_and_redaction() -> None:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    collection = _collection()
    project_id = uuid4()
    contract_id = uuid4()
    run_id = UUID(RUN_ID)
    step_id = uuid4()
    attempt_id = uuid4()
    producer_id = uuid4()
    artifact_id = uuid4()
    version_id = uuid4()
    snapshot_id = uuid4()
    evidence_ids = tuple(uuid4() for _ in collection.candidates)
    admitted = admit_artifact_candidate(
        collection,
        schema_version=collection.schema_version,
        source_snapshot_ids=(str(snapshot_id),),
        evidence_ids=tuple(str(item) for item in evidence_ids),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )
    app = create_app()
    owner, credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    _, other_credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    app.state.artifact_read_service = ArtifactReadService(factory)
    try:
        with factory() as session, session.begin():
            _seed_published_collection(
                session,
                collection=collection,
                admitted_content=admitted.content,
                admitted_hash=admitted.content_hash,
                owner_id=owner.id,
                project_id=project_id,
                contract_id=contract_id,
                run_id=run_id,
                step_id=step_id,
                attempt_id=attempt_id,
                producer_id=producer_id,
                artifact_id=artifact_id,
                version_id=version_id,
                snapshot_id=snapshot_id,
                evidence_ids=evidence_ids,
            )

        with TestClient(app) as client:
            client.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
            detail = client.get(f"/api/artifact-versions/{version_id}/paper-collection")
            first = client.get(
                f"/api/artifact-versions/{version_id}/paper-candidates",
                params={"limit": 2},
            )
            assert detail.status_code == first.status_code == 200
            cursor = first.json()["page"]["next_cursor"]
            second = client.get(
                f"/api/artifact-versions/{version_id}/paper-candidates",
                params={"limit": 2, "cursor": cursor},
            )
            assert second.status_code == 200
            assert len(first.json()["data"] + second.json()["data"]) == 3
            rendered = (detail.text + first.text + second.text).casefold()
            assert "must-not-leak" not in rendered
            assert "authorization" not in rendered
            assert detail.json()["data"]["content_hash"] == admitted.content_hash

        with TestClient(app) as other:
            other.cookies.set(
                settings.SESSION_COOKIE_NAME, other_credential, path="/api"
            )
            hidden = other.get(f"/api/artifact-versions/{version_id}/paper-collection")
            assert hidden.status_code == 404
            assert hidden.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def _seed_published_collection(
    session: Session,
    *,
    collection: PaperCollection,
    admitted_content: dict[str, object],
    admitted_hash: str,
    owner_id: str,
    project_id,
    contract_id,
    run_id,
    step_id,
    attempt_id,
    producer_id,
    artifact_id,
    version_id,
    snapshot_id,
    evidence_ids,
) -> None:
    project = build_research_project(
        project_id=project_id,
        session_id=owner_id,
        name="PaperCollection API PostgreSQL read",
        case_key="exoplanet_host_star",
        created_at=NOW,
        updated_at=NOW,
    )
    draft = build_contract_draft(project, created_at=NOW, updated_at=NOW)
    contract = build_research_contract(
        project,
        draft,
        contract_id=contract_id,
        content_hash=HASH,
        created_at=NOW,
    )
    run = ResearchRunModel(
        id=run_id,
        project_id=project_id,
        contract_id=contract_id,
        execution_mode="demo_replay",
        status="completed",
        progress=100,
        latest_event_sequence=1,
        revision=1,
        idempotency_key="paper_collection_api-postgres-run",
        request_hash=collection.input_hash,
        created_at=NOW,
        updated_at=NOW,
    )
    step = RunStepModel(
        id=step_id,
        run_id=run_id,
        position=0,
        key="searching_papers",
        label="Searching papers",
        enter_status="searching_papers",
        success_status="summarizing_papers",
        status="completed",
        progress=100,
        public_message="Completed",
        created_at=NOW,
    )
    attempt = StepAttemptModel(
        id=attempt_id,
        run_step_id=step_id,
        attempt_number=1,
        idempotency_key="paper_collection_api-attempt",
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        created_at=NOW,
    )
    producer = ProducerExecutionModel(
        id=producer_id,
        run_id=run_id,
        run_step_id=step_id,
        step_attempt_id=attempt_id,
        step_key="searching_papers",
        idempotency_key="paper_collection_api-producer",
        lease_generation=1,
        producer_type="algorithm",
        producer_name=collection.producer.producer_name,
        producer_version=collection.producer.producer_version,
        parameters={},
        parameters_hash=collection.producer.parameters_hash,
        input_hash=collection.input_hash,
        output_hash=collection.output_hash,
        status="completed",
        started_at=NOW,
        finished_at=NOW,
        latency_ms=0,
        created_at=NOW,
    )
    artifact = ResearchArtifactModel(
        id=artifact_id,
        project_id=project_id,
        kind="paper_collection",
        title="Paper collection",
        logical_key="paper_collection.primary",
        created_at=NOW,
    )
    snapshot = SourceSnapshotModel(
        id=snapshot_id,
        project_id=project_id,
        source_id="crossref",
        source_type="paper_metadata",
        retrieved_at=NOW,
        query={"normalized": collection.query.normalized_query_string},
        query_hash=collection.query.query_hash,
        content_hash=collection.source_snapshots[0].content_hash,
        license_note="Public metadata only.",
        request_metadata={
            "method": "GET",
            "authorization": "Bearer must-not-leak",
        },
    )
    version = ArtifactVersionModel(
        id=version_id,
        artifact_id=artifact_id,
        project_id=project_id,
        created_by_run_id=run_id,
        run_step_id=step_id,
        step_attempt_id=attempt_id,
        producer_execution_id=producer_id,
        version_number=1,
        publication_key="paper_collection_api-paper-collection",
        schema_version=collection.schema_version,
        content=admitted_content,
        content_hash=admitted_hash,
        input_hash=collection.input_hash,
        source_mode="fixture",
        producer={
            "type": "algorithm",
            "name": collection.producer.producer_name,
            "version": collection.producer.producer_version,
            "parameters_hash": collection.producer.parameters_hash,
        },
        source_snapshot_ids=[str(snapshot_id)],
        evidence_ids=[str(item) for item in evidence_ids],
        created_at=NOW,
    )
    persist_authoring_models(
        session, project=project, draft=draft, contract=contract
    )
    session.flush()
    session.add(run)
    session.flush()
    session.add(step)
    session.flush()
    session.add(attempt)
    session.flush()
    session.add(producer)
    session.flush()
    session.add(snapshot)
    session.add(artifact)
    session.flush()
    session.add(version)
    session.flush()
    for index, (candidate, evidence_id) in enumerate(
        zip(collection.candidates, evidence_ids, strict=True)
    ):
        session.add(
            EvidenceModel(
                id=evidence_id,
                project_id=project_id,
                artifact_version_id=version_id,
                target_type="paper_candidate",
                target_id=candidate.candidate_id,
                evidence_type="paper_metadata",
                source_snapshot_id=snapshot_id,
                paper_id=candidate.canonical_paper_id,
                locator={"source_record_id": candidate.raw.source_record_id},
                quote_or_value=("must-not-leak" if index == 0 else candidate.title),
                extraction_method="direct_lookup",
                confidence=1.0,
                is_restricted=index == 0,
                created_at=NOW,
            )
        )
    session.flush()
    artifact.latest_version_id = version_id
