"""Literature and Evidence Graph revision execution over the real worker runtime.

Executes a parent literature Run (search → summarize → reason → graph), then
confirms RevisionPlans against it and executes the derived revision Runs with
the real worker: frozen reuse baselines are hydrated, only the affected
closure re-executes, and the Publisher appends superseding Versions. The
model provider and paper source stay deterministic; PostgreSQL is real.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select

import app.workflow.steps.literature_steps as literature_steps_module
from db_bootstrap import reset_current_schema
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchRunModel,
    SourceSnapshotModel,
    UserFeedbackModel,
)
from app.db.session import create_engine_from_url, session_factory
from services.paper_pipeline.constants import (
    CLAIM_PRODUCER_NAME,
    RELATION_PRODUCER_NAME,
)
from services.paper_pipeline.relation import (
    compute_literature_relation_adjudication_input_hash,
)
from app.schemas.core import (
    ConfirmResearchContractRequest,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    ExecutionMode,
)
from app.schemas.enums import GraphEdgeType, LiteratureRelationType
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.literature_relation import (
    LiteratureRelationsCandidate,
    build_literature_relation_confidence_subject,
)
from app.schemas.manifest import load_manifest_bundle
from app.schemas.paper_collection import PaperSourcePage
from app.schemas.paper_collection_api import (
    ExistingPaperCandidateInputRequest,
    PaperAccessEvidenceKind,
    PaperCandidateAccessEvidence,
)
from app.schemas.research_input import ResearchInputCreate
from app.schemas.revision import (
    ConfirmRevisionPlanRequest,
    CreateRevisionPlanRequest,
    CreateUserFeedbackRequest,
    FeedbackCategory,
    FeedbackTargetType,
    RelationAdjudicationDecision,
)
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    ParserBackend,
)
from app.services.artifacts import ArtifactReadService
from app.services.content_storage import LocalContentStorage, sha256_content_hash
from app.services.document_parse_store import (
    DocumentParseRepository,
    DocumentParseService,
)
from app.services.feedback_targets import FeedbackTargetAuthority
from app.services.graph_artifacts import GraphArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionRequest,
    ModelExecutionResponse,
    ModelToolCall,
)
from app.services.paper_candidate_inputs import (
    CreatePaperCandidateInputCommand,
    PaperCandidateInputRepository,
    PaperCandidateInputService,
)
from app.services.paper_collections import PaperCollectionReadService
from app.services.paper_summaries import PaperSummaryReadService
from app.services.research import ResearchApplicationService
from app.services.research_input_ingestion import (
    ResearchInputIngestionCommand,
    ResearchInputIngestionService,
)
from app.services.research_input_policy import ResearchInputPolicy
from app.services.research_input_store import (
    PersistentIdempotencyRepository,
    PersistentResearchInputStore,
)
from app.services.revisions import RevisionApplicationService
from app.services.url_fetcher import UrlFetchConfig, UrlFetchResult
from app.schemas._hashing import compute_canonical_payload_hash
from app.security import canonical_request_hash
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.step_publication import step_uuid
from app.workflow.store import PersistentWorkflowStore
from services.paper_pipeline.constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
    RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
    RELATION_CONFIDENCE_CALIBRATION_ID,
    RELATION_CONFIDENCE_CALIBRATION_METHOD,
    RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE,
    RELATION_CONFIDENCE_CALIBRATION_VERSION,
    RELATION_CONFIDENCE_DEFINITION_ID,
    RELATION_CONFIDENCE_DEFINITION_VERSION,
)
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
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
_FIXED_NOW = datetime(2026, 8, 16, 8, 0, 0, tzinfo=UTC)

_STATEMENT_A = "statement.revision.e2e.1"
_STATEMENT_B = "statement.revision.e2e.2"
_EVIDENCE_ID = "ev.title"
_SNAPSHOT_PIPELINE_ID = "a2345678-1234-4234-9234-123456789abc"


def _claim_payload(
    statement_id: str,
    text: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "source_statement_id": statement_id,
        "text": text,
        "normalized_text": text.lower(),
        "claim_type": "finding",
        "polarity": "positive",
        "objects": ("nearby host stars",),
        "metric": None,
        "unit": None,
        "conditions": (),
        "scope": (),
        "limitations": (),
        "qualifiers": (),
        "uncertainty": None,
        "comparison_basis": None,
        "evidence_ids": evidence_ids or [_EVIDENCE_ID],
    }


def _relation_payload(
    claim_a: str,
    claim_b: str,
    evidence_ids: list[str] | None = None,
) -> dict[str, object]:
    ev_ids = evidence_ids or [_EVIDENCE_ID]
    conditions = ["same catalog scope"]
    operations = (
        "identify_premises",
        "compare_objects",
        "check_conditions",
        "check_evidence",
        "classify_relation",
    )
    return {
        "source_claim_id": claim_a,
        "target_claim_id": claim_b,
        "relation_type": "compares_method",
        "direction": {
            "source_claim_id": claim_a,
            "target_claim_id": claim_b,
            "basis": "The source-to-target comparison direction is explicit.",
        },
        "conditions": conditions,
        "condition_conflicts": [],
        "condition_uncertainties": [],
        "comparability": {
            "object_status": "comparable",
            "object_basis": "Both claims concern the same astronomical objects.",
            "metric_status": "not_applicable",
            "metric_basis": "Neither structural claim declares a metric.",
            "unit_status": "not_applicable",
            "unit_basis": "Neither structural claim declares a unit.",
        },
        "evidence_ids": ev_ids,
        "trace": {
            "premise_claim_ids": [claim_a, claim_b],
            "steps": [
                {
                    "order": order,
                    "operation": operation,
                    "statement": f"Auditable {operation.replace('_', ' ')} step.",
                    "claim_ids": [claim_a, claim_b],
                    "evidence_ids": ev_ids,
                }
                for order, operation in enumerate(operations, 1)
            ],
            "conditions": conditions,
            "limitations": [],
            "conflicts": [],
            "conclusion": (
                "The two claims describe comparable methods over the same objects."
            ),
        },
    }


class _AcceptedConfidenceProvider:
    """Deterministic stand-in for the trusted calibration authority."""

    def __call__(self, *, claim_artifact_version_id: str, claims):
        from app.schemas.literature_relation import (
            LiteratureRelationConfidenceAssessment,
            LiteratureRelationConfidenceStatus,
            LiteratureRelationStatus,
        )

        eligible = sorted(claims, key=lambda claim: claim.claim_id)
        assessments = {}
        for source in eligible:
            for target in eligible:
                if source.claim_id == target.claim_id:
                    continue
                for relation_type in LiteratureRelationType:
                    subject = build_literature_relation_confidence_subject(
                        source_claim_artifact_version_id=claim_artifact_version_id,
                        source_claim_id=source.claim_id,
                        target_claim_artifact_version_id=claim_artifact_version_id,
                        target_claim_id=target.claim_id,
                        relation_type=relation_type,
                    )
                    assessment_id = f"assessment.live_scope.{subject.fingerprint[7:31]}"
                    assessments[assessment_id] = LiteratureRelationConfidenceAssessment(
                        assessment_id=assessment_id,
                        subject=subject,
                        decision=LiteratureRelationStatus.accepted,
                        status=LiteratureRelationConfidenceStatus.assessed,
                        score=0.97,
                        definition_id=RELATION_CONFIDENCE_DEFINITION_ID,
                        definition_version=RELATION_CONFIDENCE_DEFINITION_VERSION,
                        calibration_id=RELATION_CONFIDENCE_CALIBRATION_ID,
                        calibration_version=RELATION_CONFIDENCE_CALIBRATION_VERSION,
                        calibration_scientific_payload_hash=(
                            FROZEN_SCIENTIFIC_PAYLOAD_HASH
                        ),
                        calibration_content_hash=FROZEN_BENCHMARK_CONTENT_HASH,
                        calibration_sample_size=(
                            RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE
                        ),
                        calibration_method=RELATION_CONFIDENCE_CALIBRATION_METHOD,
                        applicability_scope=RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
                        acceptance_threshold=(RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD),
                        basis=("Deterministic benchmark reference assessment.",),
                    )
        return assessments


def _contract_payload() -> dict[str, object]:
    return {
        "research_goal": "整合近邻Confirmed系外行星候选与宿主恒星参数并核对文献证据。",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "disabled",
        },
        "requested_fields": ["planet.toi_id", "star.tic_id"],
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {
            "keywords": ("系外行星 宿主恒星", "exoplanet host star"),
            "source_ids": ("crossref",),
            "max_candidates": 5,
        },
        "output_requirements": ["literature_claims", "literature_relations", "graph"],
        "evidence_requirements": {},
        "quality_constraints": {},
    }


class _RevisionScriptedModel:
    """Deterministic provider boundary for the whole revision chain."""

    def __init__(self, factory) -> None:
        self._factory = factory
        self.call_counts: dict[str, int] = {
            "tool": 0,
            "paper_summary": 0,
            "literature_claim": 0,
            "literature_relation": 0,
        }
        self.fail_literature_relation = False
        self.pause_before_paper_summary = False
        self.before_step_hook = None

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        if request.response_mode == "tool":
            self.call_counts["tool"] += 1
            tool_name = request.tools[0]["function"]["name"]
            if self.before_step_hook is not None:
                self.before_step_hook(tool_name)
            payload = {}
            return ModelExecutionResponse(
                payload=payload,
                output_hash=canonical_request_hash({"tool": tool_name}),
                token_usage={
                    "prompt_tokens": 4,
                    "completion_tokens": 4,
                    "total_tokens": 8,
                },
                latency_ms=2,
                provider_request_id="req-revision-agent",
                provider_returned_model="test-returned-model-snapshot",
                tool_calls=(
                    ModelToolCall(
                        id=f"call-{uuid4()}",
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
        if request.prompt_name == "paper_summary":
            if self.pause_before_paper_summary:
                raise ModelExecutionError(
                    "MODEL_PROVIDER_UNAVAILABLE",
                    "模型服务暂时不可用，稍后重试",
                )
            self.call_counts["paper_summary"] += 1
            paper_payload = request.input_payload.get("paper_payload", {})
            evidence_list = paper_payload.get("evidence")
            if evidence_list:
                ev_id = evidence_list[0]["evidence_id"]
            else:
                ev_id = _EVIDENCE_ID
            payload = {
                "background": (),
                "methodology": (),
                "dataset": (),
                "experiments": (
                    {
                        "statement_id": _STATEMENT_A,
                        "text": (
                            "The search targets confirmed transiting planets "
                            "around nearby host stars."
                        ),
                        "evidence_ids": [ev_id],
                    },
                    {
                        "statement_id": _STATEMENT_B,
                        "text": (
                            "Recovery methods for small planet candidates use "
                            "comparable transit signatures."
                        ),
                        "evidence_ids": [ev_id],
                    },
                ),
                "discussion": (),
                "limitations": (),
                "research_questions": (),
                "evidence_ids": [ev_id],
            }
        elif request.prompt_name == "literature_claim":
            self.call_counts["literature_claim"] += 1
            summary_payload = request.input_payload.get("paper_summary", {})
            ev_ids = summary_payload.get("evidence_ids") or [_EVIDENCE_ID]
            payload = {
                "schema_version": "1.0.0",
                "claims": (
                    _claim_payload(
                        _STATEMENT_A,
                        "Confirmed transiting planets orbit nearby host stars.",
                        evidence_ids=list(ev_ids),
                    ),
                    _claim_payload(
                        _STATEMENT_B,
                        "Small-planet recovery methods share comparable "
                        "transit signatures.",
                        evidence_ids=list(ev_ids),
                    ),
                ),
            }
        elif request.prompt_name == "literature_relation":
            self.call_counts["literature_relation"] += 1
            if self.fail_literature_relation:
                raise ModelExecutionError(
                    "MODEL_PROVIDER_UNAVAILABLE",
                    "模型推理服务暂时不可用",
                )
            claims_bundle = request.input_payload.get("claims", {})
            claims_list = claims_bundle.get("claims", ())
            claim_ids = [item["claim_id"] for item in claims_list]
            assert len(claim_ids) >= 2, "relation fixture needs two claims"
            ev_ids = claims_list[0].get("evidence_ids") or [_EVIDENCE_ID]
            assert "confidence_assessments" not in request.input_payload
            assert request.input_payload["max_relation_candidates"] == 1
            comparability_policy = request.input_payload[
                "relation_comparability_policy"
            ]
            pair = next(
                item
                for item in comparability_policy["pairs"]
                if item["source_claim_id"] == claim_ids[0]
                and item["target_claim_id"] == claim_ids[1]
            )
            assert pair["non_structural_allowed"] is True
            assert pair["non_structural_metric_status"] == "not_applicable"
            assert pair["non_structural_unit_status"] == "not_applicable"
            payload = {
                "schema_version": "1.0.0",
                "relations": (
                    _relation_payload(
                        claim_ids[0],
                        claim_ids[1],
                        evidence_ids=list(ev_ids),
                    ),
                ),
            }
        else:
            raise AssertionError(f"unexpected JSON prompt: {request.prompt_name}")
        return ModelExecutionResponse(
            payload=payload,
            output_hash=canonical_request_hash(payload),
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20,
            },
            latency_ms=3,
            provider_request_id=f"req-revision-{request.prompt_name}",
            provider_returned_model="test-returned-model-snapshot",
        )


class _FrozenCrossref:
    """Same deterministic records for the parent Run and every revision."""

    source_id = "crossref"
    adapter_name = "crossref_rest"
    adapter_version = "1.0.0"

    def __init__(self) -> None:
        self.search_calls = 0
        self.records = (
            RawSourceRecord(
                source_id=self.source_id,
                source_record_id="crossref-revision-0001",
                title="Confirmed transiting planets around nearby host stars",
                authors=("Zhang San",),
                year=2024,
                doi="10.9999/revision-0001",
                arxiv_id=None,
                url="https://doi.org/10.9999/revision-0001",
                abstract=None,
            ),
        )

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode,
        data_level,
    ) -> SourceSearchResult:
        self.search_calls += 1
        snapshot = SourceSnapshotRecord(
            snapshot_id=_SNAPSHOT_PIPELINE_ID,
            source_id=self.source_id,
            source_type="paper_metadata",
            retrieved_at=_FIXED_NOW,
            query=query.original_query_string,
            query_hash=query.query_hash,
            source_version_or_etag=None,
            content_hash=canonical_request_hash(
                {"records": [record.hash_payload() for record in self.records]}
            ),
            license_note="deposited metadata; publisher license governs content",
            cache_version=None,
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
            },
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
            request_hash=canonical_request_hash({"page": 1}),
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


def _create_chain(postgres_engine: Engine) -> dict[str, object]:
    """Parent Run executed to completion plus the shared worker runtime."""

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
        factory=factory, workflow_store=store, manifests=manifests
    )
    revision_service = RevisionApplicationService(factory=factory, workflow_store=store)

    session_id = f"session-{uuid4()}"
    project = service.create_project(
        session_id=session_id,
        idempotency_key=f"project-{uuid4()}",
        request=CreateResearchProjectRequest(
            name="文献与图谱修订重算执行",
            description="revision execution end-to-end",
            case_key="exoplanet_host_star",
        ),
    )
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="执行一次完整文献链路后验证修订重算闭环",
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

    adapter = _FrozenCrossref()
    model = _RevisionScriptedModel(factory)

    def make_worker() -> ResearchRunWorker:
        return ResearchRunWorker(
            factory=factory,
            store=store,
            executor=executor,
            manifests=manifests,
            model_port=model,
            requested_model="qwen3.7-max",
            explicit_revision=None,
            paper_collection_runner=LivePaperCollectionRunner(
                adapter=adapter,
                clock=lambda: _FIXED_NOW,
            ),
        )

    asyncio.run(make_worker().execute_run(UUID(run.id)))
    final = store.load_snapshot(UUID(run.id))
    assert final.status == "completed", final.failure_summary
    assert tuple(step.key for step in final.steps) == (
        "planning",
        "searching_papers",
        "summarizing_papers",
        "reasoning_literature",
        "building_graph",
    )
    return {
        "factory": factory,
        "store": store,
        "service": service,
        "revision_service": revision_service,
        "make_worker": make_worker,
        "project_id": project.id,
        "session_id": session_id,
        "run_id": UUID(run.id),
        "adapter": adapter,
        "model": model,
        "search_calls_after_parent": adapter.search_calls,
    }


@pytest.fixture(scope="function")
def chain(postgres_engine: Engine):
    """Parent Run executed to completion plus the shared worker runtime."""

    confidence_provider = _AcceptedConfidenceProvider()
    original_provider = (
        literature_steps_module.build_live_relation_confidence_assessments
    )
    literature_steps_module.build_live_relation_confidence_assessments = (
        confidence_provider
    )
    try:
        yield _create_chain(postgres_engine)
    finally:
        literature_steps_module.build_live_relation_confidence_assessments = (
            original_provider
        )


@pytest.fixture(scope="function")
def candidate_chain(postgres_engine: Engine):
    """Production confidence scope leaves the live Relation for adjudication."""

    return _create_chain(postgres_engine)


def _latest_version_id(chain, kind: str) -> UUID:
    with chain["factory"]() as session:
        artifact = session.scalar(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.project_id == UUID(chain["project_id"]),
                ResearchArtifactModel.logical_key == f"{kind}.primary",
            )
        )
        assert artifact is not None
        assert artifact.latest_version_id is not None
        return UUID(str(artifact.latest_version_id))


def _latest_version_number(chain, kind: str) -> int:
    version_id = _latest_version_id(chain, kind)
    with chain["factory"]() as session:
        version = session.get(ArtifactVersionModel, version_id)
        assert version is not None
        return version.version_number


def _create_feedback_for_target(
    chain,
    *,
    kind: str,
    target_type: FeedbackTargetType,
    summary: str = "修正事实",
    requested_change: str = "重新执行相关推理与构建",
    category: FeedbackCategory = FeedbackCategory.correction,
    adjudication_decision: RelationAdjudicationDecision | None = None,
):
    version_id = str(_latest_version_id(chain, kind))
    version_number = _latest_version_number(chain, kind)
    artifacts = ArtifactReadService(chain["factory"])
    document_parses = chain.get("document_parses")
    summary_reader = PaperSummaryReadService(artifacts, document_parses=document_parses)
    lit_service = LiteratureArtifactReadService(
        artifacts, paper_summary_reader=summary_reader
    )
    session_id = chain["session_id"]

    if target_type is FeedbackTargetType.paper_summary:
        summary_read = asyncio.run(
            summary_reader.get_summary(version_id=version_id, session_id=session_id)
        )
        target_id = summary_read.summary.summary_id
        locator = {"artifact_version_id": version_id, "summary_id": target_id}
    elif target_type is FeedbackTargetType.claim:
        claims_read = asyncio.run(
            lit_service.list_claims(
                version_id=version_id,
                session_id=session_id,
                status=None,
                cursor=None,
                limit=1,
            )
        )
        target_id = claims_read[0][0].claim.claim_id
        locator = {"artifact_version_id": version_id, "claim_id": target_id}
    elif target_type is FeedbackTargetType.relation:
        relations_read = asyncio.run(
            lit_service.list_relations(
                version_id=version_id,
                session_id=session_id,
                status=None,
                cursor=None,
                limit=1,
            )
        )
        target_id = relations_read[0][0].relation.relation_id
        locator = {"artifact_version_id": version_id, "relation_id": target_id}
    elif target_type is FeedbackTargetType.trace:
        traces_read = asyncio.run(
            lit_service.list_reasoning_traces(
                version_id=version_id,
                session_id=session_id,
                status=None,
                cursor=None,
                limit=1,
            )
        )
        target_id = traces_read[0][0].trace.trace_id
        locator = {"artifact_version_id": version_id, "trace_id": target_id}
    elif target_type is FeedbackTargetType.graph_node:
        nodes, _, _ = GraphArtifactReadService(artifacts).list_nodes(
            version_id=version_id,
            session_id=session_id,
            node_type=None,
            cursor=None,
            limit=1,
        )
        target_id = nodes[0].node.node_id
        locator = {"artifact_version_id": version_id, "node_id": target_id}
    elif target_type is FeedbackTargetType.graph_edge:
        edges, _, _ = asyncio.run(
            GraphArtifactReadService(artifacts).list_edges(
                version_id=version_id,
                session_id=session_id,
                edge_type=None,
                node_id=None,
                cursor=None,
                limit=1,
            )
        )
        target_id = edges[0].edge.edge_id
        locator = {"artifact_version_id": version_id, "edge_id": target_id}
    elif target_type is FeedbackTargetType.artifact_version:
        with chain["factory"]() as session:
            artifact = session.scalar(
                select(ResearchArtifactModel).where(
                    ResearchArtifactModel.project_id == UUID(chain["project_id"]),
                    ResearchArtifactModel.logical_key == f"{kind}.primary",
                )
            )
            assert artifact is not None
            artifact_id = str(artifact.id)
        target_id = version_id
        locator = {"artifact_id": artifact_id, "artifact_version_id": version_id}
    else:
        raise ValueError(f"unsupported target type: {target_type}")

    return asyncio.run(
        chain["revision_service"].create_feedback(
            version_id=version_id,
            session_id=session_id,
            idempotency_key=f"feedback-{uuid4()}",
            request=CreateUserFeedbackRequest(
                expected_version_number=version_number,
                target_type=target_type,
                target_id=target_id,
                target_locator=locator,
                category=category,
                adjudication_decision=adjudication_decision,
                summary=summary,
                requested_change=requested_change,
            ),
        )
    )


def _parent_run_revision(chain, feedback_id: str) -> int:
    with chain["factory"]() as session:
        feedback = session.get(UserFeedbackModel, UUID(feedback_id))
        assert feedback is not None
        baseline = session.get(
            ArtifactVersionModel, feedback.baseline_artifact_version_id
        )
        assert baseline is not None
        parent_run = session.get(ResearchRunModel, baseline.created_by_run_id)
        assert parent_run is not None
        return parent_run.revision


def _confirm_plan(
    chain, feedback_id: str, expected_parent_run_revision: int | None = None
):
    if expected_parent_run_revision is None:
        expected_parent_run_revision = _parent_run_revision(chain, feedback_id)
    plan = chain["revision_service"].create_plan(
        project_id=str(chain["project_id"]),
        session_id=chain["session_id"],
        idempotency_key=f"plan-{uuid4()}",
        request=CreateRevisionPlanRequest(
            feedback_ids=(feedback_id,),
            expected_parent_run_revision=expected_parent_run_revision,
        ),
    )
    run_id = chain["revision_service"].confirm_plan(
        plan_id=plan.id,
        session_id=chain["session_id"],
        idempotency_key=f"confirm-{uuid4()}",
        request=ConfirmRevisionPlanRequest(expected_plan_version=plan.version),
    )
    return plan, run_id


def test_parent_production_chain_reads_through_typed_readers(chain) -> None:
    """All 5 artifacts from parent run validate through existing typed readers."""

    artifacts = ArtifactReadService(chain["factory"])
    session_id = chain["session_id"]

    collection_id = str(_latest_version_id(chain, "paper_collection"))
    collection_read = PaperCollectionReadService(artifacts).get_collection(
        version_id=collection_id, session_id=session_id
    )
    assert len(collection_read.collection.candidates) == 1
    assert collection_read.collection.candidates[0].selected is True

    summary_id = str(_latest_version_id(chain, "paper_summary"))
    summary_read = asyncio.run(
        PaperSummaryReadService(artifacts).get_summary(
            version_id=summary_id, session_id=session_id
        )
    )
    assert (
        summary_read.summary.paper_id
        == collection_read.collection.candidates[0].canonical_paper_id
    )
    assert len(summary_read.summary.evidence) >= 1

    claims_id = str(_latest_version_id(chain, "literature_claims"))
    claims_items, _, _ = asyncio.run(
        LiteratureArtifactReadService(artifacts).list_claims(
            version_id=claims_id,
            session_id=session_id,
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(claims_items) == 2

    relations_id = str(_latest_version_id(chain, "literature_relations"))
    relations_items, _, _ = asyncio.run(
        LiteratureArtifactReadService(artifacts).list_relations(
            version_id=relations_id,
            session_id=session_id,
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(relations_items) == 1

    traces_items, _, _ = asyncio.run(
        LiteratureArtifactReadService(artifacts).list_reasoning_traces(
            version_id=relations_id,
            session_id=session_id,
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(traces_items) == 1

    graph_id = str(_latest_version_id(chain, "graph"))
    graph_read = GraphArtifactReadService(artifacts).get_graph(
        version_id=graph_id, session_id=session_id
    )
    assert graph_read.node_count >= 2
    assert graph_read.edge_count >= 1


def test_relation_feedback_recomputes_only_affected_closure(chain) -> None:
    """Relations feedback recomputes reasoning+graph; search & summary are reused."""

    search_calls_before = chain["adapter"].search_calls
    summary_model_calls_before = chain["model"].call_counts["paper_summary"]
    frozen_before = {
        kind: _latest_version_id(chain, kind)
        for kind in (
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "graph",
        )
    }

    feedback = _create_feedback_for_target(
        chain, kind="literature_relations", target_type=FeedbackTargetType.relation
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))
    assert plan.recompute_steps == (
        "planning",
        "reasoning_literature",
        "building_graph",
    )

    asyncio.run(chain["make_worker"]().execute_run(run_id))
    final = chain["store"].load_snapshot(run_id)
    assert final.status == "completed", final.failure_summary
    assert tuple(step.key for step in final.steps) == (
        "planning",
        "reasoning_literature",
        "building_graph",
    )

    # Excluded steps (searching_papers, summarizing_papers) were not executed
    assert chain["adapter"].search_calls == search_calls_before
    assert chain["model"].call_counts["paper_summary"] == summary_model_calls_before
    assert (
        _latest_version_id(chain, "paper_collection")
        == frozen_before["paper_collection"]
    )
    assert _latest_version_id(chain, "paper_summary") == frozen_before["paper_summary"]

    # Recomputed steps published new versions atomically
    new_claims = _latest_version_id(chain, "literature_claims")
    new_relations = _latest_version_id(chain, "literature_relations")
    new_graph = _latest_version_id(chain, "graph")

    assert new_claims != frozen_before["literature_claims"]
    assert new_relations != frozen_before["literature_relations"]
    assert new_graph != frozen_before["graph"]

    with chain["factory"]() as session:
        claims_row = session.get(ArtifactVersionModel, new_claims)
        relations_row = session.get(ArtifactVersionModel, new_relations)
        graph_row = session.get(ArtifactVersionModel, new_graph)
        assert claims_row.supersedes_version_id == frozen_before["literature_claims"]
        assert (
            relations_row.supersedes_version_id == frozen_before["literature_relations"]
        )
        assert graph_row.supersedes_version_id == frozen_before["graph"]
        assert any(
            item["artifact_version_id"] == str(new_relations)
            for item in graph_row.content["input_versions"]["versions"]
        )


_RELATION_SCIENTIFIC_FIELDS = (
    "relation_id",
    "pair_id",
    "source_claim_id",
    "target_claim_id",
    "source_claim_artifact_version_id",
    "target_claim_artifact_version_id",
    "source_paper_summary_artifact_version_id",
    "target_paper_summary_artifact_version_id",
    "relation_type",
    "direction",
    "conditions",
    "condition_conflicts",
    "condition_uncertainties",
    "comparability",
    "evidence_ids",
    "source_snapshot_ids",
    "reasoning_trace_id",
    "confidence",
    "fingerprint",
    "scientific_review_status",
)
_TRACE_SCIENTIFIC_FIELDS = (
    "trace_id",
    "relation_id",
    "premise_claim_ids",
    "steps",
    "conditions",
    "limitations",
    "conflicts",
    "conclusion",
    "evidence_ids",
    "trace_protocol_version",
    "scientific_review_status",
)


def _scientific_projection(value, fields: tuple[str, ...]) -> dict[str, object]:
    payload = value.model_dump(mode="json")
    return {field: payload[field] for field in fields}


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_relation_edges"),
    (
        (RelationAdjudicationDecision.accepted, "accepted", 1),
        (RelationAdjudicationDecision.rejected, "rejected", 0),
    ),
)
def test_relation_adjudication_reuses_claims_and_updates_graph(
    candidate_chain,
    decision: RelationAdjudicationDecision,
    expected_status: str,
    expected_relation_edges: int,
) -> None:
    """A reviewer decision promotes or rejects the exact candidate without model calls."""

    chain = candidate_chain
    artifacts = ArtifactReadService(chain["factory"])
    literature = LiteratureArtifactReadService(artifacts)
    graph = GraphArtifactReadService(artifacts)
    frozen = {
        kind: _latest_version_id(chain, kind)
        for kind in ("literature_claims", "literature_relations", "graph")
    }
    baseline_items, _, _ = asyncio.run(
        literature.list_relations(
            version_id=str(frozen["literature_relations"]),
            session_id=chain["session_id"],
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(baseline_items) == 1
    baseline_item = baseline_items[0]
    assert baseline_item.relation.status == "candidate"
    assert baseline_item.relation.adjudication is None
    assert baseline_item.reasoning_trace is not None
    graph_before = graph.get_graph(
        version_id=str(frozen["graph"]), session_id=chain["session_id"]
    )
    assert graph_before.edge_count > 0
    assert graph_before.integrity_report.counts.relation_edge_count == 0

    claims_calls_before = chain["model"].call_counts["literature_claim"]
    relation_calls_before = chain["model"].call_counts["literature_relation"]
    feedback = _create_feedback_for_target(
        chain,
        kind="literature_relations",
        target_type=FeedbackTargetType.relation,
        category=FeedbackCategory.adjudication,
        adjudication_decision=decision,
        summary=f"{expected_status} 该候选关系",
        requested_change=f"将该关系标记为{expected_status}并重建证据图谱",
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))
    assert plan.recompute_steps == (
        "planning",
        "reasoning_literature",
        "building_graph",
    )
    decisions = {item.artifact_kind: item for item in plan.version_decisions}
    assert decisions["literature_claims"].decision == "reuse"
    assert decisions["literature_relations"].decision == "recompute"
    assert decisions["graph"].decision == "recompute"

    asyncio.run(chain["make_worker"]().execute_run(run_id))
    final = chain["store"].load_snapshot(run_id)
    assert final.status == "completed", final.failure_summary
    assert chain["model"].call_counts["literature_claim"] == claims_calls_before
    assert chain["model"].call_counts["literature_relation"] == relation_calls_before
    assert _latest_version_id(chain, "literature_claims") == frozen["literature_claims"]

    new_relations = _latest_version_id(chain, "literature_relations")
    new_graph = _latest_version_id(chain, "graph")
    assert new_relations != frozen["literature_relations"]
    assert new_graph != frozen["graph"]
    with chain["factory"]() as session:
        version = session.get(ArtifactVersionModel, new_relations)
        assert version is not None
        assert version.supersedes_version_id == frozen["literature_relations"]
        producer = session.get(ProducerExecutionModel, version.producer_execution_id)
        assert producer is not None
        assert producer.run_id == UUID(str(run_id))
        assert producer.producer_type == "algorithm"
        assert producer.producer_name == "xingwen.literature_relation_adjudication"
        baseline_version = session.get(
            ArtifactVersionModel, frozen["literature_relations"]
        )
        assert baseline_version is not None
        new_candidate = LiteratureRelationsCandidate.model_validate(version.content)
        baseline_candidate = LiteratureRelationsCandidate.model_validate(
            baseline_version.content
        )
        adjudications = tuple(
            relation.adjudication
            for relation in new_candidate.relations
            if relation.adjudication is not None
        )
        expected_input_hash = compute_literature_relation_adjudication_input_hash(
            baseline_relation_artifact_version_id=str(frozen["literature_relations"]),
            baseline_relation_content_hash=baseline_version.content_hash,
            literature_claim_artifact_version_id=str(frozen["literature_claims"]),
            adjudications=adjudications,
        )
        assert producer.input_hash == expected_input_hash
        assert producer.input_hash != baseline_candidate.input_hash
        assert new_candidate.input_hash == baseline_candidate.input_hash
        revision_producers = tuple(
            session.scalars(
                select(ProducerExecutionModel).where(
                    ProducerExecutionModel.run_id == UUID(str(run_id))
                )
            )
        )
        assert not any(
            item.producer_name == RELATION_PRODUCER_NAME for item in revision_producers
        )

    adjudicated_items, _, _ = asyncio.run(
        literature.list_relations(
            version_id=str(new_relations),
            session_id=chain["session_id"],
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(adjudicated_items) == 1
    adjudicated_item = adjudicated_items[0]
    assert adjudicated_item.relation.status == expected_status
    assert adjudicated_item.relation.adjudication is not None
    assert adjudicated_item.relation.adjudication.decision == expected_status
    assert _scientific_projection(
        adjudicated_item.relation,
        _RELATION_SCIENTIFIC_FIELDS,
    ) == _scientific_projection(
        baseline_item.relation,
        _RELATION_SCIENTIFIC_FIELDS,
    )
    assert adjudicated_item.reasoning_trace is not None
    assert _scientific_projection(
        adjudicated_item.reasoning_trace,
        _TRACE_SCIENTIFIC_FIELDS,
    ) == _scientific_projection(
        baseline_item.reasoning_trace,
        _TRACE_SCIENTIFIC_FIELDS,
    )
    assert adjudicated_item.reasoning_trace.relation_status == expected_status

    graph_after = graph.get_graph(
        version_id=str(new_graph), session_id=chain["session_id"]
    )
    assert (
        graph_after.integrity_report.counts.relation_edge_count
        == expected_relation_edges
    )


def test_trace_feedback_recomputes_literature_relations_closure(chain) -> None:
    """Trace feedback targets literature_relations owner and rebuilds graph."""

    feedback = _create_feedback_for_target(
        chain, kind="literature_relations", target_type=FeedbackTargetType.trace
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))
    assert plan.recompute_steps == (
        "planning",
        "reasoning_literature",
        "building_graph",
    )

    asyncio.run(chain["make_worker"]().execute_run(run_id))
    final = chain["store"].load_snapshot(run_id)
    assert final.status == "completed", final.failure_summary

    artifacts = ArtifactReadService(chain["factory"])
    new_relations_id = str(_latest_version_id(chain, "literature_relations"))
    traces, _, _ = asyncio.run(
        LiteratureArtifactReadService(artifacts).list_reasoning_traces(
            version_id=new_relations_id,
            session_id=chain["session_id"],
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(traces) == 1
    assert traces[0].trace.relation_status == "accepted"


def test_graph_only_feedback_recomputes_only_graph_on_frozen_relations(chain) -> None:
    """Graph-only feedback recomputes building_graph using frozen literature_relations."""

    search_calls_before = chain["adapter"].search_calls
    summary_calls_before = chain["model"].call_counts["paper_summary"]
    claim_calls_before = chain["model"].call_counts["literature_claim"]
    relation_calls_before = chain["model"].call_counts["literature_relation"]

    frozen_before = {
        kind: _latest_version_id(chain, kind)
        for kind in (
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "graph",
        )
    }

    feedback = _create_feedback_for_target(
        chain, kind="graph", target_type=FeedbackTargetType.graph_node
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))
    assert plan.recompute_steps == ("planning", "building_graph")

    asyncio.run(chain["make_worker"]().execute_run(run_id))
    final = chain["store"].load_snapshot(run_id)
    assert final.status == "completed", final.failure_summary
    assert tuple(step.key for step in final.steps) == ("planning", "building_graph")

    # Zero paper source calls and zero model calls
    assert chain["adapter"].search_calls == search_calls_before
    assert chain["model"].call_counts["paper_summary"] == summary_calls_before
    assert chain["model"].call_counts["literature_claim"] == claim_calls_before
    assert chain["model"].call_counts["literature_relation"] == relation_calls_before

    # Upstream latest versions remain unchanged
    assert (
        _latest_version_id(chain, "paper_collection")
        == frozen_before["paper_collection"]
    )
    assert _latest_version_id(chain, "paper_summary") == frozen_before["paper_summary"]
    assert (
        _latest_version_id(chain, "literature_claims")
        == frozen_before["literature_claims"]
    )
    assert (
        _latest_version_id(chain, "literature_relations")
        == frozen_before["literature_relations"]
    )

    # Graph receives a new superseding version
    new_graph = _latest_version_id(chain, "graph")
    assert new_graph != frozen_before["graph"]

    with chain["factory"]() as session:
        graph_row = session.get(ArtifactVersionModel, new_graph)
        assert graph_row.supersedes_version_id == frozen_before["graph"]
        assert any(
            item["artifact_version_id"] == str(frozen_before["literature_relations"])
            for item in graph_row.content["input_versions"]["versions"]
        )


def test_paper_summary_feedback_recomputes_from_frozen_collection(chain) -> None:
    """PaperSummary feedback recomputes summary+reasoning+graph from frozen collection."""

    search_calls_before = chain["adapter"].search_calls
    frozen_before = {
        kind: _latest_version_id(chain, kind)
        for kind in (
            "paper_collection",
            "paper_summary",
            "literature_claims",
            "literature_relations",
            "graph",
        )
    }

    feedback = _create_feedback_for_target(
        chain, kind="paper_summary", target_type=FeedbackTargetType.paper_summary
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))
    assert plan.recompute_steps == (
        "planning",
        "summarizing_papers",
        "reasoning_literature",
        "building_graph",
    )

    asyncio.run(chain["make_worker"]().execute_run(run_id))
    final = chain["store"].load_snapshot(run_id)
    assert final.status == "completed", final.failure_summary
    assert tuple(step.key for step in final.steps) == (
        "planning",
        "summarizing_papers",
        "reasoning_literature",
        "building_graph",
    )

    # searching_papers is not rerun; paper_collection reused from frozen baseline
    assert chain["adapter"].search_calls == search_calls_before
    assert (
        _latest_version_id(chain, "paper_collection")
        == frozen_before["paper_collection"]
    )

    new_summary = _latest_version_id(chain, "paper_summary")
    new_claims = _latest_version_id(chain, "literature_claims")
    new_relations = _latest_version_id(chain, "literature_relations")
    new_graph = _latest_version_id(chain, "graph")

    assert new_summary != frozen_before["paper_summary"]
    assert new_claims != frozen_before["literature_claims"]
    assert new_relations != frozen_before["literature_relations"]
    assert new_graph != frozen_before["graph"]


def test_worker_preflight_rejects_adversarial_stale_baseline_before_side_effects(
    chain,
) -> None:
    """Defense in depth: storage drift fails the sole queued revision Run."""

    frozen_graph_id = _latest_version_id(chain, "graph")
    feedback = _create_feedback_for_target(
        chain, kind="graph", target_type=FeedbackTargetType.graph_node
    )
    _, run_id = _confirm_plan(chain, str(feedback.id))

    # Adversarially drift only the frozen storage baseline. This is not a second
    # concurrent production Run; the single-active-Run invariant remains intact.
    adversarial_graph_id = uuid4()
    with chain["factory"]() as session, session.begin():
        frozen = session.get(ArtifactVersionModel, frozen_graph_id)
        assert frozen is not None
        session.add(
            ArtifactVersionModel(
                id=adversarial_graph_id,
                artifact_id=frozen.artifact_id,
                project_id=frozen.project_id,
                created_by_run_id=frozen.created_by_run_id,
                run_step_id=frozen.run_step_id,
                step_attempt_id=frozen.step_attempt_id,
                producer_execution_id=frozen.producer_execution_id,
                version_number=frozen.version_number + 1,
                publication_key=f"adversarial-stale-graph-{uuid4()}",
                schema_version=frozen.schema_version,
                content=dict(frozen.content),
                content_hash=frozen.content_hash,
                input_hash=frozen.input_hash,
                source_mode=frozen.source_mode,
                producer=dict(frozen.producer),
                source_snapshot_ids=list(frozen.source_snapshot_ids),
                evidence_ids=list(frozen.evidence_ids),
                supersedes_version_id=frozen.id,
                created_at=_FIXED_NOW,
            )
        )
        session.flush()
        artifact = session.get(ResearchArtifactModel, frozen.artifact_id)
        assert artifact is not None
        artifact.latest_version_id = adversarial_graph_id

    search_calls_before = chain["adapter"].search_calls
    summary_calls_before = chain["model"].call_counts["paper_summary"]
    claim_calls_before = chain["model"].call_counts["literature_claim"]
    relation_calls_before = chain["model"].call_counts["literature_relation"]

    asyncio.run(chain["make_worker"]().execute_run(UUID(str(run_id))))
    snapshot = chain["store"].load_snapshot(UUID(str(run_id)))
    assert snapshot.status == "failed"
    assert snapshot.failure_code == "REVISION_DATA_BASELINE_STALE"
    assert snapshot.failure_summary is not None

    assert chain["adapter"].search_calls == search_calls_before
    assert chain["model"].call_counts["paper_summary"] == summary_calls_before
    assert chain["model"].call_counts["literature_claim"] == claim_calls_before
    assert chain["model"].call_counts["literature_relation"] == relation_calls_before
    assert _latest_version_id(chain, "graph") == adversarial_graph_id
    with chain["factory"]() as session:
        assert (
            session.scalar(
                select(ArtifactVersionModel)
                .where(ArtifactVersionModel.created_by_run_id == UUID(str(run_id)))
                .limit(1)
            )
            is None
        )


def test_literature_model_failure_does_not_publish_partial_sets(chain) -> None:
    """Model provider failure during reasoning fails cleanly without partial publications."""

    latest_before = {
        kind: _latest_version_id(chain, kind)
        for kind in ("literature_claims", "literature_relations", "graph")
    }

    feedback = _create_feedback_for_target(
        chain, kind="literature_relations", target_type=FeedbackTargetType.relation
    )
    plan, run_id = _confirm_plan(chain, str(feedback.id))

    chain["model"].fail_literature_relation = True
    try:
        asyncio.run(chain["make_worker"]().execute_run(UUID(str(run_id))))
    finally:
        chain["model"].fail_literature_relation = False

    snapshot = chain["store"].load_snapshot(UUID(str(run_id)))
    assert snapshot.status == "failed"

    # 1. No partial publication occurred: latest pointers are unchanged
    assert (
        _latest_version_id(chain, "literature_claims")
        == latest_before["literature_claims"]
    )
    assert (
        _latest_version_id(chain, "literature_relations")
        == latest_before["literature_relations"]
    )
    assert _latest_version_id(chain, "graph") == latest_before["graph"]

    # 2. No partial ArtifactVersions were created by this failed Run
    with chain["factory"]() as session:
        new_versions = session.scalars(
            select(ArtifactVersionModel).where(
                ArtifactVersionModel.created_by_run_id == UUID(str(run_id))
            )
        ).all()
        assert len(new_versions) == 0

        # 3. All ProducerExecution records have terminal states (no running executions)
        producers = session.scalars(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.run_id == UUID(str(run_id))
            )
        ).all()
        assert len(producers) >= 2
        for prod in producers:
            assert prod.status != "running"

        claim_prod = next(
            p for p in producers if p.producer_name == CLAIM_PRODUCER_NAME
        )
        assert claim_prod.status == "completed"
        assert claim_prod.output_hash is not None

        relation_prod = next(
            p for p in producers if p.producer_name == RELATION_PRODUCER_NAME
        )
        assert relation_prod.status == "failed"


def test_claims_post_provider_local_failure_terminalizes_execution(
    chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Claims local admission exception fails its producer before retry/exit."""

    latest_before = {
        kind: _latest_version_id(chain, kind)
        for kind in ("literature_claims", "literature_relations", "graph")
    }
    relation_calls_before = chain["model"].call_counts["literature_relation"]
    feedback = _create_feedback_for_target(
        chain, kind="literature_relations", target_type=FeedbackTargetType.relation
    )
    _, run_id = _confirm_plan(chain, str(feedback.id))

    def fail_claims_admission(*_args, **_kwargs):
        raise RuntimeError("injected Claims post-provider local failure")

    monkeypatch.setattr(
        literature_steps_module.LiteratureClaimPipeline,
        "admit",
        fail_claims_admission,
    )
    asyncio.run(chain["make_worker"]().execute_run(UUID(str(run_id))))

    snapshot = chain["store"].load_snapshot(UUID(str(run_id)))
    assert snapshot.status == "failed"
    assert chain["model"].call_counts["literature_relation"] == relation_calls_before
    for kind, version_id in latest_before.items():
        assert _latest_version_id(chain, kind) == version_id

    with chain["factory"]() as session:
        assert (
            session.scalar(
                select(ArtifactVersionModel)
                .where(ArtifactVersionModel.created_by_run_id == UUID(str(run_id)))
                .limit(1)
            )
            is None
        )
        producers = session.scalars(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.run_id == UUID(str(run_id))
            )
        ).all()
        assert producers
        assert all(item.status != "running" for item in producers)
        claims = [
            item for item in producers if item.producer_name == CLAIM_PRODUCER_NAME
        ]
        assert claims
        assert all(item.status == "failed" for item in claims)
        assert all(
            item.error_code == "LITERATURE_CLAIM_POST_PROVIDER_LOCAL_FAILURE"
            for item in claims
        )
        assert all(item.output_hash is not None for item in claims)
        assert all(
            item.provider_request_id == "req-revision-literature_claim"
            for item in claims
        )
        assert all(item.model_response is not None for item in claims)
        assert not any(
            item.producer_name == RELATION_PRODUCER_NAME for item in producers
        )


