"""Produce and admit summaries over collected-document provenance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection import PaperBenchmarkReference, PaperCollection, PaperCollectionCandidate
from app.schemas.paper_summary import (
    PaperSummaryAdmissionResult,
    PaperSummaryAdmissionStatus,
    PaperSummaryArtifactContent,
    PaperSummaryDocumentParseReference,
    PaperSummaryEvidence,
    PaperSummaryEvidenceCandidate,
    PaperSummaryEvidenceLocator,
    PaperSummaryFailureStage,
    PaperSummaryInputVersions,
    PaperSummaryModelOutput,
    PaperSummaryModelUsage,
    PaperSummaryPaperMetadata,
    PaperSummaryProducerExecution,
    PaperSummarySourceConflict,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummaryStatementCandidate,
    PaperSummarySupportStatus,
    _seal_paper_summary_for_publication,
    compute_paper_summary_output_hash,
    dump_paper_summary_input_versions,
)
from app.schemas.scientific_document import (
    DocumentBlockKind,
    DocumentLocator,
    DocumentParseCandidate,
    DocumentParseQuality,
    TextSpan,
)
from app.services.document_parse_store import (
    DocumentParseIntegrityError,
    validate_document_locator,
)
from packages.prompts.registry import PromptRegistry

from .constants import (
    SUMMARY_PARAMETERS_VERSION,
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)


Clock = Callable[[], datetime]
ParameterValue = str | int | float | bool | None
EvidenceAdmitter = Callable[
    [PaperSummaryEvidenceCandidate],
    tuple[PaperSummaryEvidence | None, PaperSummarySourceConflict | None],
]
_SAFE_PARAMETER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FORBIDDEN_PARAMETER_FRAGMENTS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "private_key",
    "raw_model",
    "response_body",
    "secret",
)


class PaperSummaryPipeline:
    """Admit structured model output without publishing or advancing ResearchRun."""

    def __init__(
        self,
        *,
        prompt_registry: PromptRegistry | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def admit(
        self,
        *,
        paper_collection: PaperCollection,
        paper_collection_version_id: str,
        paper_id: str,
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ParameterValue],
        evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...],
        parameters_version: str = SUMMARY_PARAMETERS_VERSION,
        execution_id: str | None = None,
        run_id: str | None = None,
    ) -> PaperSummaryAdmissionResult:
        prompt = self.prompt_registry.get("paper_summary")
        if paper_id not in paper_collection.selected_paper_ids:
            raise ValueError("PaperSummary input paper must be selected by PaperCollection")
        safe_parameters = _validate_parameters(parameters)
        parameter_hash = compute_canonical_payload_hash(
            {
                "parameters_version": parameters_version,
                "parameters": safe_parameters,
            }
        )
        input_versions = _input_versions(
            paper_collection=paper_collection,
            paper_collection_version_id=paper_collection_version_id,
        )
        candidates_by_id = {
            candidate.candidate_id: candidate
            for candidate in paper_collection.candidates
        }
        snapshots_by_id = {
            snapshot.source_snapshot_id: snapshot
            for snapshot in input_versions.source_snapshots
        }
        evidence_input_hash = compute_canonical_payload_hash(
            [
                candidate.model_dump(mode="json", exclude_none=True)
                for candidate in sorted(
                    evidence_candidates, key=lambda item: item.evidence_id
                )
            ]
        )
        input_hash = compute_canonical_payload_hash(
            {
                "paper_collection_version_id": paper_collection_version_id,
                "paper_collection_schema_version": paper_collection.schema_version,
                "paper_collection_output_hash": paper_collection.output_hash,
                "source_snapshot_versions": dump_paper_summary_input_versions(
                    input_versions
                )["source_snapshots"],
                "paper_id": paper_id,
                "evidence_input_hash": evidence_input_hash,
                "prompt_name": prompt.name,
                "prompt_version": prompt.version,
                "prompt_hash": prompt.content_hash,
                "model_name": model_name,
                "parameters_version": parameters_version,
                "parameters_hash": parameter_hash,
            }
        )
        response_hash = compute_canonical_payload_hash(model_response)
        now = self._now()
        stable_execution_id = execution_id or f"execution.{input_hash[7:31]}"
        producer_fields = {
            "execution_id": stable_execution_id,
            "run_id": run_id,
            "producer_name": SUMMARY_PRODUCER_NAME,
            "producer_version": SUMMARY_PRODUCER_VERSION,
            "model_name": model_name,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "parameters_version": parameters_version,
            "parameters_hash": parameter_hash,
            "input_versions": input_versions,
            "input_hash": input_hash,
            "model_response_hash": response_hash,
            "started_at": now,
            "finished_at": now,
            "latency_ms": 0,
        }
        try:
            decoded = json.loads(model_response)
        except (json.JSONDecodeError, TypeError):
            return _rejected(
                producer_fields=producer_fields,
                stage=PaperSummaryFailureStage.json,
                error_code="paper_summary.json_invalid",
            )
        response_hash = compute_canonical_payload_hash(decoded)
        producer_fields["model_response_hash"] = response_hash
        try:
            model_output = PaperSummaryModelOutput.model_validate(decoded)
        except ValidationError:
            return _rejected(
                producer_fields=producer_fields,
                stage=PaperSummaryFailureStage.schema,
                error_code="paper_summary.schema_invalid",
            )

        summary = _admit_evidence(
            model_output=model_output,
            input_versions=input_versions,
            paper_id=paper_id,
            paper=None,
            benchmark=paper_collection.benchmark,
            evidence_candidates=evidence_candidates,
            evidence_admitter=lambda candidate: _validate_evidence_candidate(
                candidate=candidate,
                paper_id=paper_id,
                collection_candidates=candidates_by_id,
                snapshots=snapshots_by_id,
            ),
            producer_fields=producer_fields,
            input_hash=input_hash,
            response_hash=response_hash,
        )
        return PaperSummaryAdmissionResult(
            admission_status=PaperSummaryAdmissionStatus.accepted,
            summary=summary,
            producer=summary.producer,
        )

    def admit_document(
        self,
        *,
        document_parse: DocumentParseCandidate,
        document_parse_id: str,
        source_snapshot: PaperSummarySourceSnapshotReference,
        paper: PaperSummaryPaperMetadata,
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ParameterValue],
        evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...],
        model_revision: str | None = None,
        provider: str | None = None,
        provider_request_id: str | None = None,
        usage: PaperSummaryModelUsage | None = None,
        latency_ms: int = 0,
        parameters_version: str = SUMMARY_PARAMETERS_VERSION,
        execution_id: str | None = None,
        run_id: str | None = None,
    ) -> PaperSummaryAdmissionResult:
        """Admit one DocumentParse-backed structured summary."""
        if source_snapshot.content_hash != document_parse.content_hash:
            raise ValueError("DocumentParse and SourceSnapshot content hashes differ")
        if any(
            candidate.source_snapshot_id != source_snapshot.source_snapshot_id
            for candidate in evidence_candidates
        ):
            raise ValueError("document Evidence must use the pinned SourceSnapshot")
        prompt = self.prompt_registry.get("paper_summary")
        input_versions, input_hash, parameter_hash = (
            build_document_summary_input_identity(
                document_parse=document_parse,
                document_parse_id=document_parse_id,
                source_snapshot=source_snapshot,
                paper=paper,
                model_name=model_name,
                parameters=parameters,
                evidence_candidates=evidence_candidates,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                prompt_hash=prompt.content_hash,
                parameters_version=parameters_version,
            )
        )
        raw_response_hash = compute_canonical_payload_hash(model_response)
        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        finished_at = self._now()
        started_at = finished_at - timedelta(milliseconds=latency_ms)
        producer_fields = {
            "execution_id": execution_id or f"execution.{input_hash[7:31]}",
            "run_id": run_id,
            "producer_name": SUMMARY_PRODUCER_NAME,
            "producer_version": SUMMARY_PRODUCER_VERSION,
            "model_name": model_name,
            "model_revision": model_revision,
            "provider": provider,
            "provider_request_id": provider_request_id,
            "usage": usage,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "parameters_version": parameters_version,
            "parameters_hash": parameter_hash,
            "input_versions": input_versions,
            "input_hash": input_hash,
            "model_response_hash": raw_response_hash,
            "started_at": started_at,
            "finished_at": finished_at,
            "latency_ms": latency_ms,
        }
        try:
            decoded = json.loads(model_response)
        except (json.JSONDecodeError, TypeError):
            return _rejected(
                producer_fields=producer_fields,
                stage=PaperSummaryFailureStage.json,
                error_code="paper_summary.json_invalid",
            )
        response_hash = compute_canonical_payload_hash(decoded)
        producer_fields["model_response_hash"] = response_hash
        try:
            model_output = PaperSummaryModelOutput.model_validate(decoded)
        except ValidationError:
            return _rejected(
                producer_fields=producer_fields,
                stage=PaperSummaryFailureStage.schema,
                error_code="paper_summary.schema_invalid",
            )

        summary = _admit_evidence(
            model_output=model_output,
            input_versions=input_versions,
            paper_id=paper.paper_id,
            paper=paper,
            benchmark=None,
            evidence_candidates=evidence_candidates,
            evidence_admitter=lambda candidate: _validate_document_evidence_candidate(
                candidate=candidate,
                paper=paper,
                document_parse=document_parse,
                document_parse_id=document_parse_id,
                source_snapshot=source_snapshot,
            ),
            producer_fields=producer_fields,
            input_hash=input_hash,
            response_hash=response_hash,
        )
        return PaperSummaryAdmissionResult(
            admission_status=PaperSummaryAdmissionStatus.accepted,
            summary=summary,
            producer=summary.producer,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("summary pipeline clock must return timezone-aware datetime")
        return value


def _rejected(
    *,
    producer_fields: dict[str, Any],
    stage: PaperSummaryFailureStage,
    error_code: str,
) -> PaperSummaryAdmissionResult:
    producer = PaperSummaryProducerExecution(
        **producer_fields,
        status="rejected",
        error_code=error_code,
    )
    return PaperSummaryAdmissionResult(
        admission_status=PaperSummaryAdmissionStatus.rejected,
        failure_stage=stage,
        producer=producer,
    )


def _admit_evidence(
    *,
    model_output: PaperSummaryModelOutput,
    input_versions: PaperSummaryInputVersions,
    paper_id: str,
    paper: PaperSummaryPaperMetadata | None,
    benchmark: PaperBenchmarkReference | None,
    evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...],
    evidence_admitter: EvidenceAdmitter,
    producer_fields: dict[str, Any],
    input_hash: str,
    response_hash: str,
) -> PaperSummaryArtifactContent:
    supplied_evidence = _unique_evidence_candidates(evidence_candidates)
    retained_evidence: dict[str, PaperSummaryEvidence] = {}
    source_conflicts: dict[str, PaperSummarySourceConflict] = {}

    def admit_statement(
        statement: PaperSummaryStatementCandidate | None,
    ) -> PaperSummaryStatement | None:
        if statement is None:
            return None
        statement_evidence: list[PaperSummaryEvidence] = []
        missing_reference = False
        for evidence_id in statement.evidence_ids:
            candidate = supplied_evidence.get(evidence_id)
            if candidate is None:
                missing_reference = True
                continue
            admitted = retained_evidence.get(evidence_id)
            if admitted is None:
                admitted, conflict = evidence_admitter(candidate)
                if admitted is None:
                    missing_reference = True
                    continue
                retained_evidence[evidence_id] = admitted
                if conflict is not None:
                    source_conflicts[conflict.conflict_id] = conflict
            statement_evidence.append(admitted)
        retained_ids = tuple(item.evidence_id for item in statement_evidence)
        if not statement.evidence_ids:
            status = PaperSummarySupportStatus.unsupported
            validation_code = "evidence.not_provided"
        elif missing_reference or any(
            item.status is PaperSummarySupportStatus.unverifiable
            for item in statement_evidence
        ):
            status = PaperSummarySupportStatus.unverifiable
            validation_code = "evidence.unverifiable"
        elif any(
            item.status is PaperSummarySupportStatus.unsupported
            for item in statement_evidence
        ):
            status = PaperSummarySupportStatus.unsupported
            validation_code = "evidence.quote_not_found"
        else:
            status = PaperSummarySupportStatus.supported
            validation_code = "evidence.supported"
        return PaperSummaryStatement(
            statement_id=statement.statement_id,
            text=statement.text,
            evidence_ids=retained_ids,
            status=status,
            validation_code=validation_code,
        )

    research_goal = admit_statement(model_output.research_goal)
    method = admit_statement(model_output.method)
    dataset = admit_statement(model_output.dataset)
    findings = tuple(admit_statement(item) for item in model_output.findings)
    limitations = tuple(admit_statement(item) for item in model_output.limitations)
    future_work = tuple(admit_statement(item) for item in model_output.future_work)
    typed_findings = tuple(item for item in findings if item is not None)
    typed_limitations = tuple(item for item in limitations if item is not None)
    typed_future_work = tuple(item for item in future_work if item is not None)
    all_statements = tuple(
        item for item in (research_goal, method, dataset) if item is not None
    ) + typed_findings + typed_limitations + typed_future_work
    evidence_ids = tuple(
        sorted({evidence_id for item in all_statements for evidence_id in item.evidence_ids})
    )
    evidence = tuple(retained_evidence[item] for item in sorted(evidence_ids))
    conflicts = tuple(source_conflicts[item] for item in sorted(source_conflicts))
    summary_identity_hash = compute_canonical_payload_hash(
        {"input_hash": input_hash, "model_response_hash": response_hash}
    )
    summary_id = f"summary.{summary_identity_hash[7:31]}"
    producer = PaperSummaryProducerExecution(
        **producer_fields,
        status="completed",
        output_hash="sha256:" + "0" * 64,
    )
    producer_payload = producer.model_dump(mode="json", exclude_none=True)
    producer_payload["input_versions"] = dump_paper_summary_input_versions(
        input_versions
    )
    payload = {
        "kind": "paper_summary",
        "schema_version": "1.0.0",
        "summary_id": summary_id,
        "paper_id": paper_id,
        "paper": None if paper is None else paper.model_dump(mode="json"),
        "benchmark": None if benchmark is None else benchmark.model_dump(mode="json"),
        "input_versions": dump_paper_summary_input_versions(input_versions),
        "research_goal": _dump_optional(research_goal),
        "method": _dump_optional(method),
        "dataset": _dump_optional(dataset),
        "findings": [item.model_dump(mode="json") for item in typed_findings],
        "limitations": [item.model_dump(mode="json") for item in typed_limitations],
        "future_work": [item.model_dump(mode="json") for item in typed_future_work],
        "evidence_ids": evidence_ids,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "source_conflicts": [item.model_dump(mode="json") for item in conflicts],
        "producer": producer_payload,
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_paper_summary_output_hash(
        {key: value for key, value in payload.items() if value is not None}
    )
    payload["producer"]["output_hash"] = output_hash
    payload["output_hash"] = output_hash
    return _seal_paper_summary_for_publication(
        PaperSummaryArtifactContent.model_validate(payload)
    )


def _validate_evidence_candidate(
    *,
    candidate: PaperSummaryEvidenceCandidate,
    paper_id: str,
    collection_candidates: dict[str, PaperCollectionCandidate],
    snapshots: dict[str, PaperSummarySourceSnapshotReference],
) -> tuple[PaperSummaryEvidence | None, PaperSummarySourceConflict | None]:
    collection_candidate = collection_candidates.get(candidate.candidate_id)
    snapshot = snapshots.get(candidate.source_snapshot_id)
    if (
        collection_candidate is None
        or snapshot is None
        or candidate.paper_id != paper_id
        or collection_candidate.canonical_paper_id != paper_id
        or collection_candidate.raw.source_id != candidate.source_id
        or collection_candidate.raw.source_record_id != candidate.source_record_id
        or collection_candidate.raw.source_snapshot_id != candidate.source_snapshot_id
        or snapshot.source_id != candidate.source_id
    ):
        return None, None
    expected_source_urls = {
        _normalize_source_url(value)
        for value in (collection_candidate.raw.url, collection_candidate.url)
        if value is not None
    }
    locator_source_url = _normalize_source_url(str(candidate.locator.source_url))
    if not expected_source_urls or locator_source_url not in expected_source_urls:
        status = PaperSummarySupportStatus.unverifiable
        validation_code = "evidence.source_url_unverifiable"
    elif candidate.locator.kind == "paper_metadata":
        metadata_value = _paper_metadata_value(
            collection_candidate, candidate.locator.metadata_field
        )
        if metadata_value is None:
            status = PaperSummarySupportStatus.unverifiable
            validation_code = "evidence.metadata_unavailable"
        elif _normalize_evidence_text(candidate.quote_or_value) != (
            _normalize_evidence_text(metadata_value)
        ):
            status = PaperSummarySupportStatus.unsupported
            validation_code = "evidence.value_mismatch"
        else:
            status = PaperSummarySupportStatus.supported
            validation_code = "evidence.supported"
    elif candidate.accessible_excerpt is None:
        status = PaperSummarySupportStatus.unverifiable
        validation_code = "evidence.source_text_unavailable"
    elif _normalize_evidence_text(candidate.quote_or_value) not in (
        _normalize_evidence_text(candidate.accessible_excerpt)
    ):
        status = PaperSummarySupportStatus.unsupported
        validation_code = "evidence.quote_not_found"
    else:
        status = PaperSummarySupportStatus.supported
        validation_code = "evidence.supported"
    conflict = None
    if (
        candidate.claimed_source_version is not None
        and candidate.claimed_source_version != snapshot.source_version
    ):
        conflict = PaperSummarySourceConflict(
            conflict_id=f"conflict.{candidate.evidence_id}",
            evidence_id=candidate.evidence_id,
            source_snapshot_id=candidate.source_snapshot_id,
            claimed_source_version=candidate.claimed_source_version,
            source_snapshot_version=snapshot.source_version,
        )
    admitted = PaperSummaryEvidence(
        evidence_id=candidate.evidence_id,
        paper_id=candidate.paper_id,
        candidate_id=candidate.candidate_id,
        source_id=candidate.source_id,
        source_record_id=candidate.source_record_id,
        source_snapshot_id=candidate.source_snapshot_id,
        source_snapshot_version=snapshot.source_version,
        source_snapshot_content_hash=snapshot.content_hash,
        locator=candidate.locator,
        quote_or_value=candidate.quote_or_value,
        status=status,
        validation_code=validation_code,
    )
    return admitted, conflict


def build_document_summary_input_identity(
    *,
    document_parse: DocumentParseCandidate,
    document_parse_id: str,
    source_snapshot: PaperSummarySourceSnapshotReference,
    paper: PaperSummaryPaperMetadata,
    model_name: str,
    parameters: Mapping[str, ParameterValue],
    evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...],
    prompt_name: str,
    prompt_version: str,
    prompt_hash: str,
    parameters_version: str = SUMMARY_PARAMETERS_VERSION,
) -> tuple[PaperSummaryInputVersions, str, str]:
    """Build the exact immutable identity before an external model call."""

    safe_parameters = _validate_parameters(parameters)
    parameter_hash = compute_canonical_payload_hash(
        {
            "parameters_version": parameters_version,
            "parameters": safe_parameters,
        }
    )
    input_versions = PaperSummaryInputVersions(
        document_parses=(
            PaperSummaryDocumentParseReference(
                document_parse_id=document_parse_id,
                candidate_parse_id=document_parse.parse_id,
                research_input_id=document_parse.research_input_id,
                source_snapshot_id=source_snapshot.source_snapshot_id,
                input_content_hash=document_parse.content_hash,
                canonical_output_hash=document_parse.canonical_output_hash,
                parser_profile_id=document_parse.profile.parser_profile_id,
                parser_profile_version=document_parse.profile.parser_profile_version,
                config_hash=document_parse.config_hash,
            ),
        ),
        source_snapshots=(source_snapshot,),
    )
    evidence_input_hash = compute_canonical_payload_hash(
        [
            candidate.model_dump(mode="json", exclude_none=True)
            for candidate in sorted(
                evidence_candidates, key=lambda item: item.evidence_id
            )
        ]
    )
    input_hash = compute_canonical_payload_hash(
        {
            "input_versions": dump_paper_summary_input_versions(input_versions),
            "paper": paper.model_dump(mode="json"),
            "evidence_input_hash": evidence_input_hash,
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "model_name": model_name,
            "parameters_version": parameters_version,
            "parameters_hash": parameter_hash,
        }
    )
    return input_versions, input_hash, parameter_hash


def build_document_evidence_candidates(
    *,
    document_parse: DocumentParseCandidate,
    document_parse_id: str,
    paper_id: str,
    source_id: str,
    source_record_id: str,
    source_snapshot_id: str,
    max_quote_characters: int = 8_000,
) -> tuple[PaperSummaryEvidenceCandidate, ...]:
    """Project usable canonical blocks into bounded model-selectable Evidence."""
    if not 256 <= max_quote_characters <= 16_000:
        raise ValueError("max_quote_characters must be between 256 and 16000")
    candidates: list[PaperSummaryEvidenceCandidate] = []
    section: str | None = None
    paragraph = 0
    for block in document_parse.blocks:
        if block.kind is DocumentBlockKind.heading and block.text:
            section = block.text[:512]
        if (
            block.kind is DocumentBlockKind.reference
            or block.text is None
            or block.quality is DocumentParseQuality.unsupported
        ):
            continue
        paragraph += 1
        for start in range(0, len(block.text), max_quote_characters):
            end = min(len(block.text), start + max_quote_characters)
            quote = block.text[start:end]
            locator = DocumentLocator(
                page_index=block.page_index,
                block_id=block.block_id,
                bbox=block.bbox,
                reading_order=block.reading_order,
                text_span=TextSpan(start=start, end=end),
            )
            identity_hash = compute_canonical_payload_hash(
                {
                    "document_parse_id": document_parse_id,
                    "canonical_output_hash": document_parse.canonical_output_hash,
                    "block_id": block.block_id,
                    "text_span": {"start": start, "end": end},
                    "quote": quote,
                }
            )
            candidates.append(
                PaperSummaryEvidenceCandidate(
                    evidence_id=f"evidence.{identity_hash[7:31]}",
                    paper_id=paper_id,
                    candidate_id=document_parse.research_input_id,
                    source_id=source_id,
                    source_record_id=source_record_id,
                    source_snapshot_id=source_snapshot_id,
                    locator=PaperSummaryEvidenceLocator(
                        kind="paper_text",
                        section=section or "document",
                        paragraph=paragraph,
                        text_range=f"{start}:{end}",
                        document_parse_id=document_parse_id,
                        document_parse_output_hash=(
                            document_parse.canonical_output_hash
                        ),
                        document_locator=locator,
                        page_index=block.page_index,
                    ),
                    quote_or_value=quote,
                    accessible_excerpt=quote,
                )
            )
    return tuple(candidates)


def _validate_document_evidence_candidate(
    *,
    candidate: PaperSummaryEvidenceCandidate,
    paper: PaperSummaryPaperMetadata,
    document_parse: DocumentParseCandidate,
    document_parse_id: str,
    source_snapshot: PaperSummarySourceSnapshotReference,
) -> tuple[PaperSummaryEvidence | None, PaperSummarySourceConflict | None]:
    locator = candidate.locator
    document_locator = locator.document_locator
    if (
        candidate.paper_id != paper.paper_id
        or candidate.candidate_id != document_parse.research_input_id
        or candidate.source_snapshot_id != source_snapshot.source_snapshot_id
        or candidate.source_id != source_snapshot.source_id
        or locator.kind != "paper_text"
        or locator.document_parse_id != document_parse_id
        or locator.document_parse_output_hash != document_parse.canonical_output_hash
        or document_locator is None
    ):
        return None, None
    try:
        validate_document_locator(document_parse, document_locator)
    except DocumentParseIntegrityError:
        return None, None
    block = next(
        (
            item
            for item in document_parse.blocks
            if item.block_id == document_locator.block_id
        ),
        None,
    )
    if block is None or block.text is None or document_locator.text_span is None:
        return None, None
    span = document_locator.text_span
    expected_quote = block.text[span.start : span.end]
    if (
        expected_quote != candidate.quote_or_value
        or candidate.accessible_excerpt != expected_quote
    ):
        status = PaperSummarySupportStatus.unsupported
        validation_code = "evidence.quote_not_found"
    elif block.quality is DocumentParseQuality.accepted:
        status = PaperSummarySupportStatus.supported
        validation_code = "evidence.supported"
    else:
        status = PaperSummarySupportStatus.unverifiable
        validation_code = "evidence.parse_partial"
    conflict = None
    if (
        candidate.claimed_source_version is not None
        and candidate.claimed_source_version != source_snapshot.source_version
    ):
        conflict = PaperSummarySourceConflict(
            conflict_id=f"conflict.{candidate.evidence_id}",
            evidence_id=candidate.evidence_id,
            source_snapshot_id=source_snapshot.source_snapshot_id,
            claimed_source_version=candidate.claimed_source_version,
            source_snapshot_version=source_snapshot.source_version,
        )
    admitted = PaperSummaryEvidence(
        evidence_id=candidate.evidence_id,
        paper_id=candidate.paper_id,
        candidate_id=candidate.candidate_id,
        source_id=candidate.source_id,
        source_record_id=candidate.source_record_id,
        source_snapshot_id=candidate.source_snapshot_id,
        source_snapshot_version=source_snapshot.source_version,
        source_snapshot_content_hash=source_snapshot.content_hash,
        locator=locator,
        quote_or_value=candidate.quote_or_value,
        status=status,
        validation_code=validation_code,
    )
    return admitted, conflict


def _input_versions(
    *, paper_collection: PaperCollection, paper_collection_version_id: str
) -> PaperSummaryInputVersions:
    snapshots = tuple(
        PaperSummarySourceSnapshotReference(
            source_snapshot_id=snapshot.snapshot_id,
            source_id=snapshot.source_id,
            source_version=(
                snapshot.source_version_or_etag
                or snapshot.cache_version
                or snapshot.content_hash
            ),
            content_hash=snapshot.content_hash,
        )
        for snapshot in sorted(
            paper_collection.source_snapshots, key=lambda item: item.snapshot_id
        )
    )
    return PaperSummaryInputVersions(
        paper_collection_version_id=paper_collection_version_id,
        paper_collection_schema_version=paper_collection.schema_version,
        paper_collection_output_hash=paper_collection.output_hash,
        source_snapshots=snapshots,
    )


def _validate_parameters(
    parameters: Mapping[str, ParameterValue],
) -> dict[str, ParameterValue]:
    if not 1 <= len(parameters) <= 32:
        raise ValueError("model parameters must contain between 1 and 32 entries")
    result: dict[str, ParameterValue] = {}
    for key, value in parameters.items():
        normalized_key = key.casefold()
        if (
            not _SAFE_PARAMETER_KEY.fullmatch(key)
            or any(fragment in normalized_key for fragment in _FORBIDDEN_PARAMETER_FRAGMENTS)
        ):
            raise ValueError("model parameters contain forbidden or invalid keys")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("model parameter string is too long")
        result[key] = value
    return dict(sorted(result.items()))


def _unique_evidence_candidates(
    candidates: tuple[PaperSummaryEvidenceCandidate, ...],
) -> dict[str, PaperSummaryEvidenceCandidate]:
    result: dict[str, PaperSummaryEvidenceCandidate] = {}
    for candidate in candidates:
        if candidate.evidence_id in result:
            raise ValueError(f"duplicate Evidence candidate: {candidate.evidence_id}")
        result[candidate.evidence_id] = candidate
    return result


def _normalize_evidence_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_source_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def _paper_metadata_value(
    candidate: PaperCollectionCandidate, metadata_field: str | None
) -> str | None:
    if metadata_field is None:
        return None
    value = getattr(candidate.raw, metadata_field)
    if value is None:
        return None
    if isinstance(value, tuple):
        return ", ".join(value)
    return str(value)


def _dump_optional(value: PaperSummaryStatement | None) -> dict[str, Any] | None:
    return None if value is None else value.model_dump(mode="json")
