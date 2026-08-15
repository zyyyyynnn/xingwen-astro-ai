from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import ClaimType
from app.schemas.literature_claim import (
    LiteratureClaimAdmissionResult,
    LiteratureClaimBenchmarkCaseKind,
    LiteratureClaimBenchmarkEvaluationCase,
    LiteratureClaimBenchmarkReport,
    LiteratureClaimCandidate,
    LiteratureClaimExtractionOutput,
    LiteratureClaimFailureStage,
    LiteratureClaimInputVersions,
    LiteratureClaimRejectionReason,
    LiteratureClaimsCandidate,
    LiteratureClaimStatus,
)
from app.schemas.paper_benchmark import BenchmarkReviewStatus
from app.schemas.paper_collection import PaperBenchmarkReference
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryCollectionReference,
    PaperSummaryEvidence,
    PaperSummaryEvidenceLocator,
    PaperSummaryInputVersions,
    PaperSummaryItemKind,
    PaperSummaryPaperMetadata,
    PaperSummaryProducerExecution,
    PaperSummarySourceSnapshotReference,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
    _seal_paper_summary_for_publication,
    compute_paper_summary_output_hash,
)
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    PublicationAdmissionError,
    admit_artifact_candidate,
)
from pydantic import ValidationError

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
    validate_scientific_label_coverage,
)
from services.paper_pipeline.claim_benchmark import (
    main as claim_benchmark_main,
)
from services.paper_pipeline.claim_benchmark_cases import (
    build_frozen_claim_benchmark_cases,
)
from services.paper_pipeline.constants import (
    CLAIM_NORMALIZATION_VERSION,
    CLAIM_PARAMETERS_VERSION,
    CLAIM_PRODUCER_NAME,
    CLAIM_PRODUCER_VERSION,
    CLAIM_SCHEMA_VERSION,
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
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


def test_literature_claim_input_accepts_digit_leading_persistent_uuid() -> None:
    artifact_version_id = "00000000-0000-0000-0000-00000000044c"

    input_versions = LiteratureClaimInputVersions(
        paper_summary_artifact_version_id=artifact_version_id,
        paper_id=PAPER_ID,
        source_snapshots=(),
    )

    assert input_versions.paper_summary_artifact_version_id == artifact_version_id


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
        collection=PaperSummaryCollectionReference(
            artifact_version_id="artifact_version.paper_collection.fixture",
            schema_version="2.0.0",
            output_hash=compute_canonical_payload_hash(
                {"paper_collection": "fixture"}
            ),
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
        item_kind=PaperSummaryItemKind.workflow_step,
        text="The mission uses transit photometry of bright and nearby stars.",
        evidence_ids=(evidence_id,),
        status=evidence_status,
        validation_code=evidence.validation_code,
    )
    input_hash = compute_canonical_payload_hash(
        {
            "summary": summary_id,
            "input_versions": input_versions.model_dump(mode="json"),
        }
    )
    producer = PaperSummaryProducerExecution(
        execution_id="execution.paper_summary.fixture",
        producer_name="xingwen.paper_summary",
        producer_version="1.0.0",
        model_name="qwen.fixture.1",
        prompt_name="paper_summary",
        prompt_version="4.0.0",
        prompt_hash=PromptRegistry().get("paper_summary").content_hash,
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
        "schema_version": "3.0.0",
        "summary_id": summary_id,
        "paper_id": paper_id,
        "paper": PaperSummaryPaperMetadata(
            paper_id=paper_id,
            title=paper_id,
        ).model_dump(mode="json"),
        "benchmark": PaperBenchmarkReference(
            benchmark_id="benchmark.paper_reasoning.exoplanet_host_star",
            schema_version=FROZEN_BENCHMARK_SCHEMA_VERSION,
            benchmark_version=FROZEN_BENCHMARK_VERSION,
            scientific_payload_hash=FROZEN_SCIENTIFIC_PAYLOAD_HASH,
            content_hash=FROZEN_BENCHMARK_CONTENT_HASH,
            scenario_id="search.tess_mission_and_catalogs",
        ).model_dump(mode="json"),
        "input_versions": input_versions.model_dump(mode="json"),
        "background": {
            "section_kind": "background",
            "overview": None,
            "items": [],
        },
        "methodology": {
            "section_kind": "methodology",
            "overview": None,
            "items": [statement.model_dump(mode="json")],
        },
        "dataset": {
            "section_kind": "dataset",
            "overview": None,
            "items": [],
        },
        "experiments": {
            "section_kind": "experiments",
            "overview": None,
            "items": [],
        },
        "discussion": {
            "section_kind": "discussion",
            "overview": None,
            "items": [],
        },
        "limitations": {
            "section_kind": "limitations",
            "overview": None,
            "items": [],
        },
        "research_questions": {
            "section_kind": "research_questions",
            "overview": None,
            "items": [],
        },
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
    schema_version: str = "3.0.0",
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
    limitations: tuple[str, ...] = ("Evidence is limited to the public abstract",),
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
    execution_id: str | None = None,
    run_id: str | None = None,
    now: datetime = FIXED_TIME,
):
    return LiteratureClaimPipeline(
        prompt_registry=prompt_registry,
        clock=lambda: now,
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
        execution_id=execution_id,
        run_id=run_id,
    )


def test_claim_prompt_is_hash_pinned_and_schema_aligned() -> None:
    record = PromptRegistry().get("literature_claim")
    prompt_bytes = (ROOT / "packages" / "prompts" / record.path).read_bytes()

    assert record.version == "1.0.0"
    assert record.output_models == ("LiteratureClaimExtractionOutput",)
    assert record.content_hash == (
        "sha256:246c9b390d553122b5cf1d5286a64e40f16b56fb56b24417cec1c336b95a48db"
    )
    assert b"\r" not in prompt_bytes
    assert f"sha256:{sha256(prompt_bytes).hexdigest()}" == record.content_hash
    assert compute_prompt_content_hash(prompt_bytes.decode("utf-8")) == (
        record.content_hash
    )
    assert "confidence" in record.content
    assert "ReasoningTrace" in record.content
    assert "chain-of-thought" in record.content


def test_claim_input_hash_pins_schema_version() -> None:
    result = _admit(_response())
    prompt = PromptRegistry().get("literature_claim")
    parameters_hash = compute_canonical_payload_hash(
        {
            "parameters_version": CLAIM_PARAMETERS_VERSION,
            "parameters": SAFE_PARAMETERS,
        }
    )
    payload = {
        "input_versions": result.producer.input_versions.model_dump(
            mode="json", exclude_none=True
        ),
        "prompt_name": prompt.name,
        "prompt_version": prompt.version,
        "prompt_hash": prompt.content_hash,
        "model_name": "qwen.fixture.1",
        "parameters_version": CLAIM_PARAMETERS_VERSION,
        "parameters_hash": parameters_hash,
        "producer_version": CLAIM_PRODUCER_VERSION,
        "schema_version": CLAIM_SCHEMA_VERSION,
        "normalization_version": CLAIM_NORMALIZATION_VERSION,
    }

    assert result.producer.schema_version == CLAIM_SCHEMA_VERSION
    assert result.publisher_candidate is not None
    assert result.publisher_candidate.schema_version == CLAIM_SCHEMA_VERSION
    assert result.producer.input_hash == compute_canonical_payload_hash(payload)
    payload.pop("schema_version")
    assert result.producer.input_hash != compute_canonical_payload_hash(payload)


def test_tracked_literature_claim_schema_contracts_match_authoring_models() -> None:
    models = {
        model.__name__: model
        for model in (
            LiteratureClaimExtractionOutput,
            LiteratureClaimCandidate,
            LiteratureClaimAdmissionResult,
            LiteratureClaimsCandidate,
            LiteratureClaimBenchmarkEvaluationCase,
            LiteratureClaimBenchmarkReport,
        )
    }
    output = ROOT / "packages" / "schemas" / "generated" / "literature_claim"
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert {item["name"] for item in manifest["models"]} == set(models)
    for name, model in models.items():
        generated = json.loads(
            (output / "json" / f"{name}.schema.json").read_text(encoding="utf-8")
        )
        assert generated == model.model_json_schema()


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
    assert candidate.producer.prompt_version == "1.0.0"
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
    result = _admit(_response(), versions=_versions(schema_version="1.0.0"))

    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.input_schema_version_unsupported
    )


