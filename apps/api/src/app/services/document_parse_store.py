"""Internal immutable persistence for Canonical scientific document parses.

This derivative boundary deliberately exposes no HTTP route or public Artifact
kind. Callers provide a validated Canonical candidate, and the store pins it to
an owned ResearchInput, SourceSnapshot, Run step and completed
ProducerExecution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    DocumentParseLocatorModel,
    DocumentParseModel,
    ProducerExecutionModel,
    ResearchInputContentModel,
    ResearchInputModel,
    ResearchProjectModel,
    ResearchRunModel,
    SourceSnapshotModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
    DocumentBBox,
    DocumentLocator,
    DocumentParseCandidate,
    compute_scientific_document_schema_hash,
)
from app.services.content_storage import ContentStorage, sha256_content_hash


class DocumentParseError(RuntimeError):
    """Base error for the internal DocumentParse boundary."""


class DocumentParseNotFoundError(DocumentParseError):
    """Raised without revealing whether another Project owns the resource."""


class DocumentParseIntegrityError(DocumentParseError):
    """Raised when identity, provenance or locator validation fails closed."""


@dataclass(frozen=True, slots=True)
class PersistDocumentParseRequest:
    project_id: UUID
    run_id: UUID
    run_step_id: UUID
    producer_execution_id: UUID
    parse_input_hash: str
    candidate: DocumentParseCandidate


@dataclass(frozen=True, slots=True)
class DocumentParseRecord:
    id: UUID
    project_id: UUID
    research_input_id: UUID
    source_snapshot_id: UUID
    producer_execution_id: UUID
    candidate_parse_id: str
    identity_hash: str
    input_content_hash: str
    canonical_output_hash: str
    payload_content_hash: str
    overall_quality: str
    created_at: datetime
    reused: bool


@dataclass(frozen=True, slots=True)
class _DocumentParseMetadata:
    candidate_parse_id: str
    candidate_created_at: datetime
    research_input_id: UUID
    schema_version: str
    schema_hash: str
    input_content_hash: str
    canonical_output_hash: str
    config_hash: str
    payload_content_hash: str
    payload_semantic_hash: str


@dataclass(frozen=True, slots=True)
class PersistedDocumentLocator:
    id: UUID
    project_id: UUID
    document_parse_id: UUID
    source_snapshot_id: UUID
    locator_hash: str
    locator: DocumentLocator
    reused: bool


class DocumentParseService:
    """Store/retrieve Canonical payloads through the existing CAS primitive."""

    def __init__(
        self,
        repository: DocumentParseRepository,
        content_storage: ContentStorage,
    ) -> None:
        self._repository = repository
        self._content_storage = content_storage

    async def persist(self, request: PersistDocumentParseRequest) -> DocumentParseRecord:
        self._repository.validate_context(request)
        # The stored CAS payload is the stable Canonical representation: it
        # excludes process-local parse_id / created_at so two equivalent
        # logical parses publish identical CAS bytes and never orphan a blob.
        payload = request.candidate.model_dump(
            mode="json", exclude_none=True, exclude={"parse_id", "created_at"}
        )
        payload_bytes = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        payload_content_hash = sha256_content_hash(payload_bytes)
        payload_semantic_hash = document_parse_payload_semantic_hash(
            request.candidate
        )
        storage_ref = await self._content_storage.store(
            payload_bytes, payload_content_hash
        )
        return self._repository.persist(
            request,
            payload_content_hash=payload_content_hash,
            payload_semantic_hash=payload_semantic_hash,
            payload_storage_ref=storage_ref,
        )

    async def get_candidate(
        self, *, project_id: UUID, document_parse_id: UUID
    ) -> DocumentParseCandidate:
        metadata = self._repository.metadata(
            project_id=project_id, document_parse_id=document_parse_id
        )
        payload_hash = metadata.payload_content_hash
        payload = await self._content_storage.retrieve(payload_hash)
        if payload is None:
            raise DocumentParseIntegrityError("Canonical parse payload is missing")
        if sha256_content_hash(payload) != payload_hash:
            raise DocumentParseIntegrityError("Canonical parse payload hash mismatch")
        try:
            loaded = json.loads(payload)
            # Reattach the frozen process-local metadata that is intentionally
            # kept out of the stable CAS payload (Blocker 2): parse_id /
            # created_at are stored independently in the DB and reattached on
            # read so equivalent logical parses share one CAS blob.
            loaded["parse_id"] = metadata.candidate_parse_id
            loaded["created_at"] = metadata.candidate_created_at
            candidate = DocumentParseCandidate.model_validate(loaded)
        except Exception as exc:
            raise DocumentParseIntegrityError(
                "Canonical parse payload no longer satisfies its frozen schema"
            ) from exc
        if (
            candidate.research_input_id != str(metadata.research_input_id)
            or metadata.schema_version != SCIENTIFIC_DOCUMENT_SCHEMA_VERSION
            or metadata.schema_hash != compute_scientific_document_schema_hash()
            or candidate.content_hash != metadata.input_content_hash
            or candidate.canonical_output_hash != metadata.canonical_output_hash
            or candidate.config_hash != metadata.config_hash
            or document_parse_payload_semantic_hash(candidate)
            != metadata.payload_semantic_hash
        ):
            raise DocumentParseIntegrityError(
                "Canonical parse payload does not match its frozen metadata"
            )
        return candidate

    async def persist_locator(
        self,
        *,
        project_id: UUID,
        document_parse_id: UUID,
        source_snapshot_id: UUID,
        locator: DocumentLocator,
    ) -> PersistedDocumentLocator:
        candidate = await self.get_candidate(
            project_id=project_id, document_parse_id=document_parse_id
        )
        _validate_locator(candidate, locator)
        return self._repository.persist_locator(
            project_id=project_id,
            document_parse_id=document_parse_id,
            source_snapshot_id=source_snapshot_id,
            locator=locator,
        )


class DocumentParseRepository:
    """PostgreSQL metadata repository with Project-scoped reuse."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def validate_context(self, request: PersistDocumentParseRequest) -> None:
        with self._factory() as session:
            self._validated_context(
                session, request, lock=False, materialize_snapshot=False
            )

    def persist(
        self,
        request: PersistDocumentParseRequest,
        *,
        payload_content_hash: str,
        payload_semantic_hash: str,
        payload_storage_ref: str,
    ) -> DocumentParseRecord:
        identity_hash = document_parse_identity_hash(
            request.candidate, parse_input_hash=request.parse_input_hash
        )
        schema_hash = compute_scientific_document_schema_hash()
        with self._factory() as session, session.begin():
            input_row, expected_snapshot_id = self._validated_context(
                session, request, lock=True, materialize_snapshot=True
            )
            if expected_snapshot_id is None:  # pragma: no cover - guarded
                raise DocumentParseIntegrityError(
                    "ResearchInput SourceSnapshot could not be materialized"
                )
            values = {
                "id": uuid4(),
                "project_id": request.project_id,
                "research_input_id": input_row.id,
                "source_snapshot_id": expected_snapshot_id,
                "created_by_run_id": request.run_id,
                "run_step_id": request.run_step_id,
                "producer_execution_id": request.producer_execution_id,
                "candidate_parse_id": request.candidate.parse_id,
                "identity_hash": identity_hash,
                "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
                "schema_hash": schema_hash,
                "input_content_hash": request.candidate.content_hash,
                "parse_input_hash": request.parse_input_hash,
                "canonical_output_hash": request.candidate.canonical_output_hash,
                "payload_content_hash": payload_content_hash,
                "payload_semantic_hash": payload_semantic_hash,
                "payload_storage_ref": payload_storage_ref,
                "parser_profile_id": request.candidate.profile.parser_profile_id,
                "parser_profile_version": request.candidate.profile.parser_profile_version,
                "native_engine": request.candidate.native_engine,
                "native_engine_version": request.candidate.native_engine_version,
                "visual_engine": request.candidate.visual_engine,
                "visual_engine_version": request.candidate.visual_engine_version,
                "visual_model_id": request.candidate.visual_model_id,
                "visual_model_revision": request.candidate.visual_model_revision,
                "config_hash": request.candidate.config_hash,
                "overall_quality": request.candidate.overall_quality.value,
                "candidate_created_at": request.candidate.created_at,
            }
            session.execute(
                pg_insert(DocumentParseModel.__table__)
                .values(**values)
                .on_conflict_do_nothing()
            )
            winner = session.scalar(
                select(DocumentParseModel).where(
                    DocumentParseModel.project_id == request.project_id,
                    DocumentParseModel.identity_hash == identity_hash,
                )
            )
            if winner is None:
                raise DocumentParseIntegrityError(
                    "unable to resolve authoritative DocumentParse identity"
                )
            _require_same_parse(
                winner,
                request=request,
                identity_hash=identity_hash,
                schema_hash=schema_hash,
                payload_semantic_hash=payload_semantic_hash,
                payload_content_hash=payload_content_hash,
                payload_storage_ref=payload_storage_ref,
                expected_snapshot_id=expected_snapshot_id,
            )
            return _record(winner, reused=winner.id != values["id"])

    def metadata(
        self, *, project_id: UUID, document_parse_id: UUID
    ) -> _DocumentParseMetadata:
        with self._factory() as session:
            row = session.scalar(
                select(DocumentParseModel).where(
                    DocumentParseModel.id == document_parse_id,
                    DocumentParseModel.project_id == project_id,
                )
            )
            if row is None:
                raise DocumentParseNotFoundError("DocumentParse was not found")
            return _metadata(row)

    def persist_locator(
        self,
        *,
        project_id: UUID,
        document_parse_id: UUID,
        source_snapshot_id: UUID,
        locator: DocumentLocator,
    ) -> PersistedDocumentLocator:
        locator_payload = locator.model_dump(mode="json", exclude_none=True)
        locator_hash = compute_canonical_payload_hash(locator_payload)
        locator_id = uuid4()
        with self._factory() as session, session.begin():
            parse = session.scalar(
                select(DocumentParseModel)
                .where(
                    DocumentParseModel.id == document_parse_id,
                    DocumentParseModel.project_id == project_id,
                )
                .with_for_update()
            )
            if parse is None:
                raise DocumentParseNotFoundError("DocumentParse was not found")
            if parse.source_snapshot_id != source_snapshot_id:
                raise DocumentParseIntegrityError(
                    "locator SourceSnapshot does not belong to the immutable parse"
                )
            session.execute(
                pg_insert(DocumentParseLocatorModel.__table__)
                .values(
                    id=locator_id,
                    project_id=project_id,
                    document_parse_id=document_parse_id,
                    source_snapshot_id=source_snapshot_id,
                    locator_hash=locator_hash,
                    locator=locator_payload,
                )
                .on_conflict_do_nothing(
                    index_elements=["document_parse_id", "locator_hash"]
                )
            )
            winner = session.scalar(
                select(DocumentParseLocatorModel).where(
                    DocumentParseLocatorModel.document_parse_id == document_parse_id,
                    DocumentParseLocatorModel.locator_hash == locator_hash,
                )
            )
            if winner is None:
                raise DocumentParseIntegrityError(
                    "unable to resolve authoritative locator identity"
                )
            try:
                persisted_locator = DocumentLocator.model_validate(winner.locator)
            except Exception as exc:
                raise DocumentParseIntegrityError(
                    "persisted locator no longer satisfies the Canonical schema"
                ) from exc
            persisted_hash = compute_canonical_payload_hash(
                persisted_locator.model_dump(mode="json", exclude_none=True)
            )
            if (
                winner.project_id != project_id
                or winner.source_snapshot_id != source_snapshot_id
                or persisted_hash != winner.locator_hash
                or persisted_hash != locator_hash
            ):
                raise DocumentParseIntegrityError(
                    "persisted locator has conflicting immutable content"
                )
            return PersistedDocumentLocator(
                id=winner.id,
                project_id=winner.project_id,
                document_parse_id=winner.document_parse_id,
                source_snapshot_id=winner.source_snapshot_id,
                locator_hash=winner.locator_hash,
                locator=persisted_locator,
                reused=winner.id != locator_id,
            )

    @staticmethod
    def _validated_context(
        session: Session,
        request: PersistDocumentParseRequest,
        *,
        lock: bool,
        materialize_snapshot: bool,
    ) -> tuple[ResearchInputModel, UUID | None]:
        project_query = select(ResearchProjectModel).where(
            ResearchProjectModel.id == request.project_id
        )
        input_query = select(ResearchInputModel).where(
            ResearchInputModel.id == _uuid(request.candidate.research_input_id),
            ResearchInputModel.project_id == request.project_id,
        )
        if lock:
            project_query = project_query.with_for_update()
            input_query = input_query.with_for_update()
        project = session.scalar(project_query)
        input_row = session.scalar(input_query)
        if (
            project is None
            or input_row is None
            or (
                input_row.expires_at is not None
                and input_row.expires_at <= datetime.now(UTC)
            )
        ):
            raise DocumentParseNotFoundError("ResearchInput was not found")
        content = session.get(
            ResearchInputContentModel,
            (request.project_id, request.candidate.content_hash),
        )
        if (
            content is None
            or input_row.content_hash != request.candidate.content_hash
            or input_row.status != "accepted"
        ):
            raise DocumentParseIntegrityError(
                "DocumentParse input identity does not match the immutable ResearchInput"
            )
        run = session.scalar(
            select(ResearchRunModel).where(
                ResearchRunModel.id == request.run_id,
                ResearchRunModel.project_id == request.project_id,
            )
        )
        producer = session.scalar(
            select(ProducerExecutionModel).where(
                ProducerExecutionModel.id == request.producer_execution_id,
                ProducerExecutionModel.run_id == request.run_id,
                ProducerExecutionModel.run_step_id == request.run_step_id,
            )
        )
        if run is None or producer is None:
            raise DocumentParseNotFoundError("ProducerExecution was not found")
        if (
            producer.status != "completed"
            or producer.input_hash != request.parse_input_hash
            or producer.output_hash != request.candidate.canonical_output_hash
        ):
            raise DocumentParseIntegrityError(
                "DocumentParse hashes must match its completed ProducerExecution"
            )
        snapshot, expected_snapshot_id = _source_snapshot_for_input(
            session,
            input_row=input_row,
            project_id=request.project_id,
            materialize=materialize_snapshot,
        )
        return input_row, expected_snapshot_id


