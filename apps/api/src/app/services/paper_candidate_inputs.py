"""Bridge selected PaperCandidates into the controlled ResearchInput boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    PaperCandidateInputBindingModel,
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
from app.services.research_input_store import ResearchInputRecord, ResearchInputRepository
from app.services.url_fetcher import sanitize_url_for_persistence


_PRODUCER_NAME = "paper_candidate_research_input_bridge"
_PRODUCER_VERSION = "1.0.0"
_URL_ACCESS_KINDS = frozenset(
    {"publisher_open_access", "repository_open_access", "author_provided"}
)


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
        existing = self._repository.by_idempotency_key(
            session_id=command.session_id,
            project_id=collection.project_id,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return self._project(existing, command.session_id, reused=True)

        normalized_evidence = _normalized_access_evidence(command.request)
        access_evidence_hash = (
            compute_canonical_payload_hash(
                normalized_evidence.model_dump(mode="json")
            )
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
                    if isinstance(command.request, MetadataOnlyPaperCandidateInputRequest)
                    else None
                ),
            }
        )
        input_record = await self._resolve_input(
            command,
            project_id=collection.project_id,
            identity_hash=identity_hash,
        )
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


class PaperCandidateInputRepository:
    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def by_idempotency_key(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> _BindingRecord | None:
        with self._factory() as session:
            project = session.get(ResearchProjectModel, _uuid(project_id))
            if project is None or project.session_id != session_id:
                raise _not_found()
            row = session.scalar(
                select(PaperCandidateInputBindingModel).where(
                    PaperCandidateInputBindingModel.project_id == project.id,
                    PaperCandidateInputBindingModel.idempotency_key == idempotency_key,
                )
            )
            if row is None:
                return None
            if row.request_hash != request_hash:
                raise _problem(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key conflict",
                    "The Idempotency-Key was already used for another bridge request",
                )
            return _record(row)

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
            candidate_evidence = min(candidate_evidence_options, key=lambda item: item.id)
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
                        PaperCandidateInputBindingModel.idempotency_key == idempotency_key,
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
            return replace(_record(winner), reused=winner.id != values["id"])


def _normalized_access_evidence(
    request: CreatePaperCandidateInputRequest,
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
    evidence_url = _safe_https_url(evidence.evidence_url)
    return evidence.model_copy(update={"evidence_url": evidence_url})


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


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = [
    "CreatePaperCandidateInputCommand",
    "PaperCandidateInputRepository",
    "PaperCandidateInputService",
]
