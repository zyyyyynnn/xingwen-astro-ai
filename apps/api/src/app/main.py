"""FastAPI application entry point."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db.session import create_engine_from_url, session_factory
from app.errors import ApiError
from app.middleware import (
    RequestIDMiddleware,
    SecurityMiddleware,
    api_error_exception_handler,
    api_http_exception_handler,
    api_validation_exception_handler,
    security_exception_handler,
)
from app.routers import (
    artifacts,
    dataset,
    evidence,
    graph,
    health,
    paper_acquisition,
    papers,
    reasoning,
    research,
    research_inputs,
    sessions,
    snapshots,
    sources,
    tasks,
)
from app.schemas.manifest import ManifestBundle, load_manifest_bundle
from app.security import (
    InMemoryRateLimiter,
    InMemorySessionStore,
    SecurityProblem,
    SessionService,
    install_share_token_access_log_filter,
)
from app.services.snapshots import InMemorySnapshotStore, SnapshotService
from app.services.artifacts import ArtifactReadService
from app.services.data_artifacts import DataArtifactReadService
from app.services.research import ResearchApplicationService
from app.services.resource_authority import (
    PersistentResourceAuthority,
    ResourceAuthority,
)
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.store import PersistentWorkflowStore


def _load_case_manifests() -> ManifestBundle:
    relative = Path("services/data_pipeline/manifests/exoplanet_host_star")
    for parent in Path(__file__).resolve().parents:
        manifest_root = parent / relative
        case_manifest = manifest_root / "case-manifest.v1.json"
        field_manifest = manifest_root / "field-manifest.v1.json"
        if case_manifest.is_file() and field_manifest.is_file():
            return load_manifest_bundle(case_manifest, field_manifest)
    raise RuntimeError("Exoplanet host-star Case/Field Manifest assets are missing")


def create_app() -> FastAPI:
    install_share_token_access_log_filter()
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    session_service = SessionService(
        InMemorySessionStore(), ttl_seconds=settings.SESSION_TTL_SECONDS
    )
    app.state.session_service = session_service
    app.state.session_rate_limiter = InMemoryRateLimiter(
        limit=settings.SESSION_CREATE_RATE_LIMIT
    )
    app.state.share_rate_limiter = InMemoryRateLimiter(
        limit=settings.SHARE_CREATE_RATE_LIMIT
    )
    app.state.workflow_store = None
    app.state.workflow_executor = None
    app.state.artifact_read_service = None
    app.state.data_artifact_read_service = None
    app.state.research_service = None
    app.state.db_session_factory = None
    database_engine = None
    resource_authority: ResourceAuthority | None = None
    if settings.DATABASE_URL is not None:
        database_engine = create_engine_from_url(
            settings.DATABASE_URL.get_secret_value()
        )
        app.state.db_session_factory = session_factory(database_engine)
        app.state.artifact_read_service = ArtifactReadService(
            session_factory(database_engine)
        )
        app.state.data_artifact_read_service = DataArtifactReadService(
            app.state.artifact_read_service
        )
        resource_authority = PersistentResourceAuthority(
            session_factory(database_engine)
        )
        app.router.add_event_handler("shutdown", database_engine.dispose)
    if settings.PERSISTENT_WORKFLOW_ENABLED:
        if database_engine is None:
            raise RuntimeError(
                "DATABASE_URL is required when PERSISTENT_WORKFLOW_ENABLED is true"
            )
        workflow_store = PersistentWorkflowStore(session_factory(database_engine))
        app.state.workflow_store = workflow_store
        app.state.workflow_executor = PersistentWorkflowExecutor(workflow_store)
        app.state.research_service = ResearchApplicationService(
            factory=session_factory(database_engine),
            workflow_store=workflow_store,
            manifests=_load_case_manifests(),
        )
    app.state.snapshot_store = None
    app.state.snapshot_service = None
    if resource_authority is not None:
        snapshot_store = InMemorySnapshotStore(resource_authority)
        app.state.snapshot_store = snapshot_store
        app.state.snapshot_service = SnapshotService(snapshot_store)
    app.state.research_input_store = None
    app.state.content_storage = None
    app.state.research_input_idempotency = None
    app.state.research_input_ingestion = None
    app.state.research_input_rate_limiter = InMemoryRateLimiter(
        limit=settings.RESEARCH_INPUT_RATE_LIMIT
    )
    from app.services.content_storage import LocalContentStorage
    from app.services.research_input_ingestion import ResearchInputIngestionService
    from app.services.research_input_policy import ResearchInputPolicy
    from app.services.research_input_store import (
        InMemoryIdempotencyRepository,
        InMemoryResearchInputStore,
        PersistentIdempotencyRepository,
        PersistentResearchInputStore,
    )
    from app.services.url_fetcher import UrlFetchConfig

    app.state.content_storage = LocalContentStorage(settings.RESEARCH_INPUT_UPLOAD_DIR)
    lease_ttl = timedelta(seconds=settings.RESEARCH_INPUT_IDEMPOTENCY_LEASE_SECONDS)
    if database_engine is not None:
        factory = session_factory(database_engine)
        app.state.research_input_store = PersistentResearchInputStore(factory)
        app.state.research_input_idempotency = PersistentIdempotencyRepository(
            factory, lease_ttl=lease_ttl
        )
    else:
        app.state.research_input_store = InMemoryResearchInputStore()
        app.state.research_input_idempotency = InMemoryIdempotencyRepository(
            lease_ttl=lease_ttl
        )
        app.state.research_input_store.bind_idempotency(
            app.state.research_input_idempotency
        )

    # The ingestion policy is resolved from settings once, here, so the domain
    # layer never reaches back into global configuration.
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
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(ApiError, api_error_exception_handler)
    app.add_exception_handler(HTTPException, api_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, api_http_exception_handler)
    app.add_exception_handler(RequestValidationError, api_validation_exception_handler)
    app.add_exception_handler(SecurityProblem, security_exception_handler)

    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(dataset.router)
    app.include_router(sources.router)
    app.include_router(paper_acquisition.router)
    app.include_router(papers.router)
    app.include_router(reasoning.router)
    app.include_router(graph.router)
    app.include_router(evidence.router)
    app.include_router(sessions.router)
    app.include_router(artifacts.router)
    app.include_router(research.router)
    app.include_router(snapshots.router)
    app.include_router(research_inputs.router)

    # Test-only bootstrap is mounted exclusively in test/integration
    # environments, outside the frozen /api contract surface. It is never
    # available in development or production.
    if settings.APP_ENV.lower() in {"test", "integration"}:
        from app.routers import test_bootstrap

        app.include_router(test_bootstrap.router)

    return app


app = create_app()