def document_parse_identity_hash(
    candidate: DocumentParseCandidate, *, parse_input_hash: str
) -> str:
    """Return the deterministic parse reuse identity, excluding wall-clock/id."""

    return compute_canonical_payload_hash(
        {
            "research_input_id": candidate.research_input_id,
            "content_hash": candidate.content_hash,
            "parse_input_hash": parse_input_hash,
            "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
            "schema_hash": compute_scientific_document_schema_hash(),
            "parser_profile_id": candidate.profile.parser_profile_id,
            "parser_profile_version": candidate.profile.parser_profile_version,
            "native_engine": candidate.native_engine,
            "native_engine_version": candidate.native_engine_version,
            "visual_engine": candidate.visual_engine,
            "visual_engine_version": candidate.visual_engine_version,
            "visual_model_id": candidate.visual_model_id,
            "visual_model_revision": candidate.visual_model_revision,
            "config_hash": candidate.config_hash,
            "canonical_output_hash": candidate.canonical_output_hash,
        }
    )


def document_parse_payload_semantic_hash(
    candidate: DocumentParseCandidate,
) -> str:
    """Hash stable Canonical content while excluding worker-local metadata."""

    return compute_canonical_payload_hash(
        candidate.model_dump(
            mode="json",
            exclude_none=True,
            exclude={"parse_id", "created_at"},
        )
    )


