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
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchThreadEntryModel,
    RunEventModel,
    SourceSnapshotModel,
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
from app.schemas.research_input import ResearchInputCreate
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.manifest import load_manifest_bundle
from app.schemas.paper_collection import PaperSourcePage
from app.schemas.enums import PaperDataLevel, SourceMode
from app.security import canonical_request_hash
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.services.content_storage import LocalContentStorage
from app.services.research_input_ingestion import (
    ResearchInputIngestionCommand,
    ResearchInputIngestionService,
)
from app.services.research_input_policy import ResearchInputPolicy
from app.services.research_input_store import (
    PersistentIdempotencyRepository,
    PersistentResearchInputStore,
)
from app.services.research import ResearchApplicationService
from app.services.url_fetcher import UrlFetchConfig
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
from services.scientific_skills.astro_acquisition import GaiaTapAdapter

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
            token_usage={
                "prompt_tokens": 8,
                "completion_tokens": 8,
                "total_tokens": 16,
            },
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
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
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


def test_worker_executes_uploaded_csv_scientific_task_end_to_end(
    postgres_engine: Engine,
    tmp_path: Path,
) -> None:
    factory = session_factory(postgres_engine)
    manifests = load_manifest_bundle(
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    store = PersistentWorkflowStore(factory)
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
            name="上传数据科学执行",
            description="验证上传来源到科学产物的唯一生产链",
            case_key="exoplanet_host_star",
        ),
    )

    content_storage = LocalContentStorage(tmp_path / "content")
    input_store = PersistentResearchInputStore(factory)
    ingestion = ResearchInputIngestionService(
        repository=input_store,
        idempotency_repository=PersistentIdempotencyRepository(factory),
        content_storage=content_storage,
        policy=ResearchInputPolicy.from_values(
            allowed_mime_types=("text/csv",),
            max_size_bytes=1024 * 1024,
        ),
        url_fetch_config=UrlFetchConfig(
            allowed_protocols=("https",),
            allowed_hosts=(),
            timeout_seconds=1,
            max_redirects=0,
            max_response_bytes=1024,
        ),
    )
    research_input = asyncio.run(
        ingestion.create(
            ResearchInputIngestionCommand(
                session_id=session_id,
                project_id=project.id,
                payload=ResearchInputCreate(
                    type="csv",
                    filename="observations.csv",
                    mime_type="text/csv",
                ),
                idempotency_key=f"upload-{uuid4()}",
                file_content=b"object_id,flux,temperature\nA,1.2,5700\nB,1.8,5900\n",
                file_filename="observations.csv",
            )
        )
    )
    contract_payload = {
        "research_goal": "分析上传观测表的字段完整性与数值分布。",
        "target_objects": ["host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": ["star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"keywords": (), "source_ids": (), "max_candidates": 1},
        "output_requirements": ["analysis_report"],
        "evidence_requirements": {},
        "quality_constraints": {},
        "scientific_tasks": [
            {
                "task_id": "profile-uploaded-observations",
                "skill_id": "data_profile",
                "input_refs": [research_input.id],
                "parameters": {},
            }
        ],
    }
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="分析已上传观测表",
            contract=contract_payload,  # type: ignore[arg-type]
        ),
    )
    input_store.bind_to_contract(
        session_id=session_id,
        input_id=research_input.id,
        project_id=project.id,
        contract_draft_id=draft.id,
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
    assert tuple(step.skill_id for step in snapshot.steps) == (None, "data_profile")

    worker = ResearchRunWorker(
        factory=factory,
        store=store,
        executor=PersistentWorkflowExecutor(store),
        manifests=manifests,
        model_port=ScriptedStepAgentModel(factory, UUID(run.id)),
        requested_model="qwen3.8-max",
        explicit_revision=None,
        content_storage=content_storage,
    )
    asyncio.run(worker.execute_run(UUID(run.id)))

    final = store.load_snapshot(UUID(run.id))
    assert final.status == "completed"
    with factory() as session:
        versions = session.scalars(
            select(ArtifactVersionModel).where(
                ArtifactVersionModel.created_by_run_id == UUID(run.id)
            )
        ).all()
        artifacts = [
            session.get(ResearchArtifactModel, item.artifact_id) for item in versions
        ]
        assert all(item is not None for item in artifacts)
        assert [(item.kind, item.title) for item in artifacts] == [
            ("analysis_report", "数据画像"),
        ]
        assert len(versions) == 1
        version = versions[0]
        assert version.content["kind"] == "analysis_report"
        assert version.content["result_blocks"]
        assert research_input.source_snapshot_id is not None
        snapshot_row = session.get(
            SourceSnapshotModel, UUID(research_input.source_snapshot_id)
        )
        assert snapshot_row is not None
        assert snapshot_row.source_type == "research_input_upload"
        assert str(snapshot_row.id) in version.source_snapshot_ids


def test_gaia_scientific_admission_publishes_uuid_cell_evidence_end_to_end(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_hash = "sha256:" + "5" * 64
    adapter_query_hash = "sha256:" + "6" * 64

    def acquire_from_recorded_response(
        _adapter: GaiaTapAdapter, _request: object
    ) -> dict[str, object]:
        return {
            "service": "gaia_archive",
            "data_release": "gaiadr3",
            "coordinate_frame": "ICRS",
            "query_kind": "cone_search",
            "center": {"ra_degrees": 56.7, "dec_degrees": 24.1},
            "radius_degrees": 0.05,
            "fields": ["source_id", "ra", "dec"],
            "column_metadata": [
                {"field": "source_id", "label": "Gaia DR3 宿主恒星标识", "unit": None},
                {"field": "ra", "label": "赤经", "unit": "deg"},
                {"field": "dec", "label": "赤纬", "unit": "deg"},
            ],
            "row_count": 1,
            "rows": [{"source_id": "65214061869072512", "ra": 56.7, "dec": 24.1}],
            "truncated": False,
            "result_status": "complete",
            "response_format": "csv",
            "acquisition": {
                "source_mode": "cached",
                "adapter": "gaia_tap",
                "adapter_version": "3.0.0",
                "endpoint": "https://gea.esac.esa.int/tap-server/tap/sync",
                "response_content_hash": response_hash,
                "cache_version": "gaia-dr3-cone:3.0.0:2",
                "query_hash": adapter_query_hash,
                "retrieved_at": _FIXED_NOW.isoformat(),
                "schema_revision": "gaia-dr3-source-contract:2",
                "schema_response_content_hash": "sha256:" + "7" * 64,
            },
        }

    monkeypatch.setattr(GaiaTapAdapter, "acquire", acquire_from_recorded_response)
    factory = session_factory(postgres_engine)
    manifests = load_manifest_bundle(
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
        _ROOT
        / "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
    )
    store = PersistentWorkflowStore(factory)
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
            name="Gaia 单源科学发布",
            description="验证 Gaia 准入到唯一 Publisher 的完整闭环",
            case_key="exoplanet_host_star",
        ),
    )
    contract_payload = {
        "research_goal": "查询 Gaia DR3 宿主恒星并保留逐单元证据。",
        "target_objects": ["host_star"],
        "data_requirements": {"unit_policy": "canonical"},
        "requested_fields": [
            "star.gaia_dr3_id",
            "system.right_ascension",
            "system.declination",
        ],
        "source_scope": {"allowed_sources": ["esa_gaia_dr3"]},
        "paper_search_scope": {"keywords": (), "source_ids": (), "max_candidates": 1},
        "output_requirements": ["analysis_report"],
        "evidence_requirements": {"minimum_coverage": 1},
        "quality_constraints": {
            "source_completeness_min": 1,
            "unit_consistency_min": 1,
        },
        "scientific_tasks": [
            {
                "task_id": "query-gaia-host-star",
                "skill_id": "gaia_cone_search",
                "input_refs": [],
                "parameters": {
                    "ra_degrees": 56.7,
                    "dec_degrees": 24.1,
                    "fields": ["ra", "dec"],
                    "max_results": 5,
                },
            }
        ],
    }
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="查询 Gaia DR3",
            contract=contract_payload,  # type: ignore[arg-type]
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
    content_storage = LocalContentStorage(tmp_path / "gaia-content")

    def execute_run() -> UUID:
        run = service.create_run(
            project_id=project.id,
            session_id=session_id,
            idempotency_key=f"run-{uuid4()}",
            request=CreateRunRequest(
                contract_id=contract.id,
                execution_mode=ExecutionMode.live,
            ),
        )
        run_id = UUID(run.id)
        worker = ResearchRunWorker(
            factory=factory,
            store=store,
            executor=PersistentWorkflowExecutor(store),
            manifests=manifests,
            model_port=ScriptedStepAgentModel(factory, run_id),
            requested_model="qwen3.8-max",
            explicit_revision=None,
            content_storage=content_storage,
        )
        asyncio.run(worker.execute_run(run_id))
        assert store.load_snapshot(run_id).status == "completed"
        return run_id

    run_ids = (execute_run(), execute_run())
    with factory() as session:
        versions = session.scalars(
            select(ArtifactVersionModel).where(
                ArtifactVersionModel.created_by_run_id.in_(run_ids)
            )
        ).all()
        assert len(versions) == 2
        admissions = [
            version.content["source_table_admissions"][0] for version in versions
        ]
        assert all(
            admission["source_result_status"] == "complete" for admission in admissions
        )
        snapshot_ids = {
            UUID(admission["source_snapshot_id"]) for admission in admissions
        }
        assert len(snapshot_ids) == 1
        snapshot_id = next(iter(snapshot_ids))
        evidence = session.scalars(
            select(EvidenceModel).where(EvidenceModel.source_snapshot_id == snapshot_id)
        ).all()
        assert len(evidence) == 6
        version_evidence = [set(version.evidence_ids) for version in versions]
        assert version_evidence[0].isdisjoint(version_evidence[1])
        assert {str(item.id) for item in evidence} == set.union(*version_evidence)
        assert all(item.source_snapshot_id == snapshot_id for item in evidence)


