"""Real FastAPI + PostgreSQL integration for the B-runtime research chain (#121).

Set ``TEST_DATABASE_URL`` to an isolated database whose name contains ``test``.
The suite skips when PostgreSQL is unavailable rather than substituting SQLite,
because the models and the workflow store use PostgreSQL-specific types and row
locks. It drives the *real* mounted runtime (no MSW) across:

    Session -> Project -> ContractDraft -> Contract -> Run -> RunEvent
    -> WorkspaceSnapshot

and asserts 401/403/404, ownership hiding, idempotency and revision conflicts.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from pydantic import BaseModel
from sqlalchemy import Engine

from app.config import settings
from app.db.models import (
    EvidenceModel,
    ResearchArtifactModel,
    ResearchContractDraftModel,
    ResearchProjectModel,
    SourceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.main import _load_case_manifests, create_app
from app.services.artifacts import ArtifactReadService
from app.services.research import ResearchApplicationService
from app.services.resource_authority import PersistentResourceAuthority
from app.services.snapshots import InMemorySnapshotStore, SnapshotService
from app.workflow.store import PersistentWorkflowStore
from app.workflow.publisher import (
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    admit_artifact_candidate,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


class _FixtureDatasetCandidate(BaseModel):
    kind: Literal["dataset"] = "dataset"
    field_ids: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _accept(_context: object) -> None:
    return None


def _contract_input() -> dict[str, object]:
    return {
        "research_goal": "Integrate exoplanet candidates and host-star parameters",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
        "output_requirements": ["dataset", "field_dictionary", "graph"],
        "evidence_requirements": {"require_locator": True},
        "quality_constraints": {"source_completeness_min": 1.0},
    }


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture()
def runtime() -> Iterator[dict[str, object]]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine: Engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)

    app = create_app()
    store = PersistentWorkflowStore(factory)
    app.state.workflow_store = store
    app.state.artifact_read_service = ArtifactReadService(factory)
    app.state.research_service = ResearchApplicationService(
        factory=factory, workflow_store=store, manifests=_load_case_manifests()
    )
    app.state.snapshot_service = SnapshotService(
        InMemorySnapshotStore(PersistentResourceAuthority(factory))
    )

    owner, owner_credential, owner_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    other, other_credential, other_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )

    project_id = uuid4()
    draft_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchProjectModel(
                id=project_id,
                session_id=owner.id,
                name="B-runtime research chain",
                case_key="exoplanet_host_star",
                revision=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            ResearchContractDraftModel(
                id=draft_id,
                session_id=owner.id,
                version=1,
                intent="Integrate exoplanet candidates and host-star parameters",
                status="draft",
                contract=_contract_input(),
                warnings=[],
                created_at=NOW,
                updated_at=NOW,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, owner_credential)
    try:
        yield {
            "client": client,
            "factory": factory,
            "workflow_store": store,
            "owner_session_id": owner.id,
            "owner_csrf": owner_csrf,
            "other_credential": other_credential,
            "project_id": str(project_id),
            "draft_id": str(draft_id),
        }
    finally:
        engine.dispose()
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def test_full_research_chain_over_real_runtime(runtime: dict[str, object]) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    draft_id = runtime["draft_id"]

    project = client.get(f"/api/v2/projects/{project_id}")
    assert project.status_code == 200
    assert project.json()["data"]["case_key"] == "exoplanet_host_star"
    assert "session_id" in project.json()["data"]  # owner reads its own project

    draft = client.get(f"/api/v2/research-contract-drafts/{draft_id}")
    assert draft.status_code == 200
    assert draft.json()["data"]["status"] == "draft"

    patched = client.patch(
        f"/api/v2/research-contract-drafts/{draft_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "Refined integration intent"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["version"] == 2

    stale = client.patch(
        f"/api/v2/research-contract-drafts/{draft_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "conflicting"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    confirmed = client.post(
        f"/api/v2/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": draft_id, "expected_draft_version": 2},
    )
    assert confirmed.status_code == 201
    contract_id = confirmed.json()["data"]["id"]
    assert confirmed.json()["data"]["content_hash"].startswith("sha256:")

    confirm_replay = client.post(
        f"/api/v2/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": draft_id, "expected_draft_version": 2},
    )
    assert confirm_replay.status_code == 201
    assert confirm_replay.json()["data"]["id"] == contract_id

    conflicting_draft_id = uuid4()
    factory = runtime["factory"]
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ResearchContractDraftModel(
                id=conflicting_draft_id,
                session_id=runtime["owner_session_id"],
                version=1,
                intent="Different confirmation request",
                status="draft",
                contract=_contract_input(),
                warnings=[],
                created_at=NOW,
                updated_at=NOW,
                expires_at=datetime(2026, 7, 23, tzinfo=UTC),
            )
        )
    idempotency_conflict = client.post(
        f"/api/v2/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": str(conflicting_draft_id), "expected_draft_version": 1},
    )
    assert idempotency_conflict.status_code == 409
    assert idempotency_conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    contract = client.get(f"/api/v2/research-contracts/{contract_id}")
    assert contract.status_code == 200
    # Full frozen content is recovered, not only the hash.
    assert contract.json()["data"]["requested_fields"] == [
        "planet.toi_id",
        "star.tic_id",
    ]

    created = client.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
            "derivation_kind": "original",
        },
    )
    assert created.status_code == 201
    run_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "queued"

    project_after_run = client.get(f"/api/v2/projects/{project_id}")
    assert project_after_run.json()["data"]["active_contract_id"] == contract_id
    assert project_after_run.json()["data"]["latest_run_id"] == run_id

    replay = client.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
            "derivation_kind": "original",
        },
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == run_id  # idempotent replay

    conflict = client.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
            "derivation_kind": "original",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    run = client.get(f"/api/v2/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["data"]["latest_event_sequence"] >= 1

    events = client.get(f"/api/v2/runs/{run_id}/events")
    assert events.status_code == 200
    sequences = [event["sequence"] for event in events.json()["data"]]
    assert sequences == sorted(sequences)
    assert events.json()["data"][0]["event_type"] == "run.queued"

    saved = client.put(
        f"/api/v2/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "comparative", "active_run_id": run_id},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 1
    reloaded = client.get(f"/api/v2/projects/{project_id}/workspace-snapshot")
    assert reloaded.json()["data"] == saved.json()["data"]

    non_raising = TestClient(
        client.app, base_url="https://testserver", raise_server_exceptions=False
    )
    non_raising.cookies.update(client.cookies)
    missing_parent = non_raising.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "derived-missing-parent"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
            "derivation_kind": "retry",
            "parent_run_id": str(uuid4()),
        },
    )
    assert missing_parent.status_code == 404
    assert missing_parent.json()["code"] == "RUN_NOT_FOUND"


def test_expired_draft_is_visible_but_cannot_be_changed_or_confirmed(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    expired_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ResearchContractDraftModel(
                id=expired_id,
                session_id=runtime["owner_session_id"],
                version=1,
                intent="Expired contract draft",
                status="draft",
                contract=_contract_input(),
                warnings=[],
                created_at=NOW - timedelta(days=2),
                updated_at=NOW - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )

    fetched = client.get(f"/api/v2/research-contract-drafts/{expired_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "expired"

    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    patched = client.patch(
        f"/api/v2/research-contract-drafts/{expired_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "too late"},
    )
    assert patched.status_code == 409
    assert patched.json()["code"] == "DRAFT_NOT_EDITABLE"

    confirmed = client.post(
        f"/api/v2/projects/{runtime['project_id']}/contracts",
        headers={**csrf, "Idempotency-Key": "expired-confirm"},
        json={"draft_id": str(expired_id), "expected_draft_version": 1},
    )
    assert confirmed.status_code == 409
    assert confirmed.json()["code"] == "DRAFT_NOT_EDITABLE"


def test_demo_fixture_publisher_flows_to_artifact_evidence_and_share(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    draft_id = runtime["draft_id"]

    confirmed = client.post(
        f"/api/v2/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "fixture-contract"},
        json={"draft_id": draft_id, "expected_draft_version": 1},
    )
    assert confirmed.status_code == 201
    contract_id = confirmed.json()["data"]["id"]

    created = client.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "fixture-run"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
            "derivation_kind": "original",
        },
    )
    assert created.status_code == 201
    run_id = UUID(created.json()["data"]["id"])

    factory = runtime["factory"]
    workflow: PersistentWorkflowStore = runtime["workflow_store"]  # type: ignore[assignment]
    snapshot = workflow.load_snapshot(run_id)
    lease = workflow.acquire_lease(
        run_id,
        owner="x01-fixture-publisher",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow.begin_step(
        run_id,
        step_key="planning",
        attempt_idempotency_key="fixture-attempt",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Publishing deterministic fixture",
    )

    artifact_id = uuid4()
    source_snapshot_id = uuid4()
    evidence_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ResearchArtifactModel(
                id=artifact_id,
                project_id=UUID(str(project_id)),
                kind="dataset",
                title="Deterministic exoplanet fixture",
                logical_key="x01-demo-fixture-dataset",
            )
        )
        session.add(
            SourceSnapshotModel(
                id=source_snapshot_id,
                project_id=UUID(str(project_id)),
                source_id="x01_demo_fixture",
                source_type="fixture",
                retrieved_at=NOW,
                query={"scenario": "exoplanet_host_star"},
                query_hash="sha256:" + "1" * 64,
                content_hash="sha256:" + "2" * 64,
                license_note="Repository fixture; not a live scientific source",
                request_metadata={"execution_mode": "demo_replay"},
            )
        )

    candidate = admit_artifact_candidate(
        _FixtureDatasetCandidate(
            field_ids=("planet.toi_id", "star.tic_id"),
            rows=({"planet.toi_id": "TOI-700 d", "star.tic_id": "TIC-150428135"},),
        ),
        schema_version="2.0.0",
        source_snapshot_ids=(str(source_snapshot_id),),
        evidence_ids=(str(evidence_id),),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )
    ledger = ProducerExecutionStore(factory)  # type: ignore[arg-type]
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=run_id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key="fixture-producer",
            producer_type="pipeline",
            producer_name="x01-demo-fixture",
            producer_version="1.0.0",
            input_hash="sha256:" + "3" * 64,
            parameters={"scenario": "exoplanet_host_star"},
        ),
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    ledger.finish_producer_execution(
        execution.id,
        status="completed",
        output_hash=candidate.content_hash,
    )
    published = ArtifactPublisher(factory).publish_step_outputs(  # type: ignore[arg-type]
        run_id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(
            ArtifactPublication(
                artifact_id=artifact_id,
                publication_key="x01-demo-fixture-v1",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Deterministic fixture published",
    )
    version_id = published.versions[0].id

    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            EvidenceModel(
                id=evidence_id,
                project_id=UUID(str(project_id)),
                artifact_version_id=version_id,
                target_type="field",
                target_id="planet.toi_id",
                evidence_type="database_query",
                source_snapshot_id=source_snapshot_id,
                locator={"kind": "fixture_row", "row_key": "TOI-700 d"},
                quote_or_value="TOI-700 d",
                extraction_method="x01_demo_fixture.replay",
                confidence=1.0,
            )
        )

    version = client.get(f"/api/v2/artifact-versions/{version_id}")
    assert version.status_code == 200
    assert version.json()["data"]["source_mode"] == "fixture"
    assert version.json()["data"]["evidence_ids"] == [str(evidence_id)]

    shared = client.post(
        f"/api/v2/projects/{project_id}/shares",
        headers=csrf,
        json={
            "title": "X-01 deterministic fixture evidence",
            "artifact_version_ids": [str(version_id)],
            "evidence_ids": [str(evidence_id)],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "redaction_policy": "public_metadata_only",
        },
    )
    assert shared.status_code == 201, shared.text
    public = client.get(shared.json()["data"]["share_url"])
    assert public.status_code == 200
    assert public.json()["data"]["artifact_versions"][0]["source_mode"] == "fixture"
    assert public.json()["data"]["evidence"][0]["id"] == str(evidence_id)


def test_runtime_hides_cross_session_and_requires_auth(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    project_id = runtime["project_id"]

    anonymous = TestClient(client.app, base_url="https://testserver")
    assert anonymous.get(f"/api/v2/projects/{project_id}").status_code == 401

    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, runtime["other_credential"])
    hidden = other.get(f"/api/v2/projects/{project_id}")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "PROJECT_NOT_FOUND"

    unknown = uuid4()
    assert client.get(f"/api/v2/runs/{unknown}").status_code == 404

    missing_csrf = client.post(
        f"/api/v2/projects/{project_id}/runs",
        headers={"Idempotency-Key": "no-csrf"},
        json={"contract_id": str(UUID(int=0)), "execution_mode": "live"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"
