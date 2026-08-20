"""Bridge selected PaperCandidates into the controlled ResearchInput boundary."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    PaperCandidateInputBindingModel,
    PaperCandidateInputIdempotencyModel,
    ResearchInputModel,
    ResearchProjectModel,
    SourceSnapshotModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection_api import (
    CreatePaperCandidateInputRequest,
    ExistingPaperCandidateInputRequest,
    MetadataOnlyPaperCandidateInputRequest,
    OpenAccessPaperCandidateInputRequest,
    PaperCandidateAccessEvidence,
    PaperCandidateInputBinding,
    PaperCollectionCandidateRead,
)
from app.schemas.research_input import ResearchInputCreate, ResearchInputType
from app.security import SecurityProblem
from app.services.paper_collections import PaperCollectionReadService
from app.services.research_input_ingestion import (
    ResearchInputIngestionCommand,
    ResearchInputIngestionService,
)
from app.services.research_input_store import (
    ResearchInputRecord,
    ResearchInputRepository,
)
from app.services.url_fetcher import sanitize_url_for_persistence


_PRODUCER_NAME = "paper_candidate_research_input_bridge"
_PRODUCER_VERSION = "1.0.0"
_URL_ACCESS_KINDS = frozenset(
    {"publisher_open_access", "repository_open_access", "author_provided"}
)
_DEFAULT_LEASE_TTL = timedelta(seconds=300)


@dataclass(frozen=True, slots=True)
class CreatePaperCandidateInputCommand:
    session_id: str
    paper_collection_version_id: str
    candidate_id: str
    idempotency_key: str
    request: CreatePaperCandidateInputRequest


class PaperCandidateInputService:
    def __init__(
        self,
        *,
        paper_collections: PaperCollectionReadService,
        ingestion: ResearchInputIngestionService,
        research_inputs: ResearchInputRepository,
        repository: PaperCandidateInputRepository,
    ) -> None:
        self._paper_collections = paper_collections
        self._ingestion = ingestion
        self._research_inputs = research_inputs
        self._repository = repository
        self._reader = PaperCandidateInputReadService(
            research_inputs=research_inputs,
            repository=repository,
        )

    async def create(
        self, command: CreatePaperCandidateInputCommand
    ) -> PaperCandidateInputBinding:
        collection = self._paper_collections.get_collection(
            version_id=command.paper_collection_version_id,
            session_id=command.session_id,
        )
        candidate = self._paper_collections.get_candidate(
            version_id=command.paper_collection_version_id,
            candidate_id=command.candidate_id,
            session_id=command.session_id,
        )
        if not candidate.candidate.selected:
            raise _problem(
                409,
                "PAPER_CANDIDATE_NOT_SELECTED",
                "Paper candidate is not selected",
                "Only a selected PaperCandidate may be bridged to ResearchInput",
            )
        if (
            not isinstance(command.request, MetadataOnlyPaperCandidateInputRequest)
            and collection.source_mode.value != "live"
        ):
            raise _problem(
                409,
                "PAPER_SOURCE_MODE_NOT_LIVE",
                "Paper source is not live",
                "Fixture or cached PaperCollection data cannot create a live ResearchInput",
            )
        if (
            not isinstance(command.request, MetadataOnlyPaperCandidateInputRequest)
            and candidate.candidate.raw.synthetic_note is not None
        ):
            raise _problem(
                409,
                "PAPER_CANDIDATE_SYNTHETIC",
                "Paper candidate is synthetic",
                "Synthetic PaperCandidates cannot create a ResearchInput",
            )

        request_payload = command.request.model_dump(mode="json", exclude_none=True)
        request_hash = compute_canonical_payload_hash(
            {
                "paper_collection_version_id": command.paper_collection_version_id,
                "candidate_id": command.candidate_id,
                "request": request_payload,
            }
        )
        normalized_evidence = _normalized_access_evidence(
            command.request,
            canonical_paper_id=candidate.candidate.canonical_paper_id,
        )
        access_evidence_hash = (
            compute_canonical_payload_hash(normalized_evidence.model_dump(mode="json"))
            if normalized_evidence is not None
            else None
        )
        identity_hash = compute_canonical_payload_hash(
            {
                "paper_collection_version_id": command.paper_collection_version_id,
                "candidate_id": command.candidate_id,
                "canonical_paper_id": candidate.candidate.canonical_paper_id,
                "mode": command.request.mode,
                "access_evidence_hash": access_evidence_hash,
                "access_url_hash": (
                    compute_canonical_payload_hash(command.request.access_url)
                    if isinstance(command.request, OpenAccessPaperCandidateInputRequest)
                    else None
                ),
                "filename": (
                    command.request.filename
                    if isinstance(command.request, OpenAccessPaperCandidateInputRequest)
                    else None
                ),
                "research_input_id": (
                    command.request.research_input_id
                    if isinstance(command.request, ExistingPaperCandidateInputRequest)
                    else None
                ),
                "metadata_reason": (
                    command.request.reason.value
                    if isinstance(
                        command.request, MetadataOnlyPaperCandidateInputRequest
                    )
                    else None
                ),
            }
        )
        reservation = self._repository.reserve(
            session_id=command.session_id,
            project_id=collection.project_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        if reservation.replayed is not None:
            return self._project(reservation.replayed, command.session_id, reused=True)
        assert reservation.lease_token is not None
        try:
            input_record = await self._resolve_input(
                command,
                project_id=collection.project_id,
                identity_hash=identity_hash,
            )
        except Exception:
            self._repository.release(
                session_id=command.session_id,
                project_id=collection.project_id,
                idempotency_key=command.idempotency_key,
                lease_token=reservation.lease_token,
            )
            raise
        row = self._repository.persist(
            session_id=command.session_id,
            project_id=collection.project_id,
            paper_collection_version_id=command.paper_collection_version_id,
            candidate=candidate,
            source_collection_status=collection.collection.acquisition_run.status,
            request=command.request,
            normalized_evidence=normalized_evidence,
            access_evidence_hash=access_evidence_hash,
            input_record=input_record,
            identity_hash=identity_hash,
            request_hash=request_hash,
            idempotency_key=command.idempotency_key,
            lease_token=reservation.lease_token,
        )
        return self._project(row, command.session_id, reused=row.reused)

    async def _resolve_input(
        self,
        command: CreatePaperCandidateInputCommand,
        *,
        project_id: str,
        identity_hash: str,
    ) -> ResearchInputRecord | None:
        request = command.request
        if isinstance(request, MetadataOnlyPaperCandidateInputRequest):
            return None
        if isinstance(request, ExistingPaperCandidateInputRequest):
            record = self._research_inputs.get(
                session_id=command.session_id,
                input_id=request.research_input_id,
            )
            if record is None or record.project_id != project_id:
                raise _not_found()
            expected_resource_hash = _research_input_resource_hash(record)
            if request.access_evidence.resource_identity_hash != expected_resource_hash:
                raise _access_resource_problem()
            return record
        return await self._ingestion.create(
            ResearchInputIngestionCommand(
                session_id=command.session_id,
                project_id=project_id,
                payload=ResearchInputCreate(
                    type=ResearchInputType.url,
                    url=request.access_url,
                    filename=request.filename,
                ),
                idempotency_key=f"paper-candidate:{identity_hash}",
            )
        )

    def accepted_research_input(
        self,
        *,
        session_id: str,
        project_id: str,
        paper_collection_version_id: str,
        canonical_paper_id: str,
    ) -> ResearchInputRecord | None:
        return self._reader.accepted_research_input(
            session_id=session_id,
            project_id=project_id,
            paper_collection_version_id=paper_collection_version_id,
            canonical_paper_id=canonical_paper_id,
        )

    def _project(
        self,
        row: _BindingRecord,
        session_id: str,
        *,
        reused: bool,
    ) -> PaperCandidateInputBinding:
        input_ref = None
        if row.research_input_id is not None:
            record = self._research_inputs.get(
                session_id=session_id, input_id=str(row.research_input_id)
            )
            if record is None or record.content_hash != row.research_input_content_hash:
                raise _integrity_problem()
            input_ref = record.to_ref()
        return PaperCandidateInputBinding(
            id=str(row.id),
            project_id=str(row.project_id),
            paper_collection_version_id=str(row.paper_collection_version_id),
            candidate_id=row.candidate_id,
            canonical_paper_id=row.canonical_paper_id,
            candidate_source_snapshot_id=str(row.candidate_source_snapshot_id),
            candidate_evidence_ids=(str(row.candidate_evidence_id),),
            mode=row.mode,
            outcome=row.outcome,
            source_collection_status=row.source_collection_status,
            metadata_reason=row.metadata_reason,
            access_evidence=(
                PaperCandidateAccessEvidence.model_validate(row.access_evidence)
                if row.access_evidence is not None
                else None
            ),
            access_evidence_hash=row.access_evidence_hash,
            research_input=input_ref,
            created_at=row.created_at,
            reused=reused,
        )


class PaperCandidateInputReadService:
    """Resolve an immutable accepted research-document binding."""

    def __init__(
        self,
        *,
        research_inputs: ResearchInputRepository,
        repository: PaperCandidateInputRepository,
    ) -> None:
        self._research_inputs = research_inputs
        self._repository = repository

    def accepted_research_input(
        self,
        *,
        session_id: str,
        project_id: str,
        paper_collection_version_id: str,
        canonical_paper_id: str,
    ) -> ResearchInputRecord | None:
        """Resolve the newest accepted full-text ResearchInput bound to one paper."""

        accepted = self._repository.accepted_input_for_paper(
            project_id=project_id,
            paper_collection_version_id=paper_collection_version_id,
            canonical_paper_id=canonical_paper_id,
        )
        if accepted is None:
            return None
        record = self._research_inputs.get(
            session_id=session_id, input_id=accepted.research_input_id
        )
        supported_mime_types = {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
        }
        if (
            record is None
            or record.project_id != project_id
            or record.content_hash != accepted.research_input_content_hash
            or (
                record.type not in {ResearchInputType.pdf, ResearchInputType.image}
                and record.mime_type not in supported_mime_types
            )
        ):
            return None
        return record


@dataclass(frozen=True, slots=True)
class _BindingRecord:
    id: UUID
    project_id: UUID
    paper_collection_version_id: UUID
    candidate_id: str
    canonical_paper_id: str
    candidate_source_snapshot_id: UUID
    candidate_evidence_id: UUID
    mode: str
    outcome: str
    source_collection_status: str
    metadata_reason: str | None
    access_evidence: dict[str, object] | None
    access_evidence_hash: str | None
    research_input_id: UUID | None
    research_input_content_hash: str | None
    identity_hash: str
    request_hash: str
    idempotency_key: str
    created_at: object
    reused: bool = False


@dataclass(frozen=True, slots=True)
class _BridgeReservation:
    replayed: _BindingRecord | None
    lease_token: str | None


@dataclass(frozen=True, slots=True)
class AcceptedPaperInput:
    """Newest accepted binding's pinned ResearchInput identity for one paper."""

    research_input_id: str
    research_input_content_hash: str | None


