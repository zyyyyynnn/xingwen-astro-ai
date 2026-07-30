from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import ClaimType
from app.schemas.literature_claim import (
    LiteratureClaimBenchmarkEvaluationCase,
    LiteratureClaimBenchmarkReport,
    LiteratureClaimCandidate,
    LiteratureClaimExtractionOutput,
    LiteratureClaimFailureStage,
    LiteratureClaimRejectionReason,
    LiteratureClaimsCandidate,
    LiteratureClaimStatus,
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
from app.workflow.publisher import (
    PublicationAdmissionError,
    admit_artifact_candidate,
)
from packages.prompts.registry import (
    PromptRegistry,
    compute_prompt_content_hash,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim import (
    LiteratureClaimPipeline,
    PaperSummaryArtifactVersionInput,
)
from services.paper_pipeline.claim_benchmark import (
    evaluate_literature_claims,
    main as claim_benchmark_main,
)
from services.paper_pipeline.constants import (
    CLAIM_NORMALIZATION_VERSION,
    CLAIM_PARAMETERS_VERSION,
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
    FROZEN_X00_MAIN_SHA,
)


FIXED_TIME = datetime(2026, 7, 30, 9, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).parents[3]
SAFE_PARAMETERS = {
    "temperature": 0,
    "max_output_tokens": 2048,
    "response_format": "json_schema",
}
SUMMARY_VERSION_ID = "artifact_version.paper_summary.fixture"
PAPER_ID = "paper.ricker_2015_tess"
SUMMARY_ID = "summary.ricker_2015_tess"
STATEMENT_ID = "summary_statement.ricker_method"
EVIDENCE_ID = "evidence.claim_ricker_method"
SNAPSHOT_ID = "snapshot.arxiv.ricker_2015_tess"


def _summary(
    *,
    paper_id: str = PAPER_ID,
    summary_id: str = SUMMARY_ID,
    statement_id: str = STATEMENT_ID,
    evidence_id: str = EVIDENCE_ID,
    evidence_status: PaperSummarySupportStatus = PaperSummarySupportStatus.supported,
    evidence_paper_id: str | None = None,
) -> PaperSummaryArtifactContent:
    snapshot = PaperSummarySourceSnapshotReference(
        source_snapshot_id=SNAPSHOT_ID,
        source_id="arxiv",
        source_version="arxiv.1406.0151v1",
        content_hash=compute_canonical_payload_hash(
            {"source": "arxiv", "record": "1406.0151v1"}
        ),
    )
    input_versions = PaperSummaryInputVersions(
        paper_collection_version_id="artifact_version.paper_collection.fixture",
        paper_collection_schema_version="1.0.0",
        paper_collection_output_hash=compute_canonical_payload_hash(
            {"paper_collection": "fixture"}
        ),
        source_snapshots=(snapshot,),
    )
    evidence = PaperSummaryEvidence(
        evidence_id=evidence_id,
        paper_id=evidence_paper_id or paper_id,
        candidate_id="candidate.ricker_2015_tess",
        source_id=snapshot.source_id,
        source_record_id="1406.0151",
        source_snapshot_id=snapshot.source_snapshot_id,
        source_snapshot_version=snapshot.source_version,
        source_snapshot_content_hash=snapshot.content_hash,
        locator=PaperSummaryEvidenceLocator(
            kind="paper_text",
            source_url="https://arxiv.org/abs/1406.0151",
            section="abstract",
            paragraph=1,
            text_range="sentence 1",
        ),
        quote_or_value="TESS will search for planets transiting bright and nearby stars.",
        status=evidence_status,
        validation_code=(
            "evidence.supported"
            if evidence_status is PaperSummarySupportStatus.supported
            else "evidence.quote_not_found"
        ),
    )
    statement = PaperSummaryStatement(
        statement_id=statement_id,
        text="The mission uses transit photometry of bright and nearby stars.",
        evidence_ids=(evidence_id,),
        status=evidence_status,
        validation_code=evidence.validation_code,
    )
    input_hash = compute_canonical_payload_hash(
        {"summary": summary_id, "input_versions": input_versions.model_dump(mode="json")}
    )
    producer = PaperSummaryProducerExecution(
        execution_id="execution.paper_summary.fixture",
        producer_name="xingwen.paper_summary",
        producer_version="1.0.0",
        model_name="qwen.fixture.1",
        prompt_name="paper_summary",
        prompt_version="v2",
        prompt_hash=PromptRegistry().get("paper_summary", "v2").content_hash,
        parameters_version="1.0.0",
        parameters_hash=compute_canonical_payload_hash(SAFE_PARAMETERS),
        input_versions=input_versions,
        input_hash=input_hash,
        model_response_hash=compute_canonical_payload_hash({"summary": summary_id}),
        output_hash="sha256:" + "0" * 64,
        status="completed",
        started_at=FIXED_TIME,
        finished_at=FIXED_TIME,
        latency_ms=0,
    )
    payload = {
        "kind": "paper_summary",
        "schema_version": "1.0.0",
        "summary_id": summary_id,
        "paper_id": paper_id,
        "benchmark": PaperBenchmarkReference(
            benchmark_id="benchmark.paper_reasoning.exoplanet_host_star",
            schema_version=FROZEN_BENCHMARK_SCHEMA_VERSION,
            benchmark_version=FROZEN_BENCHMARK_VERSION,
            scientific_payload_hash=FROZEN_SCIENTIFIC_PAYLOAD_HASH,
            content_hash=FROZEN_BENCHMARK_CONTENT_HASH,
            scenario_id="search.tess_mission_and_catalogs",
            x00_main_sha=FROZEN_X00_MAIN_SHA,
        ).model_dump(mode="json"),
        "input_versions": input_versions.model_dump(mode="json"),
        "research_goal": None,
        "method": statement.model_dump(mode="json"),
        "dataset": None,
        "findings": [],
        "limitations": [],
        "future_work": [],
        "evidence_ids": [evidence_id],
        "evidence": [evidence.model_dump(mode="json")],
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


def _versions(
    summary: PaperSummaryArtifactContent | None = None,
    *,
    schema_version: str = "1.0.0",
) -> dict[str, PaperSummaryArtifactVersionInput]:
    content = summary or _summary()
    return {
        SUMMARY_VERSION_ID: PaperSummaryArtifactVersionInput(
            artifact_version_id=SUMMARY_VERSION_ID,
            schema_version=schema_version,
            content=content,
        )
    }


def _claim(
    *,
    claim_type: ClaimType | str = ClaimType.method,
    statement_id: str = STATEMENT_ID,
    evidence_ids: tuple[str, ...] = (EVIDENCE_ID,),
    text: str = "TESS searches for transiting planets around bright, nearby stars.",
    normalized_text: str = "TESS uses transit photometry targeting bright nearby stars.",
    objects: tuple[str, ...] = ("bright nearby stars",),
    metric: str | None = None,
    unit: str | None = None,
    conditions: tuple[str, ...] = (
        "Mission design described before completion of the prime mission",
    ),
    scope: tuple[str, ...] = ("TESS mission design",),
    limitations: tuple[str, ...] = (
        "Evidence is limited to the public abstract",
    ),
    qualifiers: tuple[str, ...] = (),
    uncertainty: str | None = None,
    comparison_basis: str | None = None,
    polarity: str = "positive",
) -> dict[str, object]:
    return {
        "source_statement_id": statement_id,
        "text": text,
        "normalized_text": normalized_text,
        "claim_type": str(claim_type),
        "polarity": polarity,
        "objects": list(objects),
        "metric": metric,
        "unit": unit,
        "conditions": list(conditions),
        "scope": list(scope),
        "limitations": list(limitations),
        "qualifiers": list(qualifiers),
        "uncertainty": uncertainty,
        "comparison_basis": comparison_basis,
        "evidence_ids": list(evidence_ids),
    }


def _response(*claims: dict[str, object]) -> str:
    return json.dumps(
        {"schema_version": "1.0.0", "claims": list(claims or (_claim(),))},
        ensure_ascii=False,
        sort_keys=True,
    )


def _admit(
    model_response: str,
    *,
    versions: dict[str, PaperSummaryArtifactVersionInput] | None = None,
    version_id: str = SUMMARY_VERSION_ID,
    paper_id: str = PAPER_ID,
    parameters: dict[str, object] | None = None,
    prompt_registry: PromptRegistry | None = None,
    available_evidence_ids: frozenset[str] | None = None,
    available_source_snapshot_ids: frozenset[str] | None = None,
    existing_claim_fingerprints: frozenset[str] = frozenset(),
):
    return LiteratureClaimPipeline(
        prompt_registry=prompt_registry,
        clock=lambda: FIXED_TIME,
    ).admit(
        paper_summary_artifact_version_id=version_id,
        paper_id=paper_id,
        paper_summary_versions=_versions() if versions is None else versions,
        model_response=model_response,
        model_name="qwen.fixture.1",
        parameters=parameters or SAFE_PARAMETERS,
        available_evidence_ids=available_evidence_ids,
        available_source_snapshot_ids=available_source_snapshot_ids,
        existing_claim_fingerprints=existing_claim_fingerprints,
    )


def test_claim_prompt_is_hash_pinned_and_schema_aligned() -> None:
    record = PromptRegistry().get("literature_claim")
    prompt_bytes = (ROOT / "packages" / "prompts" / record.path).read_bytes()

    assert record.version == "v1"
    assert record.output_models == ("LiteratureClaimExtractionOutput",)
    assert record.content_hash == (
        "sha256:054ab7dea308222716f4cf327c7b01f2781d05e8718bf47b331a62a28775ebe1"
    )
    assert b"\r" not in prompt_bytes
    assert f"sha256:{sha256(prompt_bytes).hexdigest()}" == record.content_hash
    assert compute_prompt_content_hash(prompt_bytes.decode("utf-8")) == (
        record.content_hash
    )
    assert "confidence" in record.content
    assert "ReasoningTrace" in record.content
    assert "chain-of-thought" in record.content


def test_model_output_requires_complete_strict_claim_shape() -> None:
    payload = json.loads(_response())
    del payload["claims"][0]["conditions"]

    with pytest.raises(ValidationError):
        LiteratureClaimExtractionOutput.model_validate(payload)


@pytest.mark.parametrize(
    "claim_type",
    (ClaimType.finding, ClaimType.method, ClaimType.dataset, ClaimType.limitation),
)
def test_primary_claim_types_reach_accepted_flow(claim_type: ClaimType) -> None:
    result = _admit(_response(_claim(claim_type=claim_type)))

    assert result.admission_status is LiteratureClaimStatus.accepted
    assert result.records[0].claim_type is claim_type
    assert result.records[0].status is LiteratureClaimStatus.accepted


def test_valid_claim_is_fully_traceable_and_publisher_ready() -> None:
    result = _admit(_response())

    assert result.admission_status is LiteratureClaimStatus.accepted
    assert result.publisher_candidate is not None
    candidate = result.publisher_candidate
    claim = result.records[0]
    assert claim.paper_id == PAPER_ID
    assert claim.source_paper_summary_artifact_version_id == SUMMARY_VERSION_ID
    assert claim.source_summary_id == SUMMARY_ID
    assert claim.source_statement_id == STATEMENT_ID
    assert claim.evidence_ids == (EVIDENCE_ID,)
    assert claim.source_snapshot_ids == (SNAPSHOT_ID,)
    assert claim.producer_execution_id == result.producer.execution_id
    assert claim.input_hash == result.producer.input_hash
    assert claim.model_response_hash == result.producer.model_response_hash
    assert candidate.input_versions.paper_summary_output_hash == _summary().output_hash
    assert candidate.producer.prompt_name == "literature_claim"
    assert candidate.producer.prompt_version == "v1"
    assert candidate.producer.model_name == "qwen.fixture.1"
    assert candidate.producer.parameters_version == CLAIM_PARAMETERS_VERSION
    assert candidate.producer.output_hash == candidate.output_hash
    assert candidate.status_counts.accepted == 1
    assert candidate.evidence_references[0].source_snapshot_id == SNAPSHOT_ID


def test_unsupported_summary_evidence_keeps_claim_as_candidate() -> None:
    summary = _summary(evidence_status=PaperSummarySupportStatus.unsupported)
    result = _admit(_response(), versions=_versions(summary))

    assert result.admission_status is LiteratureClaimStatus.candidate
    assert result.records[0].status is LiteratureClaimStatus.candidate
    assert result.records[0].rejection_reason is None
    assert result.publisher_candidate is not None


def test_invalid_json_is_rejected_without_retaining_raw_model_output() -> None:
    malicious = '{"claims":["private-chain-of-thought SUPER_SECRET"'
    result = _admit(malicious)
    serialized = result.model_dump_json()

    assert result.admission_status is LiteratureClaimStatus.rejected
    assert result.failure_stage is LiteratureClaimFailureStage.json
    assert result.rejection_reason is LiteratureClaimRejectionReason.invalid_json
    assert result.records == ()
    assert result.producer.status == "rejected"
    assert result.producer.output_hash == result.output_hash
    assert "SUPER_SECRET" not in serialized
    assert "private-chain-of-thought" not in serialized


def test_schema_invalid_is_rejected_before_input_version_check() -> None:
    result = _admit(
        json.dumps({"schema_version": "1.0.0", "claims": [{}]}),
        versions={},
        version_id="artifact_version.unknown",
    )

    assert result.failure_stage is LiteratureClaimFailureStage.schema
    assert result.rejection_reason is LiteratureClaimRejectionReason.schema_invalid


def test_invalid_json_has_priority_over_unknown_input_version() -> None:
    result = _admit(
        "{invalid",
        versions={},
        version_id="artifact_version.unknown",
    )

    assert result.failure_stage is LiteratureClaimFailureStage.json
    assert result.rejection_reason is LiteratureClaimRejectionReason.invalid_json


def test_unknown_input_artifact_version_is_stably_rejected() -> None:
    result = _admit(
        _response(),
        versions={},
        version_id="artifact_version.unknown",
    )

    record = result.records[0]
    assert record.status is LiteratureClaimStatus.rejected
    assert record.failure_stage is LiteratureClaimFailureStage.input
    assert record.rejection_reason is (
        LiteratureClaimRejectionReason.input_artifact_version_unknown
    )
    assert record.source_summary_id is None
    assert result.publisher_candidate is None


def test_unsupported_input_schema_version_is_stably_rejected() -> None:
    result = _admit(_response(), versions=_versions(schema_version="2.0.0"))

    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.input_schema_version_unsupported
    )


def test_missing_evidence_is_distinct_from_unknown_evidence() -> None:
    missing = _admit(_response(_claim(evidence_ids=())))
    unknown = _admit(
        _response(_claim(evidence_ids=("evidence.unknown",)))
    )

    assert missing.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.evidence_missing
    )
    assert unknown.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.evidence_not_found
    )


