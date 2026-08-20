"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from importlib.metadata import version as package_version
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db.session import create_engine_from_url, session_factory
from app.middleware import (
    RequestIDMiddleware,
    SecurityMiddleware,
    api_http_exception_handler,
    api_validation_exception_handler,
    security_exception_handler,
)
from app.routers import (
    artifacts,
    health,
    research,
    research_inputs,
    revisions,
    sessions,
    snapshots,
)
from app.schemas.manifest import ManifestBundle, load_manifest_bundle
from app.security import (
    InMemoryRateLimiter,
    InMemorySessionStore,
    PersistentSessionStore,
    SecurityProblem,
    SessionService,
    install_share_token_access_log_filter,
)
from app.services.artifacts import ArtifactReadService
from app.services.data_artifacts import DataArtifactReadService
from app.services.feedback_targets import FeedbackTargetAuthority
from app.services.model_execution import (
    QwenModelExecutionAdapter,
    qwen_execution_lease_duration,
)
from app.services.research import ResearchApplicationService
from app.services.research_planner import ResearchContractPlanner
from app.services.resource_authority import (
    PersistentResourceAuthority,
    ResourceAuthority,
)
from app.services.revisions import RevisionApplicationService
from app.services.snapshots import PersistentSnapshotStore, SnapshotService
from app.workflow.cache import CacheRecordStore, CacheSelector
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.store import PersistentWorkflowStore

SessionFactory = Callable[[], Session]


def _load_case_manifests() -> ManifestBundle:
    relative = Path("services/data_pipeline/manifests/exoplanet_host_star")
    for parent in Path(__file__).resolve().parents:
        manifest_root = parent / relative
        case_manifest = manifest_root / "case-manifest.json"
        field_manifest = manifest_root / "field-manifest.json"
        if case_manifest.is_file() and field_manifest.is_file():
            return load_manifest_bundle(case_manifest, field_manifest)
    raise RuntimeError("Exoplanet host-star Case/Field Manifest assets are missing")


def _configure_database_runtime(
    app: FastAPI,
) -> tuple[object | None, SessionFactory | None, ResourceAuthority | None]:
    """Wire the single PostgreSQL-backed Research runtime when a database is configured."""

    if settings.DATABASE_URL is None:
        return None, None, None

    engine = create_engine_from_url(settings.DATABASE_URL.get_secret_value())
    factory = session_factory(engine)
    app.state.db_session_factory = factory

    artifact_read_service = ArtifactReadService(factory)
    app.state.artifact_read_service = artifact_read_service
    app.state.data_artifact_read_service = DataArtifactReadService(
        artifact_read_service
    )

    resource_authority: ResourceAuthority = PersistentResourceAuthority(factory)
    workflow_store = PersistentWorkflowStore(factory)
    workflow_executor = PersistentWorkflowExecutor(workflow_store)
    app.state.workflow_store = workflow_store
    app.state.workflow_executor = workflow_executor
    app.state.cache_record_store = CacheRecordStore(factory)
    app.state.cache_selector = CacheSelector(factory)
    integration_without_provider = (
        settings.APP_ENV.lower() == "integration" and settings.DASHSCOPE_API_KEY is None
    )
    if integration_without_provider:
        from app.test_support.integration_model import (
            DeterministicIntegrationModelExecutionPort,
        )

        model_port = DeterministicIntegrationModelExecutionPort()
        planner_provider = "integration_fixture"
        planner_model = model_port.model_name
        planner_revision = model_port.model_revision
    else:
        model_port = QwenModelExecutionAdapter(
            api_key=(
                settings.DASHSCOPE_API_KEY.get_secret_value()
                if settings.DASHSCOPE_API_KEY is not None
                else None
            ),
            base_url=settings.DASHSCOPE_BASE_URL,
            timeout_seconds=settings.DASHSCOPE_TIMEOUT_SECONDS,
            max_retries=settings.DASHSCOPE_MAX_RETRIES,
        )
        planner_provider = "qwen"
        planner_model = settings.DASHSCOPE_MODEL
        planner_revision = settings.DASHSCOPE_EXPLICIT_MODEL_REVISION
    app.state.model_execution_port = model_port
    manifests = _load_case_manifests()
    from app.services.content_storage import LocalContentStorage

    content_storage = LocalContentStorage(settings.RESEARCH_INPUT_UPLOAD_DIR)
    app.state.content_storage = content_storage
    from app.services.scientific_document.hybrid_parser import (
        HybridScientificDocumentParser,
        PaddleOcrVlClient,
    )

    visual_parser = (
        PaddleOcrVlClient(
            base_url=settings.PADDLEOCR_VL_BASE_URL,
            model_revision=settings.PADDLEOCR_VL_MODEL_REVISION,
            timeout_seconds=settings.PADDLEOCR_VL_TIMEOUT_SECONDS,
        )
        if settings.PADDLEOCR_VL_BASE_URL is not None
        and settings.PADDLEOCR_VL_MODEL_REVISION is not None
        else None
    )
    app.state.document_parser = HybridScientificDocumentParser(
        visual_parser=visual_parser,
        max_pages=settings.DOCUMENT_PARSE_MAX_PAGES,
    )
    app.state.research_planner = ResearchContractPlanner(
        model_port=model_port,
        provider=planner_provider,
        requested_model=planner_model,
        explicit_revision=planner_revision,
        manifests=manifests,
    )
    app.state.research_service = ResearchApplicationService(
        factory=factory,
        workflow_store=workflow_store,
        manifests=manifests,
        planner=app.state.research_planner,
        model_execution_lease_duration=qwen_execution_lease_duration(
            timeout_seconds=settings.DASHSCOPE_TIMEOUT_SECONDS,
            max_retries=settings.DASHSCOPE_MAX_RETRIES,
            grace_seconds=settings.MODEL_EXECUTION_LEASE_GRACE_SECONDS,
        ),
    )
    app.state.research_run_worker = None
    if settings.APP_ENV.lower() not in {"test", "integration"}:
        app.state.research_run_worker = ResearchRunWorker(
            factory=factory,
            store=workflow_store,
            executor=workflow_executor,
            manifests=manifests,
            model_port=model_port,
            requested_model=settings.DASHSCOPE_MODEL,
            explicit_revision=settings.DASHSCOPE_EXPLICIT_MODEL_REVISION,
            content_storage=content_storage,
            document_parser=app.state.document_parser,
        )

        async def _start_research_run_worker() -> None:
            app.state.research_run_worker.start()

        async def _stop_research_run_worker() -> None:
            await app.state.research_run_worker.stop()

        app.router.add_event_handler("startup", _start_research_run_worker)
        app.router.add_event_handler("shutdown", _stop_research_run_worker)
    app.router.add_event_handler("shutdown", engine.dispose)
    return engine, factory, resource_authority