def _assert_authoritative_upload_snapshot(
    snapshot: SourceSnapshotModel, *, input_row: ResearchInputModel
) -> None:
    """Single authoritative validator for an upload-backed SourceSnapshot.

    The upload provenance must be byte-exact and self-consistent: it points at
    exactly this ResearchInput, carries the canonical query, and never embeds
    the PDF/image/full text payload (lazy-upload provenance convention).
    """

    expected_query = {"research_input_id": str(input_row.id)}
    if (
        snapshot.project_id != input_row.project_id
        or snapshot.source_id != f"research_input:{input_row.id}"
        or snapshot.source_type != "research_input_upload"
        or snapshot.retrieved_at != input_row.created_at
        or snapshot.query != expected_query
        or snapshot.query_hash != compute_canonical_payload_hash(expected_query)
        or snapshot.content_hash != input_row.content_hash
        or snapshot.source_version_or_etag is not None
        or snapshot.cache_version is not None
        or snapshot.license_note != "user-provided upload"
        or snapshot.request_metadata != {"ingestion_source": "upload"}
    ):
        raise DocumentParseIntegrityError(
            "ResearchInput SourceSnapshot does not satisfy authoritative "
            "upload provenance"
        )


def _assert_source_snapshot_matches_input(
    snapshot: SourceSnapshotModel, *, input_row: ResearchInputModel
) -> None:
    """Keep existing non-upload (URL/text) provenance semantics intact.

    URL/text inputs are never rewritten into upload provenance; the snapshot is
    validated against the input's own source_type and content identity.
    """

    if (
        snapshot.project_id != input_row.project_id
        or snapshot.source_type != input_row.source_type
        or snapshot.content_hash != input_row.content_hash
    ):
        raise DocumentParseIntegrityError(
            "ResearchInput SourceSnapshot does not match its input provenance"
        )


