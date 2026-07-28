"""Cross-language gate for the committed A-05 paper-acquisition fixture.

The frontend consumes ``packages/data-access/src/fixture/paper-acquisition.fixture.json``.
AJV can only check the generated JSON Schema shape, so this suite is the
authoritative semantic gate: the committed document must round-trip through
the real Pydantic contract models, must equal a deterministic rebuild by the
real D-02 pipeline, and intentionally broken payloads must fail validation.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.paper_collection import PaperCollection
from app.schemas.paper_collection_api import (
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.demo_fixture import (
    DEMO_SCENARIO_ID,
    FIXTURE_OUTPUT_PATH,
    build_fixture_document,
)


@pytest.fixture(scope="module")
def committed_document() -> dict[str, Any]:
    return json.loads(FIXTURE_OUTPUT_PATH.read_text(encoding="utf-8"))


def test_committed_fixture_matches_deterministic_rebuild(
    committed_document: dict[str, Any],
) -> None:
    assert committed_document == build_fixture_document(), (
        "paper-acquisition.fixture.json drifted from the pipeline build; "
        "regenerate with `uv run --project apps/api python -m "
        "services.paper_pipeline.demo_fixture`"
    )


def test_committed_read_passes_pydantic(committed_document: dict[str, Any]) -> None:
    read = PaperCollectionRead.model_validate(committed_document["read"])
    assert read.source_mode.value == "fixture"
    assert all(
        execution.source_mode.value == "fixture"
        for execution in read.collection.source_executions
    )
    keys = [
        (item.ranking_key, item.canonical_paper_id, item.candidate_id)
        for item in read.collection.candidates
    ]
    assert keys == sorted(keys)


def test_every_candidate_read_passes_pydantic(
    committed_document: dict[str, Any],
) -> None:
    read = PaperCollectionRead.model_validate(committed_document["read"])
    reads = [
        PaperCollectionCandidateRead.model_validate(item)
        for item in committed_document["candidate_reads"]
    ]
    assert [str(item.candidate.candidate_id) for item in reads] == [
        str(item.candidate_id) for item in read.collection.candidates
    ]
    for item in reads:
        assert item.evidence, "every candidate read must carry Evidence"
        for evidence in item.evidence:
            assert evidence.source_snapshot_id == item.source_snapshot.id


def test_benchmark_identity_matches_frozen_package(
    committed_document: dict[str, Any],
) -> None:
    benchmark = load_frozen_benchmark()
    reference = committed_document["read"]["collection"]["benchmark"]
    assert reference["benchmark_id"] == benchmark.benchmark_id
    assert reference["benchmark_version"] == benchmark.benchmark_version
    assert reference["schema_version"] == benchmark.schema_version
    assert reference["scientific_payload_hash"] == benchmark.scientific_payload_hash
    assert reference["content_hash"] == benchmark.content_hash
    scenario = next(
        item
        for item in benchmark.search_scenarios
        if item.scenario_id == DEMO_SCENARIO_ID
    )
    query = committed_document["read"]["collection"]["query"]
    assert query["year_from"] == scenario.query.year_from
    assert query["year_to"] == scenario.query.year_to
    metrics = committed_document["read"]["collection"]["metrics"]
    assert metrics["expected_candidate_count"] == len(
        set(scenario.expected_paper_ids)
    )
    assert set(query["source_ids"]) <= set(scenario.source_ids)


def _collection_payload(document: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(document["read"]["collection"]))


def test_unsorted_keywords_fail_validation(committed_document: dict[str, Any]) -> None:
    payload = _collection_payload(committed_document)
    payload["query"]["normalized_keywords"] = list(
        reversed(payload["query"]["normalized_keywords"])
    )
    with pytest.raises(ValidationError, match="normalized_keywords"):
        PaperCollection.model_validate(payload)


def test_tampered_query_hash_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _collection_payload(committed_document)
    payload["query"]["query_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="query_hash"):
        PaperCollection.model_validate(payload)


def test_missing_snapshot_registry_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _collection_payload(committed_document)
    payload["source_snapshots"] = []
    with pytest.raises(ValidationError, match="source_snapshot_ids"):
        PaperCollection.model_validate(payload)


def test_tampered_output_hash_fails_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _collection_payload(committed_document)
    payload["output_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValidationError, match="output_hash"):
        PaperCollection.model_validate(payload)


def test_tampered_metrics_fail_validation(
    committed_document: dict[str, Any],
) -> None:
    payload = _collection_payload(committed_document)
    payload["metrics"]["candidate_count"] = payload["metrics"]["candidate_count"] + 1
    with pytest.raises(ValidationError, match="candidate metric"):
        PaperCollection.model_validate(payload)