def test_external_evidence_and_snapshot_existence_are_checked_in_order() -> None:
    evidence_missing = _admit(
        _response(),
        available_evidence_ids=frozenset(),
        available_source_snapshot_ids=frozenset(),
    )
    snapshot_missing = _admit(
        _response(),
        available_evidence_ids=frozenset({EVIDENCE_ID}),
        available_source_snapshot_ids=frozenset(),
    )

    assert evidence_missing.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.evidence_not_found
    )
    assert snapshot_missing.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.source_snapshot_not_found
    )


@pytest.mark.parametrize(
    ("claim", "paper_id"),
    (
        (_claim(statement_id="summary_statement.unknown"), PAPER_ID),
        (_claim(), "paper.other"),
    ),
)
def test_summary_statement_and_paper_ownership_mismatch_is_rejected(
    claim: dict[str, object],
    paper_id: str,
) -> None:
    result = _admit(_response(claim), paper_id=paper_id)

    assert result.records[0].failure_stage is LiteratureClaimFailureStage.ownership
    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.ownership_mismatch
    )


def test_evidence_paper_ownership_mismatch_is_rejected() -> None:
    summary = _summary(evidence_paper_id="paper.other")
    result = _admit(_response(), versions=_versions(summary))

    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.ownership_mismatch
    )