def _source_snapshot_for_input(
    session: Session,
    *,
    input_row: ResearchInputModel,
    project_id: UUID,
    materialize: bool,
) -> tuple[SourceSnapshotModel | None, UUID | None]:
    """Resolve the authoritative SourceSnapshot id for an input.

    Returns ``(snapshot, expected_source_snapshot_id)``. The expected id is the
    single authoritative snapshot the DocumentParse identity must be pinned to;
    it is ``None`` only while an upload snapshot is still being materialized.
    """

    if input_row.source_snapshot_id is not None:
        snapshot = session.scalar(
            select(SourceSnapshotModel).where(
                SourceSnapshotModel.id == input_row.source_snapshot_id,
                SourceSnapshotModel.project_id == project_id,
            )
        )
        if snapshot is None:
            raise DocumentParseIntegrityError(
                "ResearchInput SourceSnapshot is dangling or content-mismatched"
            )
        if input_row.source_type == "upload":
            _assert_authoritative_upload_snapshot(snapshot, input_row=input_row)
        else:
            _assert_source_snapshot_matches_input(snapshot, input_row=input_row)
        return snapshot, snapshot.id
    if input_row.source_type != "upload":
        raise DocumentParseIntegrityError(
            "only an upload ResearchInput may lazily materialize a SourceSnapshot"
        )
    if not materialize:
        return None, None
    query = {"research_input_id": str(input_row.id)}
    existing = session.scalar(
        select(SourceSnapshotModel).where(
            SourceSnapshotModel.project_id == project_id,
            SourceSnapshotModel.source_id == f"research_input:{input_row.id}",
            SourceSnapshotModel.source_type == "research_input_upload",
            SourceSnapshotModel.content_hash == input_row.content_hash,
        )
    )
    if existing is not None:
        _assert_authoritative_upload_snapshot(existing, input_row=input_row)
        input_row.source_snapshot_id = existing.id
        return existing, existing.id
    snapshot = SourceSnapshotModel(
        id=uuid4(),
        project_id=project_id,
        source_id=f"research_input:{input_row.id}",
        source_type="research_input_upload",
        retrieved_at=input_row.created_at,
        query=query,
        query_hash=compute_canonical_payload_hash(query),
        source_version_or_etag=None,
        content_hash=input_row.content_hash,
        license_note="user-provided upload",
        cache_version=None,
        request_metadata={"ingestion_source": "upload"},
    )
    session.add(snapshot)
    session.flush()
    input_row.source_snapshot_id = snapshot.id
    return snapshot, snapshot.id


