"""PostgreSQL and HTTP integration tests for Feedback and revision Runs."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    RevisionPlanConfirmationModel,
    RevisionPlanModel,
    RunStepModel,
    StepAttemptModel,
    UserFeedbackModel,
)
from app.main import create_app
from app.security import InMemoryRateLimiter
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.exc import DatabaseError

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
KINDS = (
    "dataset",
    "field_dictionary",
    "source_collection",
    "paper_collection",
    "paper_summary",
    "literature_claims",
    "literature_relations",
    "reasoning_traces",
    "graph",
)


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch):
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower()
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))
    app = create_app()
    owner, owner_credential, owner_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    other, other_credential, other_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    factory = app.state.db_session_factory

    ids = {
        name: uuid4()
        for name in ("project", "contract", "run", "step", "attempt", "producer")
    }
    artifact_ids = {kind: uuid4() for kind in KINDS}
    version_ids = {kind: uuid4() for kind in KINDS}
    with factory() as session, session.begin():
        project = build_research_project(
            project_id=ids["project"],
            session_id=owner.id,
            name="Revision integration",
            case_key="exoplanet_host_star",
            revision=1,
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
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
        run = ResearchRunModel(
            id=ids["run"],
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            status="completed",
            progress=100,
            derivation_kind="original",
            latest_event_sequence=0,
            revision=7,
            idempotency_key="parent-run",
            request_hash=HASH_B,
            created_at=NOW,
            updated_at=NOW,
        )
        session.add(run)
        session.flush()
        step = RunStepModel(
            id=ids["step"],
            run_id=run.id,
            position=0,
            key="planning",
            label="Planning",
            enter_status="planning",
            success_status="completed",
            max_attempts=1,
            status="completed",
            progress=100,
            public_message="Completed",
            created_at=NOW,
        )
        session.add(step)
        session.flush()
        attempt = StepAttemptModel(
            id=ids["attempt"],
            run_step_id=step.id,
            attempt_number=1,
            idempotency_key="parent-attempt",
            status="completed",
            retryable=False,
            started_at=NOW,
            finished_at=NOW,
            created_at=NOW,
        )
        session.add(attempt)
        session.flush()
        producer = ProducerExecutionModel(
            id=ids["producer"],
            run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=attempt.id,
            step_key=step.key,
            idempotency_key="parent-producer",
            lease_generation=0,
            producer_type="pipeline",
            producer_name="revision-test-seed",
            producer_version="1.0.0",
            parameters={},
            parameters_hash=HASH_A,
            input_hash=HASH_B,
            output_hash=HASH_C,
            status="completed",
            started_at=NOW,
            finished_at=NOW,
            created_at=NOW,
        )
        session.add(producer)
        session.flush()
        for kind in KINDS:
            artifact = ResearchArtifactModel(
                id=artifact_ids[kind],
                project_id=project.id,
                kind=kind,
                title=kind,
                logical_key=f"revision.{kind}",
                created_at=NOW,
            )
            session.add(artifact)
            session.flush()
            version = ArtifactVersionModel(
                id=version_ids[kind],
                artifact_id=artifact.id,
                project_id=project.id,
                created_by_run_id=run.id,
                run_step_id=step.id,
                step_attempt_id=attempt.id,
                producer_execution_id=producer.id,
                version_number=1,
                publication_key=f"revision-{kind}-v1",
                schema_version="2.0.0",
                content={"kind": kind},
                content_hash=HASH_C,
                input_hash=HASH_B,
                source_mode="live",
                producer={"name": "revision-test-seed"},
                source_snapshot_ids=[],
                evidence_ids=[],
                created_at=NOW,
            )
            session.add(version)
            session.flush()
            artifact.latest_version_id = version.id

    client = TestClient(app, base_url="https://testserver")
    client.cookies.set(settings.SESSION_COOKIE_NAME, owner_credential)
    client.__enter__()
    try:
        yield {
            "app": app,
            "client": client,
            "factory": factory,
            "project_id": str(ids["project"]),
            "parent_run_id": str(ids["run"]),
            "owner_session_id": owner.id,
            "owner_credential": owner_credential,
            "owner_csrf": owner_csrf,
            "other_session_id": other.id,
            "other_credential": other_credential,
            "other_csrf": other_csrf,
            "artifact_ids": artifact_ids,
            "version_ids": version_ids,
        }
    finally:
        client.__exit__(None, None, None)
        command.downgrade(config, "base")
        command.upgrade(config, "head")


def _feedback_body() -> dict[str, object]:
    return {
        "expected_version_number": 1,
        "target_type": "artifact_version",
        "target_id": "target-1",
        "target_locator": {"field": "value"},
        "category": "correction",
        "summary": "The published value needs correction",
        "requested_change": "Recompute this result from the frozen inputs",
    }


def _create_feedback(runtime: dict[str, object], kind: str, *, key: str):
    client = runtime["client"]
    assert isinstance(client, TestClient)
    return client.post(
        f"/api/artifact-versions/{runtime['version_ids'][kind]}/feedback",  # type: ignore[index]
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": key,
        },
        json=_feedback_body(),
    )


def _create_plan(runtime: dict[str, object], feedback_id: str, *, key: str):
    client = runtime["client"]
    assert isinstance(client, TestClient)
    return client.post(
        f"/api/projects/{runtime['project_id']}/revision-plans",
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": key,
        },
        json={"feedback_ids": [feedback_id], "expected_parent_run_revision": 7},
    )


def test_revision_plan_impact_closures(runtime: dict[str, object]) -> None:
    expected = {
        "dataset": {"dataset", "field_dictionary", "source_collection", "graph"},
        "paper_collection": {
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
        "paper_summary": {
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
        "literature_claims": {
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
        "literature_relations": {"literature_relations", "reasoning_traces", "graph"},
        "reasoning_traces": {"reasoning_traces", "graph"},
        "graph": {"graph"},
    }
    for kind, affected_kinds in expected.items():
        feedback = _create_feedback(runtime, kind, key=f"feedback-{kind}")
        assert feedback.status_code == 201, feedback.text
        plan = _create_plan(runtime, feedback.json()["data"]["id"], key=f"plan-{kind}")
        assert plan.status_code == 201, plan.text
        data = plan.json()["data"]
        actual = {
            item["artifact_kind"]
            for item in data["version_decisions"]
            if item["decision"] == "recompute"
        }
        assert actual == affected_kinds
        assert data["recompute_steps"][0] == "planning"
        assert data["conflicts"] == []


def test_confirm_is_idempotent_restart_safe_and_preserves_parent(
    runtime: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    client = runtime["client"]
    assert isinstance(client, TestClient)
    feedback = _create_feedback(runtime, "paper_summary", key="feedback-confirm")
    plan = _create_plan(runtime, feedback.json()["data"]["id"], key="plan-confirm")
    plan_data = plan.json()["data"]
    headers = {
        "X-CSRF-Token": str(runtime["owner_csrf"]),
        "Idempotency-Key": "confirm-once",
    }
    first = client.post(
        f"/api/revision-plans/{plan_data['id']}/confirm",
        headers=headers,
        json={"expected_plan_version": 1},
    )
    second = client.post(
        f"/api/revision-plans/{plan_data['id']}/confirm",
        headers=headers,
        json={"expected_plan_version": 1},
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    run = first.json()["data"]
    assert run["derivation_kind"] == "revision"
    assert run["parent_run_id"] == runtime["parent_run_id"]
    assert run["revision_plan_id"] == plan_data["id"]
    assert run["feedback_ids"] == [feedback.json()["data"]["id"]]
    assert run["recompute_steps"] == plan_data["recompute_steps"]
    assert set(run["reused_artifact_version_ids"]) == set(
        plan_data["reusable_artifact_version_ids"]
    )

    factory = runtime["factory"]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(RevisionPlanConfirmationModel)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchRunModel)
                .where(ResearchRunModel.derivation_kind == "revision")
            )
            == 1
        )
        parent = session.get(ResearchRunModel, UUID(str(runtime["parent_run_id"])))
        assert parent is not None
        assert (parent.status, parent.revision, parent.progress) == (
            "completed",
            7,
            100,
        )
        assert all(
            version.version_number == 1 and version.supersedes_version_id is None
            for version in session.scalars(select(ArtifactVersionModel))
        )

    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(str(TEST_DATABASE_URL)))
    restarted = create_app()
    with TestClient(restarted, base_url="https://testserver") as restarted_client:
        restarted_client.cookies.set(
            settings.SESSION_COOKIE_NAME, str(runtime["owner_credential"])
        )
        loaded = restarted_client.get(f"/api/runs/{run['id']}")
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["data"]["revision_plan_id"] == plan_data["id"]


def test_security_validation_idempotency_and_rate_limit(
    runtime: dict[str, object],
) -> None:
    client = runtime["client"]
    assert isinstance(client, TestClient)
    version_id = runtime["version_ids"]["graph"]  # type: ignore[index]
    stale_body = {**_feedback_body(), "expected_version_number": 2}
    stale = client.post(
        f"/api/artifact-versions/{version_id}/feedback",
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": "stale-feedback",
        },
        json=stale_body,
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "ARTIFACT_VERSION_CONFLICT"

    missing_csrf = client.post(
        f"/api/artifact-versions/{version_id}/feedback",
        headers={"Idempotency-Key": "missing-csrf"},
        json=_feedback_body(),
    )
    assert missing_csrf.status_code == 403
    missing_key = client.post(
        f"/api/artifact-versions/{version_id}/feedback",
        headers={"X-CSRF-Token": str(runtime["owner_csrf"])},
        json=_feedback_body(),
    )
    assert missing_key.status_code == 422

    first = _create_feedback(runtime, "graph", key="feedback-idempotency")
    replay = _create_feedback(runtime, "graph", key="feedback-idempotency")
    assert first.status_code == replay.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    divergent = client.post(
        f"/api/artifact-versions/{version_id}/feedback",
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": "feedback-idempotency",
        },
        json={**_feedback_body(), "summary": "A different request"},
    )
    assert divergent.status_code == 409
    assert divergent.json()["code"] == "IDEMPOTENCY_CONFLICT"

    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.set(settings.SESSION_COOKIE_NAME, str(runtime["other_credential"]))
    hidden = other.get(f"/api/feedback/{first.json()['data']['id']}")
    unknown = other.get(f"/api/feedback/{uuid4()}")
    assert (
        (hidden.status_code, hidden.json()["code"])
        == (unknown.status_code, unknown.json()["code"])
        == (404, "FEEDBACK_NOT_FOUND")
    )

    client.app.state.revision_rate_limiter = InMemoryRateLimiter(limit=1)
    limited_first = _create_feedback(runtime, "dataset", key="rate-first")
    limited_second = _create_feedback(runtime, "paper_collection", key="rate-second")
    assert limited_first.status_code == 201
    assert limited_second.status_code == 429
    assert limited_second.json()["code"] == "RATE_LIMITED"


def test_stale_plan_fails_before_creating_revision_run(
    runtime: dict[str, object],
) -> None:
    feedback = _create_feedback(runtime, "graph", key="feedback-stale-plan")
    plan = _create_plan(runtime, feedback.json()["data"]["id"], key="plan-stale")
    factory = runtime["factory"]
    with factory() as session, session.begin():
        version_one = session.get(
            ArtifactVersionModel,
            runtime["version_ids"]["graph"],  # type: ignore[index]
        )
        assert version_one is not None
        version_two = ArtifactVersionModel(
            id=uuid4(),
            artifact_id=version_one.artifact_id,
            project_id=version_one.project_id,
            created_by_run_id=version_one.created_by_run_id,
            run_step_id=version_one.run_step_id,
            step_attempt_id=version_one.step_attempt_id,
            producer_execution_id=version_one.producer_execution_id,
            version_number=2,
            publication_key="revision-graph-v2",
            schema_version=version_one.schema_version,
            content={"kind": "graph", "revision": 2},
            content_hash=HASH_A,
            input_hash=version_one.input_hash,
            source_mode=version_one.source_mode,
            producer=dict(version_one.producer),
            source_snapshot_ids=list(version_one.source_snapshot_ids),
            evidence_ids=list(version_one.evidence_ids),
            supersedes_version_id=version_one.id,
            created_at=NOW,
        )
        session.add(version_two)
        session.flush()
        artifact = session.get(ResearchArtifactModel, version_one.artifact_id)
        assert artifact is not None
        artifact.latest_version_id = version_two.id
    client = runtime["client"]
    assert isinstance(client, TestClient)
    response = client.post(
        f"/api/revision-plans/{plan.json()['data']['id']}/confirm",
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": "confirm-stale",
        },
        json={"expected_plan_version": 1},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_PLAN_STALE"
    with factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(RevisionPlanConfirmationModel)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchRunModel)
                .where(ResearchRunModel.derivation_kind == "revision")
            )
            == 0
        )


def test_concurrent_confirmation_creates_one_run(runtime: dict[str, object]) -> None:
    feedback = _create_feedback(runtime, "graph", key="feedback-concurrent")
    plan = _create_plan(runtime, feedback.json()["data"]["id"], key="plan-concurrent")
    path = f"/api/revision-plans/{plan.json()['data']['id']}/confirm"

    def confirm() -> tuple[int, str]:
        client = TestClient(runtime["app"], base_url="https://testserver")
        client.cookies.set(
            settings.SESSION_COOKIE_NAME, str(runtime["owner_credential"])
        )
        response = client.post(
            path,
            headers={
                "X-CSRF-Token": str(runtime["owner_csrf"]),
                "Idempotency-Key": "confirm-concurrent",
            },
            json={"expected_plan_version": 1},
        )
        return response.status_code, response.json()["data"]["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: confirm(), range(2)))
    assert {status for status, _ in results} == {201}
    assert len({run_id for _, run_id in results}) == 1
    factory = runtime["factory"]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(RevisionPlanConfirmationModel)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchRunModel)
                .where(ResearchRunModel.derivation_kind == "revision")
            )
            == 1
        )


def test_confirmation_idempotency_key_is_project_scoped(
    runtime: dict[str, object],
) -> None:
    first_feedback = _create_feedback(
        runtime, "graph", key="feedback-project-key-first"
    )
    second_feedback = _create_feedback(
        runtime, "paper_summary", key="feedback-project-key-second"
    )
    first_plan = _create_plan(
        runtime,
        first_feedback.json()["data"]["id"],
        key="plan-project-key-first",
    )
    second_plan = _create_plan(
        runtime,
        second_feedback.json()["data"]["id"],
        key="plan-project-key-second",
    )
    paths = (
        f"/api/revision-plans/{first_plan.json()['data']['id']}/confirm",
        f"/api/revision-plans/{second_plan.json()['data']['id']}/confirm",
    )

    def confirm(path: str) -> tuple[int, dict[str, object]]:
        client = TestClient(runtime["app"], base_url="https://testserver")
        client.cookies.set(
            settings.SESSION_COOKIE_NAME, str(runtime["owner_credential"])
        )
        response = client.post(
            path,
            headers={
                "X-CSRF-Token": str(runtime["owner_csrf"]),
                "Idempotency-Key": "shared-confirmation-key",
            },
            json={"expected_plan_version": 1},
        )
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(confirm, paths))
    assert {status for status, _ in results} == {201, 409}
    conflict = next(payload for status, payload in results if status == 409)
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"

    factory = runtime["factory"]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(RevisionPlanConfirmationModel)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ResearchRunModel)
                .where(ResearchRunModel.derivation_kind == "revision")
            )
            == 1
        )


def test_feedback_plan_and_confirmation_are_database_immutable(
    runtime: dict[str, object],
) -> None:
    feedback = _create_feedback(runtime, "graph", key="feedback-immutable")
    plan = _create_plan(runtime, feedback.json()["data"]["id"], key="plan-immutable")
    client = runtime["client"]
    assert isinstance(client, TestClient)
    confirmation = client.post(
        f"/api/revision-plans/{plan.json()['data']['id']}/confirm",
        headers={
            "X-CSRF-Token": str(runtime["owner_csrf"]),
            "Idempotency-Key": "confirm-immutable",
        },
        json={"expected_plan_version": 1},
    )
    assert confirmation.status_code == 201, confirmation.text
    factory = runtime["factory"]
    cases = (
        update(UserFeedbackModel)
        .where(UserFeedbackModel.id == UUID(feedback.json()["data"]["id"]))
        .values(summary="mutated"),
        update(RevisionPlanModel)
        .where(RevisionPlanModel.id == UUID(plan.json()["data"]["id"]))
        .values(plan_hash=HASH_A),
        update(RevisionPlanConfirmationModel)
        .where(
            RevisionPlanConfirmationModel.revision_plan_id
            == UUID(plan.json()["data"]["id"])
        )
        .values(request_hash=HASH_A),
    )
    for statement in cases:
        with pytest.raises(DatabaseError), factory() as session, session.begin():
            session.execute(statement)
