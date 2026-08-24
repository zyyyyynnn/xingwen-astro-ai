"""Instance-wide model provider status and local configuration transport."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from app.config import settings
from app.schemas.core import (
    ConfigureModelProviderRequest,
    Envelope,
    ModelProviderConfigurationStatus,
    ResponseLinks,
    ResponseMeta,
)
from app.security import SecurityProblem, SessionRecord
from app.services.model_provider_configuration import (
    ModelProviderConfigurationService,
)


router = APIRouter(prefix="/api/model-provider", tags=["model-provider"])


def _service(request: Request) -> ModelProviderConfigurationService:
    service = request.app.state.model_provider_configuration_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="MODEL_PROVIDER_CONFIGURATION_UNAVAILABLE",
            title="Model provider configuration unavailable",
            detail="当前工作台尚未连接持久化运行环境。",
        )
    return service


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _envelope(
    request: Request, data: ModelProviderConfigurationStatus
) -> Envelope[ModelProviderConfigurationStatus]:
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self="/api/model-provider/configuration"),
    )


def _consume_write_limit(request: Request, response: Response) -> None:
    record: SessionRecord = request.state.session
    remaining, reset_seconds = (
        request.app.state.model_provider_config_rate_limiter.consume(record.id)
    )
    response.headers["RateLimit-Limit"] = str(settings.MODEL_PROVIDER_CONFIG_RATE_LIMIT)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(reset_seconds)


@router.get(
    "/configuration",
    operation_id="getModelProviderConfiguration",
    response_model=Envelope[ModelProviderConfigurationStatus],
)
def get_configuration(
    request: Request, response: Response
) -> Envelope[ModelProviderConfigurationStatus]:
    response.headers["Cache-Control"] = "no-store"
    status = _service(request).status()
    response.headers["ETag"] = str(status.revision)
    return _envelope(request, status)


@router.put(
    "/configuration",
    operation_id="configureModelProvider",
    response_model=Envelope[ModelProviderConfigurationStatus],
)
def configure(
    request: Request,
    response: Response,
    body: ConfigureModelProviderRequest,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    expected_revision: Annotated[int, Header(alias="If-Match", ge=0)],
) -> Envelope[ModelProviderConfigurationStatus]:
    _ = csrf_token
    _consume_write_limit(request, response)
    response.headers["Cache-Control"] = "no-store"
    status = _service(request).configure(body, expected_revision=expected_revision)
    response.headers["ETag"] = str(status.revision)
    return _envelope(request, status)


@router.delete(
    "/configuration",
    operation_id="removeModelProviderConfiguration",
    response_model=Envelope[ModelProviderConfigurationStatus],
)
def remove_configuration(
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    expected_revision: Annotated[int, Header(alias="If-Match", ge=0)],
) -> Envelope[ModelProviderConfigurationStatus]:
    _ = csrf_token
    _consume_write_limit(request, response)
    response.headers["Cache-Control"] = "no-store"
    status = _service(request).remove_override(expected_revision=expected_revision)
    response.headers["ETag"] = str(status.revision)
    return _envelope(request, status)


__all__ = ["router"]
