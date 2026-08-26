"""Scientific Data Integration Benchmark contract (frozen corpus + report).

Defines the system-level data-integration benchmark that composes the existing
production stages — cross-source alignment, identity normalization, unit
conversion, conflict detection, fixture adjudication repair and fail-closed
failure recovery — over one frozen, versioned, hash-pinned corpus. Metrics carry
explicit numerators, denominators, empty-denominator behavior and versions;
there is never a single vague "accuracy". The benchmark observes production
engines only and never mutates production results.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import CORE_MODEL_CONFIG, ContentHash, Identifier, JsonValue, UtcDateTime
from .scientific_document_benchmark import (
    BenchmarkMetricValue,
    _PENDING_OUTPUT_HASH,
)

SCHEMA_VERSION = "2.1.0"

#: The eleven required integration metrics. Every report must declare each one;
#: a capability that genuinely cannot run yet must still be declared with an
#: honest ``not_run``/``unsupported`` status instead of being omitted.
REQUIRED_METRIC_NAMES: tuple[str, ...] = (
    "source_retrieval_completeness",
    "field_value_correctness",
    "entity_alignment_precision",
    "entity_alignment_recall",
    "unit_normalization_success",
    "conflict_detection",
    "repair_success",
    "false_repair_rate",
    "evidence_coverage",
    "reproducibility_hash_stability",
    "failure_recovery",
)


class IntegrationCaseCategory(StrEnum):
    """Why a case exists in the frozen corpus."""

    integration = "integration"
    failure_injection = "failure_injection"
    repair_probe = "repair_probe"


class ExpectedEntityPair(BaseModel):
    """One adjudicated ground-truth alignment between a left and a right row."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="ExpectedEntityPair")

    left_row_key: tuple[tuple[str, str], ...]
    right_row_key: tuple[tuple[str, str], ...]


class IdentityValueExpectation(BaseModel):
    """Expected canonical identity value for one aligned source row."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="IdentityValueExpectation")

    side: str = Field(pattern=r"^(left|right)$")
    row_key: tuple[tuple[str, str], ...]
    field_id: str = Field(min_length=1)
    expected_normalized_value: str = Field(min_length=1)


class SourceRetrievalExpectation(BaseModel):
    """One independently adjudicated source row that must be observable."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="SourceRetrievalExpectation")

    side: Literal["left", "right"]
    source_id: Identifier
    source_snapshot_id: Identifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    fixture_id: Identifier
    fixture_content_hash: ContentHash
    row_key: tuple[tuple[str, str], ...] = Field(min_length=1)


class FieldValueAdjudication(BaseModel):
    """Frozen canonical field/value truth evaluated through production mapping."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="FieldValueAdjudication")

    field_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_table: str = Field(min_length=1)
    raw_field: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    expected_canonical_value: str = Field(min_length=1)


class ConflictAdjudication(BaseModel):
    """Frozen conflict truth, including the exact participating source rows."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="ConflictAdjudication")

    conflict_code: Identifier
    expected_detected: bool
    left_row_keys: tuple[tuple[tuple[str, str], ...], ...] = Field(min_length=1)
    right_row_keys: tuple[tuple[tuple[str, str], ...], ...] = Field(min_length=1)


class RepairAdjudication(BaseModel):
    """Frozen checkpoint decision and independently expected resolution."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="RepairAdjudication")

    conflict_code: Identifier
    action: Literal["accepted", "rejected", "keep_unresolved"]
    expected_resolution: Literal["resolved", "unresolved"]
    rationale: str = Field(min_length=1)
    adjudicated_at: UtcDateTime


class ConversionProbe(BaseModel):
    """One frozen mapping/unit assertion against the production conversion stage.

    Positive probes assert the exact serialized canonical value; rejection
    probes assert that a contradictory request fails closed.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="ConversionProbe")

    quantity_kind: str = Field(min_length=1)
    source_unit: str | None = None
    target_unit: str | None = None
    input_value: str = Field(min_length=1)
    expected_value: str | None = None
    expects_rejection: bool = False

    @model_validator(mode="after")
    def require_outcome(self) -> Self:
        if self.expects_rejection and self.expected_value is not None:
            raise ValueError(
                "a rejection probe must not also declare an expected value"
            )
        if not self.expects_rejection and self.expected_value is None:
            raise ValueError("a positive probe must freeze its expected value")
        return self