def test_missing_evidence_is_distinct_from_unknown_evidence() -> None:
    missing = _admit(_response(_claim(evidence_ids=())))
    unknown = _admit(_response(_claim(evidence_ids=("evidence.unknown",))))

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
            schema_version="3.0.0",
            content=summary,
        )
    }

    result = _admit(_response(), versions=versions)

    assert result.records[0].failure_stage is LiteratureClaimFailureStage.ownership
    assert result.records[0].rejection_reason is (
        LiteratureClaimRejectionReason.ownership_mismatch
    )
    assert (
        result.records[0].source_paper_summary_artifact_version_id == SUMMARY_VERSION_ID
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
    different_condition = _claim(conditions=("Applies to the completed prime mission",))
    result = _admit(_response(first, duplicate, different_condition))

    assert result.publisher_candidate is not None
    assert result.publisher_candidate.status_counts.accepted == 2
    assert result.publisher_candidate.status_counts.rejected == 1
    assert (
        sum(
            item.rejection_reason is LiteratureClaimRejectionReason.duplicate_claim
            for item in result.records
        )
        == 1
    )
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
    first_payload = json.loads(
        _response(
            _claim(),
            _claim(
                claim_type=ClaimType.limitation,
                text="The abstract does not establish observed mission yield.",
                normalized_text="The abstract does not establish observed mission yield.",
                polarity="negative",
            ),
        )
    )
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


@pytest.mark.parametrize(
    ("model_response", "expected_status"),
    (
        (_response(), LiteratureClaimStatus.accepted),
        (
            _response(_claim(evidence_ids=())),
            LiteratureClaimStatus.rejected,
        ),
        ("{invalid", LiteratureClaimStatus.rejected),
    ),
    ids=("accepted", "record_rejected", "json_rejected"),
)
def test_execution_runtime_does_not_change_stable_hashes(
    model_response: str,
    expected_status: LiteratureClaimStatus,
) -> None:
    first = _admit(
        model_response,
        execution_id="execution.explicit.a",
        run_id="run.explicit.a",
        now=FIXED_TIME,
    )
    second = _admit(
        model_response,
        execution_id="execution.explicit.b",
        run_id="run.explicit.b",
        now=FIXED_TIME + timedelta(minutes=5),
    )

    assert first.admission_status is expected_status
    assert second.admission_status is expected_status
    assert first.producer.execution_id != second.producer.execution_id
    assert first.producer.run_id != second.producer.run_id
    assert first.producer.started_at != second.producer.started_at
    assert first.producer.input_hash == second.producer.input_hash
    assert first.producer.model_response_hash == second.producer.model_response_hash
    assert first.output_hash == second.output_hash
    if first.records:
        assert tuple(item.producer_execution_id for item in first.records) != tuple(
            item.producer_execution_id for item in second.records
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


def test_prompt_definition_change_changes_input_and_output_hashes(
    tmp_path: Path,
) -> None:
    prompt_root = tmp_path / "prompts"
    shutil.copytree(ROOT / "packages" / "prompts", prompt_root)
    prompt_path = prompt_root / "literature_claim" / "prompt.md"
    changed_content = prompt_path.read_text(encoding="utf-8").replace(
        "version: 1.0.0",
        "version: 2.0.0",
        1,
    )
    prompt_path.write_text(changed_content, encoding="utf-8", newline="\n")
    registry_path = prompt_root / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["prompts"]["literature_claim"]["version"] = "2.0.0"
    registry["prompts"]["literature_claim"]["content_hash"] = (
        compute_prompt_content_hash(changed_content)
    )
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

    assert first.producer.prompt_version == "1.0.0"
    assert second.producer.prompt_version == "2.0.0"
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
    snapshot_bindings = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=item,
            persisted_source_snapshot_id=str(
                uuid5(NAMESPACE_URL, f"claim-snapshot:{item}")
            ),
        )
        for item in result.publisher_candidate.source_snapshot_ids
    )
    persisted_snapshots = {
        item.pipeline_source_snapshot_id: item.persisted_source_snapshot_id
        for item in snapshot_bindings
    }
    evidence_bindings = tuple(
        ArtifactEvidenceBinding(
            target_type="claim",
            target_id=item.claim_id,
            pipeline_evidence_id=item.evidence_id,
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_evidence_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"claim-evidence:{item.claim_id}:{item.evidence_id}",
                )
            ),
            persisted_source_snapshot_id=persisted_snapshots[item.source_snapshot_id],
        )
        for item in result.publisher_candidate.evidence_references
    )

    def validate_context(context: ArtifactAdmissionContext) -> None:
        assert context.candidate is result.publisher_candidate
        assert (
            context.source_snapshot_ids
            == result.publisher_candidate.source_snapshot_ids
        )
        assert context.evidence_ids == result.publisher_candidate.evidence_ids
        assert context.persisted_source_snapshot_ids == tuple(
            item.persisted_source_snapshot_id for item in snapshot_bindings
        )
        assert context.persisted_evidence_ids == tuple(
            item.persisted_evidence_id for item in evidence_bindings
        )

    admitted = admit_artifact_candidate(
        result.publisher_candidate,
        schema_version=result.publisher_candidate.schema_version,
        source_snapshot_ids=result.publisher_candidate.source_snapshot_ids,
        evidence_ids=result.publisher_candidate.evidence_ids,
        evidence_validator=validate_context,
        domain_validator=validate_context,
        quality_validator=validate_context,
        source_snapshot_bindings=snapshot_bindings,
        evidence_bindings=evidence_bindings,
    )
    publication = ArtifactPublication(
        artifact_id=uuid4(),
        publication_key="literature_claim-benchmark-fixture",
        producer_execution_id=uuid4(),
        candidate=admitted,
        source_mode="fixture",
    )

    assert admitted.content["kind"] == "literature_claims"
    assert admitted.content["output_hash"] == result.output_hash
    assert admitted.content_hash == compute_canonical_payload_hash(admitted.content)
    assert publication.candidate is admitted
    reparsed = LiteratureClaimsCandidate.model_validate(admitted.content)
    assert reparsed.claims == result.records

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        admit_artifact_candidate(
            reparsed,
            schema_version=reparsed.schema_version,
            source_snapshot_ids=reparsed.source_snapshot_ids,
            evidence_ids=reparsed.evidence_ids,
            evidence_validator=lambda _: None,
            domain_validator=lambda _: None,
            quality_validator=lambda _: None,
        )