def test_relation_post_provider_local_failure_terminalizes_execution(
    chain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Relation local admission exception fails after Claims is completed."""

    latest_before = {
        kind: _latest_version_id(chain, kind)
        for kind in ("literature_claims", "literature_relations", "graph")
    }
    feedback = _create_feedback_for_target(
        chain, kind="literature_relations", target_type=FeedbackTargetType.relation
    )
    _, run_id = _confirm_plan(chain, str(feedback.id))

    def fail_relation_admission(*_args, **_kwargs):
        raise RuntimeError("injected Relation post-provider local failure")

    monkeypatch.setattr(
        literature_steps_module.LiteratureRelationPipeline,
        "admit",
        fail_relation_admission,
    )
    asyncio.run(chain["make_worker"]().execute_run(UUID(str(run_id))))

    snapshot = chain["store"].load_snapshot(UUID(str(run_id)))
    assert snapshot.status == "failed"
    for kind, version_id in latest_before.items():
        assert _latest_version_id(chain, kind) == version_id

    with chain["factory"]() as session:
        assert (
            session.scalar(
                select(ArtifactVersionModel)
                .where(ArtifactVersionModel.created_by_run_id == UUID(str(run_id)))
                .limit(1)
            )
            is None
        )
        producers = session.scalars(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.run_id == UUID(str(run_id))
            )
        ).all()
        assert producers
        assert all(item.status != "running" for item in producers)
        claims = [
            item for item in producers if item.producer_name == CLAIM_PRODUCER_NAME
        ]
        relations = [
            item for item in producers if item.producer_name == RELATION_PRODUCER_NAME
        ]
        assert claims
        assert relations
        assert all(item.status == "completed" for item in claims)
        assert all(item.output_hash is not None for item in claims)
        assert all(item.status == "failed" for item in relations)
        assert all(
            item.error_code == "LITERATURE_RELATION_POST_PROVIDER_LOCAL_FAILURE"
            for item in relations
        )
        assert all(item.output_hash is not None for item in relations)
        assert all(
            item.provider_request_id == "req-revision-literature_relation"
            for item in relations
        )
        assert all(item.model_response is not None for item in relations)


def test_literature_evidence_locator_full_provenance_and_graph_build(chain) -> None:
    """Persisted literature Evidence locator preserves all fields and Graph input validates."""

    relations_version_id = _latest_version_id(chain, "literature_relations")
    with chain["factory"]() as session:
        evidence_rows = session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.artifact_version_id == relations_version_id
            )
        ).all()
        assert len(evidence_rows) >= 1
        for row in evidence_rows:
            assert isinstance(row.locator, dict)
            assert "kind" in row.locator
            assert "section" in row.locator
            assert "page" in row.locator
            assert "paragraph" in row.locator
            assert "range" in row.locator
            assert "metadata_field" in row.locator
            assert "summary_evidence_id" in row.locator
            assert "source_record_id" in row.locator

    artifacts = ArtifactReadService(chain["factory"])
    graph_version_id = str(_latest_version_id(chain, "graph"))
    graph_service = GraphArtifactReadService(artifacts)
    graph_read = graph_service.get_graph(
        version_id=graph_version_id,
        session_id=chain["session_id"],
    )
    assert graph_read.edge_count >= 1
    edges, _, _ = asyncio.run(
        graph_service.list_edges(
            version_id=graph_version_id,
            session_id=chain["session_id"],
            edge_type=None,
            node_id=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(edges) >= 1
    for item in edges:
        if item.edge.edge_type is GraphEdgeType.supports_finding:
            assert item.edge.relation_trace is None
            assert len(item.evidence) >= 1
        else:
            assert item.edge.relation_trace is not None
            assert item.edge.relation_trace.relation_id is not None
            assert len(item.evidence) >= 1


@pytest.mark.parametrize("document_source", ("upload", "url_fetch"))
def test_document_parse_backed_summary_revision_preserves_provenance_and_recomputes_graph(
    postgres_engine: Engine, tmp_path: Path, document_source: str
) -> None:
    """DocumentParse-backed Summary reuses frozen summary and validates complete provenance."""

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
        factory=factory, workflow_store=store, manifests=manifests
    )
    revision_service = RevisionApplicationService(factory=factory, workflow_store=store)

    session_id = f"session-{uuid4()}"
    project = service.create_project(
        session_id=session_id,
        idempotency_key=f"project-{uuid4()}",
        request=CreateResearchProjectRequest(
            name="文献全文与图谱修订重算执行",
            description="document-parse backed revision execution end-to-end",
            case_key="exoplanet_host_star",
        ),
    )
    draft = service.create_draft(
        project_id=project.id,
        session_id=session_id,
        idempotency_key=f"draft-{uuid4()}",
        request=CreateResearchContractDraftRequest(
            intent="验证包含全文DocumentParse的文献摘要在修订重算时的冻结复用与图谱生成",
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

    content_storage = LocalContentStorage(tmp_path / "cas")
    input_store = PersistentResearchInputStore(factory)
    pdf_bytes = b"%PDF-1.7\nScientific Document Content for Revision Test\n"

    async def fetch_document(url: str, config: UrlFetchConfig) -> UrlFetchResult:
        assert url == "https://repository.example/paper.pdf"
        content_hash = sha256_content_hash(pdf_bytes)
        return UrlFetchResult(
            content_hash=content_hash,
            content_bytes=pdf_bytes,
            mime_type="application/pdf",
            status_code=200,
            final_url=url,
            source_snapshot=SourceSnapshotRecord(
                snapshot_id="snapshot.document-source",
                source_id="repository.example",
                source_type="url_fetch",
                retrieved_at=_FIXED_NOW,
                query=url,
                query_hash=canonical_request_hash(url),
                content_hash=content_hash,
                license_note="Controlled document fixture",
                request_metadata={"status_code": 200},
            ),
        )

    research_input = asyncio.run(
        ResearchInputIngestionService(
            repository=input_store,
            idempotency_repository=PersistentIdempotencyRepository(factory),
            content_storage=content_storage,
            policy=ResearchInputPolicy.from_values(
                allowed_mime_types=("application/pdf",),
                max_size_bytes=1024 * 1024,
            ),
            url_fetch_config=UrlFetchConfig(
                allowed_protocols=("https",),
                allowed_hosts=(),
                timeout_seconds=1,
                max_redirects=0,
                max_response_bytes=1024,
            ),
            url_fetcher=fetch_document,
        ).create(
            ResearchInputIngestionCommand(
                session_id=session_id,
                project_id=project.id,
                payload=ResearchInputCreate(
                    type="url" if document_source == "url_fetch" else "pdf",
                    url=(
                        "https://repository.example/paper.pdf"
                        if document_source == "url_fetch"
                        else None
                    ),
                    filename="test_paper.pdf",
                    mime_type="application/pdf",
                ),
                idempotency_key=f"upload-{uuid4()}",
                file_content=pdf_bytes if document_source == "upload" else None,
                file_filename="test_paper.pdf" if document_source == "upload" else None,
            )
        )
    )

    def _doc_candidate(input_id: UUID, content_hash: str) -> DocumentParseCandidate:
        block = DocumentBlock(
            block_id="primary-paragraph-block",
            page_index=0,
            reading_order=0,
            kind=DocumentBlockKind.paragraph,
            bbox=DocumentBBox(x1=10, y1=20, x2=200, y2=120),
            text="The search targets confirmed transiting planets around nearby host stars.",
            quality=DocumentParseQuality.accepted,
            parser_backend=ParserBackend.native,
            parser_profile_id="native-default",
        )
        profile = DocumentParseProfile(
            parser_profile_id="native-default",
            parser_profile_version="1.0.0",
            native_backend="pymupdf",
            visual_backend=None,
            routing_policy_id="native-default",
            resource_policy_id="default-budget",
            configuration_hash="sha256:" + "c" * 64,
        )
        return DocumentParseCandidate(
            parse_id="document-parse-candidate",
            research_input_id=str(input_id),
            content_hash=content_hash,
            profile=profile,
            native_engine="pymupdf",
            native_engine_version="1.0.0",
            config_hash=profile.configuration_hash,
            canonical_output_hash=compute_canonical_payload_hash(
                {"blocks": [block.model_dump(mode="json")]}
            ),
            pages=(
                DocumentPage(
                    page_index=0,
                    width_points=612.0,
                    height_points=792.0,
                    block_ids=("primary-paragraph-block",),
                ),
            ),
            blocks=(block,),
            tables=(),
            overall_quality=DocumentParseQuality.accepted,
            created_at=_FIXED_NOW,
        )

    class _TestDocParser:
        @property
        def profile(self) -> DocumentParseProfile:
            return DocumentParseProfile(
                parser_profile_id="native-default",
                parser_profile_version="1.0.0",
                native_backend="pymupdf",
                visual_backend=None,
                routing_policy_id="native-default",
                resource_policy_id="default-budget",
                configuration_hash="sha256:" + "c" * 64,
            )

        def parse_document(self, input: DocumentParseInput) -> DocumentParseCandidate:
            return _doc_candidate(UUID(input.research_input_id), input.content_hash)

    adapter = _FrozenCrossref()
    model = _RevisionScriptedModel(factory)
    document_parser = _TestDocParser()
    adapter.records += (
        RawSourceRecord(
            source_id="crossref",
            source_record_id="document-source-paper",
            title="Stellar parameters for nearby transiting planet systems",
            authors=("Document Author",),
            year=2025,
            doi="10.9999/document-source-paper",
            arxiv_id=None,
            url="https://doi.org/10.9999/document-source-paper",
            abstract=None,
        ),
    )

    def make_worker() -> ResearchRunWorker:
        return ResearchRunWorker(
            factory=factory,
            store=store,
            executor=executor,
            manifests=manifests,
            model_port=model,
            requested_model="qwen3.7-max",
            explicit_revision=None,
            paper_collection_runner=LivePaperCollectionRunner(
                adapter=adapter,
                clock=lambda: _FIXED_NOW,
            ),
            content_storage=content_storage,
            document_parser=document_parser,
        )

    confidence_provider = _AcceptedConfidenceProvider()
    original_provider = (
        literature_steps_module.build_live_relation_confidence_assessments
    )
    literature_steps_module.build_live_relation_confidence_assessments = (
        confidence_provider
    )
    try:

        def _project_latest_version_id(kind: str) -> UUID:
            with factory() as session:
                artifact = session.scalar(
                    select(ResearchArtifactModel).where(
                        ResearchArtifactModel.project_id == UUID(project.id),
                        ResearchArtifactModel.logical_key == f"{kind}.primary",
                    )
                )
                assert artifact is not None
                assert artifact.latest_version_id is not None
                return UUID(str(artifact.latest_version_id))

        artifacts = ArtifactReadService(factory)
        paper_collections = PaperCollectionReadService(artifacts)
        paper_candidate_input_service = PaperCandidateInputService(
            paper_collections=paper_collections,
            ingestion=ResearchInputIngestionService(
                repository=input_store,
                idempotency_repository=PersistentIdempotencyRepository(factory),
                content_storage=content_storage,
                policy=ResearchInputPolicy.from_values(
                    allowed_mime_types=("application/pdf",),
                    max_size_bytes=1024 * 1024,
                ),
                url_fetch_config=UrlFetchConfig(
                    allowed_protocols=("https",),
                    allowed_hosts=(),
                    timeout_seconds=1,
                    max_redirects=0,
                    max_response_bytes=1024,
                ),
            ),
            research_inputs=input_store,
            repository=PaperCandidateInputRepository(factory),
        )

        bridged = False

        def _bridge_hook(tool_name: str) -> None:
            nonlocal bridged
            if bridged:
                return
            with factory() as session:
                artifact = session.scalar(
                    select(ResearchArtifactModel).where(
                        ResearchArtifactModel.project_id == UUID(project.id),
                        ResearchArtifactModel.logical_key == "paper_collection.primary",
                    )
                )
                if artifact is None or artifact.latest_version_id is None:
                    return
                collection_ver_id = str(artifact.latest_version_id)
            collection_read = paper_collections.get_collection(
                version_id=collection_ver_id, session_id=session_id
            )
            assert len(collection_read.collection.candidates) == 2
            bound_candidate = collection_read.collection.candidates[-1]
            assert bound_candidate.selected
            cand_id = bound_candidate.candidate_id
            access_evidence = PaperCandidateAccessEvidence(
                kind=PaperAccessEvidenceKind.author_provided,
                license="CC-BY-4.0",
                evidence_url="https://publisher.example/proof",
                canonical_paper_id=bound_candidate.canonical_paper_id,
                resource_type="research_input",
                resource_identity_hash=canonical_request_hash(
                    {
                        "resource_type": "research_input",
                        "research_input_id": str(research_input.id),
                        "content_hash": research_input.content_hash,
                    }
                ),
            )
            asyncio.run(
                paper_candidate_input_service.create(
                    CreatePaperCandidateInputCommand(
                        session_id=session_id,
                        paper_collection_version_id=collection_ver_id,
                        candidate_id=cand_id,
                        idempotency_key=f"bridge-{uuid4()}",
                        request=ExistingPaperCandidateInputRequest(
                            mode="existing_research_input",
                            research_input_id=str(research_input.id),
                            access_evidence=access_evidence,
                        ),
                    )
                )
            )
            bridged = True

        model.before_step_hook = _bridge_hook

        # 1. Execute parent run through DocumentParse-backed summary, claims, relations, graph
        parent_run_id = UUID(run.id)
        asyncio.run(make_worker().execute_run(parent_run_id))
        final = store.load_snapshot(parent_run_id)
        assert final.status == "completed", final.failure_summary

        parent_summary_version_id = _project_latest_version_id("paper_summary")
        parent_relations_version_id = _project_latest_version_id("literature_relations")
        parent_claims_version_id = _project_latest_version_id("literature_claims")
        parent_graph_version_id = _project_latest_version_id("graph")

        # Confirm parent summary is DocumentParse-backed
        summary_ver = artifacts.get_version(
            version_id=str(parent_summary_version_id), session_id=session_id
        )
        assert (
            len(
                summary_ver.content.get("input_versions", {}).get("document_parses", ())
            )
            == 1
        )

        # 2. Submit relation feedback and confirm revision plan
        doc_parse_service = DocumentParseService(
            DocumentParseRepository(factory), content_storage
        )
        summary_reader = PaperSummaryReadService(
            ArtifactReadService(factory),
            document_parses=doc_parse_service,
        )
        target_authority = FeedbackTargetAuthority(
            ArtifactReadService(factory),
            paper_summary_reader=summary_reader,
        )
        revision_service = RevisionApplicationService(
            factory=factory,
            workflow_store=store,
            target_authority=target_authority,
        )
        chain_ctx = {
            "factory": factory,
            "revision_service": revision_service,
            "project_id": project.id,
            "session_id": session_id,
            "document_parses": doc_parse_service,
        }
        feedback = _create_feedback_for_target(
            chain_ctx,
            kind="literature_relations",
            target_type=FeedbackTargetType.relation,
            summary="修正关系",
            requested_change="重新执行相关推理与构建",
        )
        plan, confirmed_run_id = _confirm_plan(chain_ctx, feedback.id)
        revision_run_id = UUID(str(confirmed_run_id))

        search_calls_before = adapter.search_calls
        summary_calls_before = model.call_counts["paper_summary"]

        # 3. Execute revision run
        asyncio.run(make_worker().execute_run(revision_run_id))
        rev_final = store.load_snapshot(revision_run_id)
        assert rev_final.status == "completed", rev_final.failure_summary

        # Assertions 1-11:
        # 1. PaperSummary exact ArtifactVersion ID unchanged
        assert _project_latest_version_id("paper_summary") == parent_summary_version_id

        # 2. No re-execution of paper search
        assert adapter.search_calls == search_calls_before

        # 3. No re-acquisition of external paper sources
        assert model.call_counts["paper_summary"] == summary_calls_before

        # 4. reasoning_literature executed normally
        assert any(
            step.key == "reasoning_literature" and step.status == "completed"
            for step in rev_final.steps
        )
        assert any(
            step.key == "building_graph" and step.status == "completed"
            for step in rev_final.steps
        )
        assert not any(
            step.key in {"searching_papers", "summarizing_papers"}
            for step in rev_final.steps
        )

        # 5. Claims + Relations published atomically as co-output publication set
        new_claims_ver_id = _project_latest_version_id("literature_claims")
        new_relations_ver_id = _project_latest_version_id("literature_relations")
        assert new_claims_ver_id != parent_claims_version_id
        assert new_relations_ver_id != parent_relations_version_id
        new_claims_ver = artifacts.get_version(
            version_id=str(new_claims_ver_id), session_id=session_id
        )
        new_relations_ver = artifacts.get_version(
            version_id=str(new_relations_ver_id), session_id=session_id
        )
        assert new_claims_ver.supersedes_version_id == str(parent_claims_version_id)
        assert new_relations_ver.supersedes_version_id == str(
            parent_relations_version_id
        )
        assert new_claims_ver.created_by_run_id == str(revision_run_id)
        assert new_relations_ver.created_by_run_id == str(revision_run_id)

        # 6. ReasoningTrace in LiteratureRelations
        summary_reader = PaperSummaryReadService(
            artifacts,
            document_parses=doc_parse_service,
        )
        lit_service = LiteratureArtifactReadService(
            artifacts, paper_summary_reader=summary_reader
        )
        traces, _, _ = asyncio.run(
            lit_service.list_reasoning_traces(
                version_id=str(new_relations_ver_id),
                session_id=session_id,
                status=None,
                cursor=None,
                limit=10,
            )
        )
        assert len(traces) >= 1
        assert traces[0].trace.conclusion is not None

        # 7. Graph completely rebuilt from new exact LiteratureRelations version
        new_graph_ver_id = _project_latest_version_id("graph")
        assert new_graph_ver_id != parent_graph_version_id
        new_graph_ver = artifacts.get_version(
            version_id=str(new_graph_ver_id), session_id=session_id
        )
        assert new_graph_ver.supersedes_version_id == str(parent_graph_version_id)
        assert new_graph_ver.created_by_run_id == str(revision_run_id)

        # 8. Typed readers read new Claims, Relations, Graph
        graph_service = GraphArtifactReadService(artifacts)
        graph_read = graph_service.get_graph(
            version_id=str(new_graph_ver_id), session_id=session_id
        )
        assert graph_read.edge_count >= 1

        # 9. DocumentParse / ResearchInput / Evidence / SourceSnapshot provenance closure holds
        summary_read = asyncio.run(
            summary_reader.get_summary(
                version_id=str(parent_summary_version_id), session_id=session_id
            )
        )
        assert len(summary_read.summary.input_versions.document_parses) == 1
        assert (
            summary_read.summary.input_versions.document_parses[0].document_parse_id
            is not None
        )

        # 10. No raw/private chain-of-thought persistence
        assert "private" not in str(new_relations_ver.content).lower()
        assert "chain_of_thought" not in str(new_relations_ver.content).lower()

        # 11. Old ArtifactVersions remain readable
        old_summary_read = asyncio.run(
            summary_reader.get_summary(
                version_id=str(parent_summary_version_id), session_id=session_id
            )
        )
        assert old_summary_read.artifact_version_id == str(parent_summary_version_id)
        old_graph_read = graph_service.get_graph(
            version_id=str(parent_graph_version_id), session_id=session_id
        )
        assert old_graph_read.version.artifact_version_id == str(
            parent_graph_version_id
        )
    finally:
        literature_steps_module.build_live_relation_confidence_assessments = (
            original_provider
        )


def test_uuid_shaped_logical_snapshot_identity_is_not_treated_as_persisted_uuid(
    chain,
) -> None:
    """A logical pipeline snapshot ID with UUID format is mapped deterministically to a distinct persisted UUID."""

    logical_id = _SNAPSHOT_PIPELINE_ID
    project_id = str(chain["project_id"])
    expected_persisted_uuid = step_uuid(project_id, f"source-snapshot:{logical_id}")

    # Verify that the logical string and persisted UUID are distinct despite both having UUID shape
    assert logical_id != str(expected_persisted_uuid)

    with chain["factory"]() as session:
        # 1. SourceSnapshotModel row in DB has the deterministic derived UUID, not the logical ID
        snapshot = session.get(SourceSnapshotModel, expected_persisted_uuid)
        assert snapshot is not None
        assert snapshot.source_id == "crossref"
        assert str(snapshot.id) == str(expected_persisted_uuid)

        raw_logical_snapshot = session.get(SourceSnapshotModel, UUID(logical_id))
        assert raw_logical_snapshot is None

        # 2. EvidenceModel rows reference the deterministic persisted UUID
        summary_ver_id = _latest_version_id(chain, "paper_summary")
        evidence_rows = session.scalars(
            select(EvidenceModel).where(
                EvidenceModel.artifact_version_id == summary_ver_id
            )
        ).all()
        assert len(evidence_rows) >= 1
        for ev in evidence_rows:
            assert ev.source_snapshot_id == expected_persisted_uuid
            assert str(ev.source_snapshot_id) != logical_id

        # 3. ArtifactVersionModel source_snapshot_ids lists the persisted UUID
        summary_version = session.get(ArtifactVersionModel, summary_ver_id)
        assert summary_version is not None
        assert str(expected_persisted_uuid) in [
            str(x) for x in summary_version.source_snapshot_ids
        ]

    # 4. Typed readers close all PaperSummary, LiteratureClaims, LiteratureRelations, and Graph queries
    artifacts = ArtifactReadService(chain["factory"])
    session_id = chain["session_id"]
    summary_read = asyncio.run(
        PaperSummaryReadService(artifacts).get_summary(
            version_id=str(summary_ver_id), session_id=session_id
        )
    )
    assert summary_read.summary.source_snapshot_ids == (logical_id,)

    claims_id = str(_latest_version_id(chain, "literature_claims"))
    claims_items, _, _ = asyncio.run(
        LiteratureArtifactReadService(artifacts).list_claims(
            version_id=claims_id,
            session_id=session_id,
            status=None,
            cursor=None,
            limit=10,
        )
    )
    assert len(claims_items) == 2

    graph_id = str(_latest_version_id(chain, "graph"))
    graph_read = GraphArtifactReadService(artifacts).get_graph(
        version_id=graph_id, session_id=session_id
    )
    assert graph_read.edge_count >= 1
