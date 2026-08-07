"""Research Input ingestion application service (B-19).

This is the use-case boundary for creating a Research Input. It owns the
orchestration the HTTP router used to perform inline:

* **project ownership is the first domain gate** -- ``require_owned_project``
  runs before idempotency, before any URL fetch, before any storage write and
  before any snapshot persistence, so a foreign/missing/malformed project never
  produces a side effect;
* **HTTP request identity** (``Idempotency-Key``) is resolved next, so a URL
  replay never issues a second network request;
* **content identity** is computed from real bytes;
* **MIME/filename** rules come from the injected domain policy;
* content is published to immutable storage, provenance is persisted, and the
  input + idempotency completion are committed **atomically** under the
  reservation's lease token.

Nothing here imports FastAPI: the input is a plain
:class:`ResearchInputIngestionCommand` and the output is a store record, so the
use case is testable without a transport.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.schemas.research_input import (
    RESEARCH_INPUT_FILENAME_INVALID,
    RESEARCH_INPUT_MIME_REJECTED,
    URL_FETCH_BLOCKED,
    ResearchInputCreate,
    ResearchInputType,
)
from app.security import SecurityProblem
from app.services.content_storage import ContentStorage, sha256_content_hash
from app.services.research_input_policy import (
    ResearchInputPolicy,
    canonical_research_input_request_hash,
    filename_extension_matches,
    sanitize_filename,
    sniff_mime_type,
    validate_declared_mime,
)
from app.services.research_input_store import (
    IdempotencyReservation,
    PreparedInput,
    ResearchInputIdempotencyRepository,
    ResearchInputRecord,
    ResearchInputRepository,
)
from app.services.url_fetcher import (
    UrlFetchConfig,
    UrlFetchError,
    UrlFetchResult,
    fetch_url,
)


@dataclass(frozen=True, slots=True)
class ResearchInputIngestionCommand:
    """One create request, already parsed off the transport.

    ``file_content`` carries the fully-read upload bytes: byte identity is part
    of the request fingerprint, so the bytes must be available before the
    idempotency decision is made.
    """

    session_id: str
    project_id: str
    payload: ResearchInputCreate
    idempotency_key: str
    file_content: bytes | None = None
    file_filename: str | None = None


class ResearchInputIngestionService:
    """Application use case for ingesting one controlled research input."""

    def __init__(
        self,
        *,
        repository: ResearchInputRepository,
        idempotency_repository: ResearchInputIdempotencyRepository,
        content_storage: ContentStorage,
        policy: ResearchInputPolicy,
        url_fetch_config: UrlFetchConfig,
        url_fetcher=fetch_url,  # noqa: ANN001 - injected port, kept duck-typed for tests
    ) -> None:
        self._repository = repository
        self._idempotency = idempotency_repository
        self._storage = content_storage
        self._policy = policy
        self._url_fetch_config = url_fetch_config
        self._url_fetcher = url_fetcher

    async def create(
        self, command: ResearchInputIngestionCommand
    ) -> ResearchInputRecord:
        """Ingest one input, honouring request idempotency before side effects."""

        # 1. Ownership gate FIRST. No side effect may precede this.
        canonical_project_id = self._repository.require_owned_project(
            session_id=command.session_id,
            project_id=command.project_id,
        )

        if command.payload.type is ResearchInputType.url:
            return await self._create_url(
                command, canonical_project_id=canonical_project_id
            )
        return await self._create_bytes(
            command, canonical_project_id=canonical_project_id
        )

    # ---- URL ---------------------------------------------------------------

    async def _create_url(
        self, command: ResearchInputIngestionCommand, *, canonical_project_id: str
    ) -> ResearchInputRecord:
        payload = command.payload
        assert payload.url is not None

        # The URL fingerprint is built from the *submitted request*, never from
        # fetched content: replay has to be decidable before the network is
        # touched at all.
        request_hash = canonical_research_input_request_hash(
            project_id=canonical_project_id,
            input_type=payload.type,
            url=payload.url,
            filename=payload.filename,
            mime_type=payload.mime_type,
        )
        reservation = self._idempotency.resolve(
            session_id=command.session_id,
            project_id=canonical_project_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        if reservation.replayed_input_id is not None:
            return self._replay(command, reservation.replayed_input_id)

        try:
            try:
                # ``fetch_url`` validates the first hop and every redirect hop
                # under the same policy, so no separate pre-validation pass is
                # needed (and a second one would only drift from it).
                result = await self._url_fetcher(payload.url, self._url_fetch_config)
            except UrlFetchError as exc:
                raise _url_fetch_problem(exc) from exc

            self._assert_snapshot_consistency(result)
            content = result.content_bytes
            content_hash = result.content_hash
            prepared = self._prepare(
                command.payload,
                content=content,
                storage_ref="",
                mime_hint=result.mime_type,
                filename_hint=payload.filename,
                source_snapshot=result.source_snapshot,
            )
        except Exception:
            # A failed fetch must not leave a completed mapping; release only
            # the lease we actually hold.
            self._release_on_failure(command, canonical_project_id, reservation)
            raise

        # Publish immutable bytes BEFORE the atomic commit (orphan blobs are
        # safe: content-addressed, immutable, not publicly referenced).
        storage_ref = await self._storage.store(content, content_hash)
        prepared = dataclasses.replace(prepared, storage_ref=storage_ref)
        return await self._commit(
            command,
            canonical_project_id=canonical_project_id,
            prepared=prepared,
            reservation=reservation,
            request_hash=request_hash,
        )

    # ---- text and upload ---------------------------------------------------

    async def _create_bytes(
        self, command: ResearchInputIngestionCommand, *, canonical_project_id: str
    ) -> ResearchInputRecord:
        payload = command.payload
        if payload.type is ResearchInputType.text:
            assert payload.text_content is not None
            content = payload.text_content.encode("utf-8")
            filename_hint = payload.filename
        else:
            assert command.file_content is not None
            content = command.file_content
            filename_hint = payload.filename or command.file_filename

        # Real byte identity enters the fingerprint: reusing a key with the
        # same filename but different bytes must conflict, not replay.
        content_hash = sha256_content_hash(content)
        request_hash = canonical_research_input_request_hash(
            project_id=canonical_project_id,
            input_type=payload.type,
            content_hash=content_hash,
            filename=filename_hint,
            mime_type=payload.mime_type,
        )
        reservation = self._idempotency.resolve(
            session_id=command.session_id,
            project_id=canonical_project_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        if reservation.replayed_input_id is not None:
            return self._replay(command, reservation.replayed_input_id)

        try:
            storage_ref = await self._storage.store(content, content_hash)
            prepared = self._prepare(
                command.payload,
                content=content,
                storage_ref=storage_ref,
                mime_hint=None,
                filename_hint=filename_hint,
                source_snapshot=None,
            )
        except Exception:
            self._release_on_failure(command, canonical_project_id, reservation)
            raise

        return await self._commit(
            command,
            canonical_project_id=canonical_project_id,
            prepared=prepared,
            reservation=reservation,
            request_hash=request_hash,
        )

    # ---- shared ------------------------------------------------------------

    def _prepare(
        self,
        payload: ResearchInputCreate,
        *,
        content: bytes,
        storage_ref: str,
        mime_hint: str | None,
        filename_hint: str | None,
        source_snapshot,
    ) -> PreparedInput:
        """Resolve MIME (from real bytes) and a safe filename, then build facts."""

        content_hash = sha256_content_hash(content)
        sniffed = sniff_mime_type(content)
        mime_type = self._resolve_mime(payload, sniffed, mime_hint)
        filename = self._clean_filename(filename_hint, mime_type)
        return PreparedInput(
            content_hash=content_hash,
            storage_ref=storage_ref,
            size_bytes=len(content),
            mime_type=mime_type,
            filename=filename,
            source_snapshot=source_snapshot,
        )

    async def _commit(
        self,
        command: ResearchInputIngestionCommand,
        *,
        canonical_project_id: str,
        prepared: PreparedInput,
        reservation: IdempotencyReservation,
        request_hash: str,
    ) -> ResearchInputRecord:
        try:
            record = self._repository.commit_ingestion(
                session_id=command.session_id,
                project_id=canonical_project_id,
                payload=command.payload,
                prepared=prepared,
                idempotency_key=command.idempotency_key,
                lease_token=reservation.lease_token or "",
                request_hash=request_hash,
            )
        except Exception:
            # The atomic commit failed (e.g. a stale lease was reclaimed): the
            # input was never created and the reservation is left pending (or
            # already reclaimed), so the request stays retryable. Release only
            # when we still hold the token we reserved.
            self._release_on_failure(command, canonical_project_id, reservation)
            raise
        return record

    def _release_on_failure(
        self,
        command: ResearchInputIngestionCommand,
        canonical_project_id: str,
        reservation: IdempotencyReservation,
    ) -> None:
        if reservation.lease_token is not None:
            self._idempotency.release(
                session_id=command.session_id,
                project_id=canonical_project_id,
                idempotency_key=command.idempotency_key,
                lease_token=reservation.lease_token,
            )

    def _replay(
        self, command: ResearchInputIngestionCommand, input_id: str
    ) -> ResearchInputRecord:
        record = self._repository.get(
            session_id=command.session_id, input_id=input_id
        )
        if record is None:
            raise SecurityProblem(
                status=409,
                code="IDEMPOTENCY_CONFLICT",
                title="Idempotent replay unavailable",
                detail="The previously created resource is no longer available",
            )
        return record

    def _resolve_mime(
        self,
        payload: ResearchInputCreate,
        sniffed_mime: str | None,
        client_mime: str | None,
    ) -> str | None:
        resolved = validate_declared_mime(
            declared_type=payload.type,
            sniffed_mime=sniffed_mime,
            client_mime=client_mime,
            allowed_mimes=self._policy.allowed_mimes,
        )
        if resolved is None:
            raise SecurityProblem(
                status=415,
                code=RESEARCH_INPUT_MIME_REJECTED,
                title="Unsupported content type",
                detail="The content type is not supported for the declared input type",
            )
        return resolved

    @staticmethod
    def _clean_filename(raw: str | None, mime_type: str | None) -> str | None:
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

    @staticmethod
    def _assert_snapshot_consistency(result: UrlFetchResult) -> None:
        """Fail loudly if fetched provenance disagrees with the fetched bytes."""

        actual = sha256_content_hash(result.content_bytes)
        if result.content_hash != actual or result.source_snapshot.content_hash != actual:
            raise SecurityProblem(
                status=502,
                code="URL_FETCH_FAILED",
                title="URL fetch failed",
                detail="Fetched content failed its provenance integrity check",
            )


def _url_fetch_problem(exc: UrlFetchError) -> SecurityProblem:
    status_code = 422 if exc.code == URL_FETCH_BLOCKED else 502
    return SecurityProblem(
        status=status_code,
        code=exc.code,
        title="URL fetch rejected" if status_code == 422 else "URL fetch failed",
        detail=exc.detail,
    )


__all__ = [
    "ResearchInputIngestionCommand",
    "ResearchInputIngestionService",
]