def test_publisher_seal_is_bound_to_original_candidate_instance() -> None:
    result = _admit(_response())
    assert result.publisher_candidate is not None
    copied = result.publisher_candidate.model_copy()
    deep_copied = result.publisher_candidate.model_copy(deep=True)
    tampered = result.publisher_candidate.model_copy(
        update={"output_hash": "sha256:" + "0" * 64}
    )

    for candidate in (copied, deep_copied, tampered):
        with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
            admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                evidence_validator=lambda _: None,
                domain_validator=lambda _: None,
                quality_validator=lambda _: None,
            )


def test_intermediate_model_output_cannot_bypass_publisher() -> None:
    model_output = LiteratureClaimExtractionOutput.model_validate_json(_response())

    for candidate in (model_output, model_output.claims[0]):
        with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
            admit_artifact_candidate(
                candidate,
                schema_version="3.0.0",
                source_snapshot_ids=(SNAPSHOT_ID,),
                evidence_ids=(EVIDENCE_ID,),
                evidence_validator=lambda _: None,
                domain_validator=lambda _: None,
                quality_validator=lambda _: None,
            )


def test_non_authoritative_claim_models_cannot_bypass_publisher() -> None:
    result = _admit(_response())
    for candidate in (result.records[0], result):
        with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
            admit_artifact_candidate(
                candidate,
                schema_version="1.0.0",
                source_snapshot_ids=(SNAPSHOT_ID,),
                evidence_ids=(EVIDENCE_ID,),
                evidence_validator=lambda _: None,
                domain_validator=lambda _: None,
                quality_validator=lambda _: None,
            )


