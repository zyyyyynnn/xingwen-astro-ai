"""Cross-language gate for the committed paper-acquisition fixture.

The frontend consumes ``packages/data-access/src/fixture/paper-acquisition.fixture.json``.
AJV can only check the generated JSON Schema shape, so this suite is the
authoritative semantic gate: the committed document must round-trip through
the real Pydantic contract models, must equal a deterministic rebuild by the
real paper acquisition pipeline, and intentionally broken payloads must fail validation.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_collection import PaperCollection
from app.schemas.paper_collection_api import (
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from app.schemas.core import ArtifactVersionDetail
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.demo_fixture import (
    DEMO_SCENARIO_ID,
    FIXTURE_OUTPUT_PATH,
    build_demo_records,
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
        assert item.paper_collection_version_id == read.artifact_version_id
        assert item.paper_collection_input_hash == read.collection.input_hash
        assert item.source_snapshot.id == read.source_snapshots[0].id


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


def test_seed_records_are_derived_from_the_frozen_benchmark() -> None:
    """The expected-paper records must equal the frozen seed papers, not a
    hand-maintained transcription."""

    benchmark = load_frozen_benchmark()
    scenario = next(
        item
        for item in benchmark.search_scenarios
        if item.scenario_id == DEMO_SCENARIO_ID
    )
    seeds_by_id = {paper.paper_id: paper for paper in benchmark.seed_papers}
    records = build_demo_records(benchmark)
    expected = [seeds_by_id[paper_id] for paper_id in scenario.expected_paper_ids]
    seed_records = records[: len(expected)]
    for record, seed in zip(seed_records, expected, strict=True):
        assert "fixture" in seed.intended_uses
        assert record.title == seed.title
        assert record.authors == tuple(seed.authors)
        assert record.year == seed.year
        assert record.doi == seed.doi
        assert record.arxiv_id == seed.arxiv_id
        # The derivation, not a transcription, builds the source identifiers:
        # the crossref record id and canonical DOI URL are both derived from
        # the seed DOI, and a real seed is never labelled synthetic.
        assert record.source_record_id == f"crossref:{seed.doi}"
        assert record.url == f"https://doi.org/{seed.doi}"
        assert record.synthetic_note is None
    # The seed records must appear first, in scenario ``expected_paper_ids``
    # order, and be followed only by the three synthetic review records.
    assert [record.doi for record in seed_records] == [
        seeds_by_id[paper_id].doi for paper_id in scenario.expected_paper_ids
    ]
    assert len(records) == len(expected) + 3


def test_seed_derivation_assertions_have_discriminating_power() -> None:
    """Counter-example guard: the field/order checks above must actually fail
    when the seed records are paired against the wrong seeds, proving the
    positive test is not a tautology of ``_seed_records`` construction."""

    benchmark = load_frozen_benchmark()
    scenario = next(
        item
        for item in benchmark.search_scenarios
        if item.scenario_id == DEMO_SCENARIO_ID
    )
    seeds_by_id = {paper.paper_id: paper for paper in benchmark.seed_papers}
    records = build_demo_records(benchmark)
    expected = [seeds_by_id[paper_id] for paper_id in scenario.expected_paper_ids]
    seed_records = records[: len(expected)]
    assert len(expected) >= 2
    # Rotate the expected papers by one: a correct derivation must not match
    # this deliberately mis-ordered pairing (the expected DOIs are distinct).
    wrong = expected[1:] + expected[:1]
    assert [seed.doi for seed in wrong] != [record.doi for record in seed_records]
    with pytest.raises(AssertionError):
        for record, seed in zip(seed_records, wrong, strict=True):
            assert record.title == seed.title
            assert record.doi == seed.doi


def test_synthetic_records_carry_explicit_per_candidate_notes(
    committed_document: dict[str, Any],
) -> None:
    read = PaperCollectionRead.model_validate(committed_document["read"])
    notes = [
        candidate.raw.synthetic_note for candidate in read.collection.candidates
    ]
    synthetic = [note for note in notes if note is not None]
    real = [note for note in notes if note is None]
    assert len(synthetic) == 3
    assert len(real) == 4
    for note in synthetic:
        assert "Synthetic demo record" in note
        assert "Not a real publication" in note


def test_paper_collection_fixture_matches_zero_evidence_publication_authority(
    committed_document: dict[str, Any],
) -> None:
    assert "evidence" not in committed_document["read"]

    version = committed_document["artifact_version"]

    assert version["evidence_ids"] == []
    assert version["evidence"] == []


def test_artifact_version_identity_is_consistent_with_the_collection(
    committed_document: dict[str, Any],
) -> None:
    """Mirror the PaperCollection API `_validated_collection` cross-checks: the generic
    ArtifactVersion identity must be derived from the same canonical dump."""

    version = ArtifactVersionDetail.model_validate(
        committed_document["artifact_version"]
    ).model_dump(mode="json", exclude_none=False)
    read = committed_document["read"]
    assert version["content"] == read["collection"]
    assert version["content_hash"] == read["content_hash"]
    assert version["content_hash"] == compute_canonical_payload_hash(
        version["content"]
    )
    assert version["input_hash"] == read["collection"]["input_hash"]
    assert version["schema_version"] == read["collection"]["schema_version"]
    producer = version["producer"]
    assert producer == read["producer_execution"]["producer"]
    assert producer["name"] == read["collection"]["producer"]["producer_name"]
    assert (
        producer["version"] == read["collection"]["producer"]["producer_version"]
    )
    assert (
        producer["parameters_hash"]
        == read["collection"]["producer"]["parameters_hash"]
    )
    rules = read["collection"]["rules"]
    assert version["producer_execution"]["parameters"] == rules
    assert (
        version["producer_execution"]["parameters_hash"]
        == read["collection"]["producer"]["parameters_hash"]
    )
    assert version["producer_execution"]["output_hash"] == version["content_hash"]


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
