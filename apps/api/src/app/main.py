"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.errors import ApiError
from app.middleware import (
    RequestIDMiddleware,
    api_error_exception_handler,
    api_http_exception_handler,
    api_validation_exception_handler,
)
from app.routers import (
    dataset,
    evidence,
    graph,
    health,
    paper_acquisition,
    papers,
    reasoning,
    sources,
    tasks,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
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
    app.add_exception_handler(RequestValidationError, api_validation_exception_handler)

    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(dataset.router)
    app.include_router(sources.router)
    app.include_router(paper_acquisition.router)
    app.include_router(papers.router)
    app.include_router(reasoning.router)
    app.include_router(graph.router)
    app.include_router(evidence.router)

    return app


app = create_app()
