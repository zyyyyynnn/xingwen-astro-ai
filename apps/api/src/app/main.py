
"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db.session import create_engine_from_url, session_factory
from app.errors import ApiError
from app.middleware import (
    RequestIDMiddleware,
    V2SecurityMiddleware,
    api_error_exception_handler,
    api_http_exception_handler,
    api_validation_exception_handler,
    v2_security_exception_handler,
)
from app.routers import (
    dataset,
    evidence,
    graph,
    health,
    paper_acquisition,
    papers,
    reasoning,
    sessions,
    sources,
    tasks,
)
from app.security import InMemoryRateLimiter, InMemorySessionStore, SecurityProblem, SessionService
from app.workflow.persistent_executor import PersistentWorkflowExecutor
from app.workflow.store import PersistentWorkflowStore


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )

    session_service = SessionService(
        InMemorySessionStore(), ttl_seconds=settings.SESSION_TTL_SECONDS
    )
    app.state.session_service = session_service
    app.state.session_rate_limiter = InMemoryRateLimiter(
        limit=settings.SESSION_CREATE_RATE_LIMIT
    )
    app.state.workflow_store = None
    app.state.workflow_executor = None
    if settings.PERSISTENT_WORKFLOW_ENABLED:
        if settings.DATABASE_URL is None:
            raise RuntimeError(
                "DATABASE_URL is required when PERSISTENT_WORKFLOW_ENABLED is true"
            )
        workflow_engine = create_engine_from_url(settings.DATABASE_URL.get_secret_value())
        app.state.workflow_store = PersistentWorkflowStore(session_factory(workflow_engine))
        app.state.workflow_executor = PersistentWorkflowExecutor(app.state.workflow_store)
        app.router.add_event_handler("shutdown", workflow_engine.dispose)
    app.add_middleware(
        V2SecurityMiddleware,
        sessions=session_service,
        cookie_name=settings.SESSION_COOKIE_NAME,
    )
    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
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
    app.add_exception_handler(SecurityProblem, v2_security_exception_handler)

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

    return app


app = create_app()