def test_summary_version_repository_ownership_mismatch_is_rejected() -> None:
    summary = _summary()
    versions = {
        SUMMARY_VERSION_ID: PaperSummaryArtifactVersionInput(
            artifact_version_id="artifact_version.paper_summary.other",
            schema_version="1.0.0",
            content=summary,
        )
    }

    result = _admit(_response(), versions=versions)

    assert result.records[0].failure_stage is LiteratureClaimFailureStage.ownership
    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.ownership_mismatch
    )
    assert (
        result.records[0].source_paper_summary_artifact_version_id
        == SUMMARY_VERSION_ID
    )


def test_normalization_preserves_negation_conditions_limits_and_uncertainty() -> None:
    claim = _claim(
        text="The public abstract does not establish observed mission yield.",
        normalized_text="The public abstract does not establish observed mission yield.",
        polarity="negative",
        conditions=("Only the provided public abstract is considered",),
        scope=("Observed prime-mission yield",),
        limitations=("No completed yield catalog is provided",),
        qualifiers=("does not establish",),
        uncertainty="The observed yield remains unverified",
    )

    result = _admit(_response(claim))
    admitted = result.records[0]

    assert admitted.status is LiteratureClaimStatus.accepted
    assert "not" in admitted.normalized_text
    assert admitted.conditions == tuple(claim["conditions"])
    assert admitted.scope == tuple(claim["scope"])
    assert admitted.limitations == tuple(claim["limitations"])
    assert admitted.qualifiers == tuple(claim["qualifiers"])
    assert admitted.uncertainty == claim["uncertainty"]