class PaperCandidateInputRepository:
    def __init__(
        self,
        factory: Callable[[], Session],
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = _DEFAULT_LEASE_TTL,
    ) -> None:
        self._factory = factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_ttl = lease_ttl

    def reserve(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> _BridgeReservation:
        project_uuid = _uuid(project_id)
        now = self._clock()
        with self._factory() as session, session.begin():
            project = session.get(ResearchProjectModel, project_uuid)
            if project is None or project.session_id != session_id:
                raise _not_found()
            existing = session.get(
                PaperCandidateInputIdempotencyModel,
                (session_id, project_uuid, idempotency_key),
                with_for_update=True,
            )
            if existing is not None:
                return self._reservation_from_row(
                    session, existing, request_hash=request_hash, now=now
                )
            token = secrets.token_urlsafe(24)
            session.add(
                PaperCandidateInputIdempotencyModel(
                    session_id=session_id,
                    project_id=project_uuid,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    binding_id=None,
                    status="pending",
                    lease_token=token,
                    lease_expires_at=now + self._lease_ttl,
                    created_at=now,
                    updated_at=now,
                )
            )
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
            else:
                return _BridgeReservation(replayed=None, lease_token=token)

        with self._factory() as session, session.begin():
            winner = session.get(
                PaperCandidateInputIdempotencyModel,
                (session_id, project_uuid, idempotency_key),
                with_for_update=True,
            )
            if winner is None:
                raise _integrity_problem()
            return self._reservation_from_row(
                session, winner, request_hash=request_hash, now=now
            )

    def release(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
    ) -> None:
        with self._factory() as session, session.begin():
            row = session.get(
                PaperCandidateInputIdempotencyModel,
                (session_id, _uuid(project_id), idempotency_key),
                with_for_update=True,
            )
            if (
                row is not None
                and row.status == "pending"
                and row.lease_token == lease_token
            ):
                session.delete(row)

    def _reservation_from_row(
        self,
        session: Session,
        row: PaperCandidateInputIdempotencyModel,
        *,
        request_hash: str,
        now: datetime,
    ) -> _BridgeReservation:
        if row.request_hash != request_hash:
            raise _idempotency_conflict()
        if row.status == "completed" and row.binding_id is not None:
            binding = session.get(PaperCandidateInputBindingModel, row.binding_id)
            if binding is None or binding.project_id != row.project_id:
                raise _integrity_problem()
            return _BridgeReservation(replayed=_record(binding), lease_token=None)
        if row.lease_expires_at is not None and row.lease_expires_at > now:
            raise _idempotency_in_progress()
        token = secrets.token_urlsafe(24)
        row.lease_token = token
        row.lease_expires_at = now + self._lease_ttl
        row.updated_at = now
        return _BridgeReservation(replayed=None, lease_token=token)

    def accepted_input_for_paper(
        self,
        *,
        project_id: str,
        paper_collection_version_id: str,
        canonical_paper_id: str,
    ) -> AcceptedPaperInput | None:
        with self._factory() as session:
            row = session.scalar(
                select(PaperCandidateInputBindingModel)
                .where(
                    PaperCandidateInputBindingModel.project_id == _uuid(project_id),
                    PaperCandidateInputBindingModel.paper_collection_version_id
                    == _uuid(paper_collection_version_id),
                    PaperCandidateInputBindingModel.canonical_paper_id
                    == canonical_paper_id,
                    PaperCandidateInputBindingModel.outcome == "accepted",
                    PaperCandidateInputBindingModel.research_input_id.is_not(None),
                )
                .order_by(
                    PaperCandidateInputBindingModel.created_at.desc(),
                    PaperCandidateInputBindingModel.id.desc(),
                )
                .limit(1)
            )
        if row is None or row.research_input_id is None:
            return None
        return AcceptedPaperInput(
            research_input_id=str(row.research_input_id),
            research_input_content_hash=row.research_input_content_hash,
        )

    def persist(
        self,
        *,
        session_id: str,
        project_id: str,
        paper_collection_version_id: str,
        candidate: PaperCollectionCandidateRead,
        source_collection_status: str,
        request: CreatePaperCandidateInputRequest,
        normalized_evidence: PaperCandidateAccessEvidence | None,
        access_evidence_hash: str | None,
        input_record: ResearchInputRecord | None,
        identity_hash: str,
        request_hash: str,
        idempotency_key: str,
        lease_token: str,
    ) -> _BindingRecord:
        with self._factory() as session, session.begin():
            project_uuid = _uuid(project_id)
            version_uuid = _uuid(paper_collection_version_id)
            project = session.get(ResearchProjectModel, project_uuid)
            version = session.get(ArtifactVersionModel, version_uuid)
            if (
                project is None
                or project.session_id != session_id
                or version is None
                or version.project_id != project_uuid
            ):
                raise _not_found()
            reservation = session.get(
                PaperCandidateInputIdempotencyModel,
                (session_id, project_uuid, idempotency_key),
                with_for_update=True,
            )
            if (
                reservation is None
                or reservation.status != "pending"
                or reservation.request_hash != request_hash
                or reservation.lease_token != lease_token
            ):
                raise _idempotency_reservation_lost()
            snapshot_uuid = _uuid(candidate.source_snapshot.id)
            snapshot = session.get(SourceSnapshotModel, snapshot_uuid)
            if snapshot is None or snapshot.project_id != project_uuid:
                raise _integrity_problem()
            candidate_evidence_options = tuple(
                item
                for item in candidate.evidence
                if item.target_type == "paper_candidate"
                and item.evidence_type == "paper_metadata"
            )
            if not candidate_evidence_options:
                raise _integrity_problem()
            candidate_evidence = min(
                candidate_evidence_options, key=lambda item: item.id
            )
            evidence_uuid = _uuid(candidate_evidence.id)
            evidence_row = session.scalar(
                select(EvidenceModel).where(
                    EvidenceModel.id == evidence_uuid,
                    EvidenceModel.project_id == project_uuid,
                    EvidenceModel.artifact_version_id == version_uuid,
                    EvidenceModel.source_snapshot_id == snapshot_uuid,
                    EvidenceModel.target_id.in_(
                        (
                            candidate.candidate.candidate_id,
                            candidate.candidate.canonical_paper_id,
                        )
                    ),
                )
            )
            if evidence_row is None:
                raise _integrity_problem()
            input_uuid = _uuid(input_record.id) if input_record is not None else None
            if input_uuid is not None:
                input_row = session.get(ResearchInputModel, input_uuid)
                if (
                    input_row is None
                    or input_row.project_id != project_uuid
                    or input_row.session_id != session_id
                    or input_row.content_hash != input_record.content_hash
                ):
                    raise _not_found()
            values = {
                "id": uuid4(),
                "project_id": project_uuid,
                "paper_collection_version_id": version_uuid,
                "candidate_id": candidate.candidate.candidate_id,
                "canonical_paper_id": candidate.candidate.canonical_paper_id,
                "candidate_source_snapshot_id": snapshot_uuid,
                "candidate_evidence_id": evidence_uuid,
                "mode": request.mode,
                "outcome": "metadata_only" if input_record is None else "accepted",
                "source_collection_status": source_collection_status,
                "metadata_reason": (
                    request.reason.value
                    if isinstance(request, MetadataOnlyPaperCandidateInputRequest)
                    else None
                ),
                "access_evidence": (
                    normalized_evidence.model_dump(mode="json")
                    if normalized_evidence is not None
                    else None
                ),
                "access_evidence_hash": access_evidence_hash,
                "research_input_id": input_uuid,
                "research_input_content_hash": (
                    input_record.content_hash if input_record is not None else None
                ),
                "identity_hash": identity_hash,
                "request_hash": request_hash,
                "idempotency_key": idempotency_key,
                "producer_name": _PRODUCER_NAME,
                "producer_version": _PRODUCER_VERSION,
            }
            session.execute(
                pg_insert(PaperCandidateInputBindingModel.__table__)
                .values(**values)
                .on_conflict_do_nothing()
            )
            winner = session.scalar(
                select(PaperCandidateInputBindingModel).where(
                    PaperCandidateInputBindingModel.project_id == project_uuid,
                    PaperCandidateInputBindingModel.identity_hash == identity_hash,
                )
            )
            if winner is None:
                by_key = session.scalar(
                    select(PaperCandidateInputBindingModel).where(
                        PaperCandidateInputBindingModel.project_id == project_uuid,
                        PaperCandidateInputBindingModel.idempotency_key
                        == idempotency_key,
                    )
                )
                if by_key is None or by_key.request_hash != request_hash:
                    raise _problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency key conflict",
                        "The Idempotency-Key was already used for another bridge request",
                    )
                winner = by_key
            _require_same_binding(winner, values)
            reservation.status = "completed"
            reservation.binding_id = winner.id
            reservation.lease_token = None
            reservation.lease_expires_at = None
            reservation.updated_at = self._clock()
            return replace(_record(winner), reused=winner.id != values["id"])


