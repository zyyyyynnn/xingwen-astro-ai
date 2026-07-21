"""Frozen D-01 inputs and D-02 producer rule versions."""

from __future__ import annotations

from pathlib import Path


FROZEN_BENCHMARK_SCHEMA_VERSION = "1.3.0"
FROZEN_BENCHMARK_VERSION = "1.3.0"
FROZEN_SCIENTIFIC_PAYLOAD_HASH = (
    "sha256:32db9d4345d904f3f5b9fbe975c41cdfebd4fb45ecc5747e6845959bd220e9cd"
)
FROZEN_BENCHMARK_CONTENT_HASH = (
    "sha256:07fa19820cdbd5b908d4f30705bb863fb9a28050caf7bf54f6c01130467b1e2d"
)
FROZEN_X00_MAIN_SHA = "eb7e23f6d0c14555627c602c6e5a2b84210ba833"
FROZEN_BENCHMARK_PATH = (
    Path(__file__).resolve().parent
    / "benchmarks"
    / "exoplanet_host_star"
    / "paper-reasoning-benchmark.v1.json"
)

PRODUCER_NAME = "xingwen.paper_collection"
PRODUCER_VERSION = "1.0.0"
QUERY_NORMALIZATION_VERSION = "1.0.0"
CANONICALIZATION_VERSION = "1.0.0"
DEDUPE_VERSION = "1.0.0"
RANKING_VERSION = "1.0.0"
SELECTION_VERSION = "1.0.0"
RETRY_POLICY_VERSION = "1.0.0"
SOURCE_POLICY_VERSION = "1.0.0"
CROSSREF_ADAPTER_VERSION = "1.0.0"