@pytest.mark.parametrize(
    "claim",
    (
        _claim(metric="radius", unit="R or R_sun"),
        _claim(objects=("TESS candidates", "confirmed planets")),
        _claim(
            text="The abstract does not establish yield.",
            normalized_text="The abstract establishes yield.",
            polarity="negative",
        ),
    ),
)
def test_unsafe_normalization_and_incomparable_object_merge_are_rejected(
    claim: dict[str, object],
) -> None:
    result = _admit(_response(claim))

    assert result.records[0].failure_stage is (
        LiteratureClaimFailureStage.normalization
    )
    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.normalization_unsafe
    )


def test_known_unit_alias_is_normalized_without_conversion() -> None:
    result = _admit(_response(_claim(metric="temperature", unit="kelvin")))

    assert result.records[0].unit == "K"


def test_exact_structured_duplicate_is_rejected_but_conditions_are_not_merged() -> None:
    first = _claim()
    duplicate = _claim()
    different_condition = _claim(
        conditions=("Applies to the completed prime mission",)
    )
    result = _admit(_response(first, duplicate, different_condition))

    assert result.publisher_candidate is not None
    assert result.publisher_candidate.status_counts.accepted == 2
    assert result.publisher_candidate.status_counts.rejected == 1
    assert sum(
        item.rejection_reason is LiteratureClaimRejectionReason.duplicate_claim
        for item in result.records
    ) == 1
    assert len({item.fingerprint for item in result.records}) == 2


