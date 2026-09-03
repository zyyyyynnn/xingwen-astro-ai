"""PostgreSQL and HTTP contract tests for generic artifact reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from db_bootstrap import reset_current_schema
from sqlalchemy import Engine

from app.config import settings
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
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
from artifact_publication_test_support import build_reference_dataset_candidate
from app.main import create_app
from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.services.artifacts import ArtifactReadService


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
NOW = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


@pytest.fixture(scope="module")
def read_context(postgres_engine: Engine) -> dict[str, object]:
    factory = session_factory(postgres_engine)
    app = create_app()
    app.state.artifact_read_service = ArtifactReadService(factory)
    owner, owner_credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    other, other_credential, _ = app.state.session_service.create(now=datetime.now(UTC))
    ids = {
        name: UUID(int=index)
        for index, name in enumerate(
            (
                "project",
                "contract",
                "run",
                "step",
                "attempt",
                "producer",
                "artifact_1",
                "version_1",
                "snapshot",
                "evidence",
                "artifact_2",
                "version_2",
                "artifact_3",
                "version_3",
            ),
            start=1,
        )
    }
    with factory() as session, session.begin():
        project = build_research_project(
            project_id=ids["project"],
            session_id=owner.id,
            name="Artifact boundary reads",
            case_key="exoplanet_host_star",
            created_at=NOW,
            updated_at=NOW,
        )
        draft = build_contract_draft(project, created_at=NOW, updated_at=NOW)
        contract = build_research_contract(
            project,
            draft,
            contract_id=ids["contract"],
            content_hash=HASH_A,
            created_at=NOW,
        )
        run = ResearchRunModel(
            id=ids["run"],
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            status="completed",
            progress=100,
            latest_event_sequence=1,
            revision=1,
            idempotency_key="artifact_read-run",
            request_hash=HASH_B,
            created_at=NOW,
            updated_at=NOW,
        )
        step = RunStepModel(
            id=ids["step"],
            run_id=run.id,
            position=0,
            key="planning",
            label="Planning",
            enter_status="planning",
            success_status="fetching_data",
            status="completed",
            progress=100,
            public_message="Completed",
            created_at=NOW,
        )
        attempt = StepAttemptModel(
            id=ids["attempt"],
            run_step_id=step.id,
            attempt_number=1,
            idempotency_key="attempt-1",
            status="completed",
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
            created_at=NOW,
        )
        producer = ProducerExecutionModel(
            id=ids["producer"],
            run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=attempt.id,
            step_key=step.key,
            idempotency_key="producer-1",
            lease_generation=1,
            producer_type="model",
            producer_name="fixture-producer",
            producer_version="1.0.0",
            model_provider="fixture",
            requested_model="fixture-model",
            prompt_name="summary",
            prompt_version="1.0.0",
            prompt_hash=HASH_A,
            parameters={"max_tokens": 128, "api_token": "must-not-leak"},
            parameters_hash=HASH_A,
            input_hash=HASH_B,
            output_hash=HASH_C,
            status="completed",
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
            token_usage={"input_tokens": 10, "output_tokens": 5},
            latency_ms=50,
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
        snapshot = SourceSnapshotModel(
            id=ids["snapshot"],
            project_id=project.id,
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=NOW,
            query={
                "keywords": ["exoplanet"],
                "authorization": "Bearer must-not-leak",
                "url": "https://example.test/search?q=star&api_key=must-not-leak",
                "notes": "bearer_token=embedded-query-secret",
            },
            query_hash=HASH_A,
            source_version_or_etag="authorization=must-not-leak",
            content_hash=HASH_B,
            license_note="Metadata license applies.",
            cache_version="1",
            request_metadata={
                "method": "GET",
                "cookie": "must-not-leak",
                "response_headers": {
                    "etag": "etag-1",
                    "set-cookie": "must-not-leak",
                },
            },
        )
        artifacts: list[ResearchArtifactModel] = []
        versions: list[ArtifactVersionModel] = []
        dataset_content = build_reference_dataset_candidate(run_id=run.id).content
        dataset = DatasetArtifactCandidate.model_validate(dataset_content)
        transformation_evidence_ids = tuple(
            UUID(int=100 + index)
            for index, _item in enumerate(dataset.transformation_evidence)
        )
        for index in range(1, 4):
            artifact = ResearchArtifactModel(
                id=ids[f"artifact_{index}"],
                project_id=project.id,
                kind="dataset",
                title=f"Artifact {index}",
                logical_key=f"dataset.{index}",
                created_at=NOW,
            )
            version = ArtifactVersionModel(
                id=ids[f"version_{index}"],
                artifact_id=artifact.id,
                project_id=project.id,
                created_by_run_id=run.id,
                run_step_id=step.id,
                step_attempt_id=attempt.id,
                producer_execution_id=producer.id,
                version_number=1,
                publication_key=f"publication-{index}",
                schema_version=str(dataset_content["schema_version"]),
                content=dataset_content,
                content_hash=HASH_C,
                input_hash=HASH_B,
                source_mode="live",
                producer={
                    "type": "model",
                    "name": "fixture-producer",
                    "version": "1.0.0",
                    "model_provider": "fixture",
                    "requested_model": "fixture-model",
                    "prompt_name": "summary",
                    "prompt_version": "1.0.0",
                    "prompt_hash": HASH_A,
                    "parameters_hash": HASH_A,
                },
                source_snapshot_ids=[str(snapshot.id)] if index == 1 else [],
                evidence_ids=(
                    [
                        str(ids["evidence"]),
                        *(str(item) for item in transformation_evidence_ids),
                    ]
                    if index == 1
                    else []
                ),
                created_at=NOW,
            )
            artifacts.append(artifact)
            versions.append(version)
        session.add(snapshot)
        session.add_all(artifacts)
        session.flush()
        session.add_all(versions)
        session.flush()
        evidence = EvidenceModel(
            id=ids["evidence"],
            project_id=project.id,
            artifact_version_id=ids["version_1"],
            target_type="dataset_cell",
            target_id="TOI-700-d:planet.toi_id",
            evidence_type="database_value",
            source_snapshot_id=snapshot.id,
            locator={
                "row_key": "TOI-700-d",
                "upstream_evidence_ids": [
                    f"upstream-{index}" for index in range(501)
                ],
                "cookie": "must-not-leak",
                "notes": "auth_header=embedded-locator-secret",
            },
            quote_or_value="TOI-700 d",
            extraction_method="direct_lookup",
            confidence=1.0,
            is_restricted=False,
            created_at=NOW,
        )
        transformation_evidence = tuple(
            EvidenceModel(
                id=persisted_id,
                project_id=project.id,
                artifact_version_id=ids["version_1"],
                target_type="canonical_field",
                target_id=item.canonical_field_id,
                evidence_type="data_transformation",
                source_snapshot_id=snapshot.id,
                locator=item.locator.model_dump(mode="json"),
                quote_or_value=(
                    item.canonical_value
                    if item.canonical_value is not None
                    else item.raw_value
                ),
                extraction_method="data_artifact_admission",
                confidence=1.0,
                is_restricted=False,
                created_at=NOW,
            )
            for persisted_id, item in zip(
                transformation_evidence_ids,
                dataset.transformation_evidence,
                strict=True,
            )
        )
        session.add_all((evidence, *transformation_evidence))
        session.flush()
        for artifact, version in zip(artifacts, versions, strict=True):
            artifact.latest_version_id = version.id

    def client(credential: str | None) -> TestClient:
        result = TestClient(app)
        if credential is not None:
            result.cookies.set(
                settings.SESSION_COOKIE_NAME,
                credential,
                path="/api",
            )
        return result

    return {
        "app": app,
        "factory": factory,
        "ids": ids,
        "owner_session_id": owner.id,
        "owner": client(owner_credential),
        "other": client(other_credential),
        "anonymous": client(None),
        "other_session": other,
    }


def test_http_reads_complete_provenance_and_redact_sensitive_fields(
    read_context: dict[str, object],
) -> None:
    ids = read_context["ids"]
    client = read_context["owner"]
    assert isinstance(ids, dict)
    assert isinstance(client, TestClient)
    response = client.get(f"/api/artifact-versions/{ids['version_1']}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_snapshot_ids"] == [str(ids["snapshot"])]
    assert data["evidence_ids"][0] == str(ids["evidence"])
    assert len(data["evidence_ids"]) > 1
    assert data["producer_execution"]["parameters"] == {"max_tokens": 128}
    assert data["content"]["kind"] == "dataset"
    assert data["presentation"]["kind"] == "dataset"
    snapshot = data["source_snapshots"][0]
    rendered = str(response.json()).casefold()
    assert "must-not-leak" not in rendered
    assert snapshot["request_metadata"] == {
        "method": "GET",
        "response_headers": {"etag": "etag-1"},
    }
    assert snapshot["source_version_or_etag"] == "[REDACTED]"
    assert snapshot["query"]["url"] == "https://example.test/search?q=star"
    assert snapshot["query"]["notes"] == "[REDACTED]"
    assert data["evidence"][0]["quote_or_value"] == "TOI-700 d"
    assert data["evidence"][0]["locator"]["notes"] == "[REDACTED]"
    assert "embedded-" not in rendered
    assert response.headers["cache-control"] == "no-store"

    evidence = client.get(f"/api/evidence/{ids['evidence']}")
    source = client.get(f"/api/source-snapshots/{ids['snapshot']}")
    artifact = client.get(f"/api/artifacts/{ids['artifact_1']}")
    assert evidence.status_code == source.status_code == artifact.status_code == 200
    assert evidence.json()["data"]["source_snapshot"]["id"] == str(ids["snapshot"])
    assert artifact.json()["data"]["versions"][0]["id"] == str(ids["version_1"])


def test_full_content_keeps_complete_evidence_locator(
    read_context: dict[str, object],
) -> None:
    ids = read_context["ids"]
    factory = read_context["factory"]
    owner_session_id = read_context["owner_session_id"]
    assert isinstance(ids, dict)
    assert callable(factory)
    assert isinstance(owner_session_id, str)

    service = ArtifactReadService(factory)
    bounded = service.get_version(
        version_id=str(ids["version_1"]),
        session_id=owner_session_id,
    )
    complete = service.get_version(
        version_id=str(ids["version_1"]),
        session_id=owner_session_id,
        full_content=True,
    )
    standalone = service.get_evidence(
        evidence_id=str(ids["evidence"]),
        session_id=owner_session_id,
    )

    assert len(bounded.evidence[0].locator["upstream_evidence_ids"]) == 500
    assert len(standalone.locator["upstream_evidence_ids"]) == 500
    assert len(complete.evidence[0].locator["upstream_evidence_ids"]) == 501


def test_cursor_is_stable_scoped_and_bounded(
    read_context: dict[str, object],
) -> None:
    ids = read_context["ids"]
    client = read_context["owner"]
    assert isinstance(ids, dict)
    assert isinstance(client, TestClient)
    path = f"/api/runs/{ids['run']}/artifacts"
    first = client.get(path, params={"limit": 2})
    assert first.status_code == 200
    payload = first.json()
    assert payload["page"]["has_more"] is True
    assert len(payload["data"]) == 2
    cursor = payload["page"]["next_cursor"]
    second = client.get(path, params={"limit": 2, "cursor": cursor})
    assert second.status_code == 200
    assert len(second.json()["data"]) == 1
    all_ids = [item["id"] for item in payload["data"] + second.json()["data"]]
    assert len(all_ids) == len(set(all_ids)) == 3
    assert all_ids == [
        str(ids["artifact_3"]),
        str(ids["artifact_2"]),
        str(ids["artifact_1"]),
    ]
    assert client.get(path, params={"kind": "graph"}).json()["data"] == []
    filtered = client.get(path, params={"kind": "dataset", "limit": 1}).json()
    filtered_cursor = filtered["page"]["next_cursor"]
    assert filtered_cursor is not None
    assert (
        client.get(
            path,
            params={"kind": "dataset", "limit": 1, "cursor": filtered_cursor},
        ).status_code
        == 200
    )
    assert client.get(path, params={"cursor": filtered_cursor}).status_code == 400
    assert client.get(path, params={"cursor": "not-a-cursor"}).status_code == 400
    assert client.get(path, params={"cursor": "%%%%"}).status_code == 400
    assert client.get(path, params={"limit": 101}).status_code == 422


def test_authentication_ownership_not_found_and_integrity_problem_details(
    read_context: dict[str, object],
) -> None:
    ids = read_context["ids"]
    owner = read_context["owner"]
    other = read_context["other"]
    anonymous = read_context["anonymous"]
    factory = read_context["factory"]
    assert isinstance(ids, dict)
    assert isinstance(owner, TestClient)
    assert isinstance(other, TestClient)
    assert isinstance(anonymous, TestClient)
    assert callable(factory)
    private_paths = (
        f"/api/runs/{ids['run']}/artifacts",
        f"/api/artifacts/{ids['artifact_1']}",
        f"/api/artifact-versions/{ids['version_1']}",
        f"/api/evidence/{ids['evidence']}",
        f"/api/source-snapshots/{ids['snapshot']}",
    )
    assert all(anonymous.get(path).status_code == 401 for path in private_paths)
    hidden_responses = tuple(other.get(path) for path in private_paths)
    missing = owner.get(f"/api/artifacts/{UUID(int=999)}")
    assert all(response.status_code == 404 for response in hidden_responses)
    assert missing.status_code == 404
    assert all(
        response.json()["detail"] == missing.json()["detail"] == "Resource not found"
        for response in hidden_responses
    )

    with factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, ids["version_1"])
        assert version is not None
        original_content = version.content
        version.content = {"kind": "dataset"}
    invalid_presentation = owner.get(f"/api/artifact-versions/{ids['version_1']}")
    assert invalid_presentation.status_code == 403
    assert invalid_presentation.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"

    with factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, ids["version_1"])
        assert version is not None
        version.content = original_content
        version.evidence_ids = [str(UUID(int=999))]
    denied = owner.get(f"/api/artifact-versions/{ids['version_1']}")
    assert denied.status_code == 403
    assert denied.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    assert "traceback" not in denied.text.casefold()