def _validate_locator(
    candidate: DocumentParseCandidate, locator: DocumentLocator
) -> None:
    pages = {page.page_index: page for page in candidate.pages}
    page = pages.get(locator.page_index)
    if page is None:
        raise DocumentParseIntegrityError("locator references a dangling page")
    if locator.bbox is not None and (
        locator.bbox.x2 > page.width_points
        or locator.bbox.y2 > page.height_points
    ):
        raise DocumentParseIntegrityError("locator bbox escapes its page geometry")

    blocks = {block.block_id: block for block in candidate.blocks}
    block = None
    if locator.reading_order is not None and locator.block_id is None:
        raise DocumentParseIntegrityError("locator reading_order requires block_id")
    if locator.block_id is not None:
        block = blocks.get(locator.block_id)
        if block is None or block.page_index != locator.page_index:
            raise DocumentParseIntegrityError("locator references a dangling block")
        if (
            locator.reading_order is not None
            and block.reading_order != locator.reading_order
        ):
            raise DocumentParseIntegrityError("locator reading_order does not match block")
        if locator.text_span is not None:
            if block.text is None or locator.text_span.end > len(block.text):
                raise DocumentParseIntegrityError("locator text_span escapes block text")

    table_cell = None
    table_block = None
    if locator.table_id is not None:
        table = next(
            (item for item in candidate.tables if item.table_id == locator.table_id),
            None,
        )
        if table is None or table.page_index != locator.page_index:
            raise DocumentParseIntegrityError("locator references a dangling table")
        table_block = blocks.get(table.block_id) if table.block_id is not None else None
        if table_block is None or table_block.page_index != locator.page_index:
            raise DocumentParseIntegrityError(
                "locator table is not backed by its canonical block"
            )
        if block is not None and table.block_id != block.block_id:
            raise DocumentParseIntegrityError(
                "locator block and table belong to different regions"
            )
        if locator.cell_id is not None:
            table_cell = next(
                (
                    cell
                    for row in table.rows
                    for cell in row
                    if cell.cell_id == locator.cell_id
                ),
                None,
            )
            if table_cell is None:
                raise DocumentParseIntegrityError("locator references a dangling table cell")

    reference_bbox = (
        table_cell.bbox
        if table_cell is not None and table_cell.bbox is not None
        else block.bbox
        if block is not None
        else table_block.bbox
        if table_block is not None
        else None
    )
    if (
        locator.bbox is not None
        and reference_bbox is not None
        and not _bbox_contains(reference_bbox, locator.bbox)
    ):
        raise DocumentParseIntegrityError(
            "locator bbox escapes its referenced block or table cell"
        )