class IntegrationCase(BaseModel):
    """One frozen benchmark case composing referenced scenario + expectations.

    ``scenario_id`` references a scenario of the pinned crossmatch benchmark
    manifest; conversion-only cases omit it. Failure-injection cases name the
    required injection class they cover and their exact expected error code.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="IntegrationCase")

    case_id: Identifier
    category: IntegrationCaseCategory
    scenario_id: Identifier | None = None
    injection_class: str | None = None
    expected_error_code: str | None = None
    expected_accepted_pairs: tuple[ExpectedEntityPair, ...] = Field(default=())
    source_retrieval_expectations: tuple[SourceRetrievalExpectation, ...] = Field(
        default=()
    )
    field_value_adjudications: tuple[FieldValueAdjudication, ...] = Field(default=())
    conflict_adjudications: tuple[ConflictAdjudication, ...] = Field(default=())
    repair_adjudications: tuple[RepairAdjudication, ...] = Field(default=())
    identity_expectations: tuple[IdentityValueExpectation, ...] = Field(default=())
    conversion_probes: tuple[ConversionProbe, ...] = Field(default=())

    @model_validator(mode="after")
    def require_content(self) -> Self:
        if (
            self.scenario_id is None
            and not self.conversion_probes
            and not self.field_value_adjudications
        ):
            raise ValueError(
                f"case {self.case_id} needs a scenario reference or conversion probes"
            )
        if self.category == IntegrationCaseCategory.failure_injection:
            has_rejection_probe = any(
                probe.expects_rejection for probe in self.conversion_probes
            )
            if self.expected_error_code is None and not has_rejection_probe:
                raise ValueError(
                    f"failure-injection case {self.case_id} must freeze its "
                    "expected error code (or carry a rejection probe)"
                )
            if self.injection_class is None:
                raise ValueError(
                    f"failure-injection case {self.case_id} must declare its "
                    "injection class"
                )
        if (
            self.repair_adjudications
            and self.category != IntegrationCaseCategory.repair_probe
        ):
            raise ValueError("repair adjudications belong to repair_probe cases only")
        if (
            self.category == IntegrationCaseCategory.repair_probe
            and not self.repair_adjudications
        ):
            raise ValueError("repair_probe cases must freeze repair adjudications")
        return self


class ScientificDataIntegrationBenchmarkManifest(BaseModel):
    """Frozen corpus: hash-pinned scenarios + adjudicated ground truth."""

    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        title="ScientificDataIntegrationBenchmarkManifest",
    )

    benchmark_id: Identifier
    version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
    content_hash: ContentHash
    data_level: str = Field(default="synthetic_fixture")
    provenance_note: str = Field(min_length=1)
    adjudication_source: str = Field(min_length=1)
    adjudicated_at: UtcDateTime
    inconclusive_policy: str = Field(min_length=1)
    evaluation_version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
    metric_formulas: dict[str, str] = Field(min_length=len(REQUIRED_METRIC_NAMES))
    crossmatch_benchmark_id: Identifier
    crossmatch_benchmark_version: str
    crossmatch_benchmark_content_hash: ContentHash
    rule_set_id: Identifier
    rule_set_version: str
    rule_set_content_hash: ContentHash
    cases: tuple[IntegrationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("integration benchmark case_ids must be unique")
        if set(self.metric_formulas) != set(REQUIRED_METRIC_NAMES):
            raise ValueError("integration benchmark metric formulas must be complete")
        return self


def compute_integration_manifest_content_hash(
    manifest: ScientificDataIntegrationBenchmarkManifest,
) -> ContentHash:
    """Deterministic hash of the frozen corpus, excluding the self hash."""
    return compute_canonical_payload_hash(
        manifest.model_dump(mode="json", exclude={"content_hash"})
    )


class IntegrationCaseResult(BaseModel):
    """Observed outcome of one frozen case; never mutates production state."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="IntegrationCaseResult")

    case_id: Identifier
    category: IntegrationCaseCategory
    status: str = Field(pattern=r"^(passed|failed)$")
    observed: dict[str, JsonValue] = Field(default_factory=dict)
    expected_error_code: str | None = None
    observed_error_code: str | None = None
    input_hash: ContentHash | None = None
    output_hash: ContentHash | None = None
    reproduced_output_hash: ContentHash | None = None
    failure_detail: str | None = None


class ScientificDataIntegrationReport(BaseModel):
    """Aggregate machine-readable integration benchmark report (hashed)."""

    model_config = ConfigDict(
        **CORE_MODEL_CONFIG, title="ScientificDataIntegrationReport"
    )

    report_id: Identifier
    schema_version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
    benchmark_manifest_id: Identifier
    benchmark_manifest_version: str
    benchmark_manifest_content_hash: ContentHash
    evaluation_version: str
    metric_formulas: dict[str, str]
    inconclusive_policy: str = Field(min_length=1)
    metrics: tuple[BenchmarkMetricValue, ...] = Field(min_length=1)
    cases: tuple[IntegrationCaseResult, ...] = Field(min_length=1)
    input_hash: ContentHash
    output_hash: ContentHash
    created_at: UtcDateTime

    @model_validator(mode="after")
    def require_all_core_metrics_declared(self) -> Self:
        names = {metric.name for metric in self.metrics}
        missing = [name for name in REQUIRED_METRIC_NAMES if name not in names]
        if missing:
            raise ValueError(f"integration report missing required metrics: {missing}")
        if set(self.metric_formulas) != set(REQUIRED_METRIC_NAMES):
            raise ValueError("integration report metric formulas must be complete")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("integration report case_ids must be unique")
        return self

    @model_validator(mode="after")
    def require_self_verifying_output_hash(self) -> Self:
        expected = compute_integration_report_hash(self)
        if self.output_hash == _PENDING_OUTPUT_HASH:
            return self
        if self.output_hash != expected:
            raise ValueError(
                "integration report output_hash does not self-verify "
                f"(got {self.output_hash}, expected {expected})"
            )
        return self


def integration_payload_for_hash(report: ScientificDataIntegrationReport) -> dict:
    """Deterministic payload excluding self hash and wall-clock time."""
    return report.model_dump(mode="json", exclude={"output_hash", "created_at"})


def compute_integration_report_hash(
    report: ScientificDataIntegrationReport,
) -> str:
    return compute_canonical_payload_hash(integration_payload_for_hash(report))


__all__ = [
    "REQUIRED_METRIC_NAMES",
    "IntegrationCaseCategory",
    "ExpectedEntityPair",
    "IdentityValueExpectation",
    "SourceRetrievalExpectation",
    "FieldValueAdjudication",
    "ConflictAdjudication",
    "RepairAdjudication",
    "ConversionProbe",
    "IntegrationCase",
    "ScientificDataIntegrationBenchmarkManifest",
    "compute_integration_manifest_content_hash",
    "IntegrationCaseResult",
    "ScientificDataIntegrationReport",
    "integration_payload_for_hash",
    "compute_integration_report_hash",
]
