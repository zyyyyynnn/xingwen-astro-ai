"""HTTP transport for research-input attachment and URL ingestion.

This router is deliberately thin. It parses HTTP (including the hard request
body ceiling that must trip *before* any parser buffers a body), reads the
required headers, delegates to
:class:`~app.services.research_input_ingestion.ResearchInputIngestionService`,
and maps the result or the raised problem onto a response.

It performs no hashing, no URL fetching, no MIME sniffing, no storage writes
and no repository calls of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, Request, Response, status
from pydantic import TypeAdapter, ValidationError
from starlette.datastructures import UploadFile

from app.config import settings
from app.http.body_limits import (
    RequestBodyTooLarge,
    bounded_body_request,
    declared_content_length,
    multipart_request_limit,
)
from app.schemas.core import CollectionEnvelope, CursorPage, Envelope, ResponseLinks, ResponseMeta
from app.schemas.research_input import (
    RESEARCH_INPUT_INVALID,
    RESEARCH_INPUT_NOT_FOUND,
    RESEARCH_INPUT_TOO_LARGE,
    BindResearchInputRequest,
    CreateResearchInputMultipartRequest,
    CreateResearchInputRequest,
    FILE_INPUT_TYPES,
    ResearchInputCreate,
    ResearchInputDetail,
    ResearchInputRef,
    ResearchInputType,
)
from app.security import SecurityProblem
from app.services.research_input_ingestion import (
    ResearchInputIngestionCommand,
    ResearchInputIngestionService,
)
from app.services.research_input_store import ResearchInputRepository

router = APIRouter(prefix="/api", tags=["research-inputs"])

_READ_CHUNK_BYTES = 65536
#: A create request carries one file and a handful of small metadata fields.
_MAX_UPLOAD_FILES = 1
_MAX_FORM_FIELDS = 12

_JSON_REQUEST_ADAPTER = TypeAdapter(CreateResearchInputRequest)
_BIND_REQUEST_ADAPTER = TypeAdapter(BindResearchInputRequest)


def _store(request: Request) -> ResearchInputRepository:
    store = request.app.state.research_input_store
    if store is None:
        raise SecurityProblem(
            status=503,
            code="RESEARCH_INPUT_RUNTIME_UNAVAILABLE",
            title="Research input runtime unavailable",
            detail="The research input runtime is not configured",
        )
    return store


def _ingestion_service(request: Request) -> ResearchInputIngestionService:
    service = getattr(request.app.state, "research_input_ingestion", None)
    if service is None:
        raise SecurityProblem(
            status=503,
            code="RESEARCH_INPUT_RUNTIME_UNAVAILABLE",
            title="Research input runtime unavailable",
            detail="The research input runtime is not configured",
        )
    return service


def _session_id(request: Request) -> str:
    return request.state.session.id


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/research-inputs",
    operation_id="createResearchInput",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchInputRef],
)
async def create_research_input(
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[ResearchInputRef]:
    _ = csrf_token
    limiter = request.app.state.research_input_rate_limiter
    remaining, reset_seconds = limiter.consume(_session_id(request))

    payload, file_content, file_filename = await _parse_create_request(request)
    record = await _ingestion_service(request).create(
        ResearchInputIngestionCommand(
            session_id=_session_id(request),
            project_id=payload.project_id,
            payload=_as_domain_payload(payload),
            idempotency_key=idempotency_key,
            file_content=file_content,
            file_filename=file_filename,
        )
    )

    _no_store(response)
    response.headers["Location"] = f"/api/research-inputs/{record.id}"
    response.headers["RateLimit-Limit"] = str(limiter.limit)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(reset_seconds)
    return Envelope(
        data=record.to_ref(),
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/research-inputs/{record.id}"),
    )


@router.get(
    "/research-inputs",
    operation_id="listResearchInputs",
    response_model=CollectionEnvelope[ResearchInputRef],
)
def list_research_inputs(
    request: Request,
    response: Response,
    project_id: Annotated[str, Query(min_length=1)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ResearchInputRef]:
    refs, next_cursor, has_more = _store(request).list(
        session_id=_session_id(request),
        project_id=project_id,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    return CollectionEnvelope(
        data=refs,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self="/api/research-inputs"),
    )


@router.get(
    "/research-inputs/{input_id}",
    operation_id="getResearchInput",
    response_model=Envelope[ResearchInputDetail],
)
def get_research_input(
    input_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchInputDetail]:
    record = _store(request).get(session_id=_session_id(request), input_id=input_id)
    if record is None:
        raise _not_found()
    _no_store(response)
    return Envelope(
        data=record.to_detail(),
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/research-inputs/{record.id}"),
    )


@router.get(
    "/research-inputs/{input_id}/content",
    operation_id="getResearchInputContent",
    response_class=Response,
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "Stored content bytes of one accepted file input.",
        }
    },
)
async def get_research_input_content(
    input_id: Annotated[str, Path(min_length=1)],
    request: Request,
) -> Response:
    content, mime_type, filename = await _ingestion_service(request).read_content(
        session_id=_session_id(request), input_id=input_id
    )
    response = Response(content=content, media_type=mime_type)
    _no_store(response)
    response.headers["Content-Disposition"] = _content_disposition(filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.delete(
    "/research-inputs/{input_id}",
    operation_id="deleteResearchInput",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_research_input(
    input_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> None:
    _ = csrf_token
    _store(request).delete(session_id=_session_id(request), input_id=input_id)
    _no_store(response)


@router.post(
    "/research-inputs/{input_id}/bind",
    operation_id="bindResearchInput",
    response_model=Envelope[ResearchInputRef],
)
async def bind_research_input(
    input_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[ResearchInputRef]:
    _ = csrf_token
    payload = _parse_bind_request(await _read_json_body(request))
    store = _store(request)
    if payload.contract_draft_id is not None:
        store.bind_to_contract(
            session_id=_session_id(request),
            input_id=input_id,
            project_id=payload.project_id,
            contract_draft_id=payload.contract_draft_id,
        )
    else:
        store.bind_to_run(
            session_id=_session_id(request),
            input_id=input_id,
            project_id=payload.project_id,
            run_id=payload.run_id or "",
        )
    record = store.get(session_id=_session_id(request), input_id=input_id)
    if record is None:
        raise _not_found()
    _no_store(response)
    return Envelope(
        data=record.to_ref(),
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/research-inputs/{record.id}"),
    )


# ---- transport parsing -----------------------------------------------------


async def _parse_create_request(
    request: Request,
) -> tuple[Any, bytes | None, str | None]:
    """Parse a JSON body or a multipart form under a hard, pre-parser ceiling."""

    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        return await _parse_multipart(request)
    if content_type.startswith("application/json"):
        payload = _parse_json_create(await _read_json_body(request))
        return payload, None, None
    raise SecurityProblem(
        status=400,
        code=RESEARCH_INPUT_INVALID,
        title="Invalid research input request",
        detail="Expected multipart/form-data or application/json",
    )


async def _read_json_body(request: Request) -> Any:
    """Read a JSON body, enforcing the size cap on the receive channel.

    ``Content-Length`` is only a cheap early reject; the authoritative bound is
    the streaming counter, so a chunked body without a declared length cannot
    slip past.
    """

    limit = settings.RESEARCH_INPUT_MAX_SIZE_BYTES
    declared = declared_content_length(request)
    if declared is not None and declared > limit:
        raise _too_large()
    bounded = bounded_body_request(request, limit)
    try:
        return await bounded.json()
    except RequestBodyTooLarge as exc:
        raise _too_large() from exc
    except ValueError as exc:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_INVALID,
            title="Invalid research input request",
            detail="The request body is not valid JSON",
        ) from exc


def _parse_json_create(raw: Any) -> Any:  # noqa: ANN401
    try:
        return _JSON_REQUEST_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise _schema_validation_failed(exc) from exc


def _parse_bind_request(raw: Any) -> Any:  # noqa: ANN401
    try:
        return _BIND_REQUEST_ADAPTER.validate_python(raw)
    except ValidationError as exc:
        raise _schema_validation_failed(exc) from exc


async def _parse_multipart(
    request: Request,
) -> tuple[Any, bytes | None, str | None]:
    """Parse the multipart create form with bounded parts and a bounded body.

    The total ceiling is the file ceiling plus a bounded, conservative
    allowance for multipart framing, so a legal file of exactly the maximum
    size is still accepted while an oversized body is refused before the
    parser assembles it.
    """

    max_file_bytes = settings.RESEARCH_INPUT_MAX_SIZE_BYTES
    request_limit = multipart_request_limit(max_file_bytes)
    declared = declared_content_length(request)
    if declared is not None and declared > request_limit:
        raise _too_large()

    bounded = bounded_body_request(request, request_limit)
    try:
        async with bounded.form(
            max_files=_MAX_UPLOAD_FILES,
            max_fields=_MAX_FORM_FIELDS,
            max_part_size=max_file_bytes,
        ) as form:
            values: dict[str, Any] = {
                key: _form_str(form, key)
                for key in ("project_id", "type", "filename", "mime_type")
            }
            file = form.get("file")
            file = file if isinstance(file, UploadFile) else None
            content = await _read_upload(file, max_file_bytes) if file else None
            file_name = file.filename if file is not None else None
            if content is not None:
                values["file"] = content
    except RequestBodyTooLarge as exc:
        raise _too_large() from exc
    except SecurityProblem:
        raise
    except Exception as exc:  # multipart framing errors from Starlette
        if type(exc).__name__ == "MultiPartException":
            raise SecurityProblem(
                status=400,
                code=RESEARCH_INPUT_INVALID,
                title="Invalid research input request",
                detail="The multipart request body could not be parsed",
            ) from exc
        raise

    payload = _validate_multipart_values(values)
    if payload.type in FILE_INPUT_TYPES and content is None:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_INVALID,
            title="Invalid research input request",
            detail=f"type {payload.type.value} requires a multipart file upload",
        )
    if payload.type not in FILE_INPUT_TYPES and content is not None:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_INVALID,
            title="Invalid research input request",
            detail=f"type {payload.type.value} does not accept a file upload",
        )
    return payload, content, file_name


def _validate_multipart_values(values: dict[str, Any]) -> CreateResearchInputMultipartRequest:
    try:
        return CreateResearchInputMultipartRequest.model_validate(values)
    except ValidationError as exc:
        raise _schema_validation_failed(exc) from exc


def _as_domain_payload(payload: Any) -> ResearchInputCreate:  # noqa: ANN401
    """Normalize either transport model onto the shared domain payload."""

    return ResearchInputCreate(
        type=ResearchInputType(payload.type),
        url=getattr(payload, "url", None),
        text_content=getattr(payload, "text_content", None),
        filename=payload.filename,
        mime_type=payload.mime_type,
    )


async def _read_upload(file: UploadFile, max_file_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_file_bytes:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _form_str(form: Any, key: str) -> str | None:  # noqa: ANN401
    value = form.get(key)
    if value is None or isinstance(value, UploadFile):
        return None
    text = str(value)
    return text if text != "" else None


def _schema_validation_failed(exc: ValidationError) -> SecurityProblem:
    field_errors = ", ".join(
        f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return SecurityProblem(
        status=422,
        code="SCHEMA_VALIDATION_FAILED",
        title="Request validation failed",
        detail=field_errors or "The request does not match the required schema",
    )


def _too_large() -> SecurityProblem:
    return SecurityProblem(
        status=413,
        code=RESEARCH_INPUT_TOO_LARGE,
        title="Input too large",
        detail="The input exceeds the maximum allowed size",
    )


def _not_found() -> SecurityProblem:
    return SecurityProblem(
        status=404,
        code=RESEARCH_INPUT_NOT_FOUND,
        title="Resource not found",
        detail="Resource not found",
    )


def _content_disposition(filename: str | None) -> str:
    """Inline disposition with a quoted, ASCII-safe filename (never a path)."""

    if not filename:
        return "inline"
    safe = "".join(ch for ch in filename if 32 <= ord(ch) < 127 and ch not in '\\"')
    if not safe:
        return "inline"
    return f'inline; filename="{safe}"'


__all__ = ["router"]
