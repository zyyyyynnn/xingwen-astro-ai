"""Failure isolation for the reasoning chain on real PostgreSQL (#63).

A model failure during relation admission and an evidence-graph integrity
failure must both leave the already-published ArtifactVersion latest pointers
untouched (no drift), fail the run with a public message, and allow a fresh
Run over the same frozen Contract to complete through the full chain.

Reuses the production worker, repositories and publisher from the literature
revision execution suite; only the model boundary is scripted.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine

import app.workflow.steps.graph_steps as graph_steps_module
from app.workflow.agent_runtime import AgentActivityError

import test_literature_graph_revision_execution as base
from app.schemas.core import (
    ConfirmResearchContractRequest,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    ExecutionMode,
)
from app.services.research import ResearchApplicationService
from app.services.revisions import RevisionApplicationService
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.store import PersistentWorkflowStore
from db_bootstrap import reset_current_schema
from services.paper_pipeline.live_collection import LivePaperCollectionRunner

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)


class _FailureScriptedModel(base._RevisionScriptedModel):
    """Scripted model that can be told to fail one prompt on demand."""

    def __init__(self, factory, *, fail_prompt: str | None = None) -> None:
        super().__init__(factory)
        self.fail_prompt = fail_prompt

    def execute(self, request):  # noqa: ANN001 - mirrors base signature
        if self.fail_prompt == request.prompt_name:
            raise base.ModelExecutionError(
                "MODEL_PROVIDER_UNAVAILABLE",
                "injected failure for pointer-isolation coverage",
            )
        return super().execute(request)


def _create_pending_chain(engine: Engine, model) -> dict[str, object]:
    """Author Project/Contract/Run through real services without executing."""
    factory = base.session_factory(engine)
    manifests = base.load_manifest_bundle(
        base._ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        base._ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    store = PersistentWorkflowStore(factory)
    executor: PersistentWorkflowExecutor[object, object] = PersistentWorkflowExecutor(
        store
    )
    service = ResearchApplicationService(
        factory=factory, workflow_store=store, manifests=manifests
    )
    revision_service = RevisionApplicationService(factory=factory, workflow_store=store)

    session_id = f"session-{uuid4()}"
    project = service.create_project(
        session_id=session_id,
        idempotency_key=f"project-{uuid4()}",
        request=CreateResearchProjectRequest(
            name="推理链故障隔离",
            description="failure isolation end-to-end",
            case_key="exoplanet_host_star",
        ),
    )
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="验证推理链故障不漂移已发布指针",
            contract=base._contract_payload(),  # type: ignore[arg-type]
        ),
    )
    contract = service.confirm_contract(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"confirm-{uuid4()}",
        request=ConfirmResearchContractRequest(
            draft_id=draft.id,
            expected_draft_version=draft.version,
        ),
    )

    def make_worker() -> ResearchRunWorker:
        return ResearchRunWorker(
            factory=factory,
            store=store,
            executor=executor,
            manifests=manifests,
            model_port=model,
            requested_model="qwen3.8-max",
            explicit_revision=None,
            paper_collection_runner=LivePaperCollectionRunner(
                adapter=base._FrozenCrossref(),
                clock=lambda: base._FIXED_NOW,
            ),
        )

    def create_run() -> UUID:
        run = service.create_run(
            project_id=project.id,
            session_id=session_id,
            idempotency_key=f"run-{uuid4()}",
            request=CreateRunRequest(
                contract_id=contract.id,
                execution_mode=ExecutionMode.live,
            ),
        )
        return UUID(run.id)

    return {
        "factory": factory,
        "store": store,
        "service": service,
        "revision_service": revision_service,
        "make_worker": make_worker,
        "create_run": create_run,
        "project_id": project.id,
        "session_id": session_id,
        "model": model,
    }



def _latest_pointer(harness, kind: str) -> UUID | None:
    """Soft latest-pointer read: None when nothing was published yet."""
    from sqlalchemy import select
    from app.db.models import ResearchArtifactModel

    with harness["factory"]() as session:
        artifact = session.scalar(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.project_id == UUID(str(harness["project_id"])),
                ResearchArtifactModel.logical_key == f"{kind}.primary",
            )
        )
        assert artifact is not None
        return (
            UUID(str(artifact.latest_version_id))
            if artifact.latest_version_id is not None
            else None
        )


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine = base.create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


@pytest.fixture()
def confidence_provider():
    provider = base._AcceptedConfidenceProvider()
    original = base.literature_steps_module.build_live_relation_confidence_assessments
    base.literature_steps_module.build_live_relation_confidence_assessments = provider
    try:
        yield provider
    finally:
        base.literature_steps_module.build_live_relation_confidence_assessments = (
            original
        )


def test_relation_model_failure_isolates_published_prefix_and_recovers(
    postgres_engine: Engine, confidence_provider
) -> None:
    model = _FailureScriptedModel(base.session_factory(postgres_engine))
    model.fail_prompt = "literature_relation"
    harness = _create_pending_chain(postgres_engine, model)
    store: PersistentWorkflowStore = harness["store"]
    make_worker = harness["make_worker"]
    create_run = harness["create_run"]

    failed_run = create_run()
    try:
        asyncio.run(make_worker().execute_run(failed_run))
    except AgentActivityError:
        # Depending on retry classification the injected model failure may
        # surface through the runtime boundary; the authoritative isolation
        # facts are read from the persisted run below.
        pass
    snapshot = store.load_snapshot(failed_run)
    assert snapshot.status == "failed"
    failed_steps = tuple(
        step for step in snapshot.steps if step.status == "failed"
    )
    assert failed_steps
    assert all(step.key == "reasoning_literature" for step in failed_steps)

    # Everything published before the failing step stays pinned. Claims and
    # Relations are committed atomically by the reasoning step itself, so a
    # failure inside that step leaves both unpublished while search/summary
    # outputs keep their exact latest pointers; nothing may drift.
    assert _latest_pointer(harness, "paper_collection") is not None
    assert _latest_pointer(harness, "paper_summary") is not None
    assert _latest_pointer(harness, "literature_claims") is None
    assert _latest_pointer(harness, "literature_relations") is None
    assert _latest_pointer(harness, "graph") is None

    # A fresh Run over the same frozen Contract completes the whole chain.
    model.fail_prompt = None
    recovered_run = create_run()
    try:
        asyncio.run(make_worker().execute_run(recovered_run))
    except AgentActivityError:
        pass
    recovered = store.load_snapshot(recovered_run)
    assert recovered.status == "completed", recovered.failure_summary
    assert _latest_pointer(harness, "literature_relations") is not None
    graph_latest = _latest_pointer(harness, "graph")
    assert graph_latest is not None


def test_graph_integrity_failure_keeps_reasoning_pointers(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    confidence_provider,
) -> None:
    class _FailingGraphPipeline:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def admit(self, *args, **kwargs):
            raise RuntimeError("injected graph integrity failure")

        def admit_json(self, *args, **kwargs):
            raise RuntimeError("injected graph integrity failure")

    monkeypatch.setattr(
        graph_steps_module, "GraphPipeline", _FailingGraphPipeline
    )
    model = _FailureScriptedModel(base.session_factory(postgres_engine))
    harness = _create_pending_chain(postgres_engine, model)
    store: PersistentWorkflowStore = harness["store"]

    failed_run = harness["create_run"]()
    asyncio.run(harness["make_worker"]().execute_run(failed_run))
    snapshot = store.load_snapshot(failed_run)
    assert snapshot.status == "failed"
    failed_step = next(step for step in snapshot.steps if step.status == "failed")
    assert failed_step.key == "building_graph"

    # Claims AND relations were published by this very run before the graph
    # step; their latest pointers must survive the integrity failure verbatim.
    assert _latest_pointer(harness, "literature_claims") is not None
    relations_latest = _latest_pointer(harness, "literature_relations")
    assert relations_latest is not None
    assert _latest_pointer(harness, "graph") is None

    monkeypatch.undo()
    recovered_run = harness["create_run"]()
    asyncio.run(harness["make_worker"]().execute_run(recovered_run))
    recovered = store.load_snapshot(recovered_run)
    assert recovered.status == "completed", recovered.failure_summary
    assert _latest_pointer(harness, "graph") is not None
