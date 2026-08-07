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


class BenchmarkDataType(StrEnum):
    """Provenance class of a benchmark document (fakes must never impersonate)."""

    fixture = "fixture"
    golden = "golden"
    recorded = "recorded"
    live = "live"


class BenchmarkParserMode(StrEnum):
    native_only = "native_only"
    hybrid = "hybrid"


class GoldenSetEntry(BaseModel):
    """One Golden Set entry manifest (license/provenance governed)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="GoldenSetEntry")

    entry_id: Identifier
    case_key: str = Field(min_length=1)
    title: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_case_key(self) -> GoldenSetEntry:
        if self.case_key != "exoplanet_host_star":
            raise ValueError("D-10 Golden Set is scoped to exoplanet_host_star")
        return self
    data_type: BenchmarkDataType
    source: str = Field(min_length=1)
    doi_or_identifier: str | None = None
    license_note: str = Field(min_length=1)
    content_hash: ContentHash | None = None
    availability: str = Field(min_length=1)
    coverage_tags: tuple[str, ...] = Field(default=())
    local_only: bool = False


class GoldenSetManifest(BaseModel):
    """Machine-readable Golden Set manifest (version + hash locked)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="GoldenSetManifest")

    manifest_id: Identifier
    version: str = Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")
    case_key: str = "exoplanet_host_star"
    generated_at: UtcDateTime
    sample_count: Annotated[int, Field(ge=0)]
    entries: tuple[GoldenSetEntry, ...] = Field(default=())
    content_hash: ContentHash


class BenchmarkMetricValue(BaseModel):
    """One metric with explicit denominator and empty-sample behavior."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="BenchmarkMetricValue")

    name: str = Field(min_length=1)
    numerator: Annotated[float, Field(ge=0.0)]
    denominator: Annotated[float, Field(ge=0.0)]
    rate: float | None = None
    empty_behavior: str = "report_zero_rate"
    version: str = Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")


class BenchmarkCaseResult(BaseModel):
    """One document's parse evaluation against its expected annotation."""

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
    schema_version: str = Field(pattern=r"^[1-9]\d*\.\d+\.\d+$")
    parser_mode: BenchmarkParserMode
    golden_set_manifest_id: Identifier
    golden_set_version: str
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


def compute_benchmark_report_hash(report: BenchmarkReport) -> str:
    """Deterministic hash of a benchmark report's canonical payload."""
    payload = report.model_dump(mode="json", exclude_none=True)
    return compute_canonical_payload_hash(payload)


__all__ = [
    "BenchmarkDataType",
    "BenchmarkParserMode",
    "GoldenSetEntry",
    "GoldenSetManifest",
    "BenchmarkMetricValue",
    "BenchmarkCaseResult",
    "BenchmarkReport",
    "compute_benchmark_report_hash",
]
