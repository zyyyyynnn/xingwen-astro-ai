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
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from threading import Event, Lock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest

from db_bootstrap import reset_current_schema
from sqlalchemy import Engine, func, select

from app.config import settings
from app.db.models import (
    ResearchContractDraftModel,
    ModelExecutionModel,
    ResearchProjectModel,
    RunStepModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_project,
    persist_authoring_models,
)
from app.main import _load_case_manifests, create_app
from app.services.artifacts import ArtifactReadService
from app.services.research import ResearchApplicationService
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.services.research_planner import PlannerResult
from app.schemas.core import (
    PlannerClarificationRequired,
    PlannerDraftReady,
    ResearchContractInput,
    ResearchTurnResult,
)
from app.services.resource_authority import PersistentResourceAuthority
from app.services.snapshots import InMemorySnapshotStore, SnapshotService
from app.test_support.bootstrap import bootstrap_fixture_artifacts
from app.workflow.store import PersistentWorkflowStore


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 7, 22, 8, tzinfo=UTC)


class StubResearchPlanner:
    """Deterministic planner for DB integration; no provider call is faked in HTTP."""

    def prepare_request(self, **values: object) -> ModelExecutionRequest:
        return ModelExecutionRequest(
            provider="test",
            requested_model="planner-fixture",
            explicit_revision="planner-fixture-1",
            prompt_name="research_contract_planner",
            prompt_version="1.0.0",
            prompt_hash="sha256:" + "a" * 64,
            prompt="test planner",
            input_payload={
                "source": "integration-test",
                "message": values.get("message"),
                "answer_to_question_id": values.get("answer_to_question_id"),
            },
            parameters={"temperature": 0},
        )

    def execute(self, request: ModelExecutionRequest) -> PlannerResult:
        if request.input_payload.get("message") == "Force metadata failure":
            raise ModelExecutionError(
                "MODEL_RESPONSE_INVALID",
                "研究助手返回了无法验证的结果。",
                output_hash="sha256:" + "c" * 64,
                token_usage={"prompt_tokens": 7, "completion_tokens": 3},
                latency_ms=9,
                provider_request_id="provider-failed-request",
            )
        if (
            request.input_payload.get("message") == "Clarify the original stellar study"
            and request.input_payload.get("answer_to_question_id") is None
        ):
            output = PlannerClarificationRequired(
                outcome="clarification_required",
                public_analysis="当前研究时间范围会改变数据选择，需要先向用户澄清。",
                assistant_message="请补充时间范围后继续。",
                question_id="time_range",
                question="是否只研究 2020 年之后的数据？",
            )
        else:
            output = PlannerDraftReady(
                outcome="draft_ready",
                public_analysis="已核对研究对象、目标字段与允许的数据来源。",
                assistant_message="研究协议草案已准备好，请检查后确认。",
                contract=ResearchContractInput.model_validate(_contract_input()),
            )
        return PlannerResult(
            output=output,
            request=request,
            response=ModelExecutionResponse(
                payload={"outcome": "draft_ready"},
                output_hash="sha256:" + "b" * 64,
                token_usage={"prompt_tokens": 10, "completion_tokens": 20},
                latency_ms=2,
                provider_request_id="test-provider-request",
            ),
        )


class PersistenceFailingResearchService(ResearchApplicationService):
    def _persist_successful_turn(
        self,
        *,
        project_id: str,
        project_uuid: UUID,
        session_id: str,
        execution_id: UUID,
        lease_token: UUID,
        request_hash: str,
        research_intent: str,
        planner_result: PlannerResult,
    ) -> ResearchTurnResult:
        del (
            project_id,
            project_uuid,
            session_id,
            execution_id,
            lease_token,
            request_hash,
            research_intent,
            planner_result,
        )
        raise RuntimeError("simulated final persistence failure")


