"""Runtime transport for the Research Input ingestion contract (B-19).

Controlled ingestion of URL, PDF, CSV, JSON, image and text inputs into an
immutable, content-addressed boundary. The router only maps HTTP to the
ingestion boundary; ownership, MIME sniffing, filename sanitization, URL fetch
policy and persistence live behind the store/content-storage/url-fetcher
ports. No binary content or full text ever leaves in a public DTO.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Path, Query, Request, Response, status
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.config import settings
from app.schemas.core import CollectionEnvelope, CursorPage, Envelope, ResponseLinks, ResponseMeta
from app.schemas.research_input import (
    RESEARCH_INPUT_FILENAME_INVALID,
    RESEARCH_INPUT_INVALID,
    RESEARCH_INPUT_MIME_REJECTED,
    RESEARCH_INPUT_NOT_FOUND,
    RESEARCH_INPUT_TOO_LARGE,
    URL_FETCH_BLOCKED,
    URL_FETCH_FAILED,
    URL_FETCH_TOO_LARGE,
    BindResearchInputRequest,
    CreateResearchInputRequest,
    FILE_INPUT_TYPES,
    ResearchInputCreate,
    ResearchInputDetail,
    ResearchInputRef,
    ResearchInputType,
)
from app.security import SecurityProblem
from app.services.content_storage import ContentStorage, sha256_content_hash
from app.services.research_input_store import (
    InMemoryResearchInputStore,
    PreparedInput,
    ResearchInputRecord,
    ResearchInputStore,
    filename_extension_matches,
    sanitize_filename,
    sniff_mime_type,
    validate_declared_mime,
)
from app.services.url_fetcher import (
    UrlFetchConfig,
    UrlFetchError,
    fetch_url,
    validate_url_policy,
)


router = APIRouter(prefix="/api", tags=["research-inputs"])

_READ_CHUNK_BYTES = 65536


def _store(request: Request) -> ResearchInputStore:
    store = request.app.state.research_input_store
    if store is None:
        raise SecurityProblem(
            status=503,
            code="RESEARCH_INPUT_RUNTIME_UNAVAILABLE",
            title="Research input runtime unavailable",
            detail="The research input runtime is not configured",
        )
    return store


def _content_storage(request: Request) -> ContentStorage:
    return request.app.state.content_storage


def _session_id(request: Request) -> str:
    return request.state.session.id


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _url_fetch_config() -> UrlFetchConfig:
    hosts = tuple(host for host in (settings.URL_FETCH_ALLOWED_HOSTS or []))
    return UrlFetchConfig(
        allowed_protocols=tuple(
            protocol.lower() for protocol in settings.URL_FETCH_ALLOWED_PROTOCOLS
        ),
        allowed_hosts=hosts,
        timeout_seconds=settings.URL_FETCH_TIMEOUT_SECONDS,
        max_redirects=settings.URL_FETCH_MAX_REDIRECTS,
        max_response_bytes=settings.URL_FETCH_MAX_RESPONSE_BYTES,
    )


import json
import hashlib

def _compute_request_hash(
    payload: CreateResearchInputRequest, file: UploadFile | None
) -> str:
    raw = {
        "project_id": payload.project_id,
        "type": payload.type.value,
        "url": payload.url,
        "filename": payload.filename,
        "mime_type": payload.mime_type,
        "text_content": payload.text_content,
        "file_name": file.filename if file is not None else None,
    }
    dumped = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(dumped.encode("utf-8")).hexdigest()


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
    payload, file = await _parse_create_request(request)
    request_hash = _compute_request_hash(payload, file)
    try:
        record = await _ingest(request, payload, file, idempotency_key, request_hash)
    except SecurityProblem:
        raise
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
def bind_research_input(
    input_id: Annotated[str, Path(min_length=1)],
    payload: BindResearchInputRequest,
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[ResearchInputRef]:
    _ = csrf_token
    if payload.contract_draft_id is not None:
        _store(request).bind_to_contract(
            session_id=_session_id(request),
            input_id=input_id,
            project_id=payload.project_id,
            contract_draft_id=payload.contract_draft_id,
        )
    else:
        _store(request).bind_to_run(
            session_id=_session_id(request),
            input_id=input_id,
            project_id=payload.project_id,
            run_id=payload.run_id or "",
        )
    record = _store(request).get(session_id=_session_id(request), input_id=input_id)
    if record is None:
        raise _not_found()
    _no_store(response)
    return Envelope(
        data=record.to_ref(),
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/research-inputs/{record.id}"),
    )


# ---- ingestion -------------------------------------------------------------


async def _parse_create_request(
    request: Request,
) -> tuple[CreateResearchInputRequest, UploadFile | None]:
    """Parse either a JSON body or a multipart form into one validated request."""

    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        return await _parse_multipart(request)
    if content_type.startswith("application/json"):
        _check_json_body_size(request)
        try:
            return CreateResearchInputRequest.model_validate(await request.json()), None
        except ValidationError as exc:
            raise _schema_validation_failed(exc) from exc
    raise SecurityProblem(
        status=400,
        code="RESEARCH_INPUT_INVALID",
        title="Invalid research input request",
        detail="Expected multipart/form-data or application/json",
    )


async def _parse_multipart(
    request: Request,
) -> tuple[CreateResearchInputRequest, UploadFile | None]:
    _check_upload_size(request)
    form = await request.form()
    values: dict[str, Any] = {
        key: _form_str(form, key)
        for key in ("project_id", "type", "url", "filename", "mime_type", "text_content")
    }
    try:
        payload = CreateResearchInputRequest.model_validate(values)
    except ValidationError as exc:
        raise _schema_validation_failed(exc) from exc
    file = form.get("file")
    file = file if isinstance(file, UploadFile) else None
    if payload.type in FILE_INPUT_TYPES and file is None:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_INVALID,
            title="Invalid research input request",
            detail=f"type {payload.type.value} requires a multipart file upload",
        )
    if payload.type not in FILE_INPUT_TYPES and file is not None:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_INVALID,
            title="Invalid research input request",
            detail=f"type {payload.type.value} does not accept a file upload",
        )
    return payload, file


async def _ingest(
    request: Request,
    payload: CreateResearchInputRequest,
    file: UploadFile | None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> ResearchInputRecord:
    if payload.type is ResearchInputType.url:
        return await _ingest_url(request, payload, idempotency_key, request_hash)
    if payload.type is ResearchInputType.text:
        return await _ingest_text(request, payload, idempotency_key, request_hash)
    return await _ingest_upload(request, payload, file, idempotency_key, request_hash)


async def _ingest_url(
    request: Request,
    payload: CreateResearchInputRequest,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> ResearchInputRecord:
    assert payload.url is not None
    config = _url_fetch_config()
    try:
        validate_url_policy(payload.url, config)
        result = await fetch_url(payload.url, config)
    except UrlFetchError as exc:
        raise _url_fetch_problem(exc) from exc
    sniffed_mime = sniff_mime_type(result.content_bytes)
    mime_type = _resolve_mime(payload, sniffed_mime)
    filename = _clean_filename_hint(payload.filename, mime_type)
    prepared = PreparedInput(
        content_hash=result.content_hash,
        storage_ref=await _content_storage(request).store(
            result.content_bytes, result.content_hash
        ),
        size_bytes=len(result.content_bytes),
        mime_type=mime_type,
        filename=filename,
        source_snapshot=result.source_snapshot,
    )
    return _store(request).create(
        session_id=_session_id(request),
        project_id=payload.project_id,
        payload=payload,
        prepared=prepared,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )



async def _ingest_text(
    request: Request,
    payload: CreateResearchInputRequest,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> ResearchInputRecord:
    assert payload.text_content is not None
    content = payload.text_content.encode("utf-8")
    mime_type = _resolve_mime(payload, sniff_mime_type(content))
    return await _ingest_bytes(
        request, payload, content, mime_type, payload.filename, idempotency_key, request_hash
    )


async def _ingest_upload(
    request: Request,
    payload: CreateResearchInputRequest,
    file: UploadFile | None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> ResearchInputRecord:
    assert file is not None
    content = await _read_upload(file)
    mime_type = _resolve_mime(payload, sniff_mime_type(content))
    raw_filename = payload.filename or (file.filename or "")
    filename = _clean_filename_hint(raw_filename, mime_type)
    return await _ingest_bytes(
        request, payload, content, mime_type, filename, idempotency_key, request_hash
    )


async def _ingest_bytes(
    request: Request,
    payload: CreateResearchInputRequest,
    content: bytes,
    mime_type: str | None,
    filename: str | None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> ResearchInputRecord:
    content_hash = sha256_content_hash(content)
    prepared = PreparedInput(
        content_hash=content_hash,
        storage_ref=await _content_storage(request).store(content, content_hash),
        size_bytes=len(content),
        mime_type=mime_type,
        filename=filename,
        source_snapshot=None,
    )
    return _store(request).create(
        session_id=_session_id(request),
        project_id=payload.project_id,
        payload=payload,
        prepared=prepared,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )



def _resolve_mime(
    payload: ResearchInputCreate, sniffed_mime: str | None
) -> str | None:
    resolved = validate_declared_mime(
        declared_type=payload.type,
        sniffed_mime=sniffed_mime,
        client_mime=payload.mime_type,
    )
    if resolved is None:
        raise SecurityProblem(
            status=415,
            code=RESEARCH_INPUT_MIME_REJECTED,
            title="Unsupported content type",
            detail="The content type is not supported for the declared input type",
        )
    return resolved


def _clean_filename_hint(raw: str | None, mime_type: str | None) -> str | None:
    if raw is None or raw == "":
        return None
    clean = sanitize_filename(raw)
    if clean is None:
        raise SecurityProblem(
            status=400,
            code=RESEARCH_INPUT_FILENAME_INVALID,
            title="Invalid filename",
            detail="The filename is not usable as a display name",
        )
    if mime_type is not None and not filename_extension_matches(clean, mime_type):
        raise SecurityProblem(
            status=415,
            code=RESEARCH_INPUT_MIME_REJECTED,
            title="Filename and content mismatch",
            detail="The filename extension does not match the content type",
        )
    return clean


async def _read_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.RESEARCH_INPUT_MAX_SIZE_BYTES:
            raise _too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _check_upload_size(request: Request) -> None:
    length = _content_length(request)
    if length is not None and length > settings.RESEARCH_INPUT_MAX_SIZE_BYTES:
        raise _too_large()


def _check_json_body_size(request: Request) -> None:
    length = _content_length(request)
    if length is not None and length > settings.RESEARCH_INPUT_MAX_SIZE_BYTES:
        raise _too_large()


def _content_length(request: Request) -> int | None:
    try:
        return int(request.headers.get("content-length", ""))
    except ValueError:
        return None


def _form_str(form: Any, key: str) -> str | None:  # noqa: ANN401
    value = form.get(key)
    if value is None:
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


def _url_fetch_problem(exc: UrlFetchError) -> SecurityProblem:
    if exc.code == URL_FETCH_BLOCKED:
        status_code = 422
    else:
        status_code = 502
    return SecurityProblem(
        status=status_code,
        code=exc.code,
        title="URL fetch rejected" if status_code == 422 else "URL fetch failed",
        detail=exc.detail,
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
