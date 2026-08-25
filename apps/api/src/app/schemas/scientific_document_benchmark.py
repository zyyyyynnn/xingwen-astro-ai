"""Reproducible benchmark schemas and metrics for document parsing.

Defines reproducible Benchmark manifest/report schemas and metric definitions.
Metrics carry explicit technical versions, denominators, empty-sample behavior, and
deterministic hashing — never a single vague "accuracy".
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import CORE_MODEL_CONFIG, ContentHash, Identifier, UtcDateTime


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
    paired = "paired"


class BenchmarkMemoryBasis(StrEnum):
    """What ``peak_memory_bytes`` actually observed — never mislabel the boundary."""

    process_rss = "process_rss"
    python_heap_tracemalloc = "python_heap_tracemalloc"


class BenchmarkDeviceStatus(StrEnum):
    """Explicit device execution fact; absence of a GPU run is never inferred."""

    run = "run"
    not_run = "not_run"
    deferred = "deferred"


class BenchmarkMetricStatus(StrEnum):
    """How a metric value should be interpreted (Scientific Document Parsing Contract E5/E6)."""

    measured = "measured"
    not_applicable = "not_applicable"
    unsupported = "unsupported"
    not_run = "not_run"


class GoldenExpectedAnnotation(BaseModel):
    """Machine-readable expected structure for one Golden Set entry.

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
    def require_exoplanet_case_key(self) -> Self:
        if self.case_key != "exoplanet_host_star":
            raise ValueError("Scientific Document Parsing Contract Golden Set is scoped to exoplanet_host_star")
        return self

    @model_validator(mode="after")
    def prohibit_fake_provenance(self) -> Self:
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
            if self.expected is not None and self.expected.expected_page_count is not None:
                raise ValueError(
                    "local-only entry without exact content hash must not claim expected_page_count"
                )
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
    def require_sample_count_matches(self) -> Self:
        if self.sample_count != len(self.entries):
            raise ValueError(
                f"sample_count={self.sample_count} != len(entries)={len(self.entries)}"
            )
        return self

    @model_validator(mode="after")
    def require_unique_entry_ids(self) -> Self:
        ids = [entry.entry_id for entry in self.entries]
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
    benchmark ``output_hash`` deterministic across construction and reload (Scientific Document Parsing Contract
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
    def require_consistent_metric(self) -> Self:
        if self.status == BenchmarkMetricStatus.measured:
            if self.denominator is None:
                raise ValueError(f"metric '{self.name}' status=measured requires a denominator")
            expected_rate = (
                self.numerator / self.denominator
                if self.denominator > 0
                else (0.0 if self.empty_behavior == "report_zero_rate" else None)
            )
            if expected_rate is None:
                if self.rate is not None:
                    raise ValueError(
                        f"metric '{self.name}' with empty denominator must have rate=None"
                    )
            elif self.rate is None or not math.isclose(
                self.rate, expected_rate, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise ValueError(
                    f"metric '{self.name}' rate={self.rate!r} does not match "
                    f"numerator/denominator={expected_rate!r}"
                )
        else:
            if self.numerator != 0.0:
                raise ValueError(
                    f"metric '{self.name}' status={self.status.value} must not carry numerator"
                )
            if self.denominator not in (None, 0.0):
                raise ValueError(
                    f"metric '{self.name}' status={self.status.value} must not carry denominator"
                )
            if self.rate is not None:
                raise ValueError(
                    f"metric '{self.name}' status={self.status.value} must have rate=None"
                )
        return self


class BenchmarkCaseResult(BaseModel):
    """One document's parse evaluation against its expected annotation.

    Counts (``accepted_count``/``partial_count``/``unsupported_count``) describe
    THIS case only — they are derived from the case's own blocks/regions, never
    from a running global accumulator (Scientific Document Parsing Contract E4).
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="BenchmarkCaseResult")

    entry_id: Identifier
    parser_mode: BenchmarkParserMode
    document_parse_id: Identifier
    overall_quality: str
    native_routing_coverage: float | None = None
    visual_routing_coverage: float | None = None
    block_recovery: float | None = None
    scientific_value_recovery: float | None = None
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
    peak_memory_basis: BenchmarkMemoryBasis | None = None
    cpu_result: bool = True
    gpu_result: bool = False
    gpu_status: BenchmarkDeviceStatus | None = None
    failure_category: str | None = None
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def require_case_metric_ranges(self) -> Self:
        bounded = {
            "native_routing_coverage": self.native_routing_coverage,
            "visual_routing_coverage": self.visual_routing_coverage,
            "block_recovery": self.block_recovery,
            "scientific_value_recovery": self.scientific_value_recovery,
            "reading_order_error": self.reading_order_error,
            "table_structure_recovery": self.table_structure_recovery,
            "formula_recovery": self.formula_recovery,
            "figure_caption_linkage": self.figure_caption_linkage,
            "evidence_locator_validity": self.evidence_locator_validity,
        }
        for name, value in bounded.items():
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"case metric {name} must be within 0..1, got {value}")
        if self.latency_seconds is not None and self.latency_seconds < 0:
            raise ValueError("latency_seconds must be non-negative")
        if self.peak_memory_bytes is not None and self.peak_memory_bytes < 0:
            raise ValueError("peak_memory_bytes must be non-negative")
        if self.peak_memory_bytes is not None and self.peak_memory_basis is None:
            raise ValueError(
                "peak_memory_bytes requires an explicit peak_memory_basis; "
                "a Python heap boundary must never impersonate process RSS"
            )
        if self.peak_memory_bytes is None and self.peak_memory_basis is not None:
            raise ValueError("peak_memory_basis without peak_memory_bytes is meaningless")
        if self.gpu_result and self.gpu_status != BenchmarkDeviceStatus.run:
            raise ValueError(
                "gpu_result=True requires gpu_status=run; an unexecuted GPU "
                "path must be reported as not_run/deferred, never as a result"
            )
        return self


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
        if self.output_hash == _PENDING_OUTPUT_HASH:
            return self
        if self.output_hash != expected:
            raise ValueError(
                "benchmark output_hash does not self-verify "
                f"(got {self.output_hash}, expected {expected})"
            )
        return self

    @model_validator(mode="after")
    def require_parser_mode_consistency(self) -> Self:
        """Fail closed on mode/provenance mismatches before any hash is trusted."""

        visual_fields = (
            self.visual_engine,
            self.visual_engine_version,
            self.visual_model_id,
            self.visual_model_revision,
        )
        case_modes = {case.parser_mode for case in self.cases}
        if self.parser_mode == BenchmarkParserMode.native_only:
            if case_modes - {BenchmarkParserMode.native_only}:
                raise ValueError("native_only report must contain only native_only cases")
            if any(field is not None for field in visual_fields):
                raise ValueError(
                    "native_only report must not claim visual provenance"
                )
            return self
        # hybrid and paired reports describe a real visual execution; a missing
        # provenance field would make the run unfalsifiable.
        if any(field is None for field in visual_fields):
            raise ValueError(
                f"{self.parser_mode.value} report requires complete visual "
                "provenance (engine, engine version, model id, model revision)"
            )
        if self.parser_mode == BenchmarkParserMode.hybrid:
            if case_modes - {BenchmarkParserMode.hybrid}:
                raise ValueError("hybrid report must contain only hybrid cases")
            return self
        if case_modes != {
            BenchmarkParserMode.native_only,
            BenchmarkParserMode.hybrid,
        }:
            raise ValueError(
                "paired report must contain both native_only and hybrid cases"
            )
        by_mode: dict[BenchmarkParserMode, set[str]] = {}
        for case in self.cases:
            by_mode.setdefault(case.parser_mode, set()).add(case.entry_id)
        if by_mode[BenchmarkParserMode.native_only] != by_mode[BenchmarkParserMode.hybrid]:
            raise ValueError(
                "paired report must cover the identical entry set in both modes"
            )
        return self


_VOLATILE_METRIC_TAILS = ("latency", "peak_memory")


def _is_volatile_metric_name(name: str) -> bool:
    """Volatile observations describe execution cost under any mode prefix.

    Paired reports name their per-mode cost metrics ``native_only_latency`` /
    ``hybrid_peak_memory``; identity must exclude them exactly like the bare
    native-report names.
    """
    return any(
        name == tail or name.endswith(f"_{tail}") for tail in _VOLATILE_METRIC_TAILS
    )


def benchmark_payload_for_hash(report: BenchmarkReport) -> dict:
    """Deterministic report payload excluding self hash and volatile observations.

    Wall-clock ``created_at`` and real timing/memory observations vary between
    runs of identical inputs; they describe execution cost, never identity. They
    stay in the serialized report but are excluded from the reproducible
    identity hash so repeated runs of one frozen Golden Set keep a stable
    ``output_hash``.
    """
    payload = report.model_dump(mode="json", exclude={"output_hash", "created_at"})
    for case in payload.get("cases", []):
        case.pop("latency_seconds", None)
        case.pop("peak_memory_bytes", None)
    payload["metrics"] = [
        metric
        for metric in payload.get("metrics", [])
        if not _is_volatile_metric_name(metric["name"])
    ]
    return payload


def compute_benchmark_report_hash(report: BenchmarkReport) -> str:
    """Deterministic hash of a benchmark report's canonical payload."""
    return compute_canonical_payload_hash(benchmark_payload_for_hash(report))


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