def test_existing_structured_fingerprint_is_rejected() -> None:
    first = _admit(_response())
    fingerprint = first.records[0].fingerprint
    repeated = _admit(
        _response(),
        existing_claim_fingerprints=frozenset({fingerprint}),
    )

    assert repeated.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.duplicate_claim
    )


def test_hashes_are_stable_across_key_claim_and_parameter_order() -> None:
    first_payload = json.loads(_response(_claim(), _claim(
        claim_type=ClaimType.limitation,
        text="The abstract does not establish observed mission yield.",
        normalized_text="The abstract does not establish observed mission yield.",
        polarity="negative",
    )))
    reversed_payload = dict(reversed(tuple(first_payload.items())))
    reversed_payload["claims"] = list(reversed(first_payload["claims"]))

    first = _admit(json.dumps(first_payload))
    reordered = _admit(
        json.dumps(reversed_payload),
        parameters=dict(reversed(tuple(SAFE_PARAMETERS.items()))),
    )

    assert first.producer.input_hash == reordered.producer.input_hash
    assert first.producer.parameters_hash == reordered.producer.parameters_hash
    assert first.producer.model_response_hash == reordered.producer.model_response_hash
    assert first.output_hash == reordered.output_hash
    assert tuple(item.claim_id for item in first.records) == tuple(
        item.claim_id for item in reordered.records
    )


