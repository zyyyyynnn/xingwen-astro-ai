"""Load only the explicitly frozen D-01 package."""

from __future__ import annotations

from pathlib import Path

from app.schemas.paper_benchmark import BenchmarkPackage

from .constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_PATH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
)


def load_frozen_benchmark(path: Path = FROZEN_BENCHMARK_PATH) -> BenchmarkPackage:
    package = BenchmarkPackage.model_validate_json(path.read_text(encoding="utf-8"))
    validate_frozen_benchmark(package)
    return package


def validate_frozen_benchmark(package: BenchmarkPackage) -> None:
    """Reject a valid package when it is not the explicitly frozen D-01 identity."""

    expected = {
        "schema_version": FROZEN_BENCHMARK_SCHEMA_VERSION,
        "benchmark_version": FROZEN_BENCHMARK_VERSION,
        "scientific_payload_hash": FROZEN_SCIENTIFIC_PAYLOAD_HASH,
        "content_hash": FROZEN_BENCHMARK_CONTENT_HASH,
    }
    actual = {field: getattr(package, field) for field in expected}
    if actual != expected:
        raise ValueError("frozen D-01 benchmark identity mismatch")