class BlockingFirstResearchPlanner(StubResearchPlanner):
    """Hold the first provider call so a second Turn can test Project single-flight."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self._calls = 0

    def execute(self, request: ModelExecutionRequest) -> PlannerResult:
        with self._lock:
            self._calls += 1
            should_block = self._calls == 1
        if should_block:
            self.started.set()
            if not self.release.wait(timeout=10):
                raise AssertionError(
                    "timed out waiting to release the first planner call"
                )
        return super().execute(request)


class BlockingFailureResearchPlanner(StubResearchPlanner):
    """Fail only after the test has expired this worker's persisted lease."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def execute(self, request: ModelExecutionRequest) -> PlannerResult:
        del request
        self.started.set()
        if not self.release.wait(timeout=10):
            raise AssertionError("timed out waiting to release the planner failure")
        raise ModelExecutionError(
            "MODEL_PROVIDER_TIMEOUT",
            "研究助手响应超时，请稍后重试。",
        )


def _contract_input() -> dict[str, object]:
    return {
        "research_goal": "Integrate exoplanet candidates and host-star parameters",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical", "document_source_policy": "disabled"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
        "output_requirements": ["dataset", "field_dictionary", "graph"],
        "evidence_requirements": {"require_locator": True},
        "quality_constraints": {"source_completeness_min": 1.0},
    }


