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
from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine

from app.config import settings
from app.db.models import ResearchContractDraftModel, ResearchProjectModel
from app.db.session import create_engine_from_url, session_factory
from app.main import _load_case_manifests, create_app
from app.services.research import ResearchApplicationService
from app.services.resource_authority import PersistentResourceAuthority
from app.services.snapshots import InMemorySnapshotStore, SnapshotService
from app.workflow.store import PersistentWorkflowStore


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


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
    app.state.research_service = ResearchApplicationService(
        factory=factory, workflow_store=store, manifests=_load_case_manifests()
    )
    app.state.snapshot_service = SnapshotService(
        InMemorySnapshotStore(PersistentResourceAuthority(factory))
    )

    owner, owner_credential, owner_csrf = app.state.session_service.create(now=NOW)
    other, other_credential, other_csrf = app.state.session_service.create(now=NOW)

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
                expires_at=datetime(2026, 7, 23, tzinfo=UTC),
            )
        )

    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, owner_credential)
    try:
        yield {
            "client": client,
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
