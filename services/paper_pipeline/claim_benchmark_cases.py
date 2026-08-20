"""Deterministically derive the formal LiteratureClaim Pipeline case suite from tracked Paper Acquisition Benchmark."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, time, timezone
import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import ClaimType
from app.schemas.literature_claim import (
    LiteratureClaimAdmissionResult,
    LiteratureClaimBenchmarkCaseKind,
    LiteratureClaimBenchmarkEvaluationCase,
    LiteratureClaimFailureStage,
    LiteratureClaimRejectionReason,
    LiteratureClaimStatus,
)
from app.schemas.paper_benchmark import (
    BenchmarkClaim,
    BenchmarkEvidence,
    BenchmarkPackage,
    BenchmarkReviewStatus,
)
from app.schemas.paper_collection import PaperBenchmarkReference
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryEvidence,
    PaperSummaryEvidenceLocator,
    PaperSummaryInputVersions,
    PaperSummaryProducerExecution,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
    _seal_paper_summary_for_publication,
    compute_paper_summary_output_hash,
)
from packages.prompts.registry import PromptRegistry

from .benchmark import validate_frozen_benchmark
from .claim import LiteratureClaimPipeline, PaperSummaryArtifactVersionInput
from .constants import (
    SUMMARY_PARAMETERS_VERSION,
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)


_REPLAY_MODEL_NAME = "paper_benchmark-approved-label-replay"
_REPLAY_PARAMETERS: dict[str, str | int] = {
    "temperature": 0,
    "max_output_tokens": 2048,
    "response_format": "json_schema",
}


def build_frozen_claim_benchmark_cases(
    benchmark: BenchmarkPackage,
) -> tuple[LiteratureClaimBenchmarkEvaluationCase, ...]:
    """Build all approved scientific cases plus stable admission negatives."""

    validate_frozen_benchmark(benchmark)
    approved = tuple(
        sorted(
            (
                item
                for item in benchmark.claims
                if item.review_status is BenchmarkReviewStatus.approved
            ),
            key=lambda item: item.claim_id,
        )
    )
    if not approved:
        raise ValueError("frozen Paper Acquisition Benchmark package has no approved Claim labels")

    scientific: list[LiteratureClaimBenchmarkEvaluationCase] = []
    accepted_by_claim_id: dict[str, LiteratureClaimAdmissionResult] = {}
    for claim in approved:
        fixture = _build_claim_fixture(benchmark, claim)
        admission = fixture["pipeline"].admit(
            paper_summary_artifact_version_id=fixture["version_id"],
            paper_id=claim.paper_id,
            paper_summary_versions=fixture["versions"],
            model_response=fixture["response"],
            model_name=_REPLAY_MODEL_NAME,
            parameters=_REPLAY_PARAMETERS,
        )
        if (
            admission.admission_status is not LiteratureClaimStatus.accepted
            or len(admission.records) != 1
        ):
            raise ValueError(
                f"approved Paper Acquisition Benchmark Claim did not enter accepted LiteratureClaim Pipeline flow: {claim.claim_id}"
            )
        accepted_by_claim_id[claim.claim_id] = admission
        scientific.append(
            LiteratureClaimBenchmarkEvaluationCase(
                case_id=f"scientific.{claim.claim_id}",
                case_kind=LiteratureClaimBenchmarkCaseKind.scientific_label,
                benchmark_claim_id=claim.claim_id,
                record_claim_id=admission.records[0].claim_id,
                admission=admission,
            )
        )

    seed_claim = approved[0]
    fixture = _build_claim_fixture(benchmark, seed_claim)
    accepted = accepted_by_claim_id[seed_claim.claim_id]
    base_payload = fixture["claim_payload"]
    negatives = (
        _negative_case(
            case_id="rejection.invalid_json",
            fixture=fixture,
            model_response="{invalid",
            expected_stage=LiteratureClaimFailureStage.json,
            expected_reason=LiteratureClaimRejectionReason.invalid_json,
        ),
        _negative_case(
            case_id="rejection.ownership_mismatch",
            fixture=fixture,
            model_response=_response(
                {
                    **base_payload,
                    "source_statement_id": (
                        f"{base_payload['source_statement_id']}.unowned"
                    ),
                }
            ),
            expected_stage=LiteratureClaimFailureStage.ownership,
            expected_reason=LiteratureClaimRejectionReason.ownership_mismatch,
        ),
        _negative_case(
            case_id="rejection.evidence_missing",
            fixture=fixture,
            model_response=_response({**base_payload, "evidence_ids": []}),
            expected_stage=LiteratureClaimFailureStage.evidence,
            expected_reason=LiteratureClaimRejectionReason.evidence_missing,
        ),
        _negative_case(
            case_id="rejection.duplicate",
            fixture=fixture,
            model_response=fixture["response"],
            expected_stage=LiteratureClaimFailureStage.duplicate,
            expected_reason=LiteratureClaimRejectionReason.duplicate_claim,
            existing_claim_fingerprints=frozenset(
                {accepted.records[0].fingerprint}
            ),
        ),
    )
    return tuple(sorted((*scientific, *negatives), key=lambda item: item.case_id))


def _negative_case(
    *,
    case_id: str,
    fixture: dict[str, Any],
    model_response: str,
    expected_stage: LiteratureClaimFailureStage,
    expected_reason: LiteratureClaimRejectionReason,
    existing_claim_fingerprints: frozenset[str] = frozenset(),
) -> LiteratureClaimBenchmarkEvaluationCase:
    admission = fixture["pipeline"].admit(
        paper_summary_artifact_version_id=fixture["version_id"],
        paper_id=fixture["paper_id"],
        paper_summary_versions=fixture["versions"],
        model_response=model_response,
        model_name=_REPLAY_MODEL_NAME,
        parameters=_REPLAY_PARAMETERS,
        existing_claim_fingerprints=existing_claim_fingerprints,
    )
    return LiteratureClaimBenchmarkEvaluationCase(
        case_id=case_id,
        case_kind=LiteratureClaimBenchmarkCaseKind.rejection_case,
        record_claim_id=(
            admission.records[0].claim_id if admission.records else None
        ),
        expected_failure_stage=expected_stage,
        expected_rejection_reason=expected_reason,
        admission=admission,
    )


def _build_claim_fixture(
    benchmark: BenchmarkPackage,
    claim: BenchmarkClaim,
) -> dict[str, Any]:
    evidence_by_id = {item.evidence_id: item for item in benchmark.evidence}
    evidence = tuple(evidence_by_id[item] for item in claim.evidence_ids)
    statement_id = f"summary_statement.literature_claim.{claim.claim_id.removeprefix('claim.')}"
    summary = _build_summary(benchmark, claim, statement_id, evidence)
    version_id = str(
        uuid5(
            NAMESPACE_URL,
            "xingwen.literature-claim-benchmark:"
            f"{claim.claim_id.removeprefix('claim.')}",
        )
    )
    claim_payload = {
        "source_statement_id": statement_id,
        "text": claim.text,
        "normalized_text": claim.normalized_text,
        "claim_type": claim.claim_type.value,
        "polarity": "neutral",
        "objects": [claim.paper_id],
        "metric": None,
        "unit": None,
        "conditions": list(claim.conditions),
        "scope": [],
        "limitations": [],
        "qualifiers": [],
        "uncertainty": None,
        "comparison_basis": None,
        "evidence_ids": list(claim.evidence_ids),
    }
    return {
        "pipeline": LiteratureClaimPipeline(
            clock=lambda: _benchmark_time(benchmark),
        ),
        "paper_id": claim.paper_id,
        "version_id": version_id,
        "versions": {
            version_id: PaperSummaryArtifactVersionInput(
                artifact_version_id=version_id,
                schema_version=summary.schema_version,
                content=summary,
            )
        },
        "claim_payload": claim_payload,
        "response": _response(claim_payload),
    }


def _build_summary(
    benchmark: BenchmarkPackage,
    claim: BenchmarkClaim,
    statement_id: str,
    benchmark_evidence: tuple[BenchmarkEvidence, ...],
) -> PaperSummaryArtifactContent:
    snapshots: list[PaperSummarySourceSnapshotReference] = []
    evidence: list[PaperSummaryEvidence] = []
    source_version = f"{benchmark.benchmark_id}@{benchmark.benchmark_version}"
    for item in benchmark_evidence:
        snapshot = PaperSummarySourceSnapshotReference(
            source_snapshot_id=(
                "source_snapshot.paper_benchmark."
                f"{item.evidence_id.removeprefix('evidence.')}"
            ),
            source_id="paper_benchmark",
            source_version=source_version,
            content_hash=compute_canonical_payload_hash(
                item.model_dump(mode="json", exclude_none=True)
            ),
        )
        snapshots.append(snapshot)
        evidence.append(
            PaperSummaryEvidence(
                evidence_id=item.evidence_id,
                paper_id=claim.paper_id,
                candidate_id=(
                    f"candidate.paper_benchmark.{claim.paper_id.removeprefix('paper.')}"
                ),
                source_id=snapshot.source_id,
                source_record_id=item.evidence_id,
                source_snapshot_id=snapshot.source_snapshot_id,
                source_snapshot_version=snapshot.source_version,
                source_snapshot_content_hash=snapshot.content_hash,
                locator=PaperSummaryEvidenceLocator.model_validate(
                    item.locator.model_dump(mode="json", exclude_none=True)
                ),
                quote_or_value=item.quote_or_value,
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            )
        )
    ordered_snapshots = tuple(sorted(snapshots, key=lambda item: item.source_snapshot_id))
    ordered_evidence = tuple(sorted(evidence, key=lambda item: item.evidence_id))
    input_versions = PaperSummaryInputVersions(
        paper_collection_version_id=str(
            uuid5(
                NAMESPACE_URL,
                "https://xingwen.example/paper-benchmark/"
                f"{claim.paper_id}/paper-collection",
            )
        ),
        paper_collection_schema_version="2.1.0",
        paper_collection_output_hash=compute_canonical_payload_hash(
            {
                "benchmark_id": benchmark.benchmark_id,
                "benchmark_version": benchmark.benchmark_version,
                "paper_id": claim.paper_id,
            }
        ),
        source_snapshots=ordered_snapshots,
    )
    input_hash = compute_canonical_payload_hash(
        {
            "benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
            "claim_id": claim.claim_id,
            "input_versions": input_versions.model_dump(mode="json"),
        }
    )
    prompt = PromptRegistry().get("paper_summary")
    producer = PaperSummaryProducerExecution(
        execution_id=f"execution.paper_benchmark_summary.{input_hash[7:31]}",
        producer_name=SUMMARY_PRODUCER_NAME,
        producer_version=SUMMARY_PRODUCER_VERSION,
        model_name=_REPLAY_MODEL_NAME,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        parameters_version=SUMMARY_PARAMETERS_VERSION,
        parameters_hash=compute_canonical_payload_hash(
            {
                "parameters_version": SUMMARY_PARAMETERS_VERSION,
                "parameters": _REPLAY_PARAMETERS,
            }
        ),
        input_versions=input_versions,
        input_hash=input_hash,
        model_response_hash=compute_canonical_payload_hash(
            claim.model_dump(mode="json", exclude_none=True)
        ),
        output_hash="sha256:" + "0" * 64,
        status="completed",
        started_at=_benchmark_time(benchmark),
        finished_at=_benchmark_time(benchmark),
        latency_ms=0,
    )
    statement = PaperSummaryStatement(
        statement_id=statement_id,
        text=claim.text,
        evidence_ids=tuple(sorted(claim.evidence_ids)),
        status=PaperSummarySupportStatus.supported,
        validation_code="evidence.supported",
    )
    statement_fields = _statement_fields(claim.claim_type, statement)
    payload = {
        "kind": "paper_summary",
        "schema_version": "2.0.0",
        "summary_id": claim.summary_id,
        "paper_id": claim.paper_id,
        "benchmark": PaperBenchmarkReference(
            benchmark_id=benchmark.benchmark_id,
            schema_version=benchmark.schema_version,
            benchmark_version=benchmark.benchmark_version,
            scientific_payload_hash=benchmark.scientific_payload_hash,
            content_hash=benchmark.content_hash,
            scenario_id=benchmark.search_scenarios[0].scenario_id,
        ).model_dump(mode="json"),
        "input_versions": input_versions.model_dump(mode="json"),
        **statement_fields,
        "evidence_ids": list(sorted(claim.evidence_ids)),
        "evidence": [item.model_dump(mode="json") for item in ordered_evidence],
        "source_conflicts": [],
        "producer": producer.model_dump(mode="json", exclude_none=True),
        "input_hash": input_hash,
        "output_hash": "sha256:" + "0" * 64,
    }
    output_hash = compute_paper_summary_output_hash(payload)
    payload["producer"]["output_hash"] = output_hash
    payload["output_hash"] = output_hash
    return _seal_paper_summary_for_publication(
        PaperSummaryArtifactContent.model_validate(payload)
    )


def _statement_fields(
    claim_type: ClaimType,
    statement: PaperSummaryStatement,
) -> dict[str, object]:
    fields: dict[str, object] = {
        "background": [],
        "methodology": [],
        "dataset": [],
        "experiments": [],
        "discussion": [],
        "limitations": [],
        "research_questions": [],
    }
    dumped = statement.model_dump(mode="json")
    if claim_type is ClaimType.goal:
        fields["background"] = [dumped]
    elif claim_type is ClaimType.method:
        fields["methodology"] = [dumped]
    elif claim_type is ClaimType.dataset:
        fields["dataset"] = [dumped]
    elif claim_type is ClaimType.limitation:
        fields["limitations"] = [dumped]
    elif claim_type is ClaimType.future_work:
        fields["research_questions"] = [dumped]
    else:
        fields["experiments"] = [dumped]
    return fields


def _response(claim_payload: dict[str, object]) -> str:
    return json.dumps(
        {"schema_version": "1.0.0", "claims": [deepcopy(claim_payload)]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _benchmark_time(benchmark: BenchmarkPackage) -> datetime:
    return datetime.combine(benchmark.created_at, time.min, tzinfo=timezone.utc)