def test_parameter_and_input_version_changes_change_hashes() -> None:
    first = _admit(_response())
    changed_parameters = _admit(
        _response(),
        parameters={**SAFE_PARAMETERS, "temperature": 1},
    )
    changed_version = _admit(
        _response(),
        versions={
            "artifact_version.paper_summary.revision_2": (
                PaperSummaryArtifactVersionInput(
                    artifact_version_id="artifact_version.paper_summary.revision_2",
                    schema_version="1.0.0",
                    content=_summary(),
                )
            )
        },
        version_id="artifact_version.paper_summary.revision_2",
    )

    assert first.producer.input_hash != changed_parameters.producer.input_hash
    assert first.output_hash != changed_parameters.output_hash
    assert first.producer.input_hash != changed_version.producer.input_hash
    assert first.output_hash != changed_version.output_hash


def test_prompt_version_change_changes_input_and_output_hashes(tmp_path: Path) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(ROOT / "packages" / "prompts", prompt_root)
    v1 = prompt_root / "literature_claim" / "v1.md"
    v2 = prompt_root / "literature_claim" / "v2.md"
    v2_content = v1.read_text(encoding="utf-8").replace(
        "version: v1",
        "version: v2",
        1,
    )
    v2.write_text(v2_content, encoding="utf-8", newline="\n")
    registry_path = prompt_root / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["prompts"]["literature_claim"]["current"] = "v2"
    registry["prompts"]["literature_claim"]["versions"]["v2"] = {
        "path": "literature_claim/v2.md",
        "content_hash": compute_prompt_content_hash(v2_content),
        "output_models": ["LiteratureClaimExtractionOutput"],
        "status": "active",
    }
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    first = _admit(_response())
    second = _admit(
        _response(),
        prompt_registry=PromptRegistry(prompt_root),
    )

    assert first.producer.prompt_version == "v1"
    assert second.producer.prompt_version == "v2"
    assert first.producer.input_hash != second.producer.input_hash
    assert first.output_hash != second.output_hash


def test_output_hash_tampering_fails_candidate_schema() -> None:
    result = _admit(_response())
    assert result.publisher_candidate is not None
    payload = result.publisher_candidate.model_dump(mode="json")
    payload["output_hash"] = "sha256:" + "0" * 64

    with pytest.raises(ValidationError, match="output_hash does not match"):
        LiteratureClaimsCandidate.model_validate(payload)


def test_publisher_ready_candidate_passes_structured_admission_port() -> None:
    result = _admit(_response())
    assert result.publisher_candidate is not None

    admitted = admit_artifact_candidate(
        result.publisher_candidate,
        schema_version=result.publisher_candidate.schema_version,
        source_snapshot_ids=result.publisher_candidate.source_snapshot_ids,
        evidence_ids=result.publisher_candidate.evidence_ids,
        evidence_validator=lambda _: None,
        domain_validator=lambda _: None,
        quality_validator=lambda _: None,
    )

    assert admitted.content["kind"] == "literature_claims"
    assert admitted.content["output_hash"] == result.output_hash
    reparsed = LiteratureClaimsCandidate.model_validate(admitted.content)
    assert reparsed.claims == result.records


def test_intermediate_model_output_cannot_bypass_publisher() -> None:
    model_output = LiteratureClaimExtractionOutput.model_validate_json(_response())

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        admit_artifact_candidate(
            model_output,
            schema_version="1.0.0",
            source_snapshot_ids=(SNAPSHOT_ID,),
            evidence_ids=(EVIDENCE_ID,),
            evidence_validator=lambda _: None,
            domain_validator=lambda _: None,
            quality_validator=lambda _: None,
        )


