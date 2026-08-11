"""Public boundary for cross-source entity alignment."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.crossmatch import (
        CrossmatchBenchmarkManifest,
        CrossmatchBenchmarkScenario,
        CrossmatchInput,
        CrossmatchResult,
    )


def align_cross_source_records(input: CrossmatchInput) -> CrossmatchResult:
    from .engine import align_cross_source_records as align

    return align(input)


def load_crossmatch_benchmark(
    path: Path | None = None,
) -> CrossmatchBenchmarkManifest:
    from .benchmark import load_crossmatch_benchmark as load

    if path is None:
        return load()
    return load(path)


def build_crossmatch_scenario_input(
    scenario: CrossmatchBenchmarkScenario,
) -> CrossmatchInput:
    from .benchmark import build_crossmatch_scenario_input as build

    return build(scenario)


__all__ = [
    "align_cross_source_records",
    "build_crossmatch_scenario_input",
    "load_crossmatch_benchmark",
]
