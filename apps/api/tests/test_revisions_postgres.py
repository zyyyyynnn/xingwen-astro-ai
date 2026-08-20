"""PostgreSQL and HTTP integration tests for Feedback and revision Runs."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from db_bootstrap import reset_current_schema
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
from app.schemas.core import (
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.security import InMemoryRateLimiter
from app.services.feedback_targets import (
    ArtifactVersionTargetReadPort,
    FeedbackTargetAuthority,
)
from app.services.revisions import RevisionApplicationService
from app.workflow.run_plan import compile_run_plan
from artifact_publication_test_support import publish_reference_dataset
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
ARTIFACT_STEP = {
    "dataset": "cleaning_data",
    "field_dictionary": "cleaning_data",
    "source_collection": "fetching_data",
    "paper_collection": "searching_papers",
    "paper_summary": "summarizing_papers",
    "literature_claims": "reasoning_literature",
    "literature_relations": "reasoning_literature",
    "reasoning_traces": "reasoning_literature",
    "graph": "building_graph",
}
CONTRACT_INPUT = ResearchContractInput.model_validate(
    {
        "research_goal": "Validate immutable feedback revision orchestration",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"year_from": 2015, "max_candidates": 20},
        "output_requirements": list(KINDS),
        "evidence_requirements": {"require_locator": True},
        "quality_constraints": {"source_completeness_min": 1.0},
    }
)
CONTRACT_CONTENT = CONTRACT_INPUT.model_dump(mode="json")
CONTRACT_HASH = compute_research_contract_content_hash(CONTRACT_INPUT)


class _FrozenRevisionArtifactVersions(ArtifactVersionTargetReadPort):
    """Keep revision-closure fixtures focused on their frozen Run graph."""

    def __init__(
        self,
        *,
        version_ids: dict[str, UUID],
        owner_session_id: str,
    ) -> None:
        self._version_ids = {
            kind: {version_id} for kind, version_id in version_ids.items()
        }
        self._owner_session_id = owner_session_id

    def allow(self, version_ids: dict[str, UUID]) -> None:
        for kind, version_id in version_ids.items():
            self._version_ids.setdefault(kind, set()).add(version_id)

    async def validate_version(
        self, *, version_id: str, artifact_kind: str, session_id: str
    ) -> None:
        allowed = self._version_ids.get(artifact_kind, set())
        if session_id != self._owner_session_id or UUID(version_id) not in allowed:
            raise AssertionError("revision fixture received an unknown ArtifactVersion")


def _seed_completed_steps(
    session,
    *,
    run: ResearchRunModel,
    contract_input: ResearchContractInput,
    producer_name: str,
) -> dict[str, tuple[UUID, UUID, UUID]]:
    executions: dict[str, tuple[UUID, UUID, UUID]] = {}
    for position, definition in enumerate(compile_run_plan(contract_input)):
        step = RunStepModel(
            id=uuid4(),
            run_id=run.id,
            position=position,
            key=definition.key,
            label=definition.label,
            enter_status=definition.enter_status,
            success_status=definition.success_status,
            max_attempts=definition.max_attempts,
            task_id=definition.task_id,
            skill_id=definition.skill_id,
            depends_on_step_keys=list(definition.depends_on_step_keys),
            status="completed",
            progress=100,
            public_message="Completed",
            created_at=NOW,
        )
        session.add(step)
        session.flush()
        attempt = StepAttemptModel(
            id=uuid4(),
            run_step_id=step.id,
            attempt_number=1,
            idempotency_key=f"{producer_name}-attempt-{step.id}",
            status="completed",
            retryable=False,
            started_at=NOW,
            finished_at=NOW,
            created_at=NOW,
        )
        session.add(attempt)
        session.flush()
        producer = ProducerExecutionModel(
            id=uuid4(),
            run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=attempt.id,
            step_key=step.key,
            idempotency_key=f"{producer_name}-producer-{step.id}",
            lease_generation=0,
            producer_type="pipeline",
            producer_name=producer_name,
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
        executions[step.key] = (step.id, attempt.id, producer.id)
    return executions


@pytest.fixture()
def runtime(monkeypatch: pytest.MonkeyPatch):
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower()
    reset_current_schema(TEST_DATABASE_URL)
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(TEST_DATABASE_URL))
    app = create_app()
    owner, owner_credential, owner_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    other, other_credential, other_csrf = app.state.session_service.create(
        now=datetime.now(UTC)
    )
    factory = app.state.db_session_factory

    ids = {name: uuid4() for name in ("project", "contract", "run")}
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
        draft = build_contract_draft(
            project,
            content=CONTRACT_CONTENT,
            created_at=NOW,
            updated_at=NOW,
        )
        contract = build_research_contract(
            project,
            draft,
            contract_id=ids["contract"],
            content_hash=CONTRACT_HASH,
            content=CONTRACT_CONTENT,
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
        executions = _seed_completed_steps(
            session,
            run=run,
            contract_input=CONTRACT_INPUT,
            producer_name="revision-test-seed",
        )
        for kind in KINDS:
            step_id, attempt_id, producer_id = executions[ARTIFACT_STEP[kind]]
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
                run_step_id=step_id,
                step_attempt_id=attempt_id,
                producer_execution_id=producer_id,
                version_number=1,
                publication_key=f"revision-{kind}-initial",
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

    artifact_version_reader = _FrozenRevisionArtifactVersions(
        version_ids=version_ids,
        owner_session_id=owner.id,
    )
    app.state.revision_service = RevisionApplicationService(
        factory=factory,
        workflow_store=app.state.workflow_store,
        target_authority=FeedbackTargetAuthority(
            app.state.artifact_read_service,
            paper_summary_reader=app.state.paper_summary_read_service,
            artifact_version_reader=artifact_version_reader,
        ),
    )

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
            "artifact_version_reader": artifact_version_reader,
        }
    finally:
        client.__exit__(None, None, None)
    reset_current_schema(TEST_DATABASE_URL)


def _feedback_body(runtime: dict[str, object], kind: str) -> dict[str, object]:
    version_id = str(runtime["version_ids"][kind])  # type: ignore[index]
    artifact_id = str(runtime["artifact_ids"][kind])  # type: ignore[index]
    return {
        "expected_version_number": 1,
        "target_type": "artifact_version",
        "target_id": version_id,
        "target_locator": {
            "artifact_id": artifact_id,
            "artifact_version_id": version_id,
        },
        "category": "correction",
        "summary": "The published value needs correction",
        "requested_change": "Recompute this result from the frozen inputs",
    }


def _seed_partial_revision_parent(
    runtime: dict[str, object],
    *,
    outputs: tuple[str, ...],
    parent_kinds: tuple[str, ...],
    unrelated_kinds: tuple[str, ...],
) -> dict[str, object]:
    contract_input = ResearchContractInput.model_validate(
        {**CONTRACT_CONTENT, "output_requirements": list(outputs)}
    )
    content = contract_input.model_dump(mode="json")
    ids = {name: uuid4() for name in ("project", "contract", "parent_run", "other_run")}
    artifact_ids = {kind: uuid4() for kind in (*parent_kinds, *unrelated_kinds)}
    version_ids = {kind: uuid4() for kind in (*parent_kinds, *unrelated_kinds)}
    factory = runtime["factory"]
    with factory() as session, session.begin():
        project = build_research_project(
            project_id=ids["project"],
            session_id=str(runtime["owner_session_id"]),
            name="Partial revision contract",
            case_key="exoplanet_host_star",
            created_at=NOW,
            updated_at=NOW,
        )
        draft = build_contract_draft(
            project, content=content, created_at=NOW, updated_at=NOW
        )
        contract = build_research_contract(
            project,
            draft,
            contract_id=ids["contract"],
            content_hash=compute_research_contract_content_hash(contract_input),
            content=content,
            created_at=NOW,
        )
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )

        def seed_run(
            prefix: str,
            *,
            revision: int,
            run_contract: ResearchContractInput,
        ) -> tuple[UUID, dict[str, tuple[UUID, UUID, UUID]]]:
            run_id = ids[f"{prefix}_run"]
            run = ResearchRunModel(
                id=run_id,
                project_id=project.id,
                contract_id=contract.id,
                execution_mode="live",
                status="completed",
                progress=100,
                derivation_kind="original",
                latest_event_sequence=0,
                revision=revision,
                idempotency_key=f"{prefix}-run-{run_id}",
                request_hash=HASH_B,
                created_at=NOW,
                updated_at=NOW,
            )
            session.add(run)
            session.flush()
            return run_id, _seed_completed_steps(
                session,
                run=run,
                contract_input=run_contract,
                producer_name=f"revision-{prefix}-seed",
            )

        parent_execution = seed_run("parent", revision=7, run_contract=contract_input)
        other_execution = seed_run("other", revision=1, run_contract=CONTRACT_INPUT)
        for kind in (*parent_kinds, *unrelated_kinds):
            execution = parent_execution if kind in parent_kinds else other_execution
            step_id, attempt_id, producer_id = execution[1][ARTIFACT_STEP[kind]]
            artifact = ResearchArtifactModel(
                id=artifact_ids[kind],
                project_id=project.id,
                kind=kind,
                title=kind,
                logical_key=f"partial.{kind}",
                created_at=NOW,
            )
            session.add(artifact)
            session.flush()
            version = ArtifactVersionModel(
                id=version_ids[kind],
                artifact_id=artifact.id,
                project_id=project.id,
                created_by_run_id=execution[0],
                run_step_id=step_id,
                step_attempt_id=attempt_id,
                producer_execution_id=producer_id,
                version_number=1,
                publication_key=f"partial-{kind}-initial",
                schema_version="2.0.0",
                content={"kind": kind},
                content_hash=HASH_C,
                input_hash=HASH_B,
                source_mode="live",
                producer={"name": "revision-partial-seed"},
                source_snapshot_ids=[],
                evidence_ids=[],
                created_at=NOW,
            )
            session.add(version)
            session.flush()
            artifact.latest_version_id = version.id
    artifact_version_reader = runtime["artifact_version_reader"]
    assert isinstance(artifact_version_reader, _FrozenRevisionArtifactVersions)
    artifact_version_reader.allow(version_ids)
    return {
        **runtime,
        "project_id": str(ids["project"]),
        "parent_run_id": str(ids["parent_run"]),
        "artifact_ids": artifact_ids,
        "version_ids": version_ids,
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
        json=_feedback_body(runtime, kind),
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
        "dataset": {
            "dataset",
            "field_dictionary",
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
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
        "literature_relations": {
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
        "reasoning_traces": {
            "literature_claims",
            "literature_relations",
            "reasoning_traces",
            "graph",
        },
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


@pytest.mark.parametrize(
    (
        "outputs",
        "parent_kinds",
        "unrelated_kinds",
        "feedback_kind",
        "recomputed_kinds",
        "steps",
    ),
    (
        (
            ("dataset", "field_dictionary", "source_collection"),
            ("dataset", "field_dictionary", "source_collection"),
            ("graph",),
            "dataset",
            ("dataset", "field_dictionary"),
            ("planning", "cleaning_data"),
        ),
        (
            ("paper_collection", "paper_summary"),
            ("paper_collection", "paper_summary"),
            ("literature_relations", "graph"),
            "paper_collection",
            ("paper_collection", "paper_summary"),
            ("planning", "searching_papers", "summarizing_papers"),
        ),
    ),
)
def test_revision_steps_only_follow_actual_parent_contract_publications(
    runtime: dict[str, object],
    outputs: tuple[str, ...],
    parent_kinds: tuple[str, ...],
    unrelated_kinds: tuple[str, ...],
    feedback_kind: str,
    recomputed_kinds: tuple[str, ...],
    steps: tuple[str, ...],
) -> None:
    scoped = _seed_partial_revision_parent(
        runtime,
        outputs=outputs,
        parent_kinds=parent_kinds,
        unrelated_kinds=unrelated_kinds,
    )
    feedback = _create_feedback(scoped, feedback_kind, key="partial-feedback")
    assert feedback.status_code == 201, feedback.text
    plan = _create_plan(scoped, feedback.json()["data"]["id"], key="partial-plan")
    assert plan.status_code == 201, plan.text
    data = plan.json()["data"]
    recompute = {
        item["artifact_kind"]: item["step_key"]
        for item in data["version_decisions"]
        if item["decision"] == "recompute"
    }
    assert set(recompute) == set(recomputed_kinds)
    assert tuple(data["recompute_steps"]) == steps
    assert set(steps) - {"planning"} == set(recompute.values())
    assert all(
        item["decision"] == "reuse"
        for item in data["version_decisions"]
        if item["artifact_kind"] in set(parent_kinds) - set(recomputed_kinds)
        or item["artifact_kind"] in unrelated_kinds
    )


def test_feedback_target_admission_fails_closed_without_side_effects(
    runtime: dict[str, object],
) -> None:
    client = runtime["client"]
    assert isinstance(client, TestClient)
    graph_version_id = str(runtime["version_ids"]["graph"])  # type: ignore[index]
    dataset_version_id = str(runtime["version_ids"]["dataset"])  # type: ignore[index]
    dataset_artifact_id = str(runtime["artifact_ids"]["dataset"])  # type: ignore[index]
    cases = (
        {
            **_feedback_body(runtime, "graph"),
            "target_id": str(uuid4()),
        },
        {
            **_feedback_body(runtime, "graph"),
            "target_type": "dataset_field",
            "target_id": "star.tic_id",
            "target_locator": {
                "artifact_version_id": graph_version_id,
                "field_id": "star.tic_id",
            },
        },
        {
            **_feedback_body(runtime, "graph"),
            "target_locator": {
                **_feedback_body(runtime, "graph")["target_locator"],  # type: ignore[dict-item]
                "unexpected": "value",
            },
        },
        {
            **_feedback_body(runtime, "graph"),
            "target_id": dataset_version_id,
            "target_locator": {
                "artifact_id": dataset_artifact_id,
                "artifact_version_id": dataset_version_id,
            },
        },
    )
    for position, body in enumerate(cases):
        response = client.post(
            f"/api/artifact-versions/{graph_version_id}/feedback",
            headers={
                "X-CSRF-Token": str(runtime["owner_csrf"]),
                "Idempotency-Key": f"invalid-target-{position}",
            },
            json=body,
        )
        assert (response.status_code, response.json()["code"]) == (
            422,
            "FEEDBACK_TARGET_INVALID",
        )

    factory = runtime["factory"]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(UserFeedbackModel)) == 0


def test_feedback_accepts_version_pinned_dataset_field_and_row_targets(
    runtime: dict[str, object],
) -> None:
    factory = runtime["factory"]
    project = build_research_project(
        project_id=uuid4(),
        session_id=str(runtime["owner_session_id"]),
        name="Typed feedback target authority",
        case_key="exoplanet_host_star",
    )
    with factory() as session, session.begin():
        persist_authoring_models(session, project=project)
    version_id = publish_reference_dataset(factory=factory, project=project)
    dataset = runtime["app"].state.data_artifact_read_service.get_dataset(
        version_id=str(version_id),
        session_id=str(runtime["owner_session_id"]),
    )
    targets = (
        ("dataset_field", dataset.dataset.columns[0].field.field_id, "field_id"),
        ("dataset_row", dataset.dataset.rows[0].row_id, "row_id"),
    )
    client = runtime["client"]
    assert isinstance(client, TestClient)
    for target_type, target_id, locator_key in targets:
        response = client.post(
            f"/api/artifact-versions/{version_id}/feedback",
            headers={
                "X-CSRF-Token": str(runtime["owner_csrf"]),
                "Idempotency-Key": f"typed-target-{target_type}",
            },
            json={
                "expected_version_number": 1,
                "target_type": target_type,
                "target_id": target_id,
                "target_locator": {
                    "artifact_version_id": str(version_id),
                    locator_key: target_id,
                },
                "category": "correction",
                "summary": "The published value needs correction",
                "requested_change": "Recompute from the frozen inputs",
            },
        )
        assert response.status_code == 201, response.text


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

    thread = client.get(
        f"/api/projects/{runtime['project_id']}/research-turns",
        params={"limit": 100},
    )
    assert thread.status_code == 200, thread.text
    revision_messages = [
        item["public_content"]
        for item in thread.json()["data"]
        if item["kind"] == "assistant_message"
        and item.get("structured_payload", {}).get("revision_stage")
    ]
    assert (
        revision_messages.count(
            "已记录这项正式修改要求。接下来会基于当前结果生成可确认的修订计划。"
        )
        == 1
    )
    assert (
        revision_messages.count(
            f"修订计划已生成：将重新执行 {len(plan_data['recompute_steps'])} 个研究步骤。确认后会创建派生研究，当前结果保持不变。"
        )
        == 1
    )
    assert (
        revision_messages.count(
            "修订计划已确认，派生研究已创建。原研究与已发布结果会继续保留。"
        )
        == 1
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
    stale_body = {
        **_feedback_body(runtime, "graph"),
        "expected_version_number": 2,
    }
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
        json=_feedback_body(runtime, "graph"),
    )
    assert missing_csrf.status_code == 403
    missing_key = client.post(
        f"/api/artifact-versions/{version_id}/feedback",
        headers={"X-CSRF-Token": str(runtime["owner_csrf"])},
        json=_feedback_body(runtime, "graph"),
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
        json={
            **_feedback_body(runtime, "graph"),
            "summary": "A different request",
        },
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
            publication_key="revision-graph-followup",
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
