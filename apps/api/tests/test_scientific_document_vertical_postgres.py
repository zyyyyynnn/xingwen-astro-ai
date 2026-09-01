"""Real PostgreSQL verticals for the Scientific Document chain.

Branch A composes, through production services only (no test bootstrap):
ResearchInput ingestion → content-addressed storage → SourceSnapshot →
HybridScientificDocumentParser parse → DocumentParse persistence → document
Evidence candidates → PaperSummary admission → ArtifactPublisher publication,
then asserts the locator/source/producer closure in the database.

Branch B continues from the persisted real DocumentParse into the data
pipeline: document observations → mapping/unit canonicalization → quality
evaluation → coherent Dataset + FieldDictionary + SourceCollection bundle
publication through the single Atomic Publisher.

The LLM boundary is the only stubbed surface (declared model-stubbed truth
level); parser, repositories, workflow lease/attempt bookkeeping, publisher
and every downstream pipeline stage run for real against PostgreSQL.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select

from app.db.models import (
    ArtifactVersionModel,
    DocumentParseModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchInputBindingModel,
    ResearchInputContentModel,
    SourceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ResearchContract,
    compute_research_contract_content_hash,
)
from app.schemas.paper_summary import (
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.research_input import ResearchInputCreate
from app.schemas.enums import SourceMode
from app.schemas.scientific_document import (
    DocumentParseInput,
    ScientificDataExtractionCandidate,
)
from app.services.data_artifact_build_inputs import DataArtifactBuildInputRepository
from app.services.content_storage import LocalContentStorage
from app.services.document_data_admission import DocumentDataAdmissionService
from app.services.document_parse_store import (
    DocumentParseRepository,
    DocumentParseService,
    PersistDocumentParseRequest,
)
from app.services.document_summary import (
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
)
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.services.research_input_ingestion import (
    ResearchInputIngestionCommand,
    ResearchInputIngestionService,
)
from app.services.research_input_policy import ResearchInputPolicy
from app.services.research_input_store import (
    PersistentIdempotencyRepository,
    PersistentResearchInputStore,
)
from app.services.scientific_document.hybrid_parser import (
    HybridScientificDocumentParser,
)
from app.services.scientific_document.local_paddle_pipeline import (
    LocalPaddleOcrVlPipeline,
)
from app.services.url_fetcher import UrlFetchConfig
from app.workflow.publisher import ArtifactPublisher, admit_artifact_candidate
from app.workflow.data_artifact_publication import (
    DataArtifactPublicationConfig,
    DataArtifactPublicationService,
)
from app.workflow.step_publication import (
    RunStepContext,
    StepPublicationFactory,
)
from app.workflow.store import (
    AttemptHandle,
    LeaseGrant,
    PersistentWorkflowStore,
    RunStepDefinition,
)
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from data_artifact_test_support import build_input
from db_bootstrap import reset_current_schema
from services.data_pipeline.crossmatch.benchmark import (
    build_crossmatch_scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.crossmatch.engine import align_cross_source_records
from services.data_pipeline.data_artifacts.projection import (
    derive_document_snapshot_bindings,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle
from services.paper_pipeline.constants import (
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)
from services.paper_pipeline.summary import build_document_evidence_candidates
from test_document_data_admission import REQUESTED_FIELDS, _with_documents

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)

NOW = datetime(2026, 8, 25, 8, 0, tzinfo=UTC)
GOLDEN_PDF = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "scientific_document"
    / "fixtures"
    / "golden_born_digital.pdf"
)
SCIENTIFIC_TABLE_IMAGE = (
    Path(__file__).resolve().parents[3]
    / "services"
    / "scientific_document"
    / "fixtures"
    / "scientific_host_star_table.png"
)
LOCAL_MODEL_BUNDLE = Path(__file__).resolve().parents[3] / "models"


class _StubSummaryModel:
    """Deterministic paper_summary model stub bound to real parsed evidence."""

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        evidence_id = request.input_payload["paper_payload"]["evidence"][0][
            "evidence_id"
        ]
        payload = {
            "background": [
                {
                    "statement_id": "summary.vertical.research_goal",
                    "text": "The fixture study integrates exoplanet host-star parameters.",
                    "evidence_ids": [evidence_id],
                }
            ],
            "methodology": [],
            "dataset": [],
            "experiments": [],
            "discussion": [],
            "limitations": [],
            "research_questions": [],
        }
        return ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage={
                "prompt_tokens": 64,
                "completion_tokens": 16,
                "total_tokens": 80,
            },
            latency_ms=11,
            provider_request_id="req-vertical-summary",
        )


def _contract_payload() -> dict[str, object]:
    return {
        "research_goal": "从上传的观测论文中归纳宿主恒星参数并形成可溯源数据集。",
        "target_objects": ["host_star", "exoplanet_candidate"],
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "research_input",
        },
        "requested_fields": list(REQUESTED_FIELDS),
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {
            "keywords": ("exoplanet host star",),
            "source_ids": ("crossref",),
            "max_candidates": 3,
        },
        "output_requirements": [
            "dataset",
            "field_dictionary",
            "source_collection",
            "paper_summary",
        ],
        "evidence_requirements": {},
        "quality_constraints": {},
    }


def _doc_steps() -> tuple[RunStepDefinition, ...]:
    transitions = (
        ("planning", "fetching_data"),
        ("fetching_data", "cleaning_data"),
        ("cleaning_data", "searching_papers"),
        ("searching_papers", "summarizing_papers"),
        ("summarizing_papers", "reasoning_literature"),
        ("reasoning_literature", "building_graph"),
        ("building_graph", "completed"),
    )
    return tuple(
        RunStepDefinition(
            key=enter,
            label=enter.replace("_", " ").title(),
            enter_status=enter,
            success_status=success,
            max_attempts=2,
        )
        for enter, success in transitions
    )


class VerticalChain:
    """Shared front-half state: real ingestion, parse, persistence, lease."""

    factory: object
    project: object
    contract: ResearchContract
    research_input: object
    storage: LocalContentStorage
    run_id: UUID
    attempt: AttemptHandle
    lease: LeaseGrant
    publications: StepPublicationFactory
    context: RunStepContext
    parse_execution_id: UUID
    parse_record: object
    parse_input_hash: str
    snapshot: object
    document: object


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


@pytest.fixture(scope="module")
def chain(postgres_engine: Engine, tmp_path_factory) -> VerticalChain:
    factory = session_factory(postgres_engine)
    project_model = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Scientific document vertical",
        case_key="exoplanet_host_star",
    )
    payload = _contract_payload()
    draft_model = build_contract_draft(project_model, content=payload)
    contract_model = build_research_contract(
        project_model,
        draft_model,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(payload),
        content=payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session,
            project=project_model,
            draft=draft_model,
            contract=contract_model,
        )

    storage = LocalContentStorage(tmp_path_factory.mktemp("vertical-cas") / "cas")
    ingestion = ResearchInputIngestionService(
        repository=PersistentResearchInputStore(factory),
        idempotency_repository=PersistentIdempotencyRepository(factory),
        content_storage=storage,
        policy=ResearchInputPolicy.from_values(
            allowed_mime_types=("application/pdf",),
            max_size_bytes=8 * 1024 * 1024,
        ),
        url_fetch_config=UrlFetchConfig(
            allowed_protocols=("https",),
            allowed_hosts=(),
            timeout_seconds=1,
            max_redirects=0,
            max_response_bytes=1024,
        ),
    )
    pdf_bytes = GOLDEN_PDF.read_bytes()
    research_input = asyncio.run(
        ingestion.create(
            ResearchInputIngestionCommand(
                session_id=project_model.session_id,
                project_id=str(project_model.id),
                payload=ResearchInputCreate(
                    type="pdf",
                    filename=GOLDEN_PDF.name,
                    mime_type="application/pdf",
                ),
                idempotency_key=f"vertical-upload-{uuid4()}",
                file_content=pdf_bytes,
                file_filename=GOLDEN_PDF.name,
            )
        )
    )
    PersistentResearchInputStore(factory).bind_to_contract(
        session_id=project_model.session_id,
        input_id=research_input.id,
        project_id=str(project_model.id),
        contract_draft_id=str(draft_model.id),
    )

    workflow = PersistentWorkflowStore(factory)
    run_snapshot = workflow.create_run(
        project_id=project_model.id,
        contract_id=contract_model.id,
        execution_mode="live",
        idempotency_key=f"vertical-run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=_doc_steps(),
    )
    lease = workflow.acquire_lease(
        run_snapshot.id,
        owner="document-vertical",
        lease_duration=timedelta(minutes=10),
        expected_status="queued",
        expected_revision=run_snapshot.revision,
    )
    attempt = workflow.begin_step(
        run_snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"vertical-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Vertical document branch",
    )

    artifacts: dict[str, UUID] = {}
    with factory() as session, session.begin():
        for kind in (
            "paper_summary",
            "dataset",
            "field_dictionary",
            "source_collection",
        ):
            artifact = ResearchArtifactModel(
                id=uuid4(),
                project_id=project_model.id,
                kind=kind,
                title=f"vertical {kind}",
                logical_key=f"{kind}.primary",
            )
            session.add(artifact)
            artifacts[kind] = artifact.id

    contract = ResearchContract(
        id=str(contract_model.id),
        project_id=str(contract_model.project_id),
        version=contract_model.version,
        content_hash=contract_model.content_hash,
        created_from_draft_id=str(contract_model.created_from_draft_id),
        created_at=(contract_model.created_at or NOW).astimezone(UTC),
        **payload,
    )
    context = RunStepContext(
        run_id=run_snapshot.id,
        project_id=project_model.id,
        session_id=project_model.session_id,
        contract=contract,
        artifacts=dict(artifacts),
        versions={},
    )
    publications = StepPublicationFactory(factory=factory)

    parser = HybridScientificDocumentParser()
    profile = parser.profile
    parse_input = DocumentParseInput(
        research_input_id=str(research_input.id),
        content_hash=research_input.content_hash,
        source_type="upload",
        mime_type="application/pdf",
        filename=GOLDEN_PDF.name,
        input_bytes=pdf_bytes,
    )
    parse_input_hash = compute_canonical_payload_hash(
        {
            "input": parse_input.model_dump(
                mode="json", exclude_none=True, exclude={"input_bytes"}
            ),
            "profile": profile.model_dump(mode="json"),
        }
    )
    parse_execution = publications.start_producer(
        context,
        step_key="planning",
        operation_key="document_parse:vertical",
        producer_type="algorithm",
        producer_name="scientific-document-parser",
        producer_version=profile.parser_profile_version,
        input_hash=parse_input_hash,
        parameters={
            "parser_profile_id": profile.parser_profile_id,
            "routing_policy_id": profile.routing_policy_id,
        },
        parameters_hash=profile.configuration_hash,
        attempt=attempt,
        lease=lease,
    )
    document = parser.parse_document(parse_input)
    publications.finish_producer(
        parse_execution.id,
        status="completed",
        output_hash=document.canonical_output_hash,
    )
    parse_service = DocumentParseService(DocumentParseRepository(factory), storage)
    parse_record = asyncio.run(
        parse_service.persist(
            PersistDocumentParseRequest(
                project_id=UUID(str(project_model.id)),
                run_id=run_snapshot.id,
                run_step_id=attempt.run_step_id,
                producer_execution_id=parse_execution.id,
                parse_input_hash=parse_input_hash,
                candidate=document,
            )
        )
    )
    snapshot = parse_service.source_snapshot(
        project_id=UUID(str(project_model.id)),
        document_parse_id=parse_record.id,
    )

    state = VerticalChain()
    state.factory = factory
    state.project = project_model
    state.contract = contract
    state.research_input = research_input
    state.storage = storage
    state.run_id = run_snapshot.id
    state.attempt = attempt
    state.lease = lease
    state.publications = publications
    state.context = context
    state.parse_execution_id = parse_execution.id
    state.parse_record = parse_record
    state.parse_input_hash = parse_input_hash
    state.snapshot = snapshot
    state.document = document
    return state


def test_ingestion_and_parse_close_on_source_snapshot(chain: VerticalChain) -> None:
    """Front half: upload synthesis, parse identity and provenance closure."""
    assert chain.research_input.source_snapshot_id is not None
    assert str(chain.snapshot.id) == str(chain.research_input.source_snapshot_id)
    assert chain.snapshot.source_id == f"research_input:{chain.research_input.id}"
    assert chain.snapshot.content_hash == chain.research_input.content_hash
    assert chain.parse_record.input_content_hash == chain.research_input.content_hash
    assert chain.document.overall_quality.value == "accepted"

    with chain.factory() as session:
        parse_row = session.get(DocumentParseModel, chain.parse_record.id)
        assert parse_row is not None
        assert parse_row.identity_hash == chain.parse_record.identity_hash
        content_row = session.scalar(
            select(ResearchInputContentModel).where(
                ResearchInputContentModel.content_hash
                == chain.research_input.content_hash
            )
        )
        assert content_row is not None
        producer_row = session.get(ProducerExecutionModel, chain.parse_execution_id)
        assert producer_row is not None
        assert producer_row.status == "completed"
        assert producer_row.input_hash == chain.parse_input_hash
        assert producer_row.output_hash == chain.document.canonical_output_hash


def test_paper_summary_statement_closes_to_research_input(chain: VerticalChain) -> None:
    """Branch A tail: summary statement → Evidence → parse → input bytes."""
    evidence_candidates = build_document_evidence_candidates(
        document_parse=chain.document,
        document_parse_id=str(chain.parse_record.id),
        paper_id="paper.vertical-fixture",
        source_id=chain.snapshot.source_id,
        source_record_id=GOLDEN_PDF.name,
        source_snapshot_id=str(chain.snapshot.id),
    )
    assert evidence_candidates, "real parsed fixture must yield text evidence"

    snapshot_reference = PaperSummarySourceSnapshotReference(
        source_snapshot_id=str(chain.snapshot.id),
        source_id=chain.snapshot.source_id,
        source_version=(
            chain.snapshot.source_version_or_etag or chain.snapshot.content_hash
        ),
        content_hash=chain.snapshot.content_hash,
    )
    execution = DocumentSummaryService(_StubSummaryModel()).execute(
        ExecuteDocumentSummaryRequest(
            document_parse=chain.document,
            document_parse_id=str(chain.parse_record.id),
            source_snapshot=snapshot_reference,
            paper=PaperSummaryPaperMetadata(
                paper_id="paper.vertical-fixture",
                title="Exoplanet Host-Star Integration Study",
            ),
            source_id=chain.snapshot.source_id,
            source_record_id=GOLDEN_PDF.name,
            research_goal=chain.contract.research_goal,
            provider="qwen",
            model="qwen3.8-max",
            model_revision="qwen3.8-max",
            parameters={"temperature": 0, "max_tokens": 2048},
            run_id=str(chain.run_id),
        )
    )
    assert execution.admission.admission_status.value == "accepted"
    summary = execution.admission.summary
    assert summary is not None

    summary_execution = chain.publications.start_producer(
        chain.context,
        step_key="planning",
        operation_key="document_paper_summary",
        producer_type="model",
        producer_name=SUMMARY_PRODUCER_NAME,
        producer_version=SUMMARY_PRODUCER_VERSION,
        input_hash=summary.input_hash,
        parameters={"temperature": 0, "max_tokens": 2048},
        model_provider="qwen",
        requested_model="qwen3.8-max",
        attempt=chain.attempt,
        lease=chain.lease,
    )
    source_bindings, evidence_bindings = chain.publications.paper_summary_bindings(
        chain.context,
        summary,
        source_snapshots_are_persisted=True,
    )
    admitted = admit_artifact_candidate(
        summary,
        schema_version=summary.schema_version,
        source_snapshot_ids=summary.source_snapshot_ids,
        evidence_ids=summary.evidence_ids,
        evidence_validator=lambda _context: None,
        domain_validator=lambda _context: None,
        quality_validator=lambda _context: None,
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )
    chain.publications.finish_producer(
        summary_execution.id,
        status="completed",
        input_hash=summary.input_hash,
        output_hash=admitted.content_hash,
    )
    publication = chain.publications.publication(
        chain.context,
        kind="paper_summary",
        candidate=admitted,
        producer_execution_id=summary_execution.id,
    )
    result = ArtifactPublisher(chain.factory).publish_step_outputs(
        chain.run_id,
        step_key="planning",
        attempt_id=chain.attempt.attempt_id,
        token=chain.lease.token,
        generation=chain.lease.generation,
        expected_status=chain.attempt.run_status,
        expected_revision=chain.attempt.run_revision,
        publications=(publication,),
        public_message="Vertical PaperSummary published",
    )
    # PublicationResult.status reports the run status after the planning step
    # succeeded (it advanced into the next canonical step), not a terminal.
    assert result.status == "fetching_data"
    version_id = result.versions[0].id

    # Statement-level locator closure onto the persisted parse and its input.
    located = [
        item for item in summary.evidence if item.locator.document_locator is not None
    ]
    assert located, "summary must retain document locators"
    for item in located:
        assert item.locator.document_parse_id == str(chain.parse_record.id)
        assert (
            item.locator.document_parse_output_hash
            == chain.document.canonical_output_hash
        )
        locator = item.locator.document_locator
        assert locator.bbox is not None
    assert set(summary.evidence_ids) <= {item.evidence_id for item in summary.evidence}

    with chain.factory() as session:
        version_row = session.get(ArtifactVersionModel, version_id)
        assert version_row is not None
        artifact_row = session.get(ResearchArtifactModel, version_row.artifact_id)
        assert artifact_row is not None
        assert artifact_row.kind == "paper_summary"
        assert artifact_row.latest_version_id == version_id
        summary_row = session.get(ProducerExecutionModel, summary_execution.id)
        assert summary_row is not None
        assert summary_row.status == "completed"
        assert summary_row.input_hash == summary.input_hash
        assert summary_row.output_hash == admitted.content_hash


def test_document_observations_truthfully_empty_without_structured_tables(
    chain: VerticalChain,
) -> None:
    """Honest degradation only; zero extraction is never success closure.

    Native-only parsing of this fixture yields no ``DocumentTable``. The
    production observation stage must therefore publish nothing instead of
    promoting paragraph text into scientific facts. The successful real-data
    vertical is asserted independently by the local-Paddle test below.
    """
    crossmatch_benchmark = load_crossmatch_benchmark()
    scenario = next(
        item
        for item in crossmatch_benchmark.scenarios
        if item.scenario_id == "exact_one_to_one"
    )
    crossmatch_result = align_cross_source_records(
        build_crossmatch_scenario_input(scenario)
    )

    admission = DocumentDataAdmissionService(
        factory=chain.factory,
        document_parses=DocumentParseService(
            DocumentParseRepository(chain.factory), chain.storage
        ),
        manifests=load_frozen_manifest_bundle(),
    )
    plan = asyncio.run(
        admission.prepare(
            project_id=UUID(str(chain.project.id)),
            run_id=chain.run_id,
            contract=chain.contract,
            crossmatch=crossmatch_result,
        )
    )
    assert plan is not None, "bound research input must produce an admission plan"
    batch = admission.execute(plan)
    assert batch.raw_candidates == ()
    assert batch.accepted == ()
    assert batch.outcomes == ()

    with chain.factory() as session:
        published_for_project = session.scalar(
            select(ResearchArtifactModel).where(
                ResearchArtifactModel.project_id == UUID(str(chain.project.id)),
                ResearchArtifactModel.kind == "dataset",
            )
        )
        assert published_for_project is not None  # artifact shell only
        assert published_for_project.latest_version_id is None, (
            "no Dataset ArtifactVersion may appear without structured tables"
        )


def test_real_visual_document_publishes_coherent_data_artifact_bundle(
    postgres_engine: Engine,
    tmp_path,
) -> None:
    """Real local Paddle output closes through admission and the sole Publisher."""
    if importlib.util.find_spec("paddleocr") is None:
        pytest.skip("approved paddleocr runtime is not installed")
    if not (
        (LOCAL_MODEL_BUNDLE / "layout_detection").is_dir()
        and (LOCAL_MODEL_BUNDLE / "vlm_recognition").is_dir()
    ):
        pytest.skip("verified local PaddleOCR-VL bundle is not provisioned")

    factory = session_factory(postgres_engine)
    project_model = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Real visual scientific-data vertical",
        case_key="exoplanet_host_star",
    )
    payload = _contract_payload()
    draft_model = build_contract_draft(project_model, content=payload)
    contract_model = build_research_contract(
        project_model,
        draft_model,
        contract_id=uuid4(),
        content_hash=compute_research_contract_content_hash(payload),
        content=payload,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session,
            project=project_model,
            draft=draft_model,
            contract=contract_model,
        )

    storage = LocalContentStorage(tmp_path / "real-visual-cas")
    ingestion = ResearchInputIngestionService(
        repository=PersistentResearchInputStore(factory),
        idempotency_repository=PersistentIdempotencyRepository(factory),
        content_storage=storage,
        policy=ResearchInputPolicy.from_values(
            allowed_mime_types=("image/png",),
            max_size_bytes=8 * 1024 * 1024,
        ),
        url_fetch_config=UrlFetchConfig(
            allowed_protocols=("https",),
            allowed_hosts=(),
            timeout_seconds=1,
            max_redirects=0,
            max_response_bytes=1024,
        ),
    )
    image_bytes = SCIENTIFIC_TABLE_IMAGE.read_bytes()
    research_input = asyncio.run(
        ingestion.create(
            ResearchInputIngestionCommand(
                session_id=project_model.session_id,
                project_id=str(project_model.id),
                payload=ResearchInputCreate(
                    type="image",
                    filename=SCIENTIFIC_TABLE_IMAGE.name,
                    mime_type="image/png",
                ),
                idempotency_key=f"real-visual-upload-{uuid4()}",
                file_content=image_bytes,
                file_filename=SCIENTIFIC_TABLE_IMAGE.name,
            )
        )
    )
    PersistentResearchInputStore(factory).bind_to_contract(
        session_id=project_model.session_id,
        input_id=research_input.id,
        project_id=str(project_model.id),
        contract_draft_id=str(draft_model.id),
    )

    workflow = PersistentWorkflowStore(factory)
    run = workflow.create_run(
        project_id=project_model.id,
        contract_id=contract_model.id,
        execution_mode="live",
        idempotency_key=f"real-visual-run-{uuid4()}",
        request_hash="sha256:" + "e" * 64,
        steps=_doc_steps(),
    )
    lease = workflow.acquire_lease(
        run.id,
        owner="real-visual-vertical",
        lease_duration=timedelta(minutes=20),
        expected_status="queued",
        expected_revision=run.revision,
    )
    attempt = workflow.begin_step(
        run.id,
        step_key="planning",
        attempt_idempotency_key=f"real-visual-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Parse and admit a real visual scientific table",
    )

    artifact_ids: dict[str, UUID] = {}
    with factory() as session, session.begin():
        for kind in ("dataset", "field_dictionary", "source_collection"):
            artifact = ResearchArtifactModel(
                id=uuid4(),
                project_id=project_model.id,
                kind=kind,
                title=f"real visual {kind}",
                logical_key=f"{kind}.real-visual-primary",
            )
            session.add(artifact)
            artifact_ids[kind] = artifact.id

    contract = ResearchContract(
        id=str(contract_model.id),
        project_id=str(contract_model.project_id),
        version=contract_model.version,
        content_hash=contract_model.content_hash,
        created_from_draft_id=str(contract_model.created_from_draft_id),
        created_at=contract_model.created_at or NOW,
        **payload,
    )
    context = RunStepContext(
        run_id=run.id,
        project_id=project_model.id,
        session_id=project_model.session_id,
        contract=contract,
        artifacts=artifact_ids,
        versions={},
    )
    publications = StepPublicationFactory(factory=factory)
    parser = HybridScientificDocumentParser(
        visual_parser=LocalPaddleOcrVlPipeline(bundle_root=LOCAL_MODEL_BUNDLE)
    )
    parse_input = DocumentParseInput(
        research_input_id=str(research_input.id),
        content_hash=research_input.content_hash,
        source_type="upload",
        mime_type="image/png",
        filename=SCIENTIFIC_TABLE_IMAGE.name,
        input_bytes=image_bytes,
    )
    parse_input_hash = compute_canonical_payload_hash(
        {
            "input": parse_input.model_dump(
                mode="json", exclude_none=True, exclude={"input_bytes"}
            ),
            "profile": parser.profile.model_dump(mode="json"),
        }
    )
    parse_execution = publications.start_producer(
        context,
        step_key="planning",
        operation_key="document_parse:real_visual",
        producer_type="algorithm",
        producer_name="scientific-document-parser",
        producer_version=parser.profile.parser_profile_version,
        input_hash=parse_input_hash,
        parameters={
            "parser_profile_id": parser.profile.parser_profile_id,
            "routing_policy_id": parser.profile.routing_policy_id,
        },
        parameters_hash=parser.profile.configuration_hash,
        attempt=attempt,
        lease=lease,
    )
    document = parser.parse_document(parse_input)
    assert document.overall_quality.value == "accepted"
    assert document.tables, "real Paddle execution must recover a table"
    assert document.visual_model_revision is not None
    publications.finish_producer(
        parse_execution.id,
        status="completed",
        output_hash=document.canonical_output_hash,
    )
    parse_service = DocumentParseService(DocumentParseRepository(factory), storage)
    parse_record = asyncio.run(
        parse_service.persist(
            PersistDocumentParseRequest(
                project_id=project_model.id,
                run_id=run.id,
                run_step_id=attempt.run_step_id,
                producer_execution_id=parse_execution.id,
                parse_input_hash=parse_input_hash,
                candidate=document,
            )
        )
    )

    scenario = next(
        item
        for item in load_crossmatch_benchmark().scenarios
        if item.scenario_id == "exact_one_to_one"
    )
    crossmatch = align_cross_source_records(build_crossmatch_scenario_input(scenario))
    admission = DocumentDataAdmissionService(
        factory=factory,
        document_parses=parse_service,
        manifests=load_frozen_manifest_bundle(),
    )
    plan = asyncio.run(
        admission.prepare(
            project_id=project_model.id,
            run_id=run.id,
            contract=contract,
            crossmatch=crossmatch,
        )
    )
    assert plan is not None
    batch = admission.execute(plan)
    assert batch.raw_candidates
    assert all(
        isinstance(item, ScientificDataExtractionCandidate)
        for item in batch.raw_candidates
    )
    accepted_fields = {item.canonical_field_id for item in batch.accepted}
    assert {"star.effective_temperature", "star.radius"} <= accepted_fields
    for observation in batch.accepted:
        locator = observation.document_locator
        assert locator.page_index == document.pages[0].page_index
        assert locator.block_id
        assert locator.table_id
        assert locator.cell_id
        assert locator.bbox is not None

    data_input = _with_documents(build_input(*REQUESTED_FIELDS), batch.accepted)
    publication_service = DataArtifactPublicationService(
        publications,
        DataArtifactBuildInputRepository(factory),
    )
    config = DataArtifactPublicationConfig(
        publish_kinds=(
            ArtifactKind.dataset,
            ArtifactKind.field_dictionary,
            ArtifactKind.source_collection,
        ),
        operation_key_prefix="data_artifact:real_visual",
        producer_error_code="REAL_VISUAL_DATA_ARTIFACT_FAILED",
        producer_version=data_input.producer_version,
        quality_failure_message="real visual data quality did not pass",
        source_mode=SourceMode.fixture,
        snapshot_bindings_override=derive_document_snapshot_bindings(data_input),
        source_snapshots=(
            data_input.authority.left_acquisition.snapshot,
            data_input.authority.right_acquisition.snapshot,
        ),
    )
    prepared = publication_service.prepare(
        context,
        step_key="planning",
        attempt=attempt,
        lease=lease,
        data_input=data_input,
        config=config,
    )
    document_values = {
        item.canonical_field_id: item
        for item in prepared.build_result.dataset.source_values
        if item.origin.kind == "document_research_input"
    }
    temperature = document_values["star.effective_temperature"]
    radius = document_values["star.radius"]
    assert temperature.canonical_value is not None
    assert radius.canonical_value is not None
    assert Decimal(temperature.canonical_value) == Decimal("5200")
    assert temperature.source_unit == "kelvin"
    assert temperature.canonical_unit == "kelvin"
    assert Decimal(radius.canonical_value) == Decimal("0.80")
    assert radius.source_unit == "solar_radius"
    assert radius.canonical_unit == "solar_radius"
    assert (
        prepared.quality.evaluation_result.contract_gate.overall_status.value == "pass"
    )
    bundle = publication_service.publish(
        context,
        prepared=prepared,
        config=config,
    )
    published = ArtifactPublisher(factory).publish_step_outputs(
        run.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        publications=bundle,
        public_message="Published the real visual scientific-data bundle",
    )
    assert published.status == "fetching_data"
    assert len(published.versions) == 3
    assert {item.source_mode for item in published.versions} == {"fixture"}

    version_ids = {item.id for item in published.versions}
    with factory() as session:
        versions = tuple(
            session.scalars(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.id.in_(version_ids)
                )
            )
        )
        artifacts = {
            session.get(ResearchArtifactModel, item.artifact_id).kind: item
            for item in versions
        }
        assert set(artifacts) == {
            "dataset",
            "field_dictionary",
            "source_collection",
        }
        assert {item.run_step_id for item in versions} == {attempt.run_step_id}
        assert {item.step_attempt_id for item in versions} == {attempt.attempt_id}
        assert {item.input_hash for item in versions} == {data_input.input_hash}
        assert {item.source_mode for item in versions} == {"fixture"}
        assert all(
            str(parse_record.source_snapshot_id) in item.source_snapshot_ids
            for item in versions
        )

        evidence = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == artifacts["dataset"].id
                )
            )
        )
        document_evidence = next(
            item
            for item in evidence
            if item.locator.get("kind") == "document_observation"
        )
        assert document_evidence.source_snapshot_id == parse_record.source_snapshot_id
        locator = document_evidence.locator["document_locator"]
        assert locator["page_index"] == document.pages[0].page_index
        assert locator["block_id"]
        assert locator["table_id"]
        assert locator["cell_id"]
        assert locator["bbox"] is not None

        snapshot = session.get(SourceSnapshotModel, parse_record.source_snapshot_id)
        assert snapshot is not None
        assert snapshot.content_hash == research_input.content_hash
        content = session.scalar(
            select(ResearchInputContentModel).where(
                ResearchInputContentModel.content_hash == research_input.content_hash
            )
        )
        assert content is not None
        binding = session.scalar(
            select(ResearchInputBindingModel).where(
                ResearchInputBindingModel.input_id == UUID(str(research_input.id))
            )
        )
        assert binding is not None
        parse_row = session.get(DocumentParseModel, parse_record.id)
        assert parse_row is not None
        assert parse_row.input_content_hash == research_input.content_hash