def _bbox_contains(container: DocumentBBox, nested: DocumentBBox) -> bool:
    return (
        container.x1 <= nested.x1
        and container.y1 <= nested.y1
        and container.x2 >= nested.x2
        and container.y2 >= nested.y2
    )


def _require_same_parse(
    row: DocumentParseModel,
    *,
    request: PersistDocumentParseRequest,
    identity_hash: str,
    schema_hash: str,
    payload_semantic_hash: str,
    payload_content_hash: str,
    payload_storage_ref: str,
    expected_snapshot_id: UUID,
) -> None:
    if (
        row.identity_hash != identity_hash
        or row.research_input_id != _uuid(request.candidate.research_input_id)
        or row.input_content_hash != request.candidate.content_hash
        or row.parse_input_hash != request.parse_input_hash
        or row.canonical_output_hash != request.candidate.canonical_output_hash
        or row.payload_semantic_hash != payload_semantic_hash
        or row.payload_content_hash != payload_content_hash
        or row.payload_storage_ref != payload_storage_ref
        or row.schema_version != SCIENTIFIC_DOCUMENT_SCHEMA_VERSION
        or row.schema_hash != schema_hash
        or row.source_snapshot_id != expected_snapshot_id
    ):
        raise DocumentParseIntegrityError(
            "existing DocumentParse identity has conflicting immutable content"
        )


def _record(row: DocumentParseModel, *, reused: bool) -> DocumentParseRecord:
    return DocumentParseRecord(
        id=row.id,
        project_id=row.project_id,
        research_input_id=row.research_input_id,
        source_snapshot_id=row.source_snapshot_id,
        producer_execution_id=row.producer_execution_id,
        candidate_parse_id=row.candidate_parse_id,
        identity_hash=row.identity_hash,
        input_content_hash=row.input_content_hash,
        canonical_output_hash=row.canonical_output_hash,
        payload_content_hash=row.payload_content_hash,
        overall_quality=row.overall_quality,
        created_at=row.created_at.astimezone(UTC),
        reused=reused,
    )


def _metadata(row: DocumentParseModel) -> _DocumentParseMetadata:
    return _DocumentParseMetadata(
        candidate_parse_id=row.candidate_parse_id,
        candidate_created_at=row.candidate_created_at.astimezone(UTC),
        research_input_id=row.research_input_id,
        schema_version=row.schema_version,
        schema_hash=row.schema_hash,
        input_content_hash=row.input_content_hash,
        canonical_output_hash=row.canonical_output_hash,
        config_hash=row.config_hash,
        payload_content_hash=row.payload_content_hash,
        payload_semantic_hash=row.payload_semantic_hash,
    )


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise DocumentParseIntegrityError(
            "DocumentParse requires a persisted UUID ResearchInput identity"
        ) from exc


__all__ = [
    "DocumentParseError",
    "DocumentParseIntegrityError",
    "DocumentParseNotFoundError",
    "DocumentParseRecord",
    "DocumentParseRepository",
    "DocumentParseService",
    "PersistDocumentParseRequest",
    "PersistedDocumentLocator",
    "document_parse_identity_hash",
    "document_parse_payload_semantic_hash",
]
