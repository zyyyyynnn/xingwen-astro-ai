"""Real PostgreSQL + FastAPI integration coverage.

Complements ``test_research_runtime_postgres.py`` by pinning the remaining
Gate semantics over the *real* mounted runtime (no MSW, no SQLite, no mocked
Repository/WorkflowStore/Publisher):

- ContractDraft/Contract payloads never carry ``execution_mode``.
- Run events never exceed the run ``latest_event_sequence``.
- WorkspaceSnapshot stale ``If-Match`` -> 409 and authoritative re-read.
- Private share list never serializes the raw token.
- Anonymous Public Share read, redaction, and post-revoke 404.
- Stable 404 for missing Project/Run/ArtifactVersion/Share.
- The test-only bootstrap router: mounted only under ``APP_ENV=test``,
  narrowed to Dataset ArtifactVersion/Evidence publication onto a
  session-owned demo_replay run, and absent under ``development``.

Requires ``TEST_DATABASE_URL`` (isolated database whose name contains
``test``); the suite skips otherwise rather than substituting SQLite.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from db_bootstrap import reset_current_schema
from pydantic import SecretStr

from app.config import settings
from app.main import create_app
from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.test_support.bootstrap import bootstrap_fixture_artifacts
from authoring_test_support import (
    build_contract_draft,
    build_research_project,
    persist_authoring_models,
)
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
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "disabled",
        },
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
        "scientific_tasks": [],
        "output_requirements": [
            "dataset",
            "field_dictionary",
            "source_collection",
        ],
        "evidence_requirements": {"require_locator": True},
        "quality_constraints": {"source_completeness_min": 1.0},
    }


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)

    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))
    monkeypatch.setattr(settings, "APP_ENV", "test")

    app = create_app()
    store: PersistentWorkflowStore = app.state.workflow_store
    factory = app.state.db_session_factory
    assert store is not None
    assert factory is not None

    owner, owner_credential, owner_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    other, other_credential, _other_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )

    project_id = uuid4()
    draft_id = uuid4()
    with factory() as session, session.begin():
        project = build_research_project(
            project_id=project_id,
            session_id=owner.id,
            name="Real Compose and Browser Integration gap coverage chain",
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

    try:
        with TestClient(app, base_url="https://testserver") as client:
            client.cookies.set(settings.SESSION_COOKIE_NAME, owner_credential)
            yield {
                "app": app,
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
        reset_current_schema(TEST_DATABASE_URL)


def _confirm_and_run(runtime: dict[str, object], *, key_suffix: str) -> tuple[str, str]:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    confirmed = client.post(
        f"/api/projects/{runtime['project_id']}/contracts",
        headers={**csrf, "Idempotency-Key": f"gap-confirm-{key_suffix}"},
        json={"draft_id": runtime["draft_id"], "expected_draft_version": 1},
    )
    assert confirmed.status_code == 201, confirmed.text
    contract_id = confirmed.json()["data"]["id"]
    created = client.post(
        f"/api/projects/{runtime['project_id']}/runs",
        headers={**csrf, "Idempotency-Key": f"gap-run-{key_suffix}"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
        },
    )
    assert created.status_code == 201, created.text
    return contract_id, created.json()["data"]["id"]


def _publish_fixture_artifact(
    runtime: dict[str, object], run_id: str
) -> tuple[str, str]:
    """Publish the canonical Dataset fixture onto the target demo_replay Run."""

    result = bootstrap_fixture_artifacts(
        session_id=str(runtime["owner_session_id"]),
        run_id=run_id,
        factory=runtime["factory"],  # type: ignore[arg-type]
        research_service=runtime["app"].state.research_service,  # type: ignore[union-attr]
        workflow_store=runtime["workflow_store"],  # type: ignore[arg-type]
    )
    assert result.evidence_ids
    return result.artifact_version_id, result.evidence_ids[0]


def test_draft_and_contract_payloads_never_carry_execution_mode(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    draft = client.get(f"/api/contracts/drafts/{runtime['draft_id']}")
    assert draft.status_code == 200
    draft_payload = draft.json()["data"]
    assert "execution_mode" not in draft_payload
    assert "execution_mode" not in draft_payload["contract"]

    contract_id, _run_id = _confirm_and_run(runtime, key_suffix="no-exec-mode")
    contract = client.get(f"/api/contracts/{contract_id}")
    assert contract.status_code == 200
    assert "execution_mode" not in contract.json()["data"]


def test_contract_confirmation_replay_returns_the_persisted_resource(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    headers = {
        "X-CSRF-Token": str(runtime["owner_csrf"]),
        "Idempotency-Key": "contract-persisted-resource",
    }
    request = {
        "draft_id": runtime["draft_id"],
        "expected_draft_version": 1,
    }
    path = f"/api/projects/{runtime['project_id']}/contracts"

    first = client.post(path, headers=headers, json=request)
    replay = client.post(path, headers=headers, json=request)

    assert first.status_code == replay.status_code == 201
    assert first.json()["data"] == replay.json()["data"]
    assert set(first.json()["data"]) == {
        "id",
        "project_id",
        "version",
        "created_from_draft_id",
        "created_at",
        "content_hash",
        *set(_contract_input()),
    }

    conflict = client.post(
        path,
        headers=headers,
        json={**request, "expected_draft_version": 2},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_run_events_never_exceed_latest_event_sequence(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    _contract_id, run_id = _confirm_and_run(runtime, key_suffix="event-bound")
    _publish_fixture_artifact(runtime, run_id)

    run = client.get(f"/api/runs/{run_id}")
    assert run.status_code == 200
    latest = run.json()["data"]["latest_event_sequence"]

    events = client.get(f"/api/runs/{run_id}/events", params={"limit": 100})
    assert events.status_code == 200
    sequences = [event["sequence"] for event in events.json()["data"]]
    assert sequences, "published run must emit events"
    assert max(sequences) <= latest
    assert sequences == sorted(sequences)


def test_workspace_snapshot_stale_revision_conflict_and_authoritative_read(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]

    saved = client.put(
        f"/api/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "comparative"},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 1
    assert saved.headers["ETag"] == "1"

    stale = client.put(
        f"/api/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "single"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    authoritative = client.get(f"/api/projects/{project_id}/workspace-snapshot")
    assert authoritative.status_code == 200
    # The stale write never silently overwrote the authoritative snapshot.
    assert authoritative.json()["data"]["revision"] == 1
    assert authoritative.json()["data"]["layout_preset"] == "comparative"


def test_share_freeze_private_list_redaction_and_revoke(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    _contract_id, run_id = _confirm_and_run(runtime, key_suffix="share-chain")
    version_id, evidence_id = _publish_fixture_artifact(runtime, run_id)

    created = client.post(
        f"/api/projects/{project_id}/shares",
        headers=csrf,
        json={
            "title": "Real Compose and Browser Integration gap share",
            "artifact_version_ids": [version_id],
            "evidence_ids": [evidence_id],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "redaction_policy": "redacted_public_snapshot",
        },
    )
    assert created.status_code == 201, created.text
    created_data = created.json()["data"]
    share_id = created_data["id"]
    share_url = created_data["share_url"]
    raw_token = created_data["share_token"]
    assert share_url.endswith(raw_token)

    # Private list never serializes the raw token or its hash.
    listed = client.get(f"/api/projects/{project_id}/shares")
    assert listed.status_code == 200
    listed_payload = listed.json()
    assert raw_token not in str(listed_payload)
    for share in listed_payload["data"]:
        assert "share_token" not in share
        assert "token_hash" not in share
        assert "token" not in share

    # Anonymous read of the public projection (no session cookie at all).
    anonymous = TestClient(client.app, base_url="https://testserver")
    public = anonymous.get(share_url)
    assert public.status_code == 200, public.text
    public_data = public.json()["data"]
    assert public_data["artifact_versions"][0]["id"] == version_id
    assert public_data["artifact_versions"][0]["source_mode"] == "fixture"
    assert public_data["evidence"][0]["id"] == evidence_id

    # Public projection carries no session, project credential, private
    # provenance, or editing surface. Locator/source fields are an explicit
    # redacted allowlist used by the read-only Evidence inspector.
    forbidden_keys = {
        "session_id",
        "project_id",
        "credential",
        "share_token",
        "token",
        "token_hash",
        "csrf",
    }
    assert forbidden_keys.isdisjoint(public_data.keys())
    for version in public_data["artifact_versions"]:
        assert forbidden_keys.isdisjoint(version.keys())
    for evidence in public_data["evidence"]:
        assert evidence["locator"]["kind"] == "source"
        assert "row" not in evidence["locator"]
        assert forbidden_keys.isdisjoint(evidence.keys())
        assert forbidden_keys.isdisjoint(evidence["source"].keys())
        assert "quote_or_value" in evidence

    # Revoke: public read degrades to the same 404 as an invalid token.
    revoked = client.delete(
        f"/api/projects/{project_id}/shares/{share_id}", headers=csrf
    )
    assert revoked.status_code == 204
    after_revoke = anonymous.get(share_url)
    assert after_revoke.status_code == 404
    assert after_revoke.json()["code"] == "SHARE_NOT_FOUND"


def test_stable_404_for_missing_resources(runtime: dict[str, object]) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    missing = uuid4()
    assert client.get(f"/api/projects/{missing}").status_code == 404
    assert client.get(f"/api/runs/{missing}").status_code == 404
    assert client.get(f"/api/artifact-versions/{missing}").status_code == 404

    anonymous = TestClient(client.app, base_url="https://testserver")
    missing_share = anonymous.get("/api/public/shares/not-a-real-token")
    assert missing_share.status_code == 404
    assert missing_share.json()["code"] == "SHARE_NOT_FOUND"


def _public_chain(
    client: TestClient,
    csrf: str,
    *,
    key_suffix: str,
    execution_mode: str = "demo_replay",
    contract_payload: dict[str, object] | None = None,
) -> dict[str, str]:
    """Create Project → Draft → Contract → Run entirely over the public API."""
    headers = {"X-CSRF-Token": csrf}
    project = client.post(
        "/api/projects",
        headers={**headers, "Idempotency-Key": f"chain-project-{key_suffix}"},
        json={
            "name": "Public authoring chain",
            "description": "Created through the public runtime",
            "case_key": "exoplanet_host_star",
        },
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]
    draft = client.post(
        f"/api/projects/{project_id}/contract-drafts",
        headers={**headers, "Idempotency-Key": f"chain-draft-{key_suffix}"},
        json={
            "intent": "Integrate exoplanet candidates and host-star parameters",
            "contract": contract_payload or _contract_input(),
        },
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["data"]["id"]
    confirmed = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**headers, "Idempotency-Key": f"chain-confirm-{key_suffix}"},
        json={"draft_id": draft_id, "expected_draft_version": 1},
    )
    assert confirmed.status_code == 201, confirmed.text
    contract_id = confirmed.json()["data"]["id"]
    run = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**headers, "Idempotency-Key": f"chain-run-{key_suffix}"},
        json={
            "contract_id": contract_id,
            "execution_mode": execution_mode,
        },
    )
    assert run.status_code == 201, run.text
    return {
        "project_id": project_id,
        "draft_id": draft_id,
        "contract_id": contract_id,
        "run_id": run.json()["data"]["id"],
    }


def test_bootstrap_publishes_fixture_onto_public_chain_run(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bootstrap publishes the frozen Dataset candidate onto a
    session-owned demo_replay run created through the public runtime."""
    monkeypatch.setattr(settings, "APP_ENV", "test")
    app = create_app()

    # Unauthenticated bootstrap attempts are rejected with the standard 401.
    anonymous = TestClient(app, base_url="https://testserver")
    rejected = anonymous.post("/api/test/bootstrap")
    assert rejected.status_code == 401

    _record, credential, csrf = app.state.session_service.create(now=datetime.now(UTC))
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential)

    # run_id is mandatory: the bootstrap cannot fabricate prerequisite state.
    missing_run = client.post("/api/test/bootstrap", headers={"X-CSRF-Token": csrf})
    assert missing_run.status_code == 422

    chain = _public_chain(client, csrf, key_suffix="bootstrap")
    seeded = client.post(
        f"/api/test/bootstrap?run_id={chain['run_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert seeded.status_code == 201, seeded.text
    data = seeded.json()["data"]
    assert data["run_id"] == chain["run_id"]
    assert data["execution_mode"] == "demo_replay"
    assert data["source_mode"] == "fixture"
    assert set(data.keys()) == {
        "run_id",
        "artifact_id",
        "artifact_version_id",
        "source_snapshot_ids",
        "evidence_ids",
        "execution_mode",
        "source_mode",
        "scenario",
    }, "bootstrap must not return project/draft/contract ids or any token"

    # The published entities are readable through the real frozen surface.
    version = client.get(f"/api/artifact-versions/{data['artifact_version_id']}")
    assert version.status_code == 200
    assert version.json()["data"]["source_mode"] == "fixture"
    assert version.json()["data"]["content"]["kind"] == "dataset"
    DatasetArtifactCandidate.model_validate(version.json()["data"]["content"])
    dataset = client.get(
        f"/api/artifact-versions/{data['artifact_version_id']}/dataset"
    )
    assert dataset.status_code == 200, dataset.text
    assert dataset.json()["data"]["dataset"]["requested_fields"] == [
        "planet.toi_id",
        "star.tic_id",
    ]
    evidence_id = data["evidence_ids"][0]
    evidence = client.get(f"/api/evidence/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["data"]["id"] == evidence_id
    events = client.get(f"/api/runs/{chain['run_id']}/events")
    assert events.status_code == 200
    assert len(events.json()["data"]) >= 2

    # Bootstrap is idempotent for the same run.
    replayed = client.post(
        f"/api/test/bootstrap?run_id={chain['run_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert replayed.status_code == 201
    assert replayed.json()["data"] == data

    # A second completed Run publishes the next coherent Data bundle. The
    # current version can then drive the real Feedback → Plan → derived Run
    # path without bypassing revision guards.
    second_run = client.post(
        f"/api/projects/{chain['project_id']}/runs",
        headers={
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "bootstrap-second-run",
        },
        json={
            "contract_id": chain["contract_id"],
            "execution_mode": "demo_replay",
        },
    )
    assert second_run.status_code == 201, second_run.text
    second_run_id = second_run.json()["data"]["id"]
    second = client.post(
        f"/api/test/bootstrap?run_id={second_run_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert second.status_code == 201, second.text
    second_version_id = second.json()["data"]["artifact_version_id"]
    second_version = client.get(f"/api/artifact-versions/{second_version_id}")
    assert second_version.status_code == 200
    assert second_version.json()["data"]["version_number"] == 2

    parent_run = client.get(f"/api/runs/{second_run_id}")
    assert parent_run.status_code == 200
    assert parent_run.json()["data"]["status"] == "completed"
    feedback = client.post(
        f"/api/artifact-versions/{second_version_id}/feedback",
        headers={
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "bootstrap-feedback",
        },
        json={
            "expected_version_number": 2,
            "target_type": "artifact_version",
            "target_id": second_version_id,
            "target_locator": {
                "artifact_id": data["artifact_id"],
                "artifact_version_id": second_version_id,
            },
            "category": "correction",
            "summary": "Recheck the source record",
            "requested_change": "Recheck the source record and regenerate the data bundle.",
        },
    )
    assert feedback.status_code == 201, feedback.text
    plan = client.post(
        f"/api/projects/{chain['project_id']}/revision-plans",
        headers={
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "bootstrap-revision-plan",
        },
        json={
            "feedback_ids": [feedback.json()["data"]["id"]],
            "expected_parent_run_revision": parent_run.json()["data"]["revision"],
        },
    )
    assert plan.status_code == 201, plan.text
    plan_data = plan.json()["data"]
    assert plan_data["recompute_steps"] == ["planning", "cleaning_data"]
    derived = client.post(
        f"/api/revision-plans/{plan_data['id']}/confirm",
        headers={
            "X-CSRF-Token": csrf,
            "Idempotency-Key": "bootstrap-revision-confirm",
        },
        json={"expected_plan_version": plan_data["version"]},
    )
    assert derived.status_code == 201, derived.text
    assert derived.json()["data"]["parent_run_id"] == second_run_id
    assert derived.json()["data"]["derivation_kind"] == "revision"

    # A live run is rejected: the fixture is demo_replay-only.
    live_chain = _public_chain(
        client, csrf, key_suffix="bootstrap-live", execution_mode="live"
    )
    live_rejected = client.post(
        f"/api/test/bootstrap?run_id={live_chain['run_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert live_rejected.status_code == 409
    assert live_rejected.json()["code"] == "BOOTSTRAP_RUN_NOT_DEMO_REPLAY"

    # A cross-session run stays a hidden 404.
    _other, other_credential, other_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    other = TestClient(app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, other_credential)
    cross = other.post(
        f"/api/test/bootstrap?run_id={chain['run_id']}",
        headers={"X-CSRF-Token": other_csrf},
    )
    assert cross.status_code == 404
    assert cross.json()["code"] == "RUN_NOT_FOUND"


def test_research_result_bootstrap_executes_literature_and_graph_worker(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = str(runtime["owner_csrf"])
    chain = _public_chain(
        client,
        csrf,
        key_suffix="research-results",
        contract_payload={
            "research_goal": "核对系外行星宿主恒星文献结论与关系。",
            "target_objects": ["exoplanet_candidate", "host_star"],
            "data_requirements": {
                "unit_policy": "canonical",
                "document_source_policy": "disabled",
            },
            "requested_fields": ["planet.toi_id", "star.tic_id"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {
                "keywords": ["exoplanet host star"],
                "source_ids": ["crossref"],
                "max_candidates": 5,
            },
            "scientific_tasks": [],
            "output_requirements": [
                "literature_claims",
                "literature_relations",
                "graph",
            ],
            "evidence_requirements": {},
            "quality_constraints": {},
        },
    )
    bootstrapped = client.post(
        f"/api/test/bootstrap/research-results?run_id={chain['run_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert bootstrapped.status_code == 201, bootstrapped.text
    data = bootstrapped.json()["data"]
    assert data["run_id"] == chain["run_id"]
    assert {
        "literature_claims",
        "literature_relations",
        "graph",
    }.issubset(data["artifact_version_ids"])

    run = client.get(f"/api/runs/{chain['run_id']}")
    assert run.status_code == 200
    assert run.json()["data"]["status"] == "completed"
    relations = client.get(
        "/api/artifact-versions/"
        f"{data['artifact_version_ids']['literature_relations']}"
        "/literature-relations"
    )
    assert relations.status_code == 200, relations.text
    assert relations.json()["data"][0]["reasoning_trace"]
    graph = client.get(
        f"/api/artifact-versions/{data['artifact_version_ids']['graph']}/graph"
    )
    assert graph.status_code == 200, graph.text
    assert graph.json()["data"]["edge_count"] >= 1


def test_session_resume_preserves_ownership_across_refresh(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Browser refresh recovery: POST /sessions with a valid cookie resumes the
    same anonymous session (fresh CSRF issued), so Run/Snapshot/Public Share
    remain recoverable instead of spawning a parallel anonymous session."""
    monkeypatch.setattr(settings, "APP_ENV", "test")
    app = create_app()

    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/sessions")
    assert created.status_code == 201
    first_csrf = created.json()["data"]["csrf_token"]

    # Create the deterministic scenario through the public authoring chain.
    data = _public_chain(client, first_csrf, key_suffix="resume")

    # Simulate a browser refresh: the cookie persists, the in-memory CSRF is
    # gone; POST /sessions must resume (not replace) the session.
    resumed = client.post("/api/sessions")
    assert resumed.status_code == 201
    resumed_csrf = resumed.json()["data"]["csrf_token"]
    assert resumed_csrf != first_csrf

    # The fresh CSRF unlocks mutations against the *same* owner context.
    project = client.get(f"/api/projects/{data['project_id']}")
    assert project.status_code == 200
    saved = client.put(
        f"/api/projects/{data['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": resumed_csrf, "If-Match": "0"},
        json={"layout_preset": "comparative", "active_run_id": data["run_id"]},
    )
    assert saved.status_code == 200, saved.text

    # A wrong token is still rejected.
    wrong = client.put(
        f"/api/projects/{data['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": "definitely-not-a-valid-token", "If-Match": "1"},
        json={"layout_preset": "single"},
    )
    assert wrong.status_code == 403

    # Ownership survived the resume: the run and its events are still visible.
    run = client.get(f"/api/runs/{data['run_id']}")
    assert run.status_code == 200
    reloaded = client.get(f"/api/projects/{data['project_id']}/workspace-snapshot")
    assert reloaded.status_code == 200
    assert reloaded.json()["data"]["active_run_id"] == data["run_id"]


def test_session_resume_preserves_ownership_across_api_restart(
    runtime: dict[str, object],
) -> None:
    """A persisted browser credential must recover its owner in a new app."""
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    credential = client.cookies.get(settings.SESSION_COOKIE_NAME)
    assert credential is not None

    restarted_app = create_app()
    with TestClient(restarted_app, base_url="https://testserver") as restarted:
        restarted.cookies.set(settings.SESSION_COOKIE_NAME, credential)
        resumed = restarted.post("/api/sessions")
        assert resumed.status_code == 201

        project = restarted.get(f"/api/projects/{runtime['project_id']}")
        assert project.status_code == 200


def test_session_resume_keeps_recent_csrf_tokens_valid_within_bound(
    runtime: dict[str, object],
) -> None:
    """Concurrent-token model: a previously issued CSRF stays valid across
    resumes (multi-tab / integration client), with a hard bound."""
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    first_csrf = str(runtime["owner_csrf"])

    resumed = client.post("/api/sessions")
    assert resumed.status_code == 201
    second_csrf = resumed.json()["data"]["csrf_token"]
    assert second_csrf != first_csrf

    # Both the original and the freshly issued token authorize mutations.
    first = client.put(
        f"/api/projects/{runtime['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": first_csrf, "If-Match": "0"},
        json={"layout_preset": "comparative"},
    )
    assert first.status_code == 200, first.text
    second = client.put(
        f"/api/projects/{runtime['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": second_csrf, "If-Match": "1"},
        json={"layout_preset": "focus"},
    )
    assert second.status_code == 200, second.text


def test_bootstrap_absent_in_development(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    app = create_app()
    _record, credential, csrf = app.state.session_service.create(now=datetime.now(UTC))
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential)
    # Authenticated request still resolves to 404: the router is not mounted.
    response = client.post("/api/test/bootstrap", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 404
