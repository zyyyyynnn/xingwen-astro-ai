"""D-08 LiteratureRelation classification and deterministic admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from typing import Any

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import (
    LiteratureClaimCandidate,
    LiteratureClaimStatus,
    LiteratureClaimsCandidate,
)
from app.schemas.literature_relation import (
    LiteratureClaimArtifactVersionReference,
    LiteratureComparabilityStatus,
    LiteratureReasoningTraceCandidate,
    LiteratureReasoningTraceStepCandidate,
    LiteratureRelationAdmissionResult,
    LiteratureRelationCandidate,
    LiteratureRelationConfidenceAssessment,
    LiteratureRelationConfidenceSubject,
    LiteratureRelationConfidenceStatus,
    LiteratureRelationEvidenceReference,
    LiteratureRelationExtractionOutput,
    LiteratureRelationFailureStage,
    LiteratureRelationInputVersions,
    LiteratureRelationModelCandidate,
    LiteratureRelationRejectionReason,
    LiteratureRelationReviewReason,
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
    LiteratureRelationStatusCounts,
    LiteratureTraceOperation,
    build_literature_relation_confidence_subject,
    compute_literature_relation_admission_output_hash,
    compute_literature_relation_fingerprint,
    compute_literature_relations_output_hash,
    compute_literature_relations_public_payload_hash,
)
from app.schemas._literature_relation_seal import (
    LiteratureRelationAdmissionSnapshot,
    _bind_literature_relation_pipeline_authority,
)
from app.schemas.paper_summary import PaperSummaryEvidence
from packages.prompts.registry import PromptRegistry

from .constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
    RELATION_COMPARISON_POLICY_VERSION,
    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD,
    RELATION_CONFIDENCE_APPLICABILITY_SCOPE,
    RELATION_CONFIDENCE_CALIBRATION_ID,
    RELATION_CONFIDENCE_CALIBRATION_METHOD,
    RELATION_CONFIDENCE_CALIBRATION_VERSION,
    RELATION_CONFIDENCE_DEFINITION_ID,
    RELATION_CONFIDENCE_DEFINITION_VERSION,
    RELATION_PAIRING_VERSION,
    RELATION_PARAMETERS_VERSION,
    RELATION_PRODUCER_NAME,
    RELATION_PRODUCER_VERSION,
    RELATION_SCHEMA_VERSION,
    RELATION_TRACE_PROTOCOL_VERSION,
)
from .summary import ParameterValue, _validate_parameters


Clock = Callable[[], datetime]
SUPPORTED_CLAIM_SCHEMA_VERSIONS = frozenset({"1.0.0"})
RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE = 4
_ZERO_HASH = "sha256:" + "0" * 64
_UNSAFE_TRACE = re.compile(
    r"(?:chain[- ]of[- ]thought|private reasoning|hidden (?:system |developer )?prompt|"
    r"system prompt|developer prompt|token[- ]by[- ]token|raw model output|"
    r"api[-_ ]?key|password|credential|私有思维链|隐藏提示词|逐.?token|凭据|密码)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class LiteratureClaimsArtifactVersionInput:
    """Repository-port value for one immutable D-07 ArtifactVersion."""

    artifact_version_id: str
    schema_version: str
    content_hash: str
    project_id: str
    content: LiteratureClaimsCandidate


@dataclass(frozen=True, slots=True)
class _ResolvedInputs:
    input_versions: LiteratureRelationInputVersions
    versions: Mapping[str, LiteratureClaimsArtifactVersionInput]
    claims: Mapping[str, tuple[LiteratureClaimCandidate, LiteratureClaimsArtifactVersionInput]]
    duplicate_claim_ids: frozenset[str]
    evidence: Mapping[str, PaperSummaryEvidence]
    duplicate_evidence_ids: frozenset[str]
    input_failure: tuple[
        LiteratureRelationFailureStage, LiteratureRelationRejectionReason
    ] | None
    ownership_invalid_version_ids: frozenset[str]


class LiteratureRelationPipeline:
    """Admit Relation/Trace output without publishing or advancing a run."""

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
        literature_claim_artifact_version_ids: tuple[str, ...],
        literature_claim_versions: Mapping[
            str, LiteratureClaimsArtifactVersionInput
        ],
        project_id: str,
        model_response: str,
        model_name: str,
        parameters: Mapping[str, ParameterValue],
        confidence_assessments: Mapping[
            str, LiteratureRelationConfidenceAssessment
        ],
        prompt_version: str | None = None,
        parameters_version: str = RELATION_PARAMETERS_VERSION,
        execution_id: str | None = None,
        run_id: str | None = None,
        available_evidence_ids: frozenset[str] | None = None,
        available_source_snapshot_ids: frozenset[str] | None = None,
        available_paper_summary_artifact_version_ids: frozenset[str] | None = None,
        existing_relation_fingerprints: frozenset[str] = frozenset(),
        _authority_minter: Callable[..., LiteratureRelationsCandidate],
    ) -> LiteratureRelationAdmissionResult:
        requested_ids = tuple(sorted(set(literature_claim_artifact_version_ids)))
        if not requested_ids:
            raise ValueError("at least one LiteratureClaims ArtifactVersion is required")
        prompt = self.prompt_registry.get("literature_reasoning", prompt_version)
        if prompt.status != "active":
            raise ValueError("only an active LiteratureRelation Prompt can be executed")
        if prompt.output_models != ("LiteratureRelationExtractionOutput",):
            raise ValueError("Prompt output contract is not LiteratureRelationExtractionOutput")
        safe_parameters = _validate_parameters(parameters)
        parameters_hash = compute_canonical_payload_hash(
            {
                "parameters_version": parameters_version,
                "parameters": safe_parameters,
            }
        )
        resolved = _resolve_inputs(
            requested_ids=requested_ids,
            versions=literature_claim_versions,
            project_id=project_id,
        )
        safe_confidence_assessments, confidence_payload = _confidence_inputs(
            confidence_assessments
        )
        input_hash = compute_canonical_payload_hash(
            {
                "input_versions": resolved.input_versions.model_dump(
                    mode="json", exclude_none=True
                ),
                "prompt_name": prompt.name,
                "prompt_version": prompt.version,
                "prompt_hash": prompt.content_hash,
                "model_name": model_name,
                "parameters_version": parameters_version,
                "parameters_hash": parameters_hash,
                "producer_version": RELATION_PRODUCER_VERSION,
                "schema_version": RELATION_SCHEMA_VERSION,
                "pairing_version": RELATION_PAIRING_VERSION,
                "comparison_policy_version": RELATION_COMPARISON_POLICY_VERSION,
                "trace_protocol_version": RELATION_TRACE_PROTOCOL_VERSION,
                "confidence_definition_id": RELATION_CONFIDENCE_DEFINITION_ID,
                "confidence_definition_version": (
                    RELATION_CONFIDENCE_DEFINITION_VERSION
                ),
                "confidence_calibration_id": RELATION_CONFIDENCE_CALIBRATION_ID,
                "confidence_calibration_version": (
                    RELATION_CONFIDENCE_CALIBRATION_VERSION
                ),
                "confidence_calibration_scientific_payload_hash": (
                    FROZEN_SCIENTIFIC_PAYLOAD_HASH
                ),
                "confidence_calibration_content_hash": FROZEN_BENCHMARK_CONTENT_HASH,
                "confidence_calibration_sample_size": (
                    RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE
                ),
                "confidence_calibration_method": (
                    RELATION_CONFIDENCE_CALIBRATION_METHOD
                ),
                "confidence_applicability_scope": (
                    RELATION_CONFIDENCE_APPLICABILITY_SCOPE
                ),
                "confidence_acceptance_threshold": (
                    RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD
                ),
                "confidence_assessments": confidence_payload,
                "admission_context": {
                    "available_evidence_ids": (
                        None
                        if available_evidence_ids is None
                        else sorted(available_evidence_ids)
                    ),
                    "available_source_snapshot_ids": (
                        None
                        if available_source_snapshot_ids is None
                        else sorted(available_source_snapshot_ids)
                    ),
                    "available_paper_summary_artifact_version_ids": (
                        None
                        if available_paper_summary_artifact_version_ids is None
                        else sorted(available_paper_summary_artifact_version_ids)
                    ),
                    "existing_relation_fingerprints": sorted(
                        existing_relation_fingerprints
                    ),
                },
            }
        )
        raw_response_hash = compute_canonical_payload_hash(model_response)
        now = self._now()
        stable_execution_id = execution_id or f"execution.{input_hash[7:31]}"
        producer_fields: dict[str, Any] = {
            "execution_id": stable_execution_id,
            "run_id": run_id,
            "step_key": "reasoning_literature",
            "producer_type": "model",
            "producer_name": RELATION_PRODUCER_NAME,
            "producer_version": RELATION_PRODUCER_VERSION,
            "model_name": model_name,
            "prompt_name": prompt.name,
            "prompt_version": prompt.version,
            "prompt_hash": prompt.content_hash,
            "schema_version": RELATION_SCHEMA_VERSION,
            "parameters_version": parameters_version,
            "parameters_hash": parameters_hash,
            "pairing_version": RELATION_PAIRING_VERSION,
            "comparison_policy_version": RELATION_COMPARISON_POLICY_VERSION,
            "trace_protocol_version": RELATION_TRACE_PROTOCOL_VERSION,
            "confidence_definition_id": RELATION_CONFIDENCE_DEFINITION_ID,
            "confidence_definition_version": RELATION_CONFIDENCE_DEFINITION_VERSION,
            "confidence_calibration_id": RELATION_CONFIDENCE_CALIBRATION_ID,
            "confidence_calibration_version": RELATION_CONFIDENCE_CALIBRATION_VERSION,
            "confidence_calibration_scientific_payload_hash": (
                FROZEN_SCIENTIFIC_PAYLOAD_HASH
            ),
            "confidence_calibration_content_hash": FROZEN_BENCHMARK_CONTENT_HASH,
            "confidence_calibration_sample_size": (
                RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE
            ),
            "confidence_calibration_method": RELATION_CONFIDENCE_CALIBRATION_METHOD,
            "confidence_applicability_scope": (
                RELATION_CONFIDENCE_APPLICABILITY_SCOPE
            ),
            "confidence_acceptance_threshold": (
                RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD
            ),
            "input_versions": resolved.input_versions,
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
                stage=LiteratureRelationFailureStage.json,
                reason=LiteratureRelationRejectionReason.invalid_json,
            )
        producer_fields["model_response_hash"] = compute_canonical_payload_hash(decoded)
        try:
            extraction = LiteratureRelationExtractionOutput.model_validate(decoded)
        except ValidationError:
            return _fatal_rejection(
                producer_fields=producer_fields,
                stage=LiteratureRelationFailureStage.schema,
                reason=LiteratureRelationRejectionReason.schema_invalid,
            )
        response_payload = {
            "schema_version": extraction.schema_version,
            "relations": sorted(
                (_canonical_response_candidate(item) for item in extraction.relations),
                key=compute_canonical_payload_hash,
            ),
        }
        response_hash = compute_canonical_payload_hash(response_payload)
        producer_fields["model_response_hash"] = response_hash
        records, traces, retained_claims, evidence, evidence_references = (
            _admit_relations(
                extraction=extraction,
                resolved=resolved,
                producer_execution_id=stable_execution_id,
                input_hash=input_hash,
                response_hash=response_hash,
                confidence_assessments=safe_confidence_assessments,
                available_evidence_ids=available_evidence_ids,
                available_source_snapshot_ids=available_source_snapshot_ids,
                available_paper_summary_artifact_version_ids=(
                    available_paper_summary_artifact_version_ids
                ),
                existing_relation_fingerprints=existing_relation_fingerprints,
            )
        )
        status = _aggregate_status(records)
        publishable = any(
            item.status is not LiteratureRelationStatus.rejected for item in records
        )
        if not publishable:
            producer_payload = {
                **producer_fields,
                "output_hash": _ZERO_HASH,
                "status": "completed",
            }
            result_payload = {
                "admission_status": status,
                "records": [
                    item.model_dump(mode="json", exclude_none=True) for item in records
                ],
                "reasoning_traces": [
                    item.model_dump(mode="json", exclude_none=True) for item in traces
                ],
                "publisher_candidate": None,
                "producer": producer_payload,
                "output_hash": _ZERO_HASH,
            }
            output_hash = compute_literature_relation_admission_output_hash(
                result_payload
            )
            producer_payload["output_hash"] = output_hash
            result_payload["output_hash"] = output_hash
            return LiteratureRelationAdmissionResult.model_validate(result_payload)

        producer_payload = {
            **producer_fields,
            "output_hash": _ZERO_HASH,
            "status": "completed",
        }
        evidence_ids = tuple(
            sorted({item.evidence_id for item in evidence_references})
        )
        source_snapshot_ids = tuple(
            sorted({item.source_snapshot_id for item in evidence_references})
        )
        candidate_payload = {
            "kind": "literature_relations",
            "schema_version": RELATION_SCHEMA_VERSION,
            "input_versions": resolved.input_versions.model_dump(
                mode="json", exclude_none=True
            ),
            "claims": [
                item.model_dump(mode="json", exclude_none=True)
                for item in retained_claims
            ],
            "relations": [
                item.model_dump(mode="json", exclude_none=True) for item in records
            ],
            "reasoning_traces": [
                item.model_dump(mode="json", exclude_none=True) for item in traces
            ],
            "evidence": [
                item.model_dump(mode="json", exclude_none=True) for item in evidence
            ],
            "evidence_references": [
                item.model_dump(mode="json", exclude_none=True)
                for item in evidence_references
            ],
            "evidence_ids": evidence_ids,
            "source_snapshot_ids": source_snapshot_ids,
            "status_counts": _status_counts(records).model_dump(mode="json"),
            "producer": producer_payload,
            "input_hash": input_hash,
            "output_hash": _ZERO_HASH,
        }
        output_hash = compute_literature_relations_output_hash(candidate_payload)
        producer_payload["output_hash"] = output_hash
        candidate_payload["output_hash"] = output_hash
        candidate = LiteratureRelationsCandidate.model_validate(candidate_payload)
        public_payload_hash = compute_literature_relations_public_payload_hash(candidate)
        commitment_input = json.dumps(
            {
                "input_hash": input_hash,
                "model_response_hash": response_hash,
                "output_hash": output_hash,
                "input_artifact_version_ids": requested_ids,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        context_hash = compute_canonical_payload_hash(
            {"input_json": commitment_input, "input_hash": input_hash}
        )
        admission_commitment_hash = compute_canonical_payload_hash(
            {
                "candidate_kind": candidate.kind,
                "schema_version": candidate.schema_version,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "public_payload_hash": public_payload_hash,
                "context_hash": context_hash,
            }
        )
        candidate = _authority_minter(
            candidate,
            LiteratureRelationAdmissionSnapshot(
                input_json=commitment_input,
                input_hash=input_hash,
                context_hash=context_hash,
                admission_commitment_hash=admission_commitment_hash,
            ),
            public_payload_hash=public_payload_hash,
        )
        return LiteratureRelationAdmissionResult(
            admission_status=status,
            records=records,
            reasoning_traces=traces,
            publisher_candidate=candidate,
            producer=candidate.producer,
            output_hash=output_hash,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("Relation pipeline clock must return timezone-aware datetime")
        return value


def _fatal_rejection(
    *,
    producer_fields: dict[str, Any],
    stage: LiteratureRelationFailureStage,
    reason: LiteratureRelationRejectionReason,
) -> LiteratureRelationAdmissionResult:
    producer_payload = {
        **producer_fields,
        "output_hash": _ZERO_HASH,
        "status": "rejected",
        "error_code": reason,
    }
    result_payload = {
        "admission_status": LiteratureRelationStatus.rejected,
        "failure_stage": stage,
        "rejection_reason": reason,
        "records": [],
        "reasoning_traces": [],
        "publisher_candidate": None,
        "producer": producer_payload,
        "output_hash": _ZERO_HASH,
    }
    output_hash = compute_literature_relation_admission_output_hash(result_payload)
    producer_payload["output_hash"] = output_hash
    result_payload["output_hash"] = output_hash
    return LiteratureRelationAdmissionResult.model_validate(result_payload)


def _resolve_inputs(
    *,
    requested_ids: tuple[str, ...],
    versions: Mapping[str, LiteratureClaimsArtifactVersionInput],
    project_id: str,
) -> _ResolvedInputs:
    references: list[LiteratureClaimArtifactVersionReference] = []
    resolved_versions: dict[str, LiteratureClaimsArtifactVersionInput] = {}
    claims: dict[
        str, tuple[LiteratureClaimCandidate, LiteratureClaimsArtifactVersionInput]
    ] = {}
    duplicate_claim_ids: set[str] = set()
    evidence: dict[str, PaperSummaryEvidence] = {}
    duplicate_evidence_ids: set[str] = set()
    missing = False
    unsupported = False
    content_mismatch = False
    ownership_invalid: set[str] = set()
    for requested_id in requested_ids:
        wrapper = versions.get(requested_id)
        if wrapper is None:
            missing = True
            references.append(
                LiteratureClaimArtifactVersionReference(
                    artifact_version_id=requested_id
                )
            )
            continue
        try:
            content = LiteratureClaimsCandidate.model_validate(
                wrapper.content.model_dump(mode="json", exclude_none=True)
            )
        except (
            ValidationError,
            PydanticSerializationError,
            AttributeError,
            TypeError,
        ):
            content_mismatch = True
            references.append(
                LiteratureClaimArtifactVersionReference(
                    artifact_version_id=requested_id
                )
            )
            continue
        actual_content_hash = compute_canonical_payload_hash(
            content.model_dump(mode="json", exclude_none=True)
        )
        if wrapper.schema_version not in SUPPORTED_CLAIM_SCHEMA_VERSIONS:
            unsupported = True
        if actual_content_hash != wrapper.content_hash:
            content_mismatch = True
        if (
            wrapper.artifact_version_id != requested_id
            or wrapper.project_id != project_id
            or content.schema_version != wrapper.schema_version
        ):
            ownership_invalid.add(requested_id)
        resolved_wrapper = LiteratureClaimsArtifactVersionInput(
            artifact_version_id=wrapper.artifact_version_id,
            schema_version=wrapper.schema_version,
            content_hash=wrapper.content_hash,
            project_id=wrapper.project_id,
            content=content,
        )
        resolved_versions[requested_id] = resolved_wrapper
        references.append(
            LiteratureClaimArtifactVersionReference(
                artifact_version_id=requested_id,
                schema_version=wrapper.schema_version,
                content_hash=wrapper.content_hash,
                output_hash=content.output_hash,
                project_id=wrapper.project_id,
                claim_ids=tuple(sorted(item.claim_id for item in content.claims)),
                paper_summary_artifact_version_ids=tuple(
                    sorted(
                        {
                            item.source_paper_summary_artifact_version_id
                            for item in content.claims
                        }
                    )
                ),
                source_snapshot_ids=tuple(sorted(content.source_snapshot_ids)),
            )
        )
        for claim in content.claims:
            if claim.claim_id in claims:
                duplicate_claim_ids.add(claim.claim_id)
            else:
                claims[claim.claim_id] = (claim, resolved_wrapper)
        for item in content.evidence:
            previous = evidence.get(item.evidence_id)
            if previous is not None and previous != item:
                duplicate_evidence_ids.add(item.evidence_id)
            else:
                evidence[item.evidence_id] = item
    input_failure = None
    if missing:
        input_failure = (
            LiteratureRelationFailureStage.input,
            LiteratureRelationRejectionReason.input_artifact_version_unknown,
        )
    elif unsupported:
        input_failure = (
            LiteratureRelationFailureStage.input,
            LiteratureRelationRejectionReason.input_schema_version_unsupported,
        )
    elif content_mismatch:
        input_failure = (
            LiteratureRelationFailureStage.input,
            LiteratureRelationRejectionReason.input_content_hash_mismatch,
        )
    return _ResolvedInputs(
        input_versions=LiteratureRelationInputVersions(
            project_id=project_id,
            claim_artifact_versions=tuple(references),
        ),
        versions=resolved_versions,
        claims=claims,
        duplicate_claim_ids=frozenset(duplicate_claim_ids),
        evidence=evidence,
        duplicate_evidence_ids=frozenset(duplicate_evidence_ids),
        input_failure=input_failure,
        ownership_invalid_version_ids=frozenset(ownership_invalid),
    )


def _admit_relations(
    *,
    extraction: LiteratureRelationExtractionOutput,
    resolved: _ResolvedInputs,
    producer_execution_id: str,
    input_hash: str,
    response_hash: str,
    confidence_assessments: Mapping[str, LiteratureRelationConfidenceAssessment],
    available_evidence_ids: frozenset[str] | None,
    available_source_snapshot_ids: frozenset[str] | None,
    available_paper_summary_artifact_version_ids: frozenset[str] | None,
    existing_relation_fingerprints: frozenset[str],
) -> tuple[
    tuple[LiteratureRelationCandidate, ...],
    tuple[LiteratureReasoningTraceCandidate, ...],
    tuple[LiteratureClaimCandidate, ...],
    tuple[PaperSummaryEvidence, ...],
    tuple[LiteratureRelationEvidenceReference, ...],
]:
    ordered = tuple(
        sorted(
            extraction.relations,
            key=lambda item: compute_canonical_payload_hash(
                _canonical_response_candidate(item)
            ),
        )
    )
    evidence_exists = (
        frozenset(resolved.evidence)
        if available_evidence_ids is None
        else available_evidence_ids
    )
    all_snapshot_ids = frozenset(
        item.source_snapshot_id for item in resolved.evidence.values()
    )
    snapshot_exists = (
        all_snapshot_ids
        if available_source_snapshot_ids is None
        else available_source_snapshot_ids
    )
    summary_version_exists = (
        frozenset(
            claim.source_paper_summary_artifact_version_id
            for claim, _version in resolved.claims.values()
        )
        if available_paper_summary_artifact_version_ids is None
        else available_paper_summary_artifact_version_ids
    )
    seen = set(existing_relation_fingerprints)
    occurrences: dict[str, int] = {}
    records: list[LiteratureRelationCandidate] = []
    traces: list[LiteratureReasoningTraceCandidate] = []
    retained_claims: dict[str, LiteratureClaimCandidate] = {}
    retained_evidence: dict[str, PaperSummaryEvidence] = {}
    retained_references: dict[
        tuple[str, str, str], LiteratureRelationEvidenceReference
    ] = {}
    for candidate in ordered:
        source_entry = resolved.claims.get(candidate.source_claim_id)
        target_entry = resolved.claims.get(candidate.target_claim_id)
        source_claim = None if source_entry is None else source_entry[0]
        target_claim = None if target_entry is None else target_entry[0]
        source_version = None if source_entry is None else source_entry[1]
        target_version = None if target_entry is None else target_entry[1]
        source_version_id = (
            None if source_version is None else source_version.artifact_version_id
        )
        target_version_id = (
            None if target_version is None else target_version.artifact_version_id
        )
        fingerprint_payload = {
            "source_claim_artifact_version_id": source_version_id,
            "source_claim_id": candidate.source_claim_id,
            "relation_type": candidate.relation_type,
            "target_claim_artifact_version_id": target_version_id,
            "target_claim_id": candidate.target_claim_id,
        }
        fingerprint = compute_literature_relation_fingerprint(fingerprint_payload)
        occurrence_index = occurrences.get(fingerprint, 0)
        occurrences[fingerprint] = occurrence_index + 1
        relation_identity_hash = compute_canonical_payload_hash(
            {
                "fingerprint": fingerprint,
                "occurrence_index": occurrence_index,
            }
        )
        relation_id = f"relation.{relation_identity_hash[7:31]}"
        pair_hash = compute_canonical_payload_hash(
            {
                "claims": sorted(
                    (
                        {
                            "artifact_version_id": source_version_id,
                            "claim_id": candidate.source_claim_id,
                        },
                        {
                            "artifact_version_id": target_version_id,
                            "claim_id": candidate.target_claim_id,
                        },
                    ),
                    key=compute_canonical_payload_hash,
                )
            }
        )
        pair_id = f"claim_pair.{pair_hash[7:31]}"
        stage: LiteratureRelationFailureStage | None = None
        reason: LiteratureRelationRejectionReason | None = None
        if resolved.input_failure is not None:
            stage, reason = resolved.input_failure
        elif source_claim is None or target_claim is None:
            stage = LiteratureRelationFailureStage.claim
            reason = LiteratureRelationRejectionReason.claim_not_found
        elif (
            source_claim.status is LiteratureClaimStatus.rejected
            or target_claim.status is LiteratureClaimStatus.rejected
        ):
            stage = LiteratureRelationFailureStage.claim
            reason = LiteratureRelationRejectionReason.claim_status_invalid
        elif (
            source_claim.source_paper_summary_artifact_version_id
            not in summary_version_exists
            or target_claim.source_paper_summary_artifact_version_id
            not in summary_version_exists
        ):
            stage = LiteratureRelationFailureStage.claim
            reason = (
                LiteratureRelationRejectionReason.paper_summary_artifact_version_unknown
            )

        endpoint_evidence_ids = tuple(
            sorted(
                set(() if source_claim is None else source_claim.evidence_ids)
                | set(() if target_claim is None else target_claim.evidence_ids)
            )
        )
        referenced_evidence = tuple(
            resolved.evidence[item]
            for item in candidate.evidence_ids
            if item in resolved.evidence
        )
        candidate_snapshot_ids = tuple(
            sorted({item.source_snapshot_id for item in referenced_evidence})
        )
        if reason is None:
            if not candidate.evidence_ids:
                stage = LiteratureRelationFailureStage.evidence
                reason = LiteratureRelationRejectionReason.evidence_missing
            elif any(
                item not in resolved.evidence
                or item not in evidence_exists
                or item in resolved.duplicate_evidence_ids
                for item in candidate.evidence_ids
            ):
                stage = LiteratureRelationFailureStage.evidence
                reason = LiteratureRelationRejectionReason.evidence_not_found
            elif any(
                item.source_snapshot_id not in snapshot_exists
                for item in referenced_evidence
            ):
                stage = LiteratureRelationFailureStage.evidence
                reason = LiteratureRelationRejectionReason.source_snapshot_not_found
            elif tuple(sorted(candidate.evidence_ids)) != endpoint_evidence_ids:
                stage = LiteratureRelationFailureStage.evidence
                reason = LiteratureRelationRejectionReason.evidence_inconsistent
        if reason is None and (
            source_version is None
            or target_version is None
            or source_version_id in resolved.ownership_invalid_version_ids
            or target_version_id in resolved.ownership_invalid_version_ids
            or candidate.source_claim_id in resolved.duplicate_claim_ids
            or candidate.target_claim_id in resolved.duplicate_claim_ids
            or not _claim_ownership_matches(source_claim, source_version)
            or not _claim_ownership_matches(target_claim, target_version)
        ):
            stage = LiteratureRelationFailureStage.ownership
            reason = LiteratureRelationRejectionReason.ownership_mismatch
        if reason is None and candidate.source_claim_id == candidate.target_claim_id:
            stage = LiteratureRelationFailureStage.pairing
            reason = LiteratureRelationRejectionReason.self_pair
        if reason is None and (
            candidate.direction.source_claim_id != candidate.source_claim_id
            or candidate.direction.target_claim_id != candidate.target_claim_id
        ):
            stage = LiteratureRelationFailureStage.direction
            reason = LiteratureRelationRejectionReason.direction_mismatch
        if reason is None and fingerprint in seen:
            stage = LiteratureRelationFailureStage.duplicate
            reason = LiteratureRelationRejectionReason.duplicate_relation
        if reason is None:
            if not candidate.conditions:
                stage = LiteratureRelationFailureStage.conditions
                reason = LiteratureRelationRejectionReason.conditions_missing
            elif candidate.condition_conflicts or (
                candidate.trace is not None and candidate.trace.conflicts
            ):
                stage = LiteratureRelationFailureStage.conditions
                reason = LiteratureRelationRejectionReason.conditions_conflict
        if reason is None:
            stage, reason = _comparability_failure(
                candidate=candidate,
                source_claim=source_claim,
                target_claim=target_claim,
            )
        confidence = _confidence(
            candidate.confidence_assessment_id, confidence_assessments
        )
        unsafe_authored_text = _contains_unsafe_authored_text(candidate, confidence)
        trace_failure = (
            (
                LiteratureRelationFailureStage.trace,
                LiteratureRelationRejectionReason.trace_unsafe,
            )
            if unsafe_authored_text
            else _trace_failure(
                candidate=candidate,
                endpoint_evidence_ids=endpoint_evidence_ids,
            )
        )
        if reason is None and trace_failure is not None:
            stage, reason = trace_failure
        expected_confidence_subject = (
            None
            if source_version_id is None or target_version_id is None
            else build_literature_relation_confidence_subject(
                source_claim_artifact_version_id=source_version_id,
                source_claim_id=candidate.source_claim_id,
                target_claim_artifact_version_id=target_version_id,
                target_claim_id=candidate.target_claim_id,
                relation_type=candidate.relation_type,
            )
        )
        confidence_failure = _confidence_failure(
            candidate.confidence_assessment_id,
            confidence,
            expected_subject=expected_confidence_subject,
        )
        if reason is None and confidence_failure is not None:
            stage, reason = confidence_failure

        review_reason: LiteratureRelationReviewReason | None = None
        if reason is not None:
            status = LiteratureRelationStatus.rejected
        elif (
            source_claim is not None
            and target_claim is not None
            and (
                source_claim.status is not LiteratureClaimStatus.accepted
                or target_claim.status is not LiteratureClaimStatus.accepted
            )
        ):
            status = LiteratureRelationStatus.candidate
            review_reason = LiteratureRelationReviewReason.claim_not_accepted
        elif candidate.condition_uncertainties:
            status = LiteratureRelationStatus.candidate
            review_reason = LiteratureRelationReviewReason.conditions_unresolved
        elif (
            confidence is not None
            and confidence.status
            is LiteratureRelationConfidenceStatus.not_evaluable
        ):
            status = LiteratureRelationStatus.candidate
            review_reason = LiteratureRelationReviewReason.confidence_not_evaluable
        elif (
            confidence is not None
            and confidence.score is not None
            and confidence.score < confidence.acceptance_threshold
        ):
            status = LiteratureRelationStatus.candidate
            review_reason = LiteratureRelationReviewReason.confidence_below_threshold
        else:
            status = LiteratureRelationStatus.accepted
        expected_decision = status
        decision_matches = (
            confidence is not None and confidence.decision is expected_decision
        )
        if (
            reason is None
            and confidence is not None
            and confidence_failure is None
            and not decision_matches
        ):
            stage = LiteratureRelationFailureStage.confidence
            reason = LiteratureRelationRejectionReason.confidence_decision_mismatch
            status = LiteratureRelationStatus.rejected
            review_reason = None

        retained_confidence = (
            confidence
            if confidence is not None
            and confidence_failure is None
            and decision_matches
            else None
        )

        trace_evidence_ids = (
            ()
            if candidate.trace is None
            else tuple(
                sorted(
                    {
                        evidence_id
                        for item in candidate.trace.steps
                        for evidence_id in item.evidence_ids
                    }
                )
            )
        )
        trace_reference_closure_complete = (
            resolved.input_failure is None
            and source_claim is not None
            and target_claim is not None
            and source_version is not None
            and target_version is not None
            and source_claim.status is not LiteratureClaimStatus.rejected
            and target_claim.status is not LiteratureClaimStatus.rejected
            and source_claim.source_paper_summary_artifact_version_id
            in summary_version_exists
            and target_claim.source_paper_summary_artifact_version_id
            in summary_version_exists
            and source_version_id not in resolved.ownership_invalid_version_ids
            and target_version_id not in resolved.ownership_invalid_version_ids
            and candidate.source_claim_id not in resolved.duplicate_claim_ids
            and candidate.target_claim_id not in resolved.duplicate_claim_ids
            and _claim_ownership_matches(source_claim, source_version)
            and _claim_ownership_matches(target_claim, target_version)
            and bool(candidate.evidence_ids)
            and tuple(sorted(candidate.evidence_ids)) == endpoint_evidence_ids
            and all(
                evidence_id in resolved.evidence
                and evidence_id in evidence_exists
                and evidence_id not in resolved.duplicate_evidence_ids
                for evidence_id in candidate.evidence_ids
            )
            and all(
                item.source_snapshot_id in snapshot_exists
                for item in referenced_evidence
            )
        )
        trace = None
        if (
            candidate.trace is not None
            and trace_failure is None
            and trace_reference_closure_complete
            and trace_evidence_ids == tuple(sorted(candidate.evidence_ids))
        ):
            trace_hash = compute_canonical_payload_hash(
                {"relation_id": relation_id, "trace": _canonical_trace(candidate)}
            )
            trace = LiteratureReasoningTraceCandidate(
                trace_id=f"trace.{trace_hash[7:31]}",
                relation_id=relation_id,
                premise_claim_ids=(
                    candidate.source_claim_id,
                    candidate.target_claim_id,
                ),
                steps=tuple(
                    LiteratureReasoningTraceStepCandidate.model_validate(
                        {
                            **item.model_dump(mode="json", exclude_none=True),
                            "claim_ids": tuple(sorted(item.claim_ids)),
                            "evidence_ids": tuple(sorted(item.evidence_ids)),
                        }
                    )
                    for item in sorted(candidate.trace.steps, key=lambda item: item.order)
                ),
                conditions=tuple(sorted(candidate.trace.conditions, key=str.casefold)),
                limitations=tuple(
                    sorted(candidate.trace.limitations, key=str.casefold)
                ),
                conflicts=tuple(sorted(candidate.trace.conflicts, key=str.casefold)),
                conclusion=candidate.trace.conclusion or "",
                evidence_ids=trace_evidence_ids,
                trace_protocol_version=RELATION_TRACE_PROTOCOL_VERSION,
                relation_status=status,
                producer_execution_id=producer_execution_id,
                input_hash=input_hash,
                model_response_hash=response_hash,
            )
            traces.append(trace)
        record = LiteratureRelationCandidate.model_validate(
            {
                "relation_id": relation_id,
                "pair_id": pair_id,
                "source_claim_id": candidate.source_claim_id,
                "target_claim_id": candidate.target_claim_id,
                "source_claim_artifact_version_id": source_version_id,
                "target_claim_artifact_version_id": target_version_id,
                "source_paper_summary_artifact_version_id": (
                    None
                    if source_claim is None
                    else source_claim.source_paper_summary_artifact_version_id
                ),
                "target_paper_summary_artifact_version_id": (
                    None
                    if target_claim is None
                    else target_claim.source_paper_summary_artifact_version_id
                ),
                "relation_type": candidate.relation_type,
                "direction": _safe_direction_payload(candidate),
                "conditions": _safe_text_tuple(candidate.conditions),
                "condition_conflicts": tuple(
                    _safe_text_tuple(candidate.condition_conflicts)
                ),
                "condition_uncertainties": tuple(
                    _safe_text_tuple(candidate.condition_uncertainties)
                ),
                "comparability": _safe_comparability_payload(candidate),
                "evidence_ids": tuple(sorted(candidate.evidence_ids)),
                "source_snapshot_ids": candidate_snapshot_ids,
                "reasoning_trace_id": None if trace is None else trace.trace_id,
                "confidence": (
                    None
                    if retained_confidence is None
                    else _safe_confidence_payload(retained_confidence)
                ),
                "fingerprint": fingerprint,
                "status": status,
                "failure_stage": stage,
                "rejection_reason": reason,
                "review_reason": review_reason,
                "producer_execution_id": producer_execution_id,
                "input_hash": input_hash,
                "model_response_hash": response_hash,
            }
        )
        records.append(record)
        if reason is None:
            seen.add(fingerprint)
        for claim in (source_claim, target_claim):
            if claim is not None:
                retained_claims.setdefault(claim.claim_id, claim)
        for side, claim, version in (
            ("source", source_claim, source_version),
            ("target", target_claim, target_version),
        ):
            if claim is None or version is None:
                continue
            content_evidence = {item.evidence_id: item for item in version.content.evidence}
            for evidence_id in claim.evidence_ids:
                item = content_evidence.get(evidence_id)
                if (
                    item is None
                    or evidence_id not in candidate.evidence_ids
                    or evidence_id not in evidence_exists
                    or item.source_snapshot_id not in snapshot_exists
                ):
                    continue
                retained_evidence[item.evidence_id] = item
                retained_references[(relation_id, side, evidence_id)] = (
                    LiteratureRelationEvidenceReference(
                        relation_id=relation_id,
                        side=side,
                        claim_id=claim.claim_id,
                        claim_artifact_version_id=version.artifact_version_id,
                        paper_summary_artifact_version_id=(
                            claim.source_paper_summary_artifact_version_id
                        ),
                        evidence_id=evidence_id,
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
        tuple(sorted(traces, key=lambda item: item.trace_id)),
        tuple(retained_claims[key] for key in sorted(retained_claims)),
        tuple(retained_evidence[key] for key in sorted(retained_evidence)),
        tuple(retained_references[key] for key in sorted(retained_references)),
    )


def _claim_ownership_matches(
    claim: LiteratureClaimCandidate,
    version: LiteratureClaimsArtifactVersionInput,
) -> bool:
    content = version.content
    return (
        claim in content.claims
        and claim.source_paper_summary_artifact_version_id
        == content.input_versions.paper_summary_artifact_version_id
        and claim.paper_id == content.input_versions.paper_id
        and claim.source_summary_id == content.input_versions.summary_id
        and set(claim.evidence_ids).issubset(content.evidence_ids)
        and set(claim.source_snapshot_ids).issubset(content.source_snapshot_ids)
    )


def _comparability_failure(
    *,
    candidate: LiteratureRelationModelCandidate,
    source_claim: LiteratureClaimCandidate | None,
    target_claim: LiteratureClaimCandidate | None,
) -> tuple[
    LiteratureRelationFailureStage | None,
    LiteratureRelationRejectionReason | None,
]:
    if source_claim is None or target_claim is None:
        return None, None
    comparison = candidate.comparability
    if comparison.object_status is not LiteratureComparabilityStatus.comparable:
        return (
            LiteratureRelationFailureStage.comparability,
            LiteratureRelationRejectionReason.object_incomparable,
        )
    metric_expected = _expected_comparability(source_claim.metric, target_claim.metric)
    if (
        comparison.metric_status is not metric_expected
        or metric_expected is LiteratureComparabilityStatus.incomparable
    ):
        return (
            LiteratureRelationFailureStage.comparability,
            LiteratureRelationRejectionReason.metric_incomparable,
        )
    unit_expected = _expected_comparability(source_claim.unit, target_claim.unit)
    if (
        comparison.unit_status is not unit_expected
        or unit_expected is LiteratureComparabilityStatus.incomparable
    ):
        return (
            LiteratureRelationFailureStage.comparability,
            LiteratureRelationRejectionReason.unit_incomparable,
        )
    return None, None


def _expected_comparability(
    source: str | None, target: str | None
) -> LiteratureComparabilityStatus:
    if source is None and target is None:
        return LiteratureComparabilityStatus.not_applicable
    if source is not None and target is not None and source.casefold() == target.casefold():
        return LiteratureComparabilityStatus.comparable
    return LiteratureComparabilityStatus.incomparable


def _trace_failure(
    *,
    candidate: LiteratureRelationModelCandidate,
    endpoint_evidence_ids: tuple[str, ...],
) -> tuple[LiteratureRelationFailureStage, LiteratureRelationRejectionReason] | None:
    trace = candidate.trace
    if trace is None:
        return (
            LiteratureRelationFailureStage.trace,
            LiteratureRelationRejectionReason.trace_missing,
        )
    if candidate.source_claim_id == candidate.target_claim_id:
        return (
            LiteratureRelationFailureStage.trace,
            LiteratureRelationRejectionReason.trace_incomplete,
        )
    if trace.premise_claim_ids != (
        candidate.source_claim_id,
        candidate.target_claim_id,
    ):
        return (
            LiteratureRelationFailureStage.trace,
            LiteratureRelationRejectionReason.trace_direction_mismatch,
        )
    required_operations = {
        LiteratureTraceOperation.identify_premises,
        LiteratureTraceOperation.compare_objects,
        LiteratureTraceOperation.check_conditions,
        LiteratureTraceOperation.check_evidence,
        LiteratureTraceOperation.classify_relation,
    }
    if candidate.comparability.metric_status is not LiteratureComparabilityStatus.not_applicable:
        required_operations.add(LiteratureTraceOperation.compare_metric)
    if candidate.comparability.unit_status is not LiteratureComparabilityStatus.not_applicable:
        required_operations.add(LiteratureTraceOperation.compare_unit)
    operations = {item.operation for item in trace.steps}
    orders = tuple(item.order for item in sorted(trace.steps, key=lambda item: item.order))
    trace_claim_ids = {
        claim_id for item in trace.steps for claim_id in item.claim_ids
    }
    if (
        not trace.steps
        or trace.conclusion is None
        or not trace.conditions
        or tuple(sorted(trace.conditions, key=str.casefold))
        != tuple(sorted(candidate.conditions, key=str.casefold))
        or tuple(sorted(trace.conflicts, key=str.casefold))
        != tuple(sorted(candidate.condition_conflicts, key=str.casefold))
        or orders != tuple(range(1, len(trace.steps) + 1))
        or any(
            len(item.claim_ids) != len(set(item.claim_ids)) for item in trace.steps
        )
        or any(
            len(values) != len(set(values))
            for values in (trace.conditions, trace.limitations, trace.conflicts)
        )
        or not required_operations.issubset(operations)
        or trace_claim_ids
        != {candidate.source_claim_id, candidate.target_claim_id}
        or any(
            not item.claim_ids
            or any(
                claim_id
                not in {candidate.source_claim_id, candidate.target_claim_id}
                for claim_id in item.claim_ids
            )
            for item in trace.steps
        )
    ):
        return (
            LiteratureRelationFailureStage.trace,
            LiteratureRelationRejectionReason.trace_incomplete,
        )
    trace_evidence_ids = {
        evidence_id for item in trace.steps for evidence_id in item.evidence_ids
    }
    if (
        trace_evidence_ids != set(endpoint_evidence_ids)
        or any(not item.evidence_ids for item in trace.steps)
        or any(
            len(item.evidence_ids) != len(set(item.evidence_ids))
            for item in trace.steps
        )
    ):
        return (
            LiteratureRelationFailureStage.trace,
            LiteratureRelationRejectionReason.trace_evidence_incomplete,
        )
    return None


def _confidence(
    assessment_id: str | None,
    assessments: Mapping[str, LiteratureRelationConfidenceAssessment],
) -> LiteratureRelationConfidenceAssessment | None:
    if assessment_id is None:
        return None
    assessment = assessments.get(assessment_id)
    if assessment is None or assessment.assessment_id != assessment_id:
        return None
    return assessment


def _contains_unsafe_authored_text(
    candidate: LiteratureRelationModelCandidate,
    confidence: LiteratureRelationConfidenceAssessment | None,
) -> bool:
    trace = candidate.trace
    values = [
        candidate.direction.basis,
        candidate.comparability.object_basis,
        candidate.comparability.metric_basis,
        candidate.comparability.unit_basis,
        *candidate.conditions,
        *candidate.condition_conflicts,
        *candidate.condition_uncertainties,
    ]
    if trace is not None:
        values.extend(item.statement for item in trace.steps)
        values.extend(trace.conditions)
        values.extend(trace.limitations)
        values.extend(trace.conflicts)
        if trace.conclusion is not None:
            values.append(trace.conclusion)
    if confidence is not None:
        values.extend(confidence.basis)
    return any(_UNSAFE_TRACE.search(item) for item in values)


def _safe_text(value: str) -> str:
    if _UNSAFE_TRACE.search(value):
        return "[unsafe model-authored content redacted]"
    return value


def _safe_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({_safe_text(item) for item in values}, key=str.casefold))


def _safe_direction_payload(candidate: LiteratureRelationModelCandidate) -> dict[str, Any]:
    payload = candidate.direction.model_dump(mode="json", exclude_none=True)
    payload["basis"] = _safe_text(candidate.direction.basis)
    return payload


def _safe_comparability_payload(
    candidate: LiteratureRelationModelCandidate,
) -> dict[str, Any]:
    payload = candidate.comparability.model_dump(mode="json", exclude_none=True)
    for field in ("object_basis", "metric_basis", "unit_basis"):
        payload[field] = _safe_text(payload[field])
    return payload


def _safe_confidence_payload(
    confidence: LiteratureRelationConfidenceAssessment,
) -> dict[str, Any]:
    payload = confidence.model_dump(mode="json", exclude_none=True)
    payload["basis"] = list(_safe_text_tuple(confidence.basis))
    return payload


def _confidence_inputs(
    assessments: Mapping[str, LiteratureRelationConfidenceAssessment],
) -> tuple[
    dict[str, LiteratureRelationConfidenceAssessment],
    list[dict[str, Any]],
]:
    valid: dict[str, LiteratureRelationConfidenceAssessment] = {}
    payload: list[dict[str, Any]] = []
    for key, value in sorted(assessments.items()):
        try:
            raw = value.model_dump(mode="json", exclude_none=True)
            assessment = LiteratureRelationConfidenceAssessment.model_validate(raw)
        except (
            ValidationError,
            PydanticSerializationError,
            AttributeError,
            TypeError,
        ):
            payload.append({"mapping_id": key, "invalid_assessment": True})
            continue
        valid[key] = assessment
        payload.append(
            {
                "mapping_id": key,
                "assessment": assessment.model_dump(mode="json", exclude_none=True),
            }
        )
    return valid, payload


def _confidence_failure(
    assessment_id: str | None,
    confidence: LiteratureRelationConfidenceAssessment | None,
    *,
    expected_subject: LiteratureRelationConfidenceSubject | None,
) -> tuple[LiteratureRelationFailureStage, LiteratureRelationRejectionReason] | None:
    if assessment_id is None or confidence is None:
        return (
            LiteratureRelationFailureStage.confidence,
            LiteratureRelationRejectionReason.confidence_undefined,
        )
    if (
        confidence.definition_id != RELATION_CONFIDENCE_DEFINITION_ID
        or confidence.definition_version != RELATION_CONFIDENCE_DEFINITION_VERSION
    ):
        return (
            LiteratureRelationFailureStage.confidence,
            LiteratureRelationRejectionReason.confidence_definition_unsupported,
        )
    if (
        confidence.calibration_id != RELATION_CONFIDENCE_CALIBRATION_ID
        or confidence.calibration_version != RELATION_CONFIDENCE_CALIBRATION_VERSION
        or confidence.calibration_scientific_payload_hash
        != FROZEN_SCIENTIFIC_PAYLOAD_HASH
        or confidence.calibration_content_hash != FROZEN_BENCHMARK_CONTENT_HASH
        or confidence.calibration_sample_size
        != RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE
        or confidence.calibration_method != RELATION_CONFIDENCE_CALIBRATION_METHOD
        or confidence.applicability_scope != RELATION_CONFIDENCE_APPLICABILITY_SCOPE
        or confidence.acceptance_threshold
        != RELATION_CONFIDENCE_ACCEPTANCE_THRESHOLD
    ):
        return (
            LiteratureRelationFailureStage.confidence,
            LiteratureRelationRejectionReason.confidence_calibration_missing,
        )
    if expected_subject is None or confidence.subject != expected_subject:
        return (
            LiteratureRelationFailureStage.confidence,
            LiteratureRelationRejectionReason.confidence_subject_mismatch,
        )
    return None


def _canonical_response_candidate(
    candidate: LiteratureRelationModelCandidate,
) -> dict[str, Any]:
    payload = candidate.model_dump(mode="json", exclude_none=True)
    for field in (
        "conditions",
        "condition_conflicts",
        "condition_uncertainties",
        "evidence_ids",
    ):
        payload[field] = sorted(payload[field], key=str.casefold)
    trace = payload.get("trace")
    if isinstance(trace, dict):
        trace["premise_claim_ids"] = list(trace["premise_claim_ids"])
        for field in ("conditions", "limitations", "conflicts"):
            trace[field] = sorted(trace[field], key=str.casefold)
        trace["steps"] = sorted(trace["steps"], key=lambda item: item["order"])
        for step in trace["steps"]:
            step["claim_ids"] = sorted(step["claim_ids"])
            step["evidence_ids"] = sorted(step["evidence_ids"])
    return payload


def _canonical_trace(candidate: LiteratureRelationModelCandidate) -> dict[str, Any]:
    payload = _canonical_response_candidate(candidate)
    return payload.get("trace", {})


def _aggregate_status(
    records: tuple[LiteratureRelationCandidate, ...],
) -> LiteratureRelationStatus:
    if any(item.status is LiteratureRelationStatus.accepted for item in records):
        return LiteratureRelationStatus.accepted
    if any(item.status is LiteratureRelationStatus.candidate for item in records):
        return LiteratureRelationStatus.candidate
    return LiteratureRelationStatus.rejected


def _status_counts(
    records: tuple[LiteratureRelationCandidate, ...],
) -> LiteratureRelationStatusCounts:
    return LiteratureRelationStatusCounts(
        accepted=sum(item.status is LiteratureRelationStatus.accepted for item in records),
        candidate=sum(
            item.status is LiteratureRelationStatus.candidate for item in records
        ),
        rejected=sum(item.status is LiteratureRelationStatus.rejected for item in records),
    )


LiteratureRelationPipeline = _bind_literature_relation_pipeline_authority(
    LiteratureRelationPipeline
)
del _bind_literature_relation_pipeline_authority


__all__ = [
    "LiteratureClaimsArtifactVersionInput",
    "LiteratureRelationPipeline",
    "RELATION_CONFIDENCE_CALIBRATION_SAMPLE_SIZE",
    "SUPPORTED_CLAIM_SCHEMA_VERSIONS",
]
