"""X-01 real PostgreSQL + FastAPI integration gap coverage (#122).

Complements ``test_v2_research_runtime_postgres.py`` by pinning the remaining
Gate semantics over the *real* mounted runtime (no MSW, no SQLite, no mocked
Repository/WorkflowStore/Publisher):

- ContractDraft/Contract payloads never carry ``execution_mode``.
- Run events never exceed the run ``latest_event_sequence``.
- WorkspaceSnapshot stale ``If-Match`` -> 409 and authoritative re-read.
- Private share list never serializes the raw token.
- Anonymous Public Share read, redaction, and post-revoke 404.
- Stable 404 for missing Project/Run/ArtifactVersion/Share.
- The test-only bootstrap router: mounted only under ``APP_ENV=test``,
  session-bound, deterministic, and absent under ``development``.

Requires ``TEST_DATABASE_URL`` (isolated database whose name contains
``test``); the suite skips otherwise rather than substituting SQLite.
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
from pydantic import BaseModel, SecretStr

from app.config import settings
from app.db.models import (
    EvidenceModel,
    ResearchArtifactModel,
    ResearchContractDraftModel,
    ResearchProjectModel,
    SourceSnapshotModel,
)
from app.main import create_app
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    admit_artifact_candidate,
)
from app.workflow.store import PersistentWorkflowStore


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


class _FixtureDatasetCandidate(BaseModel):
    kind: Literal["dataset"] = "dataset"
    field_ids: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def _validate_evidence(context: ArtifactAdmissionContext) -> None:
    if len(context.source_snapshot_ids) != 1 or len(context.evidence_ids) != 1:
        raise ValueError("fixture publication requires one SourceSnapshot and Evidence")
    UUID(context.source_snapshot_ids[0])
    UUID(context.evidence_ids[0])


def _validate_domain(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, _FixtureDatasetCandidate):
        raise ValueError("fixture publication requires the typed dataset candidate")
    declared = set(candidate.field_ids)
    if candidate.field_ids != ("planet.toi_id", "star.tic_id") or any(
        set(row) != declared for row in candidate.rows
    ):
        raise ValueError("fixture dataset must match the frozen M1 fields")


def _validate_quality(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, _FixtureDatasetCandidate) or len(candidate.rows) != 1:
        raise ValueError("fixture dataset must contain exactly one deterministic row")
    if any(not value.strip() for value in candidate.rows[0].values()):
        raise ValueError("fixture dataset values must be non-empty")


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
def runtime(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))
    monkeypatch.setattr(settings, "PERSISTENT_WORKFLOW_ENABLED", True)
    monkeypatch.setattr(settings, "APP_ENV", "test")

    app = create_app()
    store: PersistentWorkflowStore = app.state.workflow_store
    factory = app.state.db_session_factory
    assert store is not None
    assert factory is not None

    owner, owner_credential, owner_csrf = app.state.session_service.create(now=NOW)
    other, other_credential, _other_csrf = app.state.session_service.create(now=NOW)

    project_id = uuid4()
    draft_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchProjectModel(
                id=project_id,
                session_id=owner.id,
                name="X-01 gap coverage chain",
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

    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, owner_credential)
        try:
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
            command.downgrade(config, "base")
            command.upgrade(config, "head")


def _confirm_and_run(runtime: dict[str, object], *, key_suffix: str) -> tuple[str, str]:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    confirmed = client.post(
        f"/api/v2/projects/{runtime['project_id']}/contracts",
        headers={**csrf, "Idempotency-Key": f"gap-confirm-{key_suffix}"},
        json={"draft_id": runtime["draft_id"], "expected_draft_version": 1},
    )
    assert confirmed.status_code == 201, confirmed.text
    contract_id = confirmed.json()["data"]["id"]
    created = client.post(
        f"/api/v2/projects/{runtime['project_id']}/runs",
        headers={**csrf, "Idempotency-Key": f"gap-run-{key_suffix}"},
        json={
            "contract_id": contract_id,
            "execution_mode": "demo_replay",
            "derivation_kind": "original",
        },
    )
    assert created.status_code == 201, created.text
    return contract_id, created.json()["data"]["id"]


def _publish_fixture_artifact(
    runtime: dict[str, object], run_id: str
) -> tuple[str, str]:
    """Publish a deterministic fixture version and bind evidence (real path)."""
    factory = runtime["factory"]
    workflow: PersistentWorkflowStore = runtime["workflow_store"]  # type: ignore[assignment]
    run_uuid = UUID(run_id)
    project_uuid = UUID(str(runtime["project_id"]))

    snapshot = workflow.load_snapshot(run_uuid)
    lease = workflow.acquire_lease(
        run_uuid,
        owner="x01-gap-publisher",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow.begin_step(
        run_uuid,
        step_key="planning",
        attempt_idempotency_key=f"gap-attempt-{run_id}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Publishing gap-coverage fixture",
    )
    artifact_id = uuid4()
    source_snapshot_id = uuid4()
    evidence_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ResearchArtifactModel(
                id=artifact_id,
                project_id=project_uuid,
                kind="dataset",
                title="X-01 gap fixture dataset",
                logical_key=f"gap-fixture-{run_id}",
            )
        )
        session.add(
            SourceSnapshotModel(
                id=source_snapshot_id,
                project_id=project_uuid,
                source_id="x01_gap_fixture",
                source_type="fixture",
                retrieved_at=NOW,
                query={"scenario": "exoplanet_host_star"},
                query_hash="sha256:" + "1" * 64,
                content_hash="sha256:" + "2" * 64,
                license_note="Test fixture; not a live scientific source",
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
        evidence_validator=_validate_evidence,
        domain_validator=_validate_domain,
        quality_validator=_validate_quality,
    )
    ledger = ProducerExecutionStore(factory)  # type: ignore[arg-type]
    execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=run_uuid,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            idempotency_key=f"gap-producer-{run_id}",
            producer_type="pipeline",
            producer_name="x01-gap-fixture",
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
        execution.id, status="completed", output_hash=candidate.content_hash
    )
    published = ArtifactPublisher(factory).publish_step_outputs(  # type: ignore[arg-type]
        run_uuid,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=(
            ArtifactPublication(
                artifact_id=artifact_id,
                publication_key=f"gap-fixture-v1-{run_id}",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Gap-coverage fixture published",
    )
    version_id = published.versions[0].id
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            EvidenceModel(
                id=evidence_id,
                project_id=project_uuid,
                artifact_version_id=version_id,
                target_type="field",
                target_id="planet.toi_id",
                evidence_type="database_query",
                source_snapshot_id=source_snapshot_id,
                locator={"kind": "fixture_row", "row_key": "TOI-700 d"},
                quote_or_value="TOI-700 d",
                extraction_method="x01_gap_fixture.replay",
                confidence=1.0,
            )
        )
    return str(version_id), str(evidence_id)


def test_draft_and_contract_payloads_never_carry_execution_mode(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    draft = client.get(f"/api/v2/research-contract-drafts/{runtime['draft_id']}")
    assert draft.status_code == 200
    draft_payload = draft.json()["data"]
    assert "execution_mode" not in draft_payload
    assert "execution_mode" not in draft_payload["contract"]

    contract_id, _run_id = _confirm_and_run(runtime, key_suffix="no-exec-mode")
    contract = client.get(f"/api/v2/research-contracts/{contract_id}")
    assert contract.status_code == 200
    assert "execution_mode" not in contract.json()["data"]


def test_run_events_never_exceed_latest_event_sequence(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    _contract_id, run_id = _confirm_and_run(runtime, key_suffix="event-bound")
    _publish_fixture_artifact(runtime, run_id)

    run = client.get(f"/api/v2/runs/{run_id}")
    assert run.status_code == 200
    latest = run.json()["data"]["latest_event_sequence"]

    events = client.get(f"/api/v2/runs/{run_id}/events", params={"limit": 100})
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
        f"/api/v2/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "comparative"},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 1
    assert saved.headers["ETag"] == "1"

    stale = client.put(
        f"/api/v2/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "single"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"

    authoritative = client.get(f"/api/v2/projects/{project_id}/workspace-snapshot")
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
        f"/api/v2/projects/{project_id}/shares",
        headers=csrf,
        json={
            "title": "X-01 gap share",
            "artifact_version_ids": [version_id],
            "evidence_ids": [evidence_id],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "redaction_policy": "public_metadata_only",
        },
    )
    assert created.status_code == 201, created.text
    created_data = created.json()["data"]
    share_id = created_data["id"]
    share_url = created_data["share_url"]
    raw_token = created_data["share_token"]
    assert share_url.endswith(raw_token)

    # Private list never serializes the raw token or its hash.
    listed = client.get(f"/api/v2/projects/{project_id}/shares")
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

    # Public projection carries no session, project credential, locator, or
    # editing surface.
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
        assert "locator" not in evidence
        assert "quote_or_value" not in evidence
        assert forbidden_keys.isdisjoint(evidence.keys())

    # Revoke: public read degrades to the same 404 as an invalid token.
    revoked = client.delete(
        f"/api/v2/projects/{project_id}/shares/{share_id}", headers=csrf
    )
    assert revoked.status_code == 204
    after_revoke = anonymous.get(share_url)
    assert after_revoke.status_code == 404
    assert after_revoke.json()["code"] == "SHARE_NOT_FOUND"


def test_stable_404_for_missing_resources(runtime: dict[str, object]) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    missing = uuid4()
    assert client.get(f"/api/v2/projects/{missing}").status_code == 404
    assert client.get(f"/api/v2/runs/{missing}").status_code == 404
    assert client.get(f"/api/v2/artifact-versions/{missing}").status_code == 404

    anonymous = TestClient(client.app, base_url="https://testserver")
    missing_share = anonymous.get("/api/v2/shares/not-a-real-token")
    assert missing_share.status_code == 404
    assert missing_share.json()["code"] == "SHARE_NOT_FOUND"


def test_test_only_bootstrap_seeds_session_bound_deterministic_scenario(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "test")
    app = create_app()

    # Unauthenticated bootstrap attempts are rejected with the standard 401.
    anonymous = TestClient(app, base_url="https://testserver")
    rejected = anonymous.post("/api/v2/test/bootstrap")
    assert rejected.status_code == 401

    _record, credential, csrf = app.state.session_service.create(now=NOW)
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential)
    seeded = client.post("/api/v2/test/bootstrap", headers={"X-CSRF-Token": csrf})
    assert seeded.status_code == 201, seeded.text
    data = seeded.json()["data"]
    assert data["execution_mode"] == "demo_replay"
    assert data["source_mode"] == "fixture"

    # Every seeded entity is readable through the real frozen /api/v2 surface.
    project = client.get(f"/api/v2/projects/{data['project_id']}")
    assert project.status_code == 200
    draft = client.get(f"/api/v2/research-contract-drafts/{data['draft_id']}")
    assert draft.status_code == 200
    run = client.get(f"/api/v2/runs/{data['run_id']}")
    assert run.status_code == 200
    assert run.json()["data"]["execution_mode"] == "demo_replay"
    events = client.get(f"/api/v2/runs/{data['run_id']}/events")
    assert events.status_code == 200
    assert len(events.json()["data"]) >= 2
    version = client.get(f"/api/v2/artifact-versions/{data['artifact_version_id']}")
    assert version.status_code == 200
    assert version.json()["data"]["source_mode"] == "fixture"
    evidence = client.get(f"/api/v2/evidence/{data['evidence_id']}")
    assert evidence.status_code == 200
    assert evidence.json()["data"]["id"] == data["evidence_id"]

    # Bootstrap is idempotent for the same session owner.
    replayed = client.post("/api/v2/test/bootstrap", headers={"X-CSRF-Token": csrf})
    assert replayed.status_code == 201
    assert replayed.json()["data"] == data


def test_session_resume_preserves_ownership_across_refresh(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Browser refresh recovery: POST /sessions with a valid cookie resumes the
    same anonymous session (fresh CSRF issued), so Run/Snapshot/Public Share
    remain recoverable instead of spawning a parallel anonymous session."""
    monkeypatch.setattr(settings, "APP_ENV", "test")
    app = create_app()

    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/v2/sessions")
    assert created.status_code == 201
    first_csrf = created.json()["data"]["csrf_token"]

    # Seed the deterministic scenario bound to this session's owner.
    seeded = client.post("/api/v2/test/bootstrap", headers={"X-CSRF-Token": first_csrf})
    assert seeded.status_code == 201, seeded.text
    data = seeded.json()["data"]

    # Simulate a browser refresh: the cookie persists, the in-memory CSRF is
    # gone; POST /sessions must resume (not replace) the session.
    resumed = client.post("/api/v2/sessions")
    assert resumed.status_code == 201
    resumed_csrf = resumed.json()["data"]["csrf_token"]
    assert resumed_csrf != first_csrf

    # The fresh CSRF unlocks mutations against the *same* owner context.
    project = client.get(f"/api/v2/projects/{data['project_id']}")
    assert project.status_code == 200
    saved = client.put(
        f"/api/v2/projects/{data['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": resumed_csrf, "If-Match": "0"},
        json={"layout_preset": "comparative", "active_run_id": data["run_id"]},
    )
    assert saved.status_code == 200, saved.text

    # A wrong token is still rejected.
    wrong = client.put(
        f"/api/v2/projects/{data['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": "definitely-not-a-valid-token", "If-Match": "1"},
        json={"layout_preset": "single"},
    )
    assert wrong.status_code == 403

    # Ownership survived the resume: the run and its events are still visible.
    run = client.get(f"/api/v2/runs/{data['run_id']}")
    assert run.status_code == 200
    reloaded = client.get(f"/api/v2/projects/{data['project_id']}/workspace-snapshot")
    assert reloaded.status_code == 200
    assert reloaded.json()["data"]["active_run_id"] == data["run_id"]