def test_fixed_paper_benchmark_claim_benchmark_is_reproducible_and_uses_approved_labels() -> (
    None
):
    benchmark = load_frozen_benchmark()
    cases = build_frozen_claim_benchmark_cases(benchmark)
    approved_ids = {
        item.claim_id
        for item in benchmark.claims
        if item.review_status is BenchmarkReviewStatus.approved
    }
    scientific_ids = {
        case.benchmark_claim_id
        for case in cases
        if case.case_kind is LiteratureClaimBenchmarkCaseKind.scientific_label
    }

    validate_scientific_label_coverage(benchmark, cases)
    first = evaluate_literature_claims(benchmark=benchmark, cases=cases)
    second = evaluate_literature_claims(
        benchmark=benchmark,
        cases=tuple(reversed(cases)),
    )

    assert len(approved_ids) == 8
    assert scientific_ids == approved_ids
    assert first == second
    assert first.benchmark_schema_version == FROZEN_BENCHMARK_SCHEMA_VERSION
    assert first.benchmark_version == FROZEN_BENCHMARK_VERSION
    assert first.benchmark_scientific_payload_hash == FROZEN_SCIENTIFIC_PAYLOAD_HASH
    assert first.benchmark_content_hash == FROZEN_BENCHMARK_CONTENT_HASH
    assert first.sample_count == len(approved_ids) + 4
    assert first.schema_items_valid == first.sample_count - 1
    assert first.schema_items_total == first.sample_count
    assert first.rejection_cases_passed == 4
    assert first.rejection_cases_total == 4
    assert first.rejection_case_pass_rate == 1.0
    assert first.evidence_items_supported == len(approved_ids)
    assert first.evidence_items_total == len(approved_ids)
    assert first.evidence_coverage_rate == 1.0
    assert first.scientific_label_items_exact == len(approved_ids)
    assert first.scientific_label_items_total == len(approved_ids)
    assert first.scientific_label_exact_match_rate == 1.0
    assert all(
        item.scientific_label_exact_match is None
        for item in first.cases
        if item.case_kind is LiteratureClaimBenchmarkCaseKind.rejection_case
    )
    assert first.input_hash.startswith("sha256:")
    assert first.output_hash.startswith("sha256:")


