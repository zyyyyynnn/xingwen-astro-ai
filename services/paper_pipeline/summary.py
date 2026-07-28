"""D-03 PaperSummary admission over D-02 PaperCollection provenance."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection import PaperCollection, PaperCollectionCandidate
from app.schemas.paper_summary import (
    PaperSummaryAdmissionResult,
    PaperSummaryAdmissionStatus,
    PaperSummaryArtifactContent,
    PaperSummaryEvidence,
    PaperSummaryEvidenceCandidate,
    PaperSummaryFailureStage,
    PaperSummaryInputVersions,
    PaperSummaryModelOutput,
    PaperSummaryProducerExecution,
    PaperSummarySourceConflict,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummaryStatementCandidate,
    PaperSummarySupportStatus,
    compute_paper_summary_output_hash,
)
from packages.prompts.registry import PromptRegistry

from .constants import (
    SUMMARY_PARAMETERS_VERSION,
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)


Clock = Callable[[], datetime]
ParameterValue = str | int | float | bool | None
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
        prompt_version: str | None = None,
        parameters_version: str = SUMMARY_PARAMETERS_VERSION,
        execution_id: str | None = None,
        run_id: str | None = None,
    ) -> PaperSummaryAdmissionResult:
        prompt = self.prompt_registry.get("paper_summary", prompt_version)
        if prompt.status == "disabled":
            raise ValueError("disabled Prompt version cannot be executed")
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
        evidence_input_hash = compute_canonical_payload_hash(
            [
                candidate.model_dump(mode="json", exclude_none=True)
                for candidate in evidence_candidates
            ]
        )
        input_hash = compute_canonical_payload_hash(
            {
                "paper_collection_version_id": paper_collection_version_id,
                "paper_collection_schema_version": paper_collection.schema_version,
                "paper_collection_output_hash": paper_collection.output_hash,
                "source_snapshot_versions": input_versions.model_dump(
                    mode="json", exclude_none=True
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
            paper_collection=paper_collection,
            input_versions=input_versions,
            paper_id=paper_id,
            evidence_candidates=evidence_candidates,
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
    paper_collection: PaperCollection,
    input_versions: PaperSummaryInputVersions,
    paper_id: str,
    evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...],
    producer_fields: dict[str, Any],
    input_hash: str,
    response_hash: str,
) -> PaperSummaryArtifactContent:
    candidates_by_id = {
        candidate.candidate_id: candidate for candidate in paper_collection.candidates
    }
    snapshots_by_id = {
        snapshot.source_snapshot_id: snapshot
        for snapshot in input_versions.source_snapshots
    }
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
                admitted, conflict = _validate_evidence_candidate(
                    candidate=candidate,
                    paper_id=paper_id,
                    collection_candidates=candidates_by_id,
                    snapshots=snapshots_by_id,
                )
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
    payload = {
        "kind": "paper_summary",
        "schema_version": "1.0.0",
        "summary_id": summary_id,
        "paper_id": paper_id,
        "benchmark": paper_collection.benchmark.model_dump(mode="json"),
        "input_versions": input_versions.model_dump(mode="json"),
        "research_goal": _dump_optional(research_goal),
        "method": _dump_optional(method),
        "dataset": _dump_optional(dataset),
        "findings": [item.model_dump(mode="json") for item in typed_findings],
        "limitations": [item.model_dump(mode="json") for item in typed_limitations],
        "future_work": [item.model_dump(mode="json") for item in typed_future_work],
        "evidence_ids": evidence_ids,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "source_conflicts": [item.model_dump(mode="json") for item in conflicts],
        "producer": producer.model_dump(mode="json", exclude_none=True),
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_paper_summary_output_hash(
        {key: value for key, value in payload.items() if value is not None}
    )
    payload["producer"]["output_hash"] = output_hash
    payload["output_hash"] = output_hash
    return PaperSummaryArtifactContent.model_validate(payload)


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
    if candidate.accessible_excerpt is None:
        status = PaperSummarySupportStatus.unverifiable
        validation_code = "evidence.source_text_unavailable"
    elif _normalize_evidence_text(candidate.quote_or_value) not in _normalize_evidence_text(
        candidate.accessible_excerpt
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


def _dump_optional(value: PaperSummaryStatement | None) -> dict[str, Any] | None:
    return None if value is None else value.model_dump(mode="json")