def test_session_resume_keeps_recent_csrf_tokens_valid_within_bound(
    runtime: dict[str, object],
) -> None:
    """Concurrent-token model: a previously issued CSRF stays valid across
    resumes (multi-tab / integration client), with a hard bound."""
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    first_csrf = str(runtime["owner_csrf"])

    resumed = client.post("/api/v2/sessions")
    assert resumed.status_code == 201
    second_csrf = resumed.json()["data"]["csrf_token"]
    assert second_csrf != first_csrf

    # Both the original and the freshly issued token authorize mutations.
    first = client.put(
        f"/api/v2/projects/{runtime['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": first_csrf, "If-Match": "0"},
        json={"layout_preset": "comparative"},
    )
    assert first.status_code == 200, first.text
    second = client.put(
        f"/api/v2/projects/{runtime['project_id']}/workspace-snapshot",
        headers={"X-CSRF-Token": second_csrf, "If-Match": "1"},
        json={"layout_preset": "focus"},
    )
    assert second.status_code == 200, second.text


def test_test_only_bootstrap_absent_in_development(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "APP_ENV", "development")
    app = create_app()
    _record, credential, csrf = app.state.session_service.create(now=NOW)
    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, credential)
    # Authenticated request still resolves to 404: the router is not mounted.
    response = client.post("/api/v2/test/bootstrap", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 404