def test_fixed_d01_claim_benchmark_is_reproducible_and_uses_approved_labels() -> None:
    benchmark = load_frozen_benchmark()
    expected = benchmark.claims[0]
    summary = _summary(
        paper_id=expected.paper_id,
        summary_id=expected.summary_id,
        statement_id=STATEMENT_ID,
        evidence_id=expected.evidence_ids[0],
    )
    exact_claim = _claim(
        claim_type=expected.claim_type,
        evidence_ids=expected.evidence_ids,
        text=expected.text,
        normalized_text=expected.normalized_text,
        conditions=expected.conditions,
    )
    accepted = _admit(_response(exact_claim), versions=_versions(summary))
    invalid = _admit("{invalid")
    cases = (
        LiteratureClaimBenchmarkEvaluationCase(
            case_id="claim_eval.accepted",
            benchmark_claim_id=expected.claim_id,
            record_claim_id=accepted.records[0].claim_id,
            admission=accepted,
        ),
        LiteratureClaimBenchmarkEvaluationCase(
            case_id="claim_eval.invalid_json",
            benchmark_claim_id=benchmark.claims[1].claim_id,
            record_claim_id=None,
            admission=invalid,
        ),
    )

    first = evaluate_literature_claims(benchmark=benchmark, cases=cases)
    second = evaluate_literature_claims(
        benchmark=benchmark,
        cases=tuple(reversed(cases)),
    )

    assert first == second
    assert first.benchmark_version == FROZEN_BENCHMARK_VERSION
    assert first.sample_count == 2
    assert first.schema_items_valid == 1
    assert first.schema_pass_rate == 0.5
    assert first.evidence_items_supported == 1
    assert first.evidence_items_total == 1
    assert first.evidence_coverage == 1.0
    assert first.scientific_review_items_correct == 1
    assert first.scientific_review_items_total == 2
    assert first.scientific_review_accuracy == 0.5
    assert first.status_counts.accepted == 1
    assert first.status_counts.rejected == 1
    assert first.rejection_counts[0].rejection_reason is (
        LiteratureClaimRejectionReason.invalid_json
    )
    assert first.rejection_counts[0].sample_case_ids == (
        "claim_eval.invalid_json",
    )
    assert first.input_hash.startswith("sha256:")
    assert first.output_hash.startswith("sha256:")


def test_claim_benchmark_cli_writes_valid_stable_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    benchmark = load_frozen_benchmark()
    expected = benchmark.claims[0]
    summary = _summary(
        paper_id=expected.paper_id,
        summary_id=expected.summary_id,
        evidence_id=expected.evidence_ids[0],
    )
    admission = _admit(
        _response(
            _claim(
                claim_type=expected.claim_type,
                evidence_ids=expected.evidence_ids,
                text=expected.text,
                normalized_text=expected.normalized_text,
                conditions=expected.conditions,
            )
        ),
        versions=_versions(summary),
    )
    case = LiteratureClaimBenchmarkEvaluationCase(
        case_id="claim_eval.cli",
        benchmark_claim_id=expected.claim_id,
        record_claim_id=admission.records[0].claim_id,
        admission=admission,
    )
    cases_path = tmp_path / "cases.json"
    report_path = tmp_path / "report.json"
    cases_path.write_text(
        json.dumps(
            [case.model_dump(mode="json", exclude_none=True)],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claim_benchmark",
            "--cases",
            str(cases_path),
            "--output",
            str(report_path),
        ],
    )

    assert claim_benchmark_main() == 0
    report = LiteratureClaimBenchmarkReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    assert report.sample_count == 1
    assert report.scientific_review_accuracy == 1.0
    assert report.output_hash.startswith("sha256:")


def test_producer_and_normalization_versions_are_explicit() -> None:
    result = _admit(_response())

    assert result.producer.producer_name == CLAIM_PRODUCER_NAME
    assert result.producer.producer_version == CLAIM_PRODUCER_VERSION
    assert result.producer.parameters_version == CLAIM_PARAMETERS_VERSION
    assert result.records[0].normalization_version == CLAIM_NORMALIZATION_VERSION
    assert result.producer.schema_version == "1.0.0"


def test_full_candidate_round_trip_uses_one_pydantic_authoring_model() -> None:
    result = _admit(_response())
    assert result.publisher_candidate is not None
    payload = result.publisher_candidate.model_dump_json(exclude_none=True)

    reparsed = LiteratureClaimsCandidate.model_validate_json(payload)
    claim = LiteratureClaimCandidate.model_validate(
        reparsed.claims[0].model_dump(mode="json", exclude_none=True)
    )

    assert claim == result.records[0]