def _normalized_access_evidence(
    request: CreatePaperCandidateInputRequest,
    *,
    canonical_paper_id: str,
) -> PaperCandidateAccessEvidence | None:
    if isinstance(request, MetadataOnlyPaperCandidateInputRequest):
        return None
    if (
        isinstance(request, OpenAccessPaperCandidateInputRequest)
        and request.access_evidence.kind.value not in _URL_ACCESS_KINDS
    ):
        raise _problem(
            422,
            "PAPER_ACCESS_NOT_PROVEN",
            "Paper access is not proven",
            "An open-access URL requires publisher, repository, or author access evidence",
        )
    evidence = request.access_evidence
    if evidence.canonical_paper_id != canonical_paper_id:
        raise _access_resource_problem()
    if isinstance(request, OpenAccessPaperCandidateInputRequest):
        if (
            evidence.resource_type != "access_url"
            or evidence.resource_identity_hash
            != _access_url_resource_hash(request.access_url)
        ):
            raise _access_resource_problem()
    elif evidence.resource_type != "research_input":
        raise _access_resource_problem()
    evidence_url = _safe_https_url(evidence.evidence_url)
    return evidence.model_copy(update={"evidence_url": evidence_url})


def _access_url_resource_hash(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if not host or parsed.username is not None or parsed.password is not None:
            raise ValueError
        port = f":{parsed.port}" if parsed.port is not None else ""
        normalized = urlunsplit(
            (
                parsed.scheme.casefold(),
                f"{host.casefold()}{port}",
                parsed.path,
                parsed.query,
                "",
            )
        )
    except ValueError as exc:
        raise _access_resource_problem() from exc
    return compute_canonical_payload_hash(
        {"resource_type": "access_url", "url": normalized}
    )


def _research_input_resource_hash(record: ResearchInputRecord) -> str:
    return compute_canonical_payload_hash(
        {
            "resource_type": "research_input",
            "research_input_id": record.id,
            "content_hash": record.content_hash,
        }
    )


def _safe_https_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise _problem(
            422,
            "PAPER_ACCESS_NOT_PROVEN",
            "Paper access is not proven",
            "Access evidence must reference a credential-free HTTPS URL",
        )
    return sanitize_url_for_persistence(
        urlunsplit(("https", parsed.netloc.casefold(), parsed.path, parsed.query, ""))
    )


def _require_same_binding(
    row: PaperCandidateInputBindingModel, values: dict[str, object]
) -> None:
    fields = (
        "paper_collection_version_id",
        "candidate_id",
        "canonical_paper_id",
        "candidate_source_snapshot_id",
        "candidate_evidence_id",
        "mode",
        "outcome",
        "source_collection_status",
        "metadata_reason",
        "access_evidence",
        "access_evidence_hash",
        "research_input_id",
        "research_input_content_hash",
        "identity_hash",
    )
    if any(getattr(row, field) != values[field] for field in fields):
        raise _integrity_problem()


def _record(row: PaperCandidateInputBindingModel) -> _BindingRecord:
    return _BindingRecord(
        id=row.id,
        project_id=row.project_id,
        paper_collection_version_id=row.paper_collection_version_id,
        candidate_id=row.candidate_id,
        canonical_paper_id=row.canonical_paper_id,
        candidate_source_snapshot_id=row.candidate_source_snapshot_id,
        candidate_evidence_id=row.candidate_evidence_id,
        mode=row.mode,
        outcome=row.outcome,
        source_collection_status=row.source_collection_status,
        metadata_reason=row.metadata_reason,
        access_evidence=row.access_evidence,
        access_evidence_hash=row.access_evidence_hash,
        research_input_id=row.research_input_id,
        research_input_content_hash=row.research_input_content_hash,
        identity_hash=row.identity_hash,
        request_hash=row.request_hash,
        idempotency_key=row.idempotency_key,
        created_at=row.created_at,
    )


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise _not_found() from exc


def _not_found() -> SecurityProblem:
    return _problem(
        404,
        "PAPER_CANDIDATE_INPUT_NOT_FOUND",
        "Resource not found",
        "The PaperCandidate input resource was not found",
    )


def _integrity_problem() -> SecurityProblem:
    return _problem(
        409,
        "PAPER_CANDIDATE_INPUT_INTEGRITY_CONFLICT",
        "Paper candidate input integrity conflict",
        "The immutable PaperCandidate input provenance is inconsistent",
    )


def _access_resource_problem() -> SecurityProblem:
    return _problem(
        422,
        "PAPER_ACCESS_RESOURCE_MISMATCH",
        "Paper access resource mismatch",
        "Access evidence does not bind the selected paper to the requested resource",
    )


def _idempotency_conflict() -> SecurityProblem:
    return _problem(
        409,
        "IDEMPOTENCY_CONFLICT",
        "Idempotency key conflict",
        "The Idempotency-Key was already used for another bridge request",
    )


def _idempotency_in_progress() -> SecurityProblem:
    return _problem(
        409,
        "IDEMPOTENCY_IN_PROGRESS",
        "Idempotent request is in progress",
        "A matching PaperCandidate input request is still being processed",
    )


def _idempotency_reservation_lost() -> SecurityProblem:
    return _problem(
        409,
        "IDEMPOTENCY_RESERVATION_LOST",
        "Idempotency reservation lost",
        "The PaperCandidate input reservation expired or was reclaimed",
    )


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = [
    "AcceptedPaperInput",
    "CreatePaperCandidateInputCommand",
    "PaperCandidateInputRepository",
    "PaperCandidateInputReadService",
    "PaperCandidateInputService",
]