@pytest.fixture()
def runtime() -> Iterator[dict[str, object]]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine: Engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)

    app = create_app()
    store = PersistentWorkflowStore(factory)
    app.state.workflow_store = store
    app.state.artifact_read_service = ArtifactReadService(factory)
    app.state.research_service = ResearchApplicationService(
        factory=factory,
        workflow_store=store,
        manifests=_load_case_manifests(),
        planner=StubResearchPlanner(),
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
            "research_service": app.state.research_service,
            "owner_session_id": owner.id,
            "owner_csrf": owner_csrf,
            "other_credential": other_credential,
            "other_csrf": other_csrf,
            "project_id": str(project_id),
            "draft_id": str(draft_id),
        }
    finally:
        engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


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
    assert events.json()["data"][0]["activity_kind"] == "status"
    assert events.json()["data"][0]["activity_phase"] == "queued"

    saved = client.put(
        f"/api/projects/{project_id}/workspace-snapshot",
        headers={**csrf, "If-Match": "0"},
        json={"layout_preset": "comparative", "active_run_id": run_id},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["revision"] == 1
    reloaded = client.get(f"/api/projects/{project_id}/workspace-snapshot")
    assert reloaded.json()["data"] == saved.json()["data"]


def test_research_turn_persists_public_thread_and_idempotent_model_execution(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    catalog = client.get(f"/api/projects/{project_id}/research-catalog")
    assert catalog.status_code == 200
    catalog_data = catalog.json()["data"]
    assert catalog_data["case_key"] == "exoplanet_host_star"
    assert {item["value"] for item in catalog_data["target_objects"]} == {
        "exoplanet_candidate",
        "host_star",
    }
    assert len(catalog_data["requested_fields"]) == 15
    assert {item["group"] for item in catalog_data["output_requirements"]} == {
        "common",
        "advanced",
    }
    headers = {**csrf, "Idempotency-Key": "research-turn-1"}
    body = {"message": "Compare the selected host stars"}

    first = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers=headers,
        json=body,
    )
    assert first.status_code == 200
    result = first.json()["data"]
    assert result["outcome"] == "draft_ready"
    assert [entry["kind"] for entry in result["entries"]] == [
        "user_message",
        "assistant_reasoning",
        "assistant_message",
    ]
    assert result["entries"][1]["public_content"] == (
        "已核对研究对象、目标字段与允许的数据来源。"
    )
    assert all(
        "Private reasoning" not in entry["public_content"]
        for entry in result["entries"]
    )
    assert result["active_draft_id"]

    listed = client.get(f"/api/projects/{project_id}/research-turns")
    assert listed.status_code == 200
    assert [entry["kind"] for entry in listed.json()["data"]] == [
        "user_message",
        "assistant_reasoning",
        "assistant_message",
    ]
    first_page = client.get(
        f"/api/projects/{project_id}/research-turns",
        params={"limit": 1},
    )
    thread_cursor = first_page.json()["page"]["next_cursor"]
    assert thread_cursor is not None and not thread_cursor.isdigit()
    next_page = client.get(
        f"/api/projects/{project_id}/research-turns",
        params={"limit": 1, "cursor": thread_cursor},
    )
    assert next_page.status_code == 200
    tampered_cursor = thread_cursor[:-1] + ("A" if thread_cursor[-1] != "A" else "B")
    rejected_cursor = client.get(
        f"/api/projects/{project_id}/research-turns",
        params={"limit": 1, "cursor": tampered_cursor},
    )
    assert rejected_cursor.status_code == 400
    assert rejected_cursor.json()["code"] == "INVALID_CURSOR"

    project = client.get(f"/api/projects/{project_id}")
    assert project.json()["data"]["active_draft_id"] == result["active_draft_id"]

    with factory() as session:  # type: ignore[operator]
        execution = session.get(ModelExecutionModel, UUID(result["model_execution_id"]))
        assert execution is not None
        assert execution.status == "succeeded"
        assert execution.output_hash == "sha256:" + "b" * 64
        assert execution.prompt_snapshot == "test planner"
        assert execution.input_snapshot["message"] == body["message"]
        assert execution.parameters_snapshot == {"temperature": 0}
        assert execution.output_snapshot is not None
        assert execution.output_snapshot["outcome"] == "draft_ready"
        assert execution.token_usage == {"prompt_tokens": 10, "completion_tokens": 20}

    replay = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers=headers,
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"] == result

    conflict = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers=headers,
        json={"message": "A different research message"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_research_turn_rejects_a_second_active_execution_for_the_project(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    workflow_store = runtime["workflow_store"]
    planner = BlockingFirstResearchPlanner()
    client.app.state.research_service = ResearchApplicationService(
        factory=factory,  # type: ignore[arg-type]
        workflow_store=workflow_store,  # type: ignore[arg-type]
        manifests=_load_case_manifests(),
        planner=planner,
    )
    project_id = runtime["project_id"]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}

    def submit_first_turn():
        return client.post(
            f"/api/projects/{project_id}/research-turns",
            headers={**csrf, "Idempotency-Key": "active-turn-first"},
            json={"message": "First active research Turn"},
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(submit_first_turn)
        assert planner.started.wait(timeout=5)
        try:
            second = client.post(
                f"/api/projects/{project_id}/research-turns",
                headers={**csrf, "Idempotency-Key": "active-turn-second"},
                json={"message": "Second concurrent research Turn"},
            )
        finally:
            planner.release.set()
        first = first_future.result(timeout=10)

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "RESEARCH_ASSISTANT_BUSY"
    thread = client.get(f"/api/projects/{project_id}/research-turns")
    assert thread.status_code == 200
    assert all(
        entry["public_content"] != "Second concurrent research Turn"
        for entry in thread.json()["data"]
    )


def test_research_turn_reclaims_an_expired_execution_lease(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    project_id = UUID(runtime["project_id"])  # type: ignore[arg-type]
    stale_id = uuid4()
    with factory() as session, session.begin():  # type: ignore[operator]
        session.add(
            ModelExecutionModel(
                id=stale_id,
                project_id=project_id,
                provider="test",
                requested_model="abandoned-planner",
                explicit_revision="abandoned-planner-1",
                prompt_name="research_contract_planner",
                prompt_version="1.0.0",
                prompt_hash="sha256:" + "a" * 64,
                prompt_snapshot="abandoned prompt",
                input_hash="sha256:" + "b" * 64,
                input_snapshot={"message": "abandoned turn"},
                parameters_hash="sha256:" + "c" * 64,
                parameters_snapshot={"temperature": 0},
                status="running",
                idempotency_key="abandoned-turn",
                request_hash="sha256:" + "d" * 64,
                lease_token=uuid4(),
                lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
                created_at=datetime.now(UTC) - timedelta(minutes=6),
            )
        )

    response = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={
            "X-CSRF-Token": runtime["owner_csrf"],
            "Idempotency-Key": "turn-after-abandoned-worker",
        },
        json={"message": "Continue after the interrupted worker"},
    )

    assert response.status_code == 200, response.text
    with factory() as session:  # type: ignore[operator]
        abandoned = session.get(ModelExecutionModel, stale_id)
        assert abandoned is not None
        assert abandoned.status == "failed"
        assert abandoned.error_code == "MODEL_EXECUTION_LEASE_EXPIRED"
        assert abandoned.finished_at is not None


def test_expired_worker_cannot_commit_a_failure_terminal_state(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    workflow_store = runtime["workflow_store"]
    planner = BlockingFailureResearchPlanner()
    client.app.state.research_service = ResearchApplicationService(
        factory=factory,  # type: ignore[arg-type]
        workflow_store=workflow_store,  # type: ignore[arg-type]
        manifests=_load_case_manifests(),
        planner=planner,
    )
    project_id = runtime["project_id"]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}

    def submit_expiring_turn():
        return client.post(
            f"/api/projects/{project_id}/research-turns",
            headers={**csrf, "Idempotency-Key": "expired-failing-worker"},
            json={"message": "Let this provider worker expire"},
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(submit_expiring_turn)
        assert planner.started.wait(timeout=5)
        with factory() as session, session.begin():  # type: ignore[operator]
            execution = session.scalar(
                select(ModelExecutionModel).where(
                    ModelExecutionModel.idempotency_key == "expired-failing-worker"
                )
            )
            assert execution is not None
            execution.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        planner.release.set()
        failed = pending.result(timeout=10)

    assert failed.status_code == 503
    with factory() as session:  # type: ignore[operator]
        stale = session.scalar(
            select(ModelExecutionModel).where(
                ModelExecutionModel.idempotency_key == "expired-failing-worker"
            )
        )
        assert stale is not None
        assert stale.status == "running"
        assert stale.error_code is None

    client.app.state.research_service = ResearchApplicationService(
        factory=factory,  # type: ignore[arg-type]
        workflow_store=workflow_store,  # type: ignore[arg-type]
        manifests=_load_case_manifests(),
        planner=StubResearchPlanner(),
    )
    recovered = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "turn-after-expired-failure"},
        json={"message": "Continue after the stale failure"},
    )
    assert recovered.status_code == 200, recovered.text
    with factory() as session:  # type: ignore[operator]
        stale = session.scalar(
            select(ModelExecutionModel).where(
                ModelExecutionModel.idempotency_key == "expired-failing-worker"
            )
        )
        assert stale is not None
        assert stale.status == "failed"
        assert stale.error_code == "MODEL_EXECUTION_LEASE_EXPIRED"


def test_final_persistence_failure_releases_the_project_execution_slot(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    workflow_store = runtime["workflow_store"]
    client.app.state.research_service = PersistenceFailingResearchService(
        factory=factory,  # type: ignore[arg-type]
        workflow_store=workflow_store,  # type: ignore[arg-type]
        manifests=_load_case_manifests(),
        planner=StubResearchPlanner(),
    )
    project_id = runtime["project_id"]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}

    failed = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "persistence-failure"},
        json={"message": "Persist this provider result"},
    )
    assert failed.status_code == 503
    assert failed.json()["code"] == "MODEL_RESULT_PERSISTENCE_FAILED"

    with factory() as session:  # type: ignore[operator]
        execution = session.scalar(
            select(ModelExecutionModel).where(
                ModelExecutionModel.idempotency_key == "persistence-failure"
            )
        )
        assert execution is not None
        assert execution.status == "failed"

    client.app.state.research_service = ResearchApplicationService(
        factory=factory,  # type: ignore[arg-type]
        workflow_store=workflow_store,  # type: ignore[arg-type]
        manifests=_load_case_manifests(),
        planner=StubResearchPlanner(),
    )
    recovered = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "after-persistence-failure"},
        json={"message": "A new Turn after persistence recovery"},
    )
    assert recovered.status_code == 200, recovered.text