def test_claim_benchmark_metric_denominators_and_empty_subsets() -> None:
    benchmark = load_frozen_benchmark()
    cases = build_frozen_claim_benchmark_cases(benchmark)
    scientific = tuple(
        case
        for case in cases
        if case.case_kind is LiteratureClaimBenchmarkCaseKind.scientific_label
    )
    rejections = tuple(
        case
        for case in cases
        if case.case_kind is LiteratureClaimBenchmarkCaseKind.rejection_case
    )

    scientific_report = evaluate_literature_claims(
        benchmark=benchmark,
        cases=scientific,
    )
    rejection_report = evaluate_literature_claims(
        benchmark=benchmark,
        cases=rejections,
    )

    assert scientific_report.schema_pass_rate == 1.0
    assert scientific_report.scientific_label_exact_match_rate == 1.0
    assert scientific_report.evidence_coverage_rate == 1.0
    assert scientific_report.rejection_cases_total == 0
    assert scientific_report.rejection_case_pass_rate is None
    assert rejection_report.schema_items_valid == 3
    assert rejection_report.schema_items_total == 4
    assert rejection_report.schema_pass_rate == 0.75
    assert rejection_report.rejection_case_pass_rate == 1.0
    assert rejection_report.scientific_label_items_total == 0
    assert rejection_report.scientific_label_exact_match_rate is None
    assert rejection_report.evidence_items_total == 0
    assert rejection_report.evidence_coverage_rate is None
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_literature_claims(benchmark=benchmark, cases=())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("schema_version", "1.3.1"),
        ("benchmark_version", "1.3.1"),
        ("scientific_payload_hash", "sha256:" + "1" * 64),
        ("content_hash", "sha256:" + "2" * 64),
    ),
)
def test_claim_benchmark_rejects_paper_benchmark_identity_mismatch(
    field: str,
    value: str,
) -> None:
    benchmark = load_frozen_benchmark()
    cases = build_frozen_claim_benchmark_cases(benchmark)
    changed = benchmark.model_copy(update={field: value})

    with pytest.raises(
        ValueError, match="frozen paper acquisition benchmark identity mismatch"
    ):
        evaluate_literature_claims(benchmark=changed, cases=cases)