def _assert_publication_chain(
    session: Session, *, run_id: UUID, adapter: FrozenCrossrefAdapter
) -> None:
    executions = session.scalars(
        select(ProducerExecutionModel).where(ProducerExecutionModel.run_id == run_id)
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
    assert all(
        execution.provider_request_id == "req-scripted-agent"
        for execution in model_executions
    )
    assert all(
        execution.provider_returned_model == "qwen3.8-max-2026-08-01"
        for execution in model_executions
    )

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
    assert content.get("search_input") is not None
    assert content["search_input"]["schema_version"] == "1.0.0"
    assert content["search_input"]["contract_id"]
    assert content["search_input"]["input_hash"]
    assert content["acquisition_run"]["status"] == "completed"

    seen = adapter.seen_query
    assert seen is not None
    assert set(content["query"]["normalized_keywords"]) == set(seen.normalized_keywords)
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
    published = [event for event in events if event.artifact_version_ids]
    assert published

    messages = session.scalars(
        select(ResearchThreadEntryModel).where(
            ResearchThreadEntryModel.project_id == project_id,
            ResearchThreadEntryModel.kind == ResearchThreadEntryKind.assistant_message,
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
    assert {message.structured_payload.get("step_key") for message in run_messages} >= {
        "run_started",
        "planning",
        "searching_papers",
    }