def test_failed_model_execution_keeps_safe_provider_metadata(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    factory = runtime["factory"]
    project_id = runtime["project_id"]
    response = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={
            "X-CSRF-Token": runtime["owner_csrf"],
            "Idempotency-Key": "failed-model-metadata",
        },
        json={"message": "Force metadata failure"},
    )
    assert response.status_code == 503

    with factory() as session:  # type: ignore[operator]
        execution = session.scalar(
            select(ModelExecutionModel).where(
                ModelExecutionModel.idempotency_key == "failed-model-metadata"
            )
        )
        assert execution is not None
        assert execution.status == "failed"
        assert execution.output_hash == "sha256:" + "c" * 64
        assert execution.token_usage == {
            "prompt_tokens": 7,
            "completion_tokens": 3,
        }
        assert execution.latency_ms == 9
        assert execution.provider_request_id == "provider-failed-request"


def test_clarification_answer_keeps_the_original_research_intent(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    original_intent = "Clarify the original stellar study"

    first = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "clarification-root"},
        json={"message": original_intent},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["outcome"] == "clarification_required"
    question = next(
        entry
        for entry in first.json()["data"]["entries"]
        if entry["kind"] == "clarification_question"
    )

    answered = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "clarification-answer"},
        json={
            "message": "是，只研究 2020 年之后的数据。",
            "answer_to_question_id": question["id"],
        },
    )
    assert answered.status_code == 200, answered.text
    draft_id = answered.json()["data"]["active_draft_id"]
    draft = client.get(f"/api/contracts/drafts/{draft_id}")
    assert draft.status_code == 200
    assert draft.json()["data"]["intent"] == original_intent


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
    run_id = created.json()["data"]["id"]

    published = bootstrap_fixture_artifacts(
        session_id=str(runtime["owner_session_id"]),
        run_id=run_id,
        factory=runtime["factory"],  # type: ignore[arg-type]
        research_service=runtime["research_service"],  # type: ignore[arg-type]
        workflow_store=runtime["workflow_store"],  # type: ignore[arg-type]
    )
    assert published.evidence_ids
    version_id = published.artifact_version_id
    evidence_id = published.evidence_ids[0]

    version = client.get(f"/api/artifact-versions/{version_id}")
    assert version.status_code == 200
    assert version.json()["data"]["source_mode"] == "fixture"
    assert evidence_id in version.json()["data"]["evidence_ids"]
    assert version.json()["data"]["content"]["kind"] == "dataset"

    shared = client.post(
        f"/api/projects/{project_id}/shares",
        headers=csrf,
        json={
            "title": "Real Compose and Browser Integration dataset evidence",
            "artifact_version_ids": [version_id],
            "evidence_ids": [evidence_id],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "redaction_policy": "redacted_public_snapshot",
        },
    )
    assert shared.status_code == 201, shared.text
    public = client.get(shared.json()["data"]["share_url"])
    assert public.status_code == 200
    assert public.json()["data"]["artifact_versions"][0]["source_mode"] == "fixture"
    assert public.json()["data"]["evidence"][0]["id"] == evidence_id


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


