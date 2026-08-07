"""Benchmark contract for Scientific Document Parsing (D-10).

Defines the reproducible Benchmark manifest/report schemas and metric
definitions. Covers Native-only vs Hybrid (hybrid result structure reserved).
Metrics are versioned, have clear denominators, empty-sample behavior and
deterministic hashing — never a single vague "accuracy".
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import CORE_MODEL_CONFIG, ContentHash, Identifier, UtcDateTime


#: Explicit "pending" sentinel for ``BenchmarkReport.output_hash``. Builders
#: construct with this placeholder, then set the real self-verifying hash via
#: ``model_copy(update={"output_hash": ...})``. It is accepted only at
#: construction (see ``require_self_verifying_output_hash``).
_PENDING_OUTPUT_HASH = "sha256:" + "0" * 64


class BenchmarkDataType(StrEnum):
    """Provenance class of a benchmark document (fakes must never impersonate)."""

    fixture = "fixture"
    golden = "golden"
    recorded = "recorded"
    live = "live"


class BenchmarkParserMode(StrEnum):
    native_only = "native_only"
    hybrid = "hybrid"


class BenchmarkMetricStatus(StrEnum):
    """How a metric value should be interpreted (D-10 E5/E6)."""

    measured = "measured"
    not_applicable = "not_applicable"
    unsupported = "unsupported"
    not_run = "not_run"


class GoldenExpectedAnnotation(BaseModel):
    """Machine-readable expected structure for one Golden Set entry (D-10 D3).

    Lets the benchmark answer "how much of the key structure was recovered?"
    instead of merely "did a block get accepted?". Committed fixtures carry a
    full annotation; local-only/restricted entries may carry only a page_count
    and license/provenance. ``None`` means "not annotated in this checkout".
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="GoldenExpectedAnnotation")

    expected_page_count: Annotated[int, Field(ge=1)] | None = None
    critical_headings: tuple[str, ...] = Field(default=())
    selected_paragraph_block_ids: tuple[Identifier, ...] = Field(default=())
    selected_reading_order: tuple[Identifier, ...] = Field(default=())
    selected_tables: tuple[Identifier, ...] = Field(default=())
    selected_cells: tuple[Identifier, ...] = Field(default=())
    selected_formulas: tuple[Identifier, ...] = Field(default=())
    selected_figure_caption_links: tuple[Identifier, ...] = Field(default=())
    selected_scientific_values: tuple[str, ...] = Field(default=())


class GoldenSetEntry(BaseModel):
    """One Golden Set entry manifest (license/provenance governed)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="GoldenSetEntry")

    entry_id: Identifier
    case_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    data_type: BenchmarkDataType
    source: str = Field(min_length=1)
    doi_or_identifier: str | None = None
    license_note: str = Field(min_length=1)
    content_hash: ContentHash | None = None
    availability: str = Field(min_length=1)
    local_only: bool = False
    coverage_tags: tuple[str, ...] = Field(default=())
    expected: GoldenExpectedAnnotation | None = None

    @model_validator(mode="after")
    def require_exoplanet_case_key(self) -> GoldenSetEntry:
        if self.case_key != "exoplanet_host_star":
            raise ValueError("D-10 Golden Set is scoped to exoplanet_host_star")
        return self

    @model_validator(mode="after")
    def prohibit_fake_provenance(self) -> GoldenSetEntry:
        # A committed fixture carries a real content hash; a restricted/local-only
        # entry carries provenance but never a committed content hash (no PDF).
        if self.data_type == BenchmarkDataType.fixture:
            if self.content_hash is None:
                raise ValueError("committed fixture must carry its content_hash")
            if self.local_only:
                raise ValueError("committed fixture cannot be local_only")
        if self.local_only:
            if self.content_hash is not None:
                raise ValueError("local-only entry must not carry a committed content_hash")
            if not self.doi_or_identifier:
                raise ValueError("local-only real publication must carry a real DOI/identifier")
        return self


class GoldenSetManifest(BaseModel):
    """Machine-readable Golden Set manifest (version + hash locked)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="GoldenSetManifest")

    manifest_id: Identifier
    version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
    case_key: str = "exoplanet_host_star"
    generated_at: UtcDateTime
    sample_count: Annotated[int, Field(ge=0)]
    entries: tuple[GoldenSetEntry, ...] = Field(default=())

    @model_validator(mode="after")
    def require_sample_count_matches(self) -> GoldenSetManifest:
        if self.sample_count != len(self.entries):
            raise ValueError(
                f"sample_count={self.sample_count} != len(entries)={len(self.entries)}"
            )
        return self

    @model_validator(mode="after")
    def require_unique_entry_ids(self) -> GoldenSetManifest:
        ids = [e.entry_id for e in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Golden Set entry_id values must be unique")
        return self


class BenchmarkMetricValue(BaseModel):
    """One metric with explicit denominator and empty-sample behavior.

    ``status`` disambiguates a true zero (``measured`` with rate 0.0) from
    "we never measured this capability" (``not_applicable`` / ``unsupported`` /
    ``not_run``). A ``measured`` metric MUST carry a non-``None`` denominator.

    ``rate`` is a derived (computed) field: it is always ``numerator /
    denominator`` when a positive denominator is present, regardless of how the
    object was constructed or loaded. This keeps the serialized payload and the
    benchmark ``output_hash`` deterministic across construction and reload (D-10
    E7/E8).
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="BenchmarkMetricValue")

    name: str = Field(min_length=1)
    status: BenchmarkMetricStatus = BenchmarkMetricStatus.measured
    numerator: Annotated[float, Field(ge=0.0)] = 0.0
    denominator: Annotated[float, Field(ge=0.0)] | None = None
    rate: float | None = None
    empty_behavior: str = "report_zero_rate"
    version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]

    @model_validator(mode="after")
    def measured_requires_denominator(self) -> Self:
        # A measured metric MUST carry a non-None denominator (fail-closed).
        if self.status == BenchmarkMetricStatus.measured and self.denominator is None:
            raise ValueError(f"metric '{self.name}' status=measured requires a denominator")
        return self


class BenchmarkCaseResult(BaseModel):
    """One document's parse evaluation against its expected annotation.

    Counts (``accepted_count``/``partial_count``/``unsupported_count``) describe
    THIS case only — they are derived from the case's own blocks/regions, never
    from a running global accumulator (D-10 E4).
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="BenchmarkCaseResult")

    entry_id: Identifier
    parser_mode: BenchmarkParserMode
    document_parse_id: Identifier
    overall_quality: str
    native_routing_coverage: float | None = None
    visual_routing_coverage: float | None = None
    block_recovery: float | None = None
    reading_order_error: float | None = None
    table_structure_recovery: float | None = None
    formula_recovery: float | None = None
    figure_caption_linkage: float | None = None
    evidence_locator_validity: float | None = None
    accepted_count: Annotated[int, Field(ge=0)] = 0
    partial_count: Annotated[int, Field(ge=0)] = 0
    unsupported_count: Annotated[int, Field(ge=0)] = 0
    latency_seconds: float | None = None
    peak_memory_bytes: int | None = None
    cpu_result: bool = True
    gpu_result: bool = False
    failure_category: str | None = None
    input_hash: ContentHash
    output_hash: ContentHash


