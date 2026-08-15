"""PostgreSQL proof for the run-bound DocumentParse-to-PaperSummary closure."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, func, select

from app.db.models import (
    ArtifactVersionModel,
    DocumentParseModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchInputBindingModel,
    ResearchInputContentModel,
    ResearchInputModel,
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    DataRequirements,
    EvidenceRequirements,
    PaperSearchScope,
    ResearchContractInput,
    ScientificSkillId,
    ScientificTaskInput,
    SourceScope,
    compute_research_contract_content_hash,
)
from app.services.content_storage import LocalContentStorage, sha256_content_hash
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.workflow.document_pipeline_runtime import DocumentPipelineRuntime
from app.workflow.publisher import ArtifactPublisher
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.run_plan import compile_run_plan
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from services.paper_pipeline.canonicalize import canonical_paper_id, normalize_title

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)


class _SummaryModel:
    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if request.response_mode == "tool":
            tool = request.tools[0]["function"]
            payload: dict[str, object] = {}
            return ModelExecutionResponse(
                payload=payload,
                output_hash=compute_canonical_payload_hash(payload),
                token_usage={
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                },
                latency_ms=5,
                provider_request_id="postgres-agent-proof",
                tool_calls=(
                    ModelToolCall(
                        id=f"call-{tool['name']}",
                        name=tool["name"],
                        arguments={
                            "public_analysis": (
                                "依据已确认研究协议执行当前唯一受控步骤，并核对输入、来源与完成依据。"
                            )
                        },
                    ),
                ),
            )
        if request.prompt_name == "literature_claim":
            summary = request.input_payload["paper_summary_artifact"]["content"]
            statements = [
                statement
                for section_name in (
                    "background",
                    "methodology",
                    "dataset",
                    "experiments",
                    "discussion",
                    "limitations",
                    "research_questions",
                )
                for statement in (
                    [summary[section_name]["overview"]]
                    if summary[section_name].get("overview") is not None
                    else []
                )
                + summary[section_name].get("items", [])
            ]
            payload = {
                "schema_version": "1.0.0",
                "claims": [
                    {
                        "source_statement_id": statement["statement_id"],
                        "text": statement["text"],
                        "normalized_text": statement["text"],
                        "claim_type": "finding",
                        "polarity": "positive",
                        "objects": ["exoplanet transit signal"],
                        "metric": None,
                        "unit": None,
                        "conditions": ["single uploaded study"],
                        "scope": ["transit signal validation"],
                        "limitations": ["requires independent scientific review"],
                        "qualifiers": [],
                        "uncertainty": None,
                        "comparison_basis": None,
                        "evidence_ids": statement["evidence_ids"],
                    }
                    for statement in statements
                ],
            }
            return ModelExecutionResponse(
                payload=payload,
                output_hash=compute_canonical_payload_hash(payload),
                token_usage={
                    "prompt_tokens": 75,
                    "completion_tokens": 25,
                    "total_tokens": 100,
                },
                latency_ms=17,
                provider_request_id="postgres-claim-proof",
            )
        if request.prompt_name == "literature_relation":
            claims = [
                claim
                for version in request.input_payload["literature_claims"]
                for claim in version["content"]["claims"]
                if claim["status"] == "accepted"
            ]
            source, target = claims[:2]
            claim_ids = [source["claim_id"], target["claim_id"]]
            evidence_ids = sorted({*source["evidence_ids"], *target["evidence_ids"]})
            operations = (
                "identify_premises",
                "compare_objects",
                "check_conditions",
                "check_evidence",
                "classify_relation",
            )
            payload = {
                "schema_version": "1.0.0",
                "relations": [
                    {
                        "source_claim_id": source["claim_id"],
                        "target_claim_id": target["claim_id"],
                        "relation_type": "supports",
                        "direction": {
                            "source_claim_id": source["claim_id"],
                            "target_claim_id": target["claim_id"],
                            "basis": "The source claim supplies supporting context.",
                        },
                        "conditions": ["single uploaded study"],
                        "condition_conflicts": [],
                        "condition_uncertainties": [],
                        "comparability": {
                            "object_status": "comparable",
                            "object_basis": "Both claims concern exoplanet transit signals.",
                            "metric_status": "not_applicable",
                            "metric_basis": "Neither claim declares a metric.",
                            "unit_status": "not_applicable",
                            "unit_basis": "Neither claim declares a unit.",
                        },
                        "evidence_ids": evidence_ids,
                        "trace": {
                            "premise_claim_ids": claim_ids,
                            "steps": [
                                {
                                    "order": order,
                                    "operation": operation,
                                    "statement": f"Auditable {operation.replace('_', ' ')}.",
                                    "claim_ids": claim_ids,
                                    "evidence_ids": evidence_ids,
                                }
                                for order, operation in enumerate(operations, 1)
                            ],
                            "conditions": ["single uploaded study"],
                            "limitations": ["Pending independent scientific review."],
                            "conflicts": [],
                            "conclusion": "The structured support relation is evidence-linked.",
                        },
                        "confidence_assessment_id": None,
                    }
                ],
            }
            return ModelExecutionResponse(
                payload=payload,
                output_hash=compute_canonical_payload_hash(payload),
                token_usage={
                    "prompt_tokens": 110,
                    "completion_tokens": 45,
                    "total_tokens": 155,
                },
                latency_ms=29,
                provider_request_id="postgres-relation-proof",
            )
        assert request.prompt_name == "paper_summary"
        evidence_id = request.input_payload["paper_payload"]["evidence"][0][
            "evidence_id"
        ]
        empty = lambda kind: {  # noqa: E731
            "section_kind": kind,
            "overview": None,
            "items": [],
        }
        payload = {
            "background": {
                "section_kind": "background",
                "overview": {
                    "statement_id": "summary.live.background",
                    "item_kind": "narrative",
                    "text": "该文档研究系外行星凌星信号。",
                    "evidence_ids": [evidence_id],
                },
                "items": [],
            },
            "methodology": empty("methodology"),
            "dataset": empty("dataset"),
            "experiments": empty("experiments"),
            "discussion": {
                "section_kind": "discussion",
                "overview": {
                    "statement_id": "summary.live.discussion",
                    "item_kind": "narrative",
                    "text": "The validation result supports the documented transit method.",
                    "evidence_ids": [evidence_id],
                },
                "items": [],
            },
            "limitations": empty("limitations"),
            "research_questions": empty("research_questions"),
            "evidence_ids": [evidence_id],
        }
        return ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage={
                "prompt_tokens": 90,
                "completion_tokens": 18,
                "total_tokens": 108,
            },
            latency_ms=21,
            provider_request_id="postgres-summary-proof",
        )


class _AgentOnlyModel:
    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        assert request.response_mode == "tool"
        tool = request.tools[0]["function"]
        payload: dict[str, object] = {}
        return ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage={
                "prompt_tokens": 12,
                "completion_tokens": 6,
                "total_tokens": 18,
            },
            latency_ms=3,
            provider_request_id="postgres-scientific-agent-proof",
            tool_calls=(
                ModelToolCall(
                    id=f"call-{tool['name']}",
                    name=tool["name"],
                    arguments={
                        "public_analysis": (
                            "依据冻结的科学任务执行当前受控步骤，并核对来源快照、证据和终态发布。"
                        )
                    },
                ),
            ),
        )


class _ProviderFailureAgentModel:
    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        assert request.response_mode == "tool"
        raise ModelExecutionError(
            "MODEL_PROVIDER_REJECTED",
            "研究助手未接受本次请求。",
            output_hash="sha256:" + "7" * 64,
            token_usage={"prompt_tokens": 7, "completion_tokens": 0},
            latency_ms=13,
            provider_request_id="provider-failure-proof",
        )


class _RejectedToolAgentModel:
    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        assert request.response_mode == "tool"
        return ModelExecutionResponse(
            payload={},
            output_hash="sha256:" + "8" * 64,
            token_usage={"prompt_tokens": 9, "completion_tokens": 2},
            latency_ms=11,
            provider_request_id="provider-validation-proof",
            tool_calls=(
                ModelToolCall(
                    id="rejected-tool-call",
                    name="shell",
                    arguments={
                        "public_analysis": (
                            "当前返回的工具不在冻结的服务端授权目录中，必须拒绝。"
                        )
                    },
                ),
            ),
        )


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_document_pipeline_persists_and_atomically_publishes_full_closure(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    factory = session_factory(postgres_engine)
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Document Pipeline integration",
        case_key="exoplanet_host_star",
    )
    draft = build_contract_draft(project)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash="sha256:" + "a" * 64,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"document-run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=(
            RunStepDefinition(
                key="planning",
                label="Planning",
                enter_status="planning",
                success_status="summarizing_papers",
            ),
            RunStepDefinition(
                key="summarizing_papers",
                label="Summarizing papers",
                enter_status="summarizing_papers",
                success_status="completed",
                depends_on_step_keys=("planning",),
            ),
        ),
    )
    content = b"# Transit Study\n\nThe document studies exoplanet transit signals."
    content_hash = sha256_content_hash(content)
    storage = LocalContentStorage(tmp_path / "cas")
    storage_ref = asyncio.run(storage.store(content, content_hash))
    input_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchInputContentModel(
                project_id=project.id,
                content_hash=content_hash,
                storage_ref=storage_ref,
                mime_type="text/markdown",
                size_bytes=len(content),
            )
        )
    with factory() as session, session.begin():
        session.add(
            ResearchInputModel(
                id=input_id,
                session_id=project.session_id,
                project_id=project.id,
                type="text",
                source_type="upload",
                content_hash=content_hash,
                filename="transit-study.md",
                status="accepted",
                source_snapshot_id=None,
            )
        )
        session.flush()
        session.add(
            ResearchInputBindingModel(
                input_id=input_id,
                project_id=project.id,
                run_id=run.id,
                contract_draft_id=None,
            )
        )
    lease = workflow.acquire_lease(
        run.id,
        owner="document-pipeline-test",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=run.revision,
    )
    planning_attempt = workflow.begin_step(
        run.id,
        step_key="planning",
        attempt_idempotency_key=f"planning-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="正在规划",
    )
    planning = ArtifactPublisher(factory).publish_step_outputs(
        run.id,
        step_key="planning",
        attempt_id=planning_attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=planning_attempt.run_status,
        expected_revision=planning_attempt.run_revision,
        publications=(),
        public_message="规划已完成",
    )
    attempt = workflow.begin_step(
        run.id,
        step_key="summarizing_papers",
        attempt_idempotency_key=f"document-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status=planning.status,
        expected_revision=planning.revision,
        public_message="正在总结文档",
    )
    runtime = DocumentPipelineRuntime(
        session_factory=factory,
        content_storage=storage,
        model_port=_SummaryModel(),
        model_name="qwen-plus",
        model_revision="qwen-plus-test",
    )
    publications = asyncio.run(
        runtime.prepare_publications(
            run_id=run.id,
            project_id=project.id,
            research_goal="总结凌星研究方法",
            step_key="summarizing_papers",
            attempt=attempt,
            lease=lease,
        )
    )

    result = ArtifactPublisher(factory).publish_step_outputs(
        run.id,
        step_key="summarizing_papers",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=publications,
        public_message="文档总结已完成",
    )

    assert result.status == "completed"
    assert len(result.versions) == 1
    with factory() as session:
        version = session.get(ArtifactVersionModel, result.versions[0].id)
        assert version is not None and version.content["kind"] == "paper_summary"
        assert version.source_mode == "live"
        expected_paper_id = canonical_paper_id(
            doi=None,
            arxiv_id=None,
            normalized_title=normalize_title("transit-study"),
            year=None,
            normalized_authors=(),
            source_id=f"research_input:{input_id}",
            source_record_id=str(input_id),
        )
        assert version.content["paper_id"] == expected_paper_id
        assert version.content["paper"]["paper_id"] == expected_paper_id
        assert version.content["paper_id"] != f"paper.{content_hash[7:31]}"
        assert session.scalar(select(func.count(DocumentParseModel.id))) == 1
        assert session.scalar(select(func.count(SourceSnapshotModel.id))) == 1
        assert session.scalar(select(func.count(ProducerExecutionModel.id))) == 2
        evidence = session.scalar(select(EvidenceModel))
        assert evidence is not None
        assert evidence.artifact_version_id == version.id
        assert evidence.extraction_method == "paper_summary_admission"
        assert evidence.locator["paper_summary_locator"]["document_parse_id"]


def test_worker_runs_bound_document_contract_to_terminal_publication(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    factory = session_factory(postgres_engine)
    contract_input = ResearchContractInput(
        research_goal="总结上传论文中的凌星研究方法",
        target_objects=("exoplanet_candidate",),
        data_requirements=DataRequirements(),
        requested_fields=("paper.summary",),
        source_scope=SourceScope(allowed_sources=("nasa_ads",)),
        paper_search_scope=PaperSearchScope(),
        output_requirements=(ArtifactKind.paper_summary,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints={},
    )
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="ResearchRunWorker document integration",
        case_key="exoplanet_host_star",
    )
    content_payload = contract_input.model_dump(mode="json")
    draft = build_contract_draft(project, content=content_payload)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(contract_input),
        content=content_payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"worker-document-run-{uuid4()}",
        request_hash="sha256:" + "c" * 64,
        steps=compile_run_plan(contract_input),
    )
    content = b"# Worker Transit Study\n\nThis paper validates a transit method."
    content_hash = sha256_content_hash(content)
    storage = LocalContentStorage(tmp_path / "worker-cas")
    storage_ref = asyncio.run(storage.store(content, content_hash))
    input_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchInputContentModel(
                project_id=project.id,
                content_hash=content_hash,
                storage_ref=storage_ref,
                mime_type="text/markdown",
                size_bytes=len(content),
            )
        )
    with factory() as session, session.begin():
        session.add(
            ResearchInputModel(
                id=input_id,
                session_id=project.session_id,
                project_id=project.id,
                type="text",
                source_type="upload",
                content_hash=content_hash,
                filename="worker-transit.md",
                status="accepted",
                source_snapshot_id=None,
            )
        )
        session.flush()
        session.add(
            ResearchInputBindingModel(
                input_id=input_id,
                project_id=project.id,
                run_id=run.id,
                contract_draft_id=None,
            )
        )

    model = _SummaryModel()
    worker = ResearchRunWorker(
        session_factory=factory,
        store=workflow,
        executor=PersistentWorkflowExecutor(workflow),
        content_storage=storage,
        model_port=model,
        model_name="qwen-plus",
        model_revision="qwen-plus-test",
    )
    asyncio.run(worker.execute_run(run.id))

    terminal = workflow.load_snapshot(run.id)
    assert terminal.status == "completed", [
        (step.key, step.status, step.public_message, step.failure_code)
        for step in terminal.steps
    ]
    assert all(step.status == "completed" for step in terminal.steps)
    with factory() as session:
        versions = tuple(
            session.scalars(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.created_by_run_id == run.id
                )
            )
        )
        assert {version.content["kind"] for version in versions} == {
            "paper_collection",
            "paper_summary",
        }
        assert all(version.source_mode == "live" for version in versions)


def test_worker_closes_document_claim_relation_and_graph_pipeline(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    factory = session_factory(postgres_engine)
    contract_input = ResearchContractInput(
        research_goal="从上传论文构建可追溯的凌星研究证据图谱",
        target_objects=("exoplanet_candidate",),
        data_requirements=DataRequirements(),
        requested_fields=("paper.summary", "literature.claims", "graph.edges"),
        source_scope=SourceScope(allowed_sources=("nasa_ads",)),
        paper_search_scope=PaperSearchScope(),
        output_requirements=(
            ArtifactKind.paper_summary,
            ArtifactKind.literature_claims,
            ArtifactKind.literature_relations,
            ArtifactKind.reasoning_traces,
            ArtifactKind.graph,
        ),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints={},
    )
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="ResearchRunWorker literature graph integration",
        case_key="exoplanet_host_star",
    )
    content_payload = contract_input.model_dump(mode="json")
    draft = build_contract_draft(project, content=content_payload)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(contract_input),
        content=content_payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"worker-literature-run-{uuid4()}",
        request_hash="sha256:" + "d" * 64,
        steps=compile_run_plan(contract_input),
    )
    content = (
        b"# Worker Transit Evidence\n\n"
        b"This study validates an exoplanet transit signal and its method."
    )
    content_hash = sha256_content_hash(content)
    storage = LocalContentStorage(tmp_path / "literature-worker-cas")
    storage_ref = asyncio.run(storage.store(content, content_hash))
    input_id = uuid4()
    with factory() as session, session.begin():
        session.add(
            ResearchInputContentModel(
                project_id=project.id,
                content_hash=content_hash,
                storage_ref=storage_ref,
                mime_type="text/markdown",
                size_bytes=len(content),
            )
        )
    with factory() as session, session.begin():
        session.add(
            ResearchInputModel(
                id=input_id,
                session_id=project.session_id,
                project_id=project.id,
                type="text",
                source_type="upload",
                content_hash=content_hash,
                filename="worker-literature.md",
                status="accepted",
                source_snapshot_id=None,
            )
        )
        session.flush()
        session.add(
            ResearchInputBindingModel(
                input_id=input_id,
                project_id=project.id,
                run_id=run.id,
                contract_draft_id=None,
            )
        )

    worker = ResearchRunWorker(
        session_factory=factory,
        store=workflow,
        executor=PersistentWorkflowExecutor(workflow),
        content_storage=storage,
        model_port=_SummaryModel(),
        model_name="qwen-plus",
        model_revision="qwen-plus-test",
    )
    asyncio.run(worker.execute_run(run.id))

    terminal = workflow.load_snapshot(run.id)
    assert terminal.status == "completed", [
        (step.key, step.status, step.public_message, step.failure_code)
        for step in terminal.steps
    ]
    assert all(step.status == "completed" for step in terminal.steps)
    with factory() as session:
        versions = tuple(
            session.scalars(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.created_by_run_id == run.id
                )
            )
        )
        by_kind = {version.content["kind"]: version for version in versions}
        assert set(by_kind) == {
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "graph",
        }
        assert all(version.source_mode == "live" for version in versions)
        relation = by_kind["literature_relations"].content
        assert relation["relations"][0]["status"] == "accepted"
        assert relation["relations"][0].get("confidence") is None
        assert relation["reasoning_traces"]
        graph = by_kind["graph"].content
        assert graph["nodes"]
        assert graph["edges"]
        producer_rows = tuple(
            session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
        )
        assert all(row.status == "completed" for row in producer_rows)
        assert len(producer_rows) == 11
        agent_rows = tuple(
            row
            for row in producer_rows
            if row.producer_name == "research_step_agent"
        )
        assert len(agent_rows) == 5
        assert all(row.tool_call_id for row in agent_rows)
        assert all(row.validated_arguments_hash for row in agent_rows)
        assert all(row.registry_revision for row in agent_rows)


def test_worker_closes_ephemeris_task_to_terminal_scientific_publication(
    postgres_engine: Engine, tmp_path: Path
) -> None:
    factory = session_factory(postgres_engine)
    task = ScientificTaskInput(
        task_id="task.ephemeris.mars",
        skill_id=ScientificSkillId.ephemeris,
        parameters={
            "target": "mars",
            "observed_at": "2026-08-14T12:00:00Z",
            "latitude_degrees": 26.647,
            "longitude_degrees": 106.63,
            "elevation_meters": 1100.0,
        },
    )
    contract_input = ResearchContractInput(
        research_goal="计算火星在给定地点和时刻的可审计星历",
        target_objects=("mars",),
        data_requirements=DataRequirements(),
        requested_fields=("ephemeris.altitude", "ephemeris.azimuth"),
        source_scope=SourceScope(allowed_sources=("jpl_de421",)),
        paper_search_scope=PaperSearchScope(),
        scientific_tasks=(task,),
        output_requirements=(ArtifactKind.analysis_report,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints={},
    )
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="ResearchRunWorker ephemeris integration",
        case_key="exoplanet_host_star",
    )
    content_payload = contract_input.model_dump(mode="json")
    draft = build_contract_draft(project, content=content_payload)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(contract_input),
        content=content_payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"worker-ephemeris-run-{uuid4()}",
        request_hash="sha256:" + "e" * 64,
        steps=compile_run_plan(contract_input),
    )
    worker = ResearchRunWorker(
        session_factory=factory,
        store=workflow,
        executor=PersistentWorkflowExecutor(workflow),
        content_storage=LocalContentStorage(tmp_path / "ephemeris-worker-cas"),
        model_port=_AgentOnlyModel(),
        model_name="qwen-plus",
        model_revision="qwen-plus-test",
    )

    asyncio.run(worker.execute_run(run.id))

    terminal = workflow.load_snapshot(run.id)
    assert terminal.status == "completed", [
        (step.key, step.status, step.public_message, step.failure_code)
        for step in terminal.steps
    ]
    assert tuple(step.enter_status for step in terminal.steps) == (
        "planning",
        "acquiring_observations",
    )
    assert all(step.status == "completed" for step in terminal.steps)
    with factory() as session:
        versions = tuple(
            session.scalars(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.created_by_run_id == run.id
                )
            )
        )
        assert len(versions) == 1
        version = versions[0]
        assert version.content["kind"] == "analysis_report"
        assert version.source_mode == "live"
        assert version.source_snapshot_ids
        snapshots = tuple(
            session.scalars(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.id.in_(version.source_snapshot_ids)
                )
            )
        )
        assert len(snapshots) == 1
        assert snapshots[0].source_id == "jpl_de421"
        assert snapshots[0].source_version_or_etag == "DE421"
        assert snapshots[0].content_hash.startswith("sha256:")
        evidence = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == version.id
                )
            )
        )
        assert evidence
        assert all(item.source_snapshot_id == snapshots[0].id for item in evidence)
        producers = tuple(
            session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == run.id
                )
            )
        )
        assert len(producers) == 3
        agent_executions = tuple(
            item for item in producers if item.producer_name == "research_step_agent"
        )
        assert len(agent_executions) == 2
        assert {item.authorized_tool_name for item in agent_executions} == {
            "confirm_research_plan",
            "run_ephemeris",
        }
        assert {item.authorized_skill_id for item in agent_executions} == {
            None,
            "ephemeris",
        }
        assert all(item.status == "completed" for item in agent_executions)
        assert all(
            item.registry_revision.startswith("sha256:") for item in agent_executions
        )
        assert all(item.tool_call_id for item in agent_executions)
        assert all(
            item.provider_request_id == "postgres-scientific-agent-proof"
            for item in agent_executions
        )
        assert all(
            item.validated_arguments_hash.startswith("sha256:")
            for item in agent_executions
        )
        assert all(item.error_hash is None for item in agent_executions)
        assert all(item.public_message.startswith("依据") for item in agent_executions)
        assert all(item.finished_at >= item.started_at for item in agent_executions)
        steps = tuple(
            session.scalars(select(RunStepModel).where(RunStepModel.run_id == run.id))
        )
        attempts = tuple(
            session.scalars(
                select(StepAttemptModel).where(
                    StepAttemptModel.run_step_id.in_(item.id for item in steps)
                )
            )
        )
        assert len(steps) == 2
        assert len(attempts) == 2
        assert all(item.status == "completed" for item in attempts)
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(
                    RunEventModel.run_id == run.id,
                    RunEventModel.event_type == "run.completed",
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    (
        "model",
        "expected_status",
        "error_code",
        "result_hash",
        "request_id",
        "tool_call_id",
        "rejected_arguments_hash",
    ),
    (
        (
            _ProviderFailureAgentModel(),
            "failed",
            "MODEL_PROVIDER_REJECTED",
            "sha256:" + "7" * 64,
            "provider-failure-proof",
            None,
            None,
        ),
        (
            _RejectedToolAgentModel(),
            "rejected",
            "AGENT_TOOL_NOT_AUTHORIZED",
            "sha256:" + "8" * 64,
            "provider-validation-proof",
            "rejected-tool-call",
            compute_canonical_payload_hash(
                {
                    "public_analysis": (
                        "当前返回的工具不在冻结的服务端授权目录中，必须拒绝。"
                    )
                }
            ),
        ),
    ),
)
def test_worker_audits_provider_and_validation_failures_without_private_payloads(
    postgres_engine: Engine,
    tmp_path: Path,
    model: ModelExecutionPort,
    expected_status: str,
    error_code: str,
    result_hash: str,
    request_id: str,
    tool_call_id: str | None,
    rejected_arguments_hash: str | None,
) -> None:
    factory = session_factory(postgres_engine)
    contract_input = ResearchContractInput(
        research_goal="检索可追溯天文论文",
        target_objects=("mars",),
        data_requirements=DataRequirements(),
        requested_fields=("paper.title",),
        source_scope=SourceScope(allowed_sources=("nasa_ads",)),
        paper_search_scope=PaperSearchScope(),
        output_requirements=(ArtifactKind.paper_collection,),
        evidence_requirements=EvidenceRequirements(),
        quality_constraints={},
    )
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="ResearchStepAgent failure audit",
        case_key="exoplanet_host_star",
    )
    content_payload = contract_input.model_dump(mode="json")
    draft = build_contract_draft(project, content=content_payload)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(contract_input),
        content=content_payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"worker-agent-failure-{uuid4()}",
        request_hash="sha256:" + "9" * 64,
        steps=compile_run_plan(contract_input),
    )
    worker = ResearchRunWorker(
        session_factory=factory,
        store=workflow,
        executor=PersistentWorkflowExecutor(workflow),
        content_storage=LocalContentStorage(tmp_path / f"failure-{expected_status}"),
        model_port=model,
        model_name="qwen-plus",
        model_revision="qwen-plus-test",
    )

    asyncio.run(worker.execute_run(run.id))

    terminal = workflow.load_snapshot(run.id)
    assert terminal.status == "failed"
    with factory() as session:
        execution = session.scalar(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.run_id == run.id,
                ProducerExecutionModel.producer_name == "research_step_agent",
            )
        )
        assert execution is not None
        assert execution.status == expected_status
        assert execution.error_code == error_code
        assert execution.output_hash == result_hash
        assert execution.error_hash == compute_canonical_payload_hash(
            {"error_code": error_code, "result_hash": result_hash}
        )
        assert execution.provider_request_id == request_id
        assert execution.token_usage is not None
        assert execution.latency_ms is not None
        assert execution.authorized_tool_name == "confirm_research_plan"
        assert execution.authorized_skill_id is None
        assert execution.registry_revision.startswith("sha256:")
        assert execution.tool_call_id == tool_call_id
        assert execution.validated_arguments_hash is None
        assert execution.rejected_arguments_hash == rejected_arguments_hash
        assert execution.public_message is None
        assert execution.finished_at >= execution.started_at
        serialized = repr(execution.__dict__)
        assert "research_contract" not in serialized
        assert "private reasoning" not in serialized
        assert "当前返回的工具不在冻结的服务端授权目录中" not in serialized
