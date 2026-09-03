"""Literature-claim extraction and deterministic admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any
import unicodedata

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import (
    LiteratureClaimAdmissionResult,
    LiteratureClaimCandidate,
    LiteratureClaimEvidenceReference,
    LiteratureClaimExtractionOutput,
    LiteratureClaimFailureStage,
    LiteratureClaimInputVersions,
    LiteratureClaimModelCandidate,
    LiteratureClaimRejectionReason,
    LiteratureClaimsCandidate,
    LiteratureClaimStatus,
    LiteratureClaimStatusCounts,
    _seal_literature_claims_for_publication,
    compute_literature_claim_admission_output_hash,
    compute_literature_claim_fingerprint,
    compute_literature_claims_output_hash,
)
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryEvidence,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
)
from packages.prompts.registry import PromptRegistry

from .constants import (
    CLAIM_NORMALIZATION_VERSION,
    CLAIM_PARAMETERS_VERSION,
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    CLAIM_SCHEMA_VERSION,
)
from .summary import ParameterValue, _validate_parameters


Clock = Callable[[], datetime]
SUPPORTED_SUMMARY_SCHEMA_VERSIONS = frozenset({"2.0.0"})
_WHITESPACE = re.compile(r"\s+")
_NEGATION = re.compile(
    r"(?:\b(?:cannot|never|neither|no|nor|not|without)\b|不|无|未|否)",
    re.IGNORECASE,
)
_AMBIGUOUS_UNIT = re.compile(
    r"(?:\b(?:either|or|unknown)\b|[?≈~]|->|→)",
    re.IGNORECASE,
)
_UNIT_ALIASES = {
    "kelvin": "K",
    "percent": "%",
    "percentage": "%",
    "solar mass": "M_sun",
    "solar masses": "M_sun",
    "solar radius": "R_sun",
    "solar radii": "R_sun",
}


@dataclass(frozen=True, slots=True)
class PaperSummaryArtifactVersionInput:
    """Repository-port value for one already validated PaperSummary version."""

    artifact_version_id: str
    schema_version: str
    content: PaperSummaryArtifactContent


def build_literature_claim_input_identity(
    *,
    paper_summary_artifact_version_id: str,
    paper_id: str,
    paper_summary_versions: Mapping[str, PaperSummaryArtifactVersionInput],
    model_name: str,
    parameters: Mapping[str, ParameterValue],
    parameters_version: str = CLAIM_PARAMETERS_VERSION,
    prompt_registry: PromptRegistry | None = None,
) -> tuple[LiteratureClaimInputVersions, str, str]:
    """Build the parent Claim execution identity before any provider call."""

    prompts = prompt_registry or PromptRegistry()
    prompt = prompts.get("literature_claim")
    safe_parameters = _validate_parameters(parameters)
    parameters_hash = compute_canonical_payload_hash(
        {
            "parameters_version": parameters_version,
            "parameters": safe_parameters,
        }
    )
    summary_version = paper_summary_versions.get(paper_summary_artifact_version_id)
    input_versions = _input_versions(
        requested_version_id=paper_summary_artifact_version_id,
        requested_paper_id=paper_id,
        summary_version=summary_version,
    )
    input_hash = compute_canonical_payload_hash(
        {
            "input_versions": input_versions.model_dump(mode="json", exclude_none=True),
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "model_name": model_name,
            "parameters_version": parameters_version,
            "parameters_hash": parameters_hash,
            "producer_version": CLAIM_PRODUCER_VERSION,
            "schema_version": CLAIM_SCHEMA_VERSION,
            "normalization_version": CLAIM_NORMALIZATION_VERSION,
        }
    )
    return input_versions, input_hash, parameters_hash


class LiteratureClaimPipeline:
    """Admit Claim model output without publishing or advancing ResearchRun."""

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
        paper_summary_artifact_version_id: str,
        paper_id: str,
        paper_summary_versions: Mapping[str, PaperSummaryArtifactVersionInput],
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ParameterValue],
        parameters_version: str = CLAIM_PARAMETERS_VERSION,
        execution_id: str | None = None,
        run_id: str | None = None,
        available_evidence_ids: frozenset[str] | None = None,
        available_source_snapshot_ids: frozenset[str] | None = None,
        existing_claim_fingerprints: frozenset[str] = frozenset(),
    ) -> LiteratureClaimAdmissionResult:
        prompt = self.prompt_registry.get("literature_claim")
        summary_version = paper_summary_versions.get(paper_summary_artifact_version_id)
        input_versions, input_hash, parameters_hash = (
            build_literature_claim_input_identity(
                paper_summary_artifact_version_id=(paper_summary_artifact_version_id),
                paper_id=paper_id,
                paper_summary_versions=paper_summary_versions,
                model_name=model_name,
                parameters=parameters,
                parameters_version=parameters_version,
                prompt_registry=self.prompt_registry,
            )
        )
        raw_response_hash = compute_canonical_payload_hash(model_response)
        now = self._now()
        stable_execution_id = execution_id or f"execution.{input_hash[7:31]}"
        producer_fields: dict[str, Any] = {
            "execution_id": stable_execution_id,
            "run_id": run_id,
            "step_key": "reasoning_literature",
            "producer_type": "model",
            "producer_name": CLAIM_PRODUCER_NAME,
            "producer_version": CLAIM_PRODUCER_VERSION,
            "model_name": model_name,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "schema_version": CLAIM_SCHEMA_VERSION,
            "parameters_version": parameters_version,
            "parameters_hash": parameters_hash,
            "input_versions": input_versions,
            "input_hash": input_hash,
            "model_response_hash": raw_response_hash,
            "started_at": now,
            "finished_at": now,
            "latency_ms": 0,
        }
        try:
            decoded = json.loads(model_response)
        except (json.JSONDecodeError, TypeError):
            return _fatal_rejection(
                producer_fields=producer_fields,
                stage=LiteratureClaimFailureStage.json,
                reason=LiteratureClaimRejectionReason.invalid_json,
            )
        response_hash = compute_canonical_payload_hash(decoded)
        producer_fields["model_response_hash"] = response_hash
        try:
            extraction = LiteratureClaimExtractionOutput.model_validate(decoded)
        except ValidationError:
            return _fatal_rejection(
                producer_fields=producer_fields,
                stage=LiteratureClaimFailureStage.schema,
                reason=LiteratureClaimRejectionReason.schema_invalid,
            )
        response_hash = compute_canonical_payload_hash(
            {
                "schema_version": extraction.schema_version,
                "claims": sorted(
                    (_canonical_response_candidate(item) for item in extraction.claims),
                    key=compute_canonical_payload_hash,
                ),
            }
        )
        producer_fields["model_response_hash"] = response_hash

        records, evidence, evidence_references = _admit_claims(
            extraction=extraction,
            summary_version=summary_version,
            requested_summary_version_id=paper_summary_artifact_version_id,
            requested_paper_id=paper_id,
            input_versions=input_versions,
            producer_execution_id=stable_execution_id,
            input_hash=input_hash,
            response_hash=response_hash,
            available_evidence_ids=available_evidence_ids,
            available_source_snapshot_ids=available_source_snapshot_ids,
            existing_claim_fingerprints=existing_claim_fingerprints,
        )
        status = _aggregate_status(records)
        producer_payload = {
            **producer_fields,
            "output_hash": "sha256:" + "0" * 64,
            "status": "completed",
        }
        evidence_ids = tuple(sorted({item.evidence_id for item in evidence_references}))
        snapshot_ids = tuple(
            sorted({item.source_snapshot_id for item in evidence_references})
        )
        candidate_payload = {
            "kind": "literature_claims",
            "schema_version": CLAIM_SCHEMA_VERSION,
            "input_versions": input_versions.model_dump(mode="json", exclude_none=True),
            "claims": [
                item.model_dump(mode="json", exclude_none=True) for item in records
            ],
            "evidence": [
                item.model_dump(mode="json", exclude_none=True) for item in evidence
            ],
            "evidence_references": [
                item.model_dump(mode="json", exclude_none=True)
                for item in evidence_references
            ],
            "evidence_ids": evidence_ids,
            "source_snapshot_ids": snapshot_ids,
            "status_counts": _status_counts(records).model_dump(mode="json"),
            "producer": producer_payload,
            "input_hash": input_hash,
            "output_hash": "sha256:" + "0" * 64,
        }
        output_hash = compute_literature_claims_output_hash(candidate_payload)
        producer_payload["output_hash"] = output_hash
        candidate_payload["output_hash"] = output_hash
        candidate = _seal_literature_claims_for_publication(
            LiteratureClaimsCandidate.model_validate(candidate_payload)
        )
        return LiteratureClaimAdmissionResult(
            admission_status=status,
            records=records,
            publisher_candidate=candidate,
            producer=candidate.producer,
            output_hash=output_hash,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Claim pipeline clock must return timezone-aware datetime")
        return value


def _fatal_rejection(
    *,
    producer_fields: dict[str, Any],
    stage: LiteratureClaimFailureStage,
    reason: LiteratureClaimRejectionReason,
) -> LiteratureClaimAdmissionResult:
    producer_payload = {
        **producer_fields,
        "output_hash": "sha256:" + "0" * 64,
        "status": "rejected",
        "error_code": reason,
    }
    result_payload = {
        "admission_status": LiteratureClaimStatus.rejected,
        "failure_stage": stage,
        "rejection_reason": reason,
        "records": [],
        "producer": producer_payload,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_literature_claim_admission_output_hash(result_payload)
    producer_payload["output_hash"] = output_hash
    result_payload["output_hash"] = output_hash
    return LiteratureClaimAdmissionResult.model_validate(result_payload)


def _admit_claims(
    *,
    extraction: LiteratureClaimExtractionOutput,
    summary_version: PaperSummaryArtifactVersionInput | None,
    requested_summary_version_id: str,
    requested_paper_id: str,
    input_versions: LiteratureClaimInputVersions,
    producer_execution_id: str,
    input_hash: str,
    response_hash: str,
    available_evidence_ids: frozenset[str] | None,
    available_source_snapshot_ids: frozenset[str] | None,
    existing_claim_fingerprints: frozenset[str],
) -> tuple[
    tuple[LiteratureClaimCandidate, ...],
    tuple[PaperSummaryEvidence, ...],
    tuple[LiteratureClaimEvidenceReference, ...],
]:
    summary = None if summary_version is None else summary_version.content
    summary_evidence = (
        {} if summary is None else {item.evidence_id: item for item in summary.evidence}
    )
    summary_snapshots = (
        {}
        if summary is None
        else {
            item.source_snapshot_id: item
            for item in summary.input_versions.source_snapshots
        }
    )
    evidence_exists = (
        frozenset(summary_evidence)
        if available_evidence_ids is None
        else available_evidence_ids
    )
    snapshot_exists = (
        frozenset(summary_snapshots)
        if available_source_snapshot_ids is None
        else available_source_snapshot_ids
    )
    statements = (
        {}
        if summary is None
        else {item.statement_id: item for item in summary.statements()}
    )
    ordered = tuple(
        sorted(
            extraction.claims,
            key=lambda item: compute_canonical_payload_hash(
                item.model_dump(mode="json", exclude_none=True)
            ),
        )
    )
    seen = set(existing_claim_fingerprints)
    records: list[LiteratureClaimCandidate] = []
    retained_evidence: dict[str, PaperSummaryEvidence] = {}
    retained_references: dict[tuple[str, str], LiteratureClaimEvidenceReference] = {}
    occurrence_by_fingerprint: dict[str, int] = {}
    for model_candidate in ordered:
        normalized, normalization_safe = _normalize_candidate(model_candidate)
        provisional = normalized or _candidate_payload(model_candidate)
        fingerprint = compute_literature_claim_fingerprint(provisional)
        occurrence_index = occurrence_by_fingerprint.get(fingerprint, 0)
        occurrence_by_fingerprint[fingerprint] = occurrence_index + 1
        claim_identity_hash = compute_canonical_payload_hash(
            {
                "paper_summary_artifact_version_id": (
                    input_versions.paper_summary_artifact_version_id
                ),
                "fingerprint": fingerprint,
                "occurrence_index": occurrence_index,
            }
        )
        claim_id = f"claim.{claim_identity_hash[7:31]}"
        stage: LiteratureClaimFailureStage | None = None
        reason: LiteratureClaimRejectionReason | None = None
        evidence = tuple(
            item
            for evidence_id in model_candidate.evidence_ids
            if (item := summary_evidence.get(evidence_id)) is not None
        )
        snapshots = tuple(
            sorted(
                {
                    item.source_snapshot_id
                    for item in evidence
                    if item.source_snapshot_id in snapshot_exists
                }
            )
        )

        if summary_version is None:
            stage = LiteratureClaimFailureStage.input
            reason = LiteratureClaimRejectionReason.input_artifact_version_unknown
        elif summary_version.schema_version not in SUPPORTED_SUMMARY_SCHEMA_VERSIONS:
            stage = LiteratureClaimFailureStage.input
            reason = LiteratureClaimRejectionReason.input_schema_version_unsupported
        elif not model_candidate.evidence_ids:
            stage = LiteratureClaimFailureStage.evidence
            reason = LiteratureClaimRejectionReason.evidence_missing
        elif any(
            evidence_id not in summary_evidence or evidence_id not in evidence_exists
            for evidence_id in model_candidate.evidence_ids
        ):
            stage = LiteratureClaimFailureStage.evidence
            reason = LiteratureClaimRejectionReason.evidence_not_found
        elif any(
            item.source_snapshot_id not in summary_snapshots
            or item.source_snapshot_id not in snapshot_exists
            for item in evidence
        ):
            stage = LiteratureClaimFailureStage.evidence
            reason = LiteratureClaimRejectionReason.source_snapshot_not_found
        else:
            statement = statements.get(model_candidate.source_statement_id)
            if (
                summary_version.artifact_version_id != requested_summary_version_id
                or not _ownership_matches(
                    summary=summary,
                    requested_paper_id=requested_paper_id,
                    statement=statement,
                    evidence=evidence,
                    evidence_ids=model_candidate.evidence_ids,
                    snapshots=summary_snapshots,
                )
            ):
                stage = LiteratureClaimFailureStage.ownership
                reason = LiteratureClaimRejectionReason.ownership_mismatch
            elif not normalization_safe:
                stage = LiteratureClaimFailureStage.normalization
                reason = LiteratureClaimRejectionReason.normalization_unsafe
            elif fingerprint in seen:
                stage = LiteratureClaimFailureStage.duplicate
                reason = LiteratureClaimRejectionReason.duplicate_claim

        if reason is not None:
            status = LiteratureClaimStatus.rejected
        elif any(
            item.status is not PaperSummarySupportStatus.supported for item in evidence
        ):
            status = LiteratureClaimStatus.candidate
        else:
            status = LiteratureClaimStatus.accepted
        if reason is None:
            seen.add(fingerprint)

        record_payload = {
            "claim_id": claim_id,
            "source_statement_id": model_candidate.source_statement_id,
            "paper_id": requested_paper_id,
            "source_paper_summary_artifact_version_id": (
                input_versions.paper_summary_artifact_version_id
            ),
            "source_summary_id": input_versions.summary_id,
            **provisional,
            "evidence_ids": tuple(sorted(model_candidate.evidence_ids)),
            "source_snapshot_ids": snapshots,
            "normalization_version": CLAIM_NORMALIZATION_VERSION,
            "fingerprint": fingerprint,
            "status": status,
            "failure_stage": stage,
            "rejection_reason": reason,
            "producer_execution_id": producer_execution_id,
            "input_hash": input_hash,
            "model_response_hash": response_hash,
        }
        record = LiteratureClaimCandidate.model_validate(record_payload)
        records.append(record)
        if summary is None:
            continue
        for item in evidence:
            if item.evidence_id not in evidence_exists:
                continue
            snapshot = summary_snapshots.get(item.source_snapshot_id)
            if (
                snapshot is None
                or item.source_snapshot_id not in snapshot_exists
                or item.paper_id != record.paper_id
            ):
                continue
            retained_evidence[item.evidence_id] = item
            retained_references[(claim_id, item.evidence_id)] = (
                LiteratureClaimEvidenceReference(
                    claim_id=claim_id,
                    evidence_id=item.evidence_id,
                    summary_statement_id=model_candidate.source_statement_id,
                    paper_id=item.paper_id,
                    source_snapshot_id=item.source_snapshot_id,
                    source_snapshot_version=item.source_snapshot_version,
                    source_snapshot_content_hash=item.source_snapshot_content_hash,
                    status=item.status,
                    validation_code=item.validation_code,
                )
            )
    return (
        tuple(records),
        tuple(retained_evidence[key] for key in sorted(retained_evidence)),
        tuple(retained_references[key] for key in sorted(retained_references)),
    )


def _input_versions(
    *,
    requested_version_id: str,
    requested_paper_id: str,
    summary_version: PaperSummaryArtifactVersionInput | None,
) -> LiteratureClaimInputVersions:
    if summary_version is None:
        return LiteratureClaimInputVersions(
            paper_summary_artifact_version_id=requested_version_id,
            paper_summary_schema_version=None,
            paper_summary_output_hash=None,
            summary_id=None,
            paper_id=requested_paper_id,
            source_snapshots=(),
        )
    summary = summary_version.content
    return LiteratureClaimInputVersions(
        paper_summary_artifact_version_id=requested_version_id,
        paper_summary_schema_version=summary_version.schema_version,
        paper_summary_output_hash=summary.output_hash,
        summary_id=summary.summary_id,
        paper_id=requested_paper_id,
        source_snapshots=summary.input_versions.source_snapshots,
    )


def _ownership_matches(
    *,
    summary: PaperSummaryArtifactContent | None,
    requested_paper_id: str,
    statement: PaperSummaryStatement | None,
    evidence: tuple[PaperSummaryEvidence, ...],
    evidence_ids: tuple[str, ...],
    snapshots: Mapping[str, PaperSummarySourceSnapshotReference],
) -> bool:
    if (
        summary is None
        or statement is None
        or summary.paper_id != requested_paper_id
        or any(item not in statement.evidence_ids for item in evidence_ids)
    ):
        return False
    for item in evidence:
        snapshot = snapshots.get(item.source_snapshot_id)
        if (
            item.paper_id != summary.paper_id
            or snapshot is None
            or item.source_id != snapshot.source_id
            or item.source_snapshot_version != snapshot.source_version
            or item.source_snapshot_content_hash != snapshot.content_hash
        ):
            return False
    return True


def _normalize_candidate(
    candidate: LiteratureClaimModelCandidate,
) -> tuple[dict[str, Any] | None, bool]:
    payload = _candidate_payload(candidate)
    unit = payload["unit"]
    if unit is not None:
        if _AMBIGUOUS_UNIT.search(unit):
            return None, False
        payload["unit"] = _UNIT_ALIASES.get(unit.casefold(), unit)
    objects = payload["objects"]
    if len(objects) > 1 and payload["comparison_basis"] is None:
        return None, False
    if len(objects) != len(set(item.casefold() for item in objects)):
        return None, False
    for field in ("conditions", "scope", "limitations", "qualifiers"):
        values = payload[field]
        if len(values) != len(set(item.casefold() for item in values)):
            return None, False
    if _NEGATION.search(payload["text"]) and not _NEGATION.search(
        payload["normalized_text"]
    ):
        return None, False
    return payload, True


def _candidate_payload(candidate: LiteratureClaimModelCandidate) -> dict[str, Any]:
    return {
        "text": _normalize_display_text(candidate.text),
        "normalized_text": _normalize_display_text(candidate.normalized_text),
        "claim_type": candidate.claim_type,
        "polarity": candidate.polarity,
        "objects": tuple(
            sorted(
                (_normalize_display_text(item) for item in candidate.objects),
                key=str.casefold,
            )
        ),
        "metric": _normalize_optional(candidate.metric),
        "unit": _normalize_optional(candidate.unit),
        "conditions": _normalized_set(candidate.conditions),
        "scope": _normalized_set(candidate.scope),
        "limitations": _normalized_set(candidate.limitations),
        "qualifiers": _normalized_set(candidate.qualifiers),
        "uncertainty": _normalize_optional(candidate.uncertainty),
        "comparison_basis": _normalize_optional(candidate.comparison_basis),
    }


def _normalize_display_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _normalize_optional(value: str | None) -> str | None:
    return None if value is None else _normalize_display_text(value)


def _normalized_set(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            (_normalize_display_text(item) for item in values),
            key=str.casefold,
        )
    )


def _canonical_response_candidate(
    candidate: LiteratureClaimModelCandidate,
) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    for field in ("objects", "conditions", "scope", "limitations", "qualifiers"):
        payload[field] = sorted(payload[field], key=str.casefold)
    payload["evidence_ids"] = sorted(payload["evidence_ids"])
    return payload


def _aggregate_status(
    records: tuple[LiteratureClaimCandidate, ...],
) -> LiteratureClaimStatus:
    if any(item.status is LiteratureClaimStatus.accepted for item in records):
        return LiteratureClaimStatus.accepted
    if any(item.status is LiteratureClaimStatus.candidate for item in records):
        return LiteratureClaimStatus.candidate
    return LiteratureClaimStatus.rejected


def _status_counts(
    records: tuple[LiteratureClaimCandidate, ...],
) -> LiteratureClaimStatusCounts:
    return LiteratureClaimStatusCounts(
        accepted=sum(item.status is LiteratureClaimStatus.accepted for item in records),
        candidate=sum(
            item.status is LiteratureClaimStatus.candidate for item in records
        ),
        rejected=sum(item.status is LiteratureClaimStatus.rejected for item in records),
    )
