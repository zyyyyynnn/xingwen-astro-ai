"""One real service-level ResearchRun execution over the current runtime.

This test executes the real authoring chain (Project, Draft, confirmed
Contract, Run creation with frozen RunSteps) and the real execution chain
(Worker, StepRuntime dispatch, ProducerExecution lifecycle, Publisher,
ArtifactVersion, RunEvent publication, Thread Assistant Message, completion).
Only the external boundaries are deterministic: the model provider answers
with the one registered tool call and the paper source adapter returns frozen
records, so no real network is involved.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from db_bootstrap import reset_current_schema
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchThreadEntryModel,
    RunEventModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas.core import (
    ConfirmResearchContractRequest,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    ExecutionMode,
    ResearchThreadEntryKind,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.manifest import load_manifest_bundle
from app.schemas.paper_collection import PaperSourcePage
from app.schemas.enums import PaperDataLevel, SourceMode
from app.security import canonical_request_hash
from app.services.model_execution import (
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.services.research import ResearchApplicationService
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.store import PersistentWorkflowStore
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.query import normalize_text
from services.paper_pipeline.sources.base import (
    NormalizedPaperQuery,
    RawSourceRecord,
    SourceSearchResult,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)

_ROOT = Path(__file__).resolve().parents[3]
_FIXED_NOW = datetime(2026, 8, 16, 8, 0, 0, tzinfo=timezone.utc)


class ScriptedStepAgentModel:
    """Provider boundary that proves the model ledger starts before I/O."""

    def __init__(self, factory, run_id: UUID) -> None:
        self._factory = factory
        self._run_id = run_id

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        with self._factory() as session:
            running = session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == self._run_id,
                    ProducerExecutionModel.producer_type == "model",
                    ProducerExecutionModel.status == "running",
                )
            ).all()
        assert running, "model provider was called before ProducerExecution.start"
        if request.response_mode != "tool" or not request.tools:
            raise AssertionError(
                "the step agent must only issue governed tool-mode requests"
            )
        tool_name = request.tools[0]["function"]["name"]
        return ModelExecutionResponse(
            payload={},
            output_hash=canonical_request_hash(
                {"tool": tool_name, "step_key": request.input_payload}
            ),
            token_usage={"prompt_tokens": 8, "completion_tokens": 8, "total_tokens": 16},
            latency_ms=3,
            provider_request_id="req-scripted-agent",
            provider_returned_model="qwen3.8-max-2026-08-01",
            tool_calls=(
                ModelToolCall(
                    id="call-scripted-1",
                    name=tool_name,
                    arguments={
                        "public_analysis": (
                            "先核对研究协议与本步骤的执行边界，再检查输入是否齐备，"
                            "并以协议要求判断本步骤是否完成。"
                        )
                    },
                ),
            ),
        )


class FrozenCrossrefAdapter:
    """Deterministic source adapter standing in for the Crossref REST boundary."""

    source_id = "crossref"
    adapter_name = "crossref_rest"
    adapter_version = "1.0.0"

    def __init__(self, factory, run_id: UUID) -> None:
        self._factory = factory
        self._run_id = run_id
        self.seen_query: NormalizedPaperQuery | None = None
        self.records = (
            RawSourceRecord(
                source_id=self.source_id,
                source_record_id="crossref-test-0001",
                title="Confirmed transiting planets around nearby host stars",
                authors=("Zhang San", "Li Si"),
                year=2024,
                doi="10.9999/test-0001",
                arxiv_id=None,
                url="https://doi.org/10.9999/test-0001",
                abstract=None,
            ),
            RawSourceRecord(
                source_id=self.source_id,
                source_record_id="crossref-test-0002",
                title="Radius and mass recovery for small exoplanet candidates",
                authors=("Wang Wu",),
                year=2025,
                doi="10.9999/test-0002",
                arxiv_id=None,
                url="https://doi.org/10.9999/test-0002",
                abstract=None,
            ),
        )

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult:
        self.seen_query = query
        with self._factory() as session:
            running = session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == self._run_id,
                    ProducerExecutionModel.step_key == "searching_papers",
                    ProducerExecutionModel.producer_type == "algorithm",
                    ProducerExecutionModel.status == "running",
                )
            ).all()
        assert running, "paper source was called before ProducerExecution.start"
        snapshot = SourceSnapshotRecord(
            snapshot_id="crossref-test-snapshot",
            source_id=self.source_id,
            source_type="crossref_rest",
            retrieved_at=_FIXED_NOW,
            query=query.original_query_string,
            query_hash=query.query_hash,
            source_version_or_etag=None,
            content_hash=canonical_request_hash(
                {"records": [record.hash_payload() for record in self.records]}
            ),
            license_note="deposited metadata; publisher license governs content",
            cache_version=None,
            request_metadata={},
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=20,
            returned_rows=len(self.records),
            total_results=len(self.records),
            attempt_count=1,
            status_code=200,
            retrieved_at=_FIXED_NOW,
            request_hash=canonical_request_hash({"page": 1, "offset": 0}),
            response_hash=canonical_request_hash(
                {"records": [record.hash_payload() for record in self.records]}
            ),
        )
        return SourceSearchResult(
            records=self.records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


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


def _contract_payload() -> dict[str, object]:
    return {
        "research_goal": "整合近邻Confirmed系外行星候选与宿主恒星参数并核对文献证据。",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {
            "keywords": ("系外行星 宿主恒星", "exoplanet host star"),
            "source_ids": ("crossref",),
            "max_candidates": 5,
        },
        "output_requirements": ["paper_collection"],
        "evidence_requirements": {},
        "quality_constraints": {},
    }


def test_worker_executes_confirmed_contract_end_to_end(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    manifests = load_manifest_bundle(
        _ROOT / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    store = PersistentWorkflowStore(factory)
    executor: PersistentWorkflowExecutor[object, object] = PersistentWorkflowExecutor(
        store
    )
    service = ResearchApplicationService(
        factory=factory,
        workflow_store=store,
        manifests=manifests,
    )

    session_id = f"session-{uuid4()}"
    project = service.create_project(
        session_id=session_id,
        idempotency_key=f"project-{uuid4()}",
        request=CreateResearchProjectRequest(
            name="真实执行集成",
            description="端到端研究执行测试",
            case_key="exoplanet_host_star",
        ),
    )
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="按确认协议执行一次真实研究运行",
            contract=_contract_payload(),  # type: ignore[arg-type]
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
    run = service.create_run(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"run-{uuid4()}",
        request=CreateRunRequest(
            contract_id=contract.id,
            execution_mode=ExecutionMode.live,
        ),
    )

    snapshot = store.load_snapshot(UUID(run.id))
    assert tuple(step.key for step in snapshot.steps) == (
        "planning",
        "searching_papers",
    )

    adapter = FrozenCrossrefAdapter(factory, UUID(run.id))
    worker = ResearchRunWorker(
        factory=factory,
        store=store,
        executor=executor,
        manifests=manifests,
        model_port=ScriptedStepAgentModel(factory, UUID(run.id)),
        requested_model="qwen3.8-max",
        explicit_revision=None,
        paper_collection_runner=LivePaperCollectionRunner(
            adapter=adapter,
            clock=lambda: _FIXED_NOW,
        ),
    )
    asyncio.run(worker.execute_run(UUID(run.id)))

    final = store.load_snapshot(UUID(run.id))
    assert final.status == "completed"
    assert all(step.status == "completed" for step in final.steps)

    with factory() as session:
        _assert_publication_chain(session, run_id=UUID(run.id), adapter=adapter)
        _assert_run_events_and_thread(
            session, run_id=UUID(run.id), project_id=UUID(project.id)
        )


def _assert_publication_chain(
    session: Session, *, run_id: UUID, adapter: FrozenCrossrefAdapter
) -> None:
    executions = session.scalars(
        select(ProducerExecutionModel).where(
            ProducerExecutionModel.run_id == run_id
        )
    ).all()
    searching = [
        execution
        for execution in executions
        if execution.step_key == "searching_papers"
    ]
    algorithm_executions = [
        execution for execution in searching if execution.producer_type == "algorithm"
    ]
    assert len(algorithm_executions) == 1
    execution = algorithm_executions[0]
    assert execution.status == "completed"
    assert execution.requested_model is None

    model_executions = [
        execution for execution in executions if execution.producer_type == "model"
    ]
    assert model_executions
    assert all(execution.status == "completed" for execution in model_executions)
    assert all(execution.provider_request_id == "req-scripted-agent" for execution in model_executions)
    assert all(execution.provider_returned_model == "qwen3.8-max-2026-08-01" for execution in model_executions)

    version = session.scalar(
        select(ArtifactVersionModel).where(
            ArtifactVersionModel.producer_execution_id == execution.id
        )
    )
    assert version is not None
    assert version.created_by_run_id == run_id
    assert version.content_hash == execution.output_hash
    content = version.content
    assert content["kind"] == "paper_collection"
    # A contract-driven live collection carries no benchmark reference.
    assert content.get("benchmark") is None
    assert content["acquisition_run"]["status"] == "completed"

    seen = adapter.seen_query
    assert seen is not None
    assert set(content["query"]["normalized_keywords"]) == set(
        seen.normalized_keywords
    )
    contract_keywords = {
        normalize_text(keyword)
        for keyword in ("系外行星 宿主恒星", "exoplanet host star")
    }
    assert set(content["query"]["normalized_keywords"]) == contract_keywords


def _assert_run_events_and_thread(
    session: Session, *, run_id: UUID, project_id: UUID
) -> None:
    events = session.scalars(
        select(RunEventModel).where(RunEventModel.run_id == run_id)
    ).all()
    assert events
    published = [
        event for event in events if event.artifact_version_ids
    ]
    assert published

    messages = session.scalars(
        select(ResearchThreadEntryModel).where(
            ResearchThreadEntryModel.project_id == project_id,
            ResearchThreadEntryModel.kind
            == ResearchThreadEntryKind.assistant_message,
        )
    ).all()
    run_messages = [
        message
        for message in messages
        if message.structured_payload.get("origin") == "research_run"
    ]
    assert run_messages
    assert {message.structured_payload.get("run_id") for message in run_messages} == {
        str(run_id)
    }
    assert {
        message.structured_payload.get("step_key") for message in run_messages
    } >= {"run_started", "planning", "searching_papers"}