def test_formal_claim_benchmark_rejects_incomplete_scientific_coverage() -> None:
    benchmark = load_frozen_benchmark()
    cases = build_frozen_claim_benchmark_cases(benchmark)
    incomplete = tuple(
        case
        for case in cases
        if case.case_id != "scientific.claim.ricker_expected_yield"
    )

    with pytest.raises(
        ValueError,
        match="every approved Paper Acquisition Benchmark Claim exactly once",
    ):
        validate_scientific_label_coverage(benchmark, incomplete)


def test_claim_benchmark_ignores_execution_runtime_in_content_hash() -> None:
    benchmark = load_frozen_benchmark()
    first_admission = _admit(
        _response(),
        execution_id="execution.benchmark.a",
        run_id="run.benchmark.a",
        now=FIXED_TIME,
    )
    second_admission = _admit(
        _response(),
        execution_id="execution.benchmark.b",
        run_id="run.benchmark.b",
        now=FIXED_TIME + timedelta(minutes=5),
    )

    def evaluation_case(
        admission: LiteratureClaimAdmissionResult,
    ) -> LiteratureClaimBenchmarkEvaluationCase:
        return LiteratureClaimBenchmarkEvaluationCase(
            case_id="scientific.runtime_stability",
            case_kind=LiteratureClaimBenchmarkCaseKind.scientific_label,
            benchmark_claim_id="claim.ricker_transit_bright_stars",
            record_claim_id=admission.records[0].claim_id,
            admission=admission,
        )

    first = evaluate_literature_claims(
        benchmark=benchmark,
        cases=(evaluation_case(first_admission),),
    )
    second = evaluate_literature_claims(
        benchmark=benchmark,
        cases=(evaluation_case(second_admission),),
    )

    assert first_admission.producer.execution_id != (
        second_admission.producer.execution_id
    )
    assert first == second
    assert first.input_hash == second.input_hash
    assert first.output_hash == second.output_hash


def test_claim_benchmark_cli_generates_clean_checkout_suite_and_stable_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_report_path = tmp_path / "report-first.json"
    second_report_path = tmp_path / "report-second.json"
    first_cases_path = tmp_path / "cases-first.json"
    second_cases_path = tmp_path / "cases-second.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claim_benchmark",
            "--output",
            str(first_report_path),
            "--cases-output",
            str(first_cases_path),
        ],
    )
    assert claim_benchmark_main() == 0
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "claim_benchmark",
            "--output",
            str(second_report_path),
            "--cases-output",
            str(second_cases_path),
        ],
    )
    assert claim_benchmark_main() == 0

    report = LiteratureClaimBenchmarkReport.model_validate_json(
        first_report_path.read_text(encoding="utf-8")
    )
    assert report.sample_count == 12
    assert report.scientific_label_items_total == 8
    assert report.scientific_label_exact_match_rate == 1.0
    assert first_report_path.read_bytes() == second_report_path.read_bytes()
    assert first_cases_path.read_bytes() == second_cases_path.read_bytes()
    assert b"\r" not in first_report_path.read_bytes()
    assert b"\r" not in first_cases_path.read_bytes()
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
