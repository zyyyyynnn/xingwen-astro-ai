"""Shared production execution boundary for Canonical document parsing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchInputBindingModel,
    ResearchInputContentModel,
    ResearchInputModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.research_input import ResearchInputStatus, ResearchInputType
from app.schemas.scientific_document import (
    DocumentLocator,
    DocumentParseCandidate,
    DocumentParseInput,
    is_supported_scientific_document_input,
)
from app.services.content_storage import ContentStorage
from app.services.document_parse_store import (
    DocumentParseRecord,
    DocumentParseService,
    DocumentParseSourceSnapshot,
    PersistDocumentParseRequest,
)
from app.services.scientific_document.ports import DocumentParserPort
from app.workflow.step_publication import RunStepContext, StepPublicationFactory
from app.workflow.store import AttemptHandle, LeaseGrant


@dataclass(frozen=True, slots=True)
class DocumentInputSource:
    id: UUID
    input_type: ResearchInputType
    content_hash: str
    source_type: str
    mime_type: str | None
    filename: str | None

    @classmethod
    def from_record(cls, record: object) -> DocumentInputSource:
        input_type = getattr(record, "type")
        return cls(
            id=UUID(str(getattr(record, "id"))),
            input_type=(
                input_type
                if isinstance(input_type, ResearchInputType)
                else ResearchInputType(str(input_type))
            ),
            content_hash=str(getattr(record, "content_hash")),
            source_type=str(getattr(record, "source_type")),
            mime_type=getattr(record, "mime_type"),
            filename=getattr(record, "filename"),
        )


@dataclass(frozen=True, slots=True)
class ExecutedDocumentParse:
    candidate: DocumentParseCandidate
    record: DocumentParseRecord
    source_snapshot: DocumentParseSourceSnapshot


class DocumentParseExecutionService:
    """Execute the one configured parser and persist through DocumentParseService."""

    def __init__(
        self,
        *,
        factory: Callable[[], Session],
        content_storage: ContentStorage,
        parser: DocumentParserPort,
        document_parses: DocumentParseService,
        publications: StepPublicationFactory,
    ) -> None:
        self._factory = factory
        self._content_storage = content_storage
        self._parser = parser
        self._document_parses = document_parses
        self._publications = publications

    def parse_bound_inputs(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> tuple[ExecutedDocumentParse, ...]:
        sources = self._bound_document_sources(
            project_id=context.project_id,
            run_id=context.run_id,
            contract_draft_id=UUID(str(context.contract.created_from_draft_id)),
        )
        return tuple(
            self.execute(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                source=source,
                operation_key=f"document_parse:dataset:{source.id}",
            )
            for source in sources
        )

    def execute(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        source: DocumentInputSource,
        operation_key: str,
    ) -> ExecutedDocumentParse:
        if not is_supported_scientific_document_input(
            input_type=source.input_type,
            mime_type=source.mime_type,
        ):
            raise ValueError("ResearchInput is not a supported scientific document")
        content = asyncio.run(self._content_storage.retrieve(source.content_hash))
        if content is None:
            raise ValueError("The immutable ResearchInput content is missing")
        parse_input = DocumentParseInput(
            research_input_id=str(source.id),
            content_hash=source.content_hash,
            source_type=source.source_type,
            mime_type=source.mime_type or "application/octet-stream",
            filename=source.filename,
            input_bytes=content,
        )
        profile = self._parser.profile
        parse_input_hash = compute_canonical_payload_hash(
            {
                "input": parse_input.model_dump(
                    mode="json", exclude_none=True, exclude={"input_bytes"}
                ),
                "profile": profile.model_dump(mode="json"),
            }
        )
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key=operation_key,
            producer_type="algorithm",
            producer_name="scientific-document-parser",
            producer_version=profile.parser_profile_version,
            input_hash=parse_input_hash,
            parameters={
                "parser_profile_id": profile.parser_profile_id,
                "routing_policy_id": profile.routing_policy_id,
            },
            parameters_hash=profile.configuration_hash,
            attempt=attempt,
            lease=lease,
        )
        try:
            candidate = self._parser.parse_document(parse_input)
        except Exception:
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code="DOCUMENT_PARSE_FAILED",
            )
            raise
        self._publications.finish_producer(
            execution.id,
            status="completed",
            output_hash=candidate.canonical_output_hash,
        )
        record = asyncio.run(
            self._document_parses.persist(
                PersistDocumentParseRequest(
                    project_id=context.project_id,
                    run_id=context.run_id,
                    run_step_id=attempt.run_step_id,
                    producer_execution_id=execution.id,
                    parse_input_hash=parse_input_hash,
                    candidate=candidate,
                )
            )
        )
        return ExecutedDocumentParse(
            candidate=candidate,
            record=record,
            source_snapshot=self._document_parses.source_snapshot(
                project_id=context.project_id,
                document_parse_id=record.id,
            ),
        )

    def persist_locator(
        self,
        *,
        project_id: UUID,
        document_parse_id: UUID,
        source_snapshot_id: UUID,
        locator: DocumentLocator,
    ) -> None:
        asyncio.run(
            self._document_parses.persist_locator(
                project_id=project_id,
                document_parse_id=document_parse_id,
                source_snapshot_id=source_snapshot_id,
                locator=locator,
            )
        )

    def _bound_document_sources(
        self,
        *,
        project_id: UUID,
        run_id: UUID,
        contract_draft_id: UUID,
    ) -> tuple[DocumentInputSource, ...]:
        with self._factory() as session:
            rows = tuple(
                session.execute(
                    select(ResearchInputModel, ResearchInputContentModel.mime_type)
                    .join(
                        ResearchInputBindingModel,
                        ResearchInputBindingModel.input_id == ResearchInputModel.id,
                    )
                    .join(
                        ResearchInputContentModel,
                        (
                            ResearchInputContentModel.project_id
                            == ResearchInputModel.project_id
                        )
                        & (
                            ResearchInputContentModel.content_hash
                            == ResearchInputModel.content_hash
                        ),
                    )
                    .where(
                        ResearchInputModel.project_id == project_id,
                        ResearchInputModel.status == ResearchInputStatus.accepted.value,
                        (
                            (
                                ResearchInputBindingModel.contract_draft_id
                                == contract_draft_id
                            )
                            | (ResearchInputBindingModel.run_id == run_id)
                        ),
                    )
                    .order_by(ResearchInputModel.id)
                )
            )
        sources = tuple(
            DocumentInputSource(
                id=row.id,
                input_type=ResearchInputType(row.type),
                content_hash=row.content_hash,
                source_type=row.source_type,
                mime_type=mime_type,
                filename=row.filename,
            )
            for row, mime_type in rows
        )
        return tuple(
            source
            for source in sources
            if is_supported_scientific_document_input(
                input_type=source.input_type,
                mime_type=source.mime_type,
            )
        )


__all__ = [
    "DocumentInputSource",
    "DocumentParseExecutionService",
    "ExecutedDocumentParse",
]
