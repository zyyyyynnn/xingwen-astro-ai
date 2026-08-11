"""Real FastAPI + PostgreSQL integration for the research runtime chain.

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
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine, func, select

from app.config import settings
from app.db.models import (
    EvidenceModel,
    ResearchArtifactModel,
    ResearchContractDraftModel,
    ResearchProjectModel,
    SourceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_project,
    persist_authoring_models,
)
from artifact_publication_test_support import publish_reference_dataset
from app.main import _load_case_manifests, create_app
from app.schemas.core import ArtifactKind, ExportArtifactContent
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
        project = build_research_project(
            project_id=project_id,
            session_id=owner.id,
            name="Research runtime chain",
            case_key="exoplanet_host_star",
            created_at=NOW,
            updated_at=NOW,
        )
        draft = build_contract_draft(
            project,
            draft_id=draft_id,
            intent="Integrate exoplanet candidates and host-star parameters",
            status="draft",
            content=_contract_input(),
            created_at=NOW,
            updated_at=NOW,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        persist_authoring_models(session, project=project, draft=draft)

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
            "other_csrf": other_csrf,
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

    project = client.get(f"/api/projects/{project_id}")
    assert project.status_code == 200
    assert project.json()["data"]["case_key"] == "exoplanet_host_star"
    assert "session_id" in project.json()["data"]  # owner reads its own project

    draft = client.get(f"/api/contracts/drafts/{draft_id}")
    assert draft.status_code == 200
    assert draft.json()["data"]["status"] == "draft"

    patched = client.patch(
        f"/api/contracts/drafts/{draft_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "Refined integration intent"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["version"] == 2

    stale = client.patch(
        f"/api/contracts/drafts/{draft_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "conflicting"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    confirmed = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": draft_id, "expected_draft_version": 2},
    )
    assert confirmed.status_code == 201
    contract_id = confirmed.json()["data"]["id"]
    assert confirmed.json()["data"]["content_hash"].startswith("sha256:")

    confirm_replay = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": draft_id, "expected_draft_version": 2},
    )
    assert confirm_replay.status_code == 201
    assert confirm_replay.json()["data"] == confirmed.json()["data"]

    conflicting_draft_id = uuid4()
    factory = runtime["factory"]
    with factory() as session, session.begin():  # type: ignore[operator]
        project = session.get(ResearchProjectModel, UUID(project_id))
        assert project is not None
        session.add(
            build_contract_draft(
                project,
                draft_id=conflicting_draft_id,
                intent="Different confirmation request",
                status="draft",
                content=_contract_input(),
                created_at=NOW,
                updated_at=NOW,
                expires_at=datetime(2026, 7, 23, tzinfo=UTC),
            )
        )
    idempotency_conflict = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "confirm-1"},
        json={"draft_id": str(conflicting_draft_id), "expected_draft_version": 1},
    )
    assert idempotency_conflict.status_code == 409
    assert idempotency_conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    contract = client.get(f"/api/contracts/{contract_id}")
    assert contract.status_code == 200
    # Full frozen content is recovered, not only the hash.
    assert contract.json()["data"]["requested_fields"] == [
        "planet.toi_id",
        "star.tic_id",
    ]

    rejected_unsupported_target_fields = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-unsupported-target-fields"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
            "feedback_ids": ["feedback_01J"],
            "retry_from_step": "fetching_data",
            "cache_policy": "reuse",
            "parent_run_id": "run_01J",
            "derivation_kind": "retry",
        },
    )
    assert rejected_unsupported_target_fields.status_code == 422
    assert (
        client.get(f"/api/projects/{project_id}").json()["data"]["latest_run_id"]
        is None
    )

    created = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
        },
    )
    assert created.status_code == 201
    run_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "queued"
    assert created.json()["data"]["parent_run_id"] is None
    assert created.json()["data"]["derivation_kind"] == "original"
    assert created.json()["data"]["retry_from_step"] is None
    assert created.json()["data"]["cache_policy"] == "disabled"

    project_after_run = client.get(f"/api/projects/{project_id}")
    assert project_after_run.json()["data"]["active_contract_id"] == contract_id
    assert project_after_run.json()["data"]["latest_run_id"] == run_id

    replay = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "live",
        },
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == run_id  # idempotent replay

    conflict = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    run = client.get(f"/api/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["data"]["latest_event_sequence"] >= 1

    events = client.get(f"/api/runs/{run_id}/events")
    assert events.status_code == 200
    sequences = [event["sequence"] for event in events.json()["data"]]
    assert sequences == sorted(sequences)
    assert events.json()["data"][0]["event_type"] == "run.queued"

    saved = client.put(
        f"/api/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "comparative", "active_run_id": run_id},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 1
    reloaded = client.get(f"/api/projects/{project_id}/workspace-snapshot")
    assert reloaded.json()["data"] == saved.json()["data"]


def test_expired_draft_is_visible_but_cannot_be_changed_or_confirmed(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    expired_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        project = session.get(ResearchProjectModel, UUID(runtime["project_id"]))
        assert project is not None
        session.add(
            build_contract_draft(
                project,
                draft_id=expired_id,
                intent="Expired contract draft",
                status="draft",
                content=_contract_input(),
                created_at=NOW - timedelta(days=2),
                updated_at=NOW - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        )

    fetched = client.get(f"/api/contracts/drafts/{expired_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "expired"

    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    patched = client.patch(
        f"/api/contracts/drafts/{expired_id}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "too late"},
    )
    assert patched.status_code == 409
    assert patched.json()["code"] == "DRAFT_NOT_EDITABLE"

    confirmed = client.post(
        f"/api/projects/{runtime['project_id']}/contracts",
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
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "fixture-contract"},
        json={"draft_id": draft_id, "expected_draft_version": 1},
    )
    assert confirmed.status_code == 201
    contract_id = confirmed.json()["data"]["id"]

    created = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "fixture-run"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
        },
    )
    assert created.status_code == 201
    run_id = UUID(created.json()["data"]["id"])

    factory = runtime["factory"]
    workflow: PersistentWorkflowStore = runtime["workflow_store"]  # type: ignore[assignment]
    snapshot = workflow.load_snapshot(run_id)
    lease = workflow.acquire_lease(
        run_id,
        owner="real_integration-fixture-publisher",
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
        public_message="Publishing deterministic export",
    )

    artifact_id = uuid4()
    source_snapshot_id = uuid4()
    evidence_id = uuid4()
    with factory() as session:  # type: ignore[operator]
        project = session.get(ResearchProjectModel, UUID(str(project_id)))
        assert project is not None
    reference_version_id = publish_reference_dataset(
        factory=factory,  # type: ignore[arg-type]
        project=project,
    )
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ResearchArtifactModel(
                id=artifact_id,
                project_id=UUID(str(project_id)),
                kind="export",
                title="Deterministic provenance export",
                logical_key="real_integration-demo-export",
            )
        )
        session.add(
            SourceSnapshotModel(
                id=source_snapshot_id,
                project_id=UUID(str(project_id)),
                source_id="real_integration_demo_export_fixture",
                source_type="fixture",
                retrieved_at=NOW,
                query={"scenario": "exoplanet_host_star"},
                query_hash="sha256:" + "1" * 64,
                content_hash="sha256:" + "2" * 64,
                license_note="Repository fixture; not a live scientific source",
                request_metadata={"execution_mode": "demo_replay"},
            )
        )

    ledger = ProducerExecutionStore(factory)  # type: ignore[arg-type]
    candidate = admit_artifact_candidate(
        ExportArtifactContent(
            kind=ArtifactKind.export,
            format="json",
            artifact_version_ids=(str(reference_version_id),),
        ),
        schema_version="2.0.0",
        source_snapshot_ids=(str(source_snapshot_id),),
        evidence_ids=(str(evidence_id),),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=run_id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key="fixture-producer",
            producer_type="pipeline",
            producer_name="real_integration-demo-export",
            producer_version="1.0.0",
            input_hash="sha256:" + "3" * 64,
            parameters={
                "format": "json",
                "reference_version_id": str(reference_version_id),
            },
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
                publication_key="real-integration-demo-export",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Deterministic export published",
    )
    version_id = published.versions[0].id

    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            EvidenceModel(
                id=evidence_id,
                project_id=UUID(str(project_id)),
                artifact_version_id=version_id,
                target_type="export_artifact",
                target_id=str(artifact_id),
                evidence_type="export_provenance",
                source_snapshot_id=source_snapshot_id,
                locator={
                    "kind": "artifact_version_reference",
                    "artifact_version_id": str(reference_version_id),
                },
                quote_or_value=str(reference_version_id),
                extraction_method="real_integration_demo_export.replay",
                confidence=1.0,
            )
        )

    version = client.get(f"/api/artifact-versions/{version_id}")
    assert version.status_code == 200
    assert version.json()["data"]["source_mode"] == "fixture"
    assert version.json()["data"]["evidence_ids"] == [str(evidence_id)]
    assert version.json()["data"]["content"]["kind"] == "export"

    shared = client.post(
        f"/api/projects/{project_id}/shares",
        headers=csrf,
        json={
            "title": "Real Compose and Browser Integration export evidence",
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


def test_public_authoring_chain_creates_project_and_draft(
    runtime: dict[str, object],
) -> None:
    """Session → createResearchProject → createResearchContractDraft →
    update → confirm → run entirely over the public runtime (no bootstrap)."""
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}

    created = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "authoring-project-1"},
        json={
            "name": "Public authoring chain",
            "description": "Created through the public runtime",
            "case_key": "exoplanet_host_star",
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()["data"]
    assert project["revision"] == 1
    assert project["case_key"] == "exoplanet_host_star"
    assert project["active_contract_id"] is None
    assert "execution_mode" not in project
    assert created.headers["Location"] == f"/api/projects/{project['id']}"

    replay = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "authoring-project-1"},
        json={
            "name": "Public authoring chain",
            "description": "Created through the public runtime",
            "case_key": "exoplanet_host_star",
        },
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == project["id"]

    conflict = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "authoring-project-1"},
        json={"name": "Different request", "case_key": "exoplanet_host_star"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        draft_count_before = session.scalar(
            select(func.count()).select_from(ResearchContractDraftModel)
        )

    # Intent-only authoring would require a bound Contract Planner and
    # ModelExecutionPort. The current structured-input API fails closed.
    planner_unavailable = client.post(
        f"/api/projects/{project['id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "authoring-planner-unavailable"},
        json={"intent": "Plan a contract from this research intent"},
    )
    assert planner_unavailable.status_code == 422
    with factory() as session:  # type: ignore[operator]
        assert (
            session.scalar(select(func.count()).select_from(ResearchContractDraftModel))
            == draft_count_before
        )

    draft_created = client.post(
        f"/api/projects/{project['id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "authoring-draft-1"},
        json={
            "intent": "Integrate exoplanet candidates and host-star parameters",
            "contract": _contract_input(),
        },
    )
    assert draft_created.status_code == 201, draft_created.text
    draft = draft_created.json()["data"]
    assert draft["status"] == "draft"
    assert draft["version"] == 1
    assert "execution_mode" not in draft
    assert "execution_mode" not in draft["contract"]
    assert draft_created.headers["ETag"] == "1"
    assert draft_created.headers["Location"] == (f"/api/contracts/drafts/{draft['id']}")

    draft_replay = client.post(
        f"/api/projects/{project['id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "authoring-draft-1"},
        json={
            "intent": "Integrate exoplanet candidates and host-star parameters",
            "contract": _contract_input(),
        },
    )
    assert draft_replay.status_code == 201
    assert draft_replay.json()["data"]["id"] == draft["id"]

    draft_conflict = client.post(
        f"/api/projects/{project['id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "authoring-draft-1"},
        json={"intent": "Different intent", "contract": _contract_input()},
    )
    assert draft_conflict.status_code == 409
    assert draft_conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    # The freshly created draft continues through the existing lifecycle.
    patched = client.patch(
        f"/api/contracts/drafts/{draft['id']}",
        headers={**csrf, "If-Match": "1"},
        json={"intent": "Refined public authoring intent"},
    )
    assert patched.status_code == 200
    confirmed = client.post(
        f"/api/projects/{project['id']}/contracts",
        headers={**csrf, "Idempotency-Key": "authoring-confirm-1"},
        json={"draft_id": draft["id"], "expected_draft_version": 2},
    )
    assert confirmed.status_code == 201, confirmed.text
    contract_id = confirmed.json()["data"]["id"]
    run = client.post(
        f"/api/projects/{project['id']}/runs",
        headers={**csrf, "Idempotency-Key": "authoring-run-1"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
        },
    )
    assert run.status_code == 201, run.text


def test_create_draft_hides_missing_and_cross_session_projects(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    body = {
        "intent": "Integrate exoplanet candidates and host-star parameters",
        "contract": _contract_input(),
    }

    missing = client.post(
        f"/api/projects/{uuid4()}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "draft-missing-project"},
        json=body,
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "PROJECT_NOT_FOUND"

    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, runtime["other_credential"])
    cross = other.post(
        f"/api/projects/{runtime['project_id']}/contract-drafts",
        headers={
            "X-CSRF-Token": runtime["other_csrf"],
            "Idempotency-Key": "draft-cross-session",
        },
        json=body,
    )
    assert cross.status_code == 404
    assert cross.json()["code"] == "PROJECT_NOT_FOUND"


def test_draft_idempotency_and_confirmation_are_project_scoped(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    body = {
        "intent": "Integrate exoplanet candidates and host-star parameters",
        "contract": _contract_input(),
    }
    project = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "draft-scope-project"},
        json={"name": "Draft scope project", "case_key": "exoplanet_host_star"},
    ).json()["data"]

    first = client.post(
        f"/api/projects/{runtime['project_id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "shared-draft-key"},
        json=body,
    )
    second = client.post(
        f"/api/projects/{project['id']}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "shared-draft-key"},
        json=body,
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert first.json()["data"]["project_id"] == runtime["project_id"]
    assert second.json()["data"]["project_id"] == project["id"]

    cross_project = client.post(
        f"/api/projects/{project['id']}/contracts",
        headers={**csrf, "Idempotency-Key": "cross-project-confirm"},
        json={
            "draft_id": first.json()["data"]["id"],
            "expected_draft_version": 1,
        },
    )
    assert cross_project.status_code == 404
    assert cross_project.json()["code"] == "DRAFT_NOT_FOUND"


def test_list_projects_is_session_scoped_with_stable_cursor(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}

    created_ids: list[str] = []
    for index in range(3):
        response = client.post(
            "/api/projects",
            headers={**csrf, "Idempotency-Key": f"list-project-{index}"},
            json={"name": f"List project {index}", "case_key": "exoplanet_host_star"},
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["data"]["id"])

    # Full listing returns only this session's projects (3 created + fixture).
    listing = client.get("/api/projects", params={"limit": 100})
    assert listing.status_code == 200
    listed_ids = [item["id"] for item in listing.json()["data"]]
    assert set(created_ids) <= set(listed_ids)
    assert str(runtime["project_id"]) in listed_ids
    assert len(listed_ids) == len(set(listed_ids))

    # Cursor pagination is stable: walk pages of 1, never repeating a cursor
    # or an item, and terminate with has_more=false.
    seen_ids: list[str] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    for _ in range(len(listed_ids) + 2):
        params: dict[str, str] = {"limit": "1"}
        if cursor:
            params["cursor"] = cursor
        page = client.get("/api/projects", params=params)
        assert page.status_code == 200
        payload = page.json()
        seen_ids.extend(item["id"] for item in payload["data"])
        cursor = payload["page"]["next_cursor"]
        if not payload["page"]["has_more"]:
            assert cursor is None
            break
        assert cursor is not None
        assert cursor not in seen_cursors, "cursor repeated during pagination"
        seen_cursors.add(cursor)
    assert seen_ids == listed_ids
    assert len(seen_ids) == len(set(seen_ids))

    invalid = client.get("/api/projects", params={"cursor": "not-a-cursor"})
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_CURSOR"

    # The other session sees none of the owner's projects (isolation), and a
    # cursor anchored on an owner project is rejected rather than leaked.
    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, runtime["other_credential"])
    other_listing = other.get("/api/projects")
    assert other_listing.status_code == 200
    assert other_listing.json()["data"] == []
    assert other_listing.json()["page"]["has_more"] is False
    if seen_cursors:
        foreign = other.get(
            "/api/projects", params={"cursor": next(iter(seen_cursors))}
        )
        assert foreign.status_code == 400
        assert foreign.json()["code"] == "INVALID_CURSOR"


def test_public_authoring_writes_require_session_and_csrf(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    body = {"name": "No auth", "case_key": "exoplanet_host_star"}

    anonymous = TestClient(client.app, base_url="https://testserver")
    assert anonymous.get("/api/projects").status_code == 401
    assert (
        anonymous.post(
            "/api/projects", headers={"Idempotency-Key": "anon"}, json=body
        ).status_code
        == 401
    )

    missing_csrf = client.post(
        "/api/projects", headers={"Idempotency-Key": "no-csrf"}, json=body
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"

    missing_key = client.post(
        "/api/projects",
        headers={"X-CSRF-Token": runtime["owner_csrf"]},
        json=body,
    )
    assert missing_key.status_code == 422


def test_runtime_hides_cross_session_and_requires_auth(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    project_id = runtime["project_id"]

    anonymous = TestClient(client.app, base_url="https://testserver")
    assert anonymous.get(f"/api/projects/{project_id}").status_code == 401

    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, runtime["other_credential"])
    hidden = other.get(f"/api/projects/{project_id}")
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "PROJECT_NOT_FOUND"

    unknown = uuid4()
    assert client.get(f"/api/runs/{unknown}").status_code == 404

    missing_csrf = client.post(
        f"/api/projects/{project_id}/runs",
        headers={"Idempotency-Key": "no-csrf"},
        json={"contract_id": str(UUID(int=0)), "execution_mode": "live"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_INVALID"