@pytest.mark.parametrize(
    ("output", "expected_steps"),
    [
        ("dataset", ("planning", "fetching_data", "cleaning_data")),
        ("paper_collection", ("planning", "searching_papers")),
        (
            "paper_summary",
            ("planning", "searching_papers", "summarizing_papers"),
        ),
        (
            "graph",
            (
                "planning",
                "searching_papers",
                "summarizing_papers",
                "reasoning_literature",
                "building_graph",
            ),
        ),
    ],
)
def test_contract_driven_run_plan_persists_only_the_required_steps(
    runtime: dict[str, object],
    output: str,
    expected_steps: tuple[str, ...],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    suffix = output.replace("_", "-")
    project = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": f"run-plan-project-{suffix}"},
        json={"name": f"Run plan {output}", "case_key": "exoplanet_host_star"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]
    contract_input = _contract_input()
    contract_input["output_requirements"] = [output]
    draft = client.post(
        f"/api/projects/{project_id}/contract-drafts",
        headers={**csrf, "Idempotency-Key": f"run-plan-draft-{suffix}"},
        json={"intent": f"Produce {output}", "contract": contract_input},
    )
    assert draft.status_code == 201, draft.text
    confirmed = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": f"run-plan-contract-{suffix}"},
        json={
            "draft_id": draft.json()["data"]["id"],
            "expected_draft_version": 1,
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    created = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": f"run-plan-run-{suffix}"},
        json={
            "contract_id": confirmed.json()["data"]["id"],
            "execution_mode": "live",
        },
    )
    assert created.status_code == 201, created.text

    steps = client.get(f"/api/runs/{created.json()['data']['id']}/steps")
    assert steps.status_code == 200, steps.text
    persisted = steps.json()["data"]
    assert tuple(item["key"] for item in persisted) == expected_steps
    assert tuple(item["position"] for item in persisted) == tuple(
        range(len(expected_steps))
    )
    factory = runtime["factory"]
    with factory() as session:  # type: ignore[operator]
        stored_steps = tuple(
            session.scalars(
                select(RunStepModel)
                .where(RunStepModel.run_id == UUID(created.json()["data"]["id"]))
                .order_by(RunStepModel.position.asc())
            )
        )
    assert tuple(step.enter_status for step in stored_steps) == expected_steps
    assert tuple(step.success_status for step in stored_steps) == (
        *expected_steps[1:],
        "completed",
    )


def test_contract_driven_run_plan_rejects_unsupported_output_without_a_run(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "unsupported-output-project"},
        json={"name": "Unsupported output", "case_key": "exoplanet_host_star"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["data"]["id"]
    contract_input = _contract_input()
    contract_input["output_requirements"] = ["export"]
    draft = client.post(
        f"/api/projects/{project_id}/contract-drafts",
        headers={**csrf, "Idempotency-Key": "unsupported-output-draft"},
        json={"intent": "Produce an unsupported export", "contract": contract_input},
    )
    assert draft.status_code == 201, draft.text
    confirmed = client.post(
        f"/api/projects/{project_id}/contracts",
        headers={**csrf, "Idempotency-Key": "unsupported-output-contract"},
        json={
            "draft_id": draft.json()["data"]["id"],
            "expected_draft_version": 1,
        },
    )
    assert confirmed.status_code == 201, confirmed.text

    rejected = client.post(
        f"/api/projects/{project_id}/runs",
        headers={**csrf, "Idempotency-Key": "unsupported-output-run"},
        json={
            "contract_id": confirmed.json()["data"]["id"],
            "execution_mode": "live",
        },
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == "RUN_PLAN_UNSUPPORTED_OUTPUT"
    assert client.get(f"/api/projects/{project_id}").json()["data"][
        "latest_run_id"
    ] is None


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


def test_project_reads_include_a_batchable_thread_summary(
    runtime: dict[str, object],
) -> None:
    client: TestClient = runtime["client"]  # type: ignore[assignment]
    csrf = {"X-CSRF-Token": runtime["owner_csrf"]}
    project_id = runtime["project_id"]
    question_turn = client.post(
        f"/api/projects/{project_id}/research-turns",
        headers={**csrf, "Idempotency-Key": "project-summary-question"},
        json={"message": "Clarify the original stellar study"},
    )
    assert question_turn.status_code == 200, question_turn.text
    assert question_turn.json()["data"]["outcome"] == "clarification_required"

    other = client.post(
        "/api/projects",
        headers={**csrf, "Idempotency-Key": "project-summary-other"},
        json={"name": "Other project", "case_key": "exoplanet_host_star"},
    )
    assert other.status_code == 201, other.text

    listing = client.get("/api/projects", params={"limit": 100})
    assert listing.status_code == 200, listing.text
    listed_project = next(
        item for item in listing.json()["data"] if item["id"] == project_id
    )
    assert listed_project["thread_summary"] == {
        "has_thread_entries": True,
        "latest_thread_actor": "assistant",
        "has_unanswered_clarification": True,
    }
    assert client.get(f"/api/projects/{project_id}").json()["data"][
        "thread_summary"
    ] == listed_project["thread_summary"]

    other_project = next(
        item for item in listing.json()["data"] if item["id"] == other.json()["data"]["id"]
    )
    assert other_project["thread_summary"] == {
        "has_thread_entries": False,
        "latest_thread_actor": None,
        "has_unanswered_clarification": False,
    }


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