def create_app() -> FastAPI:
    install_share_token_access_log_filter()
    app = FastAPI(
        title=settings.APP_TITLE,
        version=package_version("api"),
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.state.workflow_store = None
    app.state.workflow_executor = None
    app.state.artifact_read_service = None
    app.state.data_artifact_read_service = None
    app.state.research_service = None
    app.state.revision_service = None
    app.state.model_execution_port = None
    app.state.research_planner = None
    app.state.research_run_worker = None
    app.state.db_session_factory = None
    app.state.content_storage = None
    app.state.document_parse_service = None
    app.state.paper_summary_read_service = None
    _, database_session_factory, resource_authority = _configure_database_runtime(app)

    if database_session_factory is not None:
        session_store = PersistentSessionStore(
            database_session_factory,
            retention=timedelta(seconds=settings.SESSION_RETENTION_SECONDS),
        )
    else:
        session_store = InMemorySessionStore()
    session_service = SessionService(
        session_store, ttl_seconds=settings.SESSION_TTL_SECONDS
    )
    app.state.session_store = session_store
    app.state.session_service = session_service
    app.state.session_rate_limiter = InMemoryRateLimiter(
        limit=settings.SESSION_CREATE_RATE_LIMIT
    )
    app.state.share_rate_limiter = InMemoryRateLimiter(
        limit=settings.SHARE_CREATE_RATE_LIMIT
    )
    app.state.revision_rate_limiter = InMemoryRateLimiter(
        limit=settings.REVISION_WRITE_RATE_LIMIT
    )

    app.state.snapshot_store = None
    app.state.snapshot_service = None
    if resource_authority is not None and database_session_factory is not None:
        snapshot_store = PersistentSnapshotStore(
            database_session_factory,
            resource_authority,
            retention=timedelta(seconds=settings.SHARE_RETENTION_SECONDS),
        )
        app.state.snapshot_store = snapshot_store
        app.state.snapshot_service = SnapshotService(snapshot_store)

    app.state.research_input_store = None
    app.state.research_input_idempotency = None
    app.state.research_input_ingestion = None
    app.state.paper_candidate_input_service = None
    app.state.paper_candidate_input_reader = None
    app.state.research_input_rate_limiter = InMemoryRateLimiter(
        limit=settings.RESEARCH_INPUT_RATE_LIMIT
    )

    from app.services.content_storage import LocalContentStorage
    from app.services.research_input_ingestion import ResearchInputIngestionService
    from app.services.research_input_memory_runtime import InMemoryResearchInputRuntime
    from app.services.research_input_policy import ResearchInputPolicy
    from app.services.research_input_store import (
        PersistentIdempotencyRepository,
        PersistentResearchInputStore,
    )
    from app.services.url_fetcher import UrlFetchConfig

    if app.state.content_storage is None:
        app.state.content_storage = LocalContentStorage(
            settings.RESEARCH_INPUT_UPLOAD_DIR
        )
    lease_ttl = timedelta(seconds=settings.RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS)
    if database_session_factory is not None:
        app.state.research_input_store = PersistentResearchInputStore(
            database_session_factory
        )
        app.state.research_input_idempotency = PersistentIdempotencyRepository(
            database_session_factory, lease_ttl=lease_ttl
        )
    else:
        # Explicit dependency-injected fallback for local/test ingestion only;
        # it does not provide a second ResearchRun workflow runtime.
        in_memory_runtime = InMemoryResearchInputRuntime(lease_ttl=lease_ttl)
        app.state.research_input_store = in_memory_runtime
        app.state.research_input_idempotency = in_memory_runtime

    app.state.research_input_policy = ResearchInputPolicy.from_values(
        allowed_mime_types=settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES,
        max_size_bytes=settings.RESEARCH_INPUT_MAX_SIZE_BYTES,
    )
    app.state.research_input_ingestion = ResearchInputIngestionService(
        repository=app.state.research_input_store,
        idempotency_repository=app.state.research_input_idempotency,
        content_storage=app.state.content_storage,
        policy=app.state.research_input_policy,
        url_fetch_config=UrlFetchConfig(
            allowed_protocols=tuple(
                protocol.lower() for protocol in settings.URL_FETCH_ALLOWED_PROTOCOLS
            ),
            allowed_hosts=tuple(settings.URL_FETCH_ALLOWED_HOSTS or ()),
            timeout_seconds=settings.URL_FETCH_TIMEOUT_SECONDS,
            max_redirects=settings.URL_FETCH_MAX_REDIRECTS,
            max_response_bytes=settings.URL_FETCH_MAX_RESPONSE_BYTES,
        ),
    )
    if (
        database_session_factory is not None
        and app.state.artifact_read_service is not None
    ):
        from app.services.paper_candidate_inputs import (
            PaperCandidateInputRepository,
            PaperCandidateInputReadService,
            PaperCandidateInputService,
        )
        from app.services.document_parse_store import (
            DocumentParseRepository,
            DocumentParseService,
        )
        from app.services.paper_collections import PaperCollectionReadService
        from app.services.paper_summaries import PaperSummaryReadService

        candidate_repository = PaperCandidateInputRepository(
            database_session_factory, lease_ttl=lease_ttl
        )
        app.state.paper_candidate_input_reader = PaperCandidateInputReadService(
            research_inputs=app.state.research_input_store,
            repository=candidate_repository,
        )
        app.state.paper_candidate_input_service = PaperCandidateInputService(
            paper_collections=PaperCollectionReadService(
                app.state.artifact_read_service
            ),
            ingestion=app.state.research_input_ingestion,
            research_inputs=app.state.research_input_store,
            repository=candidate_repository,
        )
        app.state.document_parse_service = DocumentParseService(
            DocumentParseRepository(database_session_factory),
            app.state.content_storage,
        )
        app.state.paper_summary_read_service = PaperSummaryReadService(
            app.state.artifact_read_service,
            document_parses=app.state.document_parse_service,
        )
        app.state.revision_service = RevisionApplicationService(
            factory=database_session_factory,
            workflow_store=app.state.workflow_store,
            target_authority=FeedbackTargetAuthority(
                app.state.artifact_read_service,
                paper_summary_reader=app.state.paper_summary_read_service,
            ),
        )

    app.add_middleware(
        SecurityMiddleware,
        sessions=session_service,
        cookie_name=settings.SESSION_COOKIE_NAME,
    )
    origins = [
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(HTTPException, api_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, api_http_exception_handler)
    app.add_exception_handler(RequestValidationError, api_validation_exception_handler)
    app.add_exception_handler(SecurityProblem, security_exception_handler)

    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(artifacts.router)
    app.include_router(research.router)
    app.include_router(revisions.router)
    app.include_router(snapshots.router)
    app.include_router(research_inputs.router)

    # Test-only bootstrap is mounted exclusively in test/integration
    # environments, outside the generated current API contract surface.
    if settings.APP_ENV.lower() in {"test", "integration"}:
        from app.routers import test_bootstrap

        app.include_router(test_bootstrap.router)

    return app


app = create_app()