class BenchmarkReport(BaseModel):
    """Aggregate reproducible benchmark report (versioned + hashed)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="BenchmarkReport")

    report_id: Identifier
    schema_version: Annotated[str, Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")]
    parser_mode: BenchmarkParserMode
    golden_set_manifest_id: Identifier
    golden_set_version: str
    golden_set_content_hash: ContentHash
    expected_annotation_hash: ContentHash
    native_engine: str
    native_engine_version: str
    visual_engine: str | None = None
    visual_engine_version: str | None = None
    visual_model_id: str | None = None
    visual_model_revision: str | None = None
    config_hash: ContentHash
    metrics: tuple[BenchmarkMetricValue, ...] = Field(default=())
    cases: tuple[BenchmarkCaseResult, ...] = Field(default=())
    input_hash: ContentHash
    output_hash: ContentHash
    created_at: UtcDateTime

    @model_validator(mode="after")
    def require_self_verifying_output_hash(self) -> Self:
        expected = compute_benchmark_report_hash(self)
        # The all-zero placeholder is the explicit "pending" sentinel used by
        # builders that construct first and then set the real hash via
        # ``model_copy(update={"output_hash": ...})``. It is accepted at
        # construction time only.
        if self.output_hash == _PENDING_OUTPUT_HASH:
            return self
        if self.output_hash != expected:
            raise ValueError(
                f"benchmark output_hash does not self-verify "
                f"(got {self.output_hash}, expected {expected})"
            )
        return self


def benchmark_payload_for_hash(report: BenchmarkReport) -> dict:
    """Deterministic payload used for the report's reproducible hash.

    Excludes ``output_hash`` (which is the value being computed) and
    ``created_at`` (wall-clock, not part of the scientific result) so identical
    scientific inputs always yield the same ``output_hash`` regardless of when
    the run happened (D-10 E7/E8).
    """
    return report.model_dump(mode="json", exclude={"output_hash", "created_at"})


def compute_benchmark_report_hash(report: BenchmarkReport) -> str:
    """Deterministic hash of a benchmark report's canonical payload."""
    payload = benchmark_payload_for_hash(report)
    return compute_canonical_payload_hash(payload)


__all__ = [
    "BenchmarkDataType",
    "BenchmarkParserMode",
    "BenchmarkMetricStatus",
    "GoldenExpectedAnnotation",
    "GoldenSetEntry",
    "GoldenSetManifest",
    "BenchmarkMetricValue",
    "BenchmarkCaseResult",
    "BenchmarkReport",
    "benchmark_payload_for_hash",
    "compute_benchmark_report_hash",
]
