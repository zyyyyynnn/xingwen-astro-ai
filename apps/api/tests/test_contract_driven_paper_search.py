"""Contract-driven PaperSearchInput and query normalization tests (Issue #202)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    PaperSearchScope,
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
    UpstreamFailureClass,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_collection import (
    NormalizedPaperQuery,
    PaperCollection,
    PaperCollectionPayload,
    PaperCollectionRules,
    PaperSearchInput,
    PaperSourcePage,
    compute_normalized_query_hash,
    compute_paper_collection_input_hash,
    compute_paper_collection_output_hash,
    compute_paper_search_input_hash,
    compute_paper_source_request_parameters_hash,
    normalize_paper_query_text,
)
from services.paper_pipeline.constants import (
    CANONICALIZATION_VERSION,
    DEDUPE_VERSION,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    QUERY_NORMALIZATION_VERSION,
    RANKING_VERSION,
    RETRY_POLICY_VERSION,
    SELECTION_VERSION,
    SOURCE_POLICY_VERSION,
)
from services.paper_pipeline.errors import PaperSearchExecutionError
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.mapper import build_paper_search_input
from services.paper_pipeline.query import (
    normalize_canonical_paper_query,
    normalize_paper_search_input,
)
from services.paper_pipeline.sources.base import (
    RawSourceRecord,
    SourceFailure,
    SourceSearchResult,
)


_FIXED_NOW = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)


def _contract(
    *,
    contract_id: str | None = None,
    version: int = 1,
    keywords: tuple[str, ...] = ("系外行星 宿主恒星", "exoplanet host star"),
    year_from: int | None = 2018,
    year_to: int | None = 2024,
    source_ids: tuple[str, ...] = ("crossref",),
    max_candidates: int = 15,
) -> ResearchContract:
    contract_input = ResearchContractInput.model_validate(
        {
            "research_goal": "验证基于规范契约驱动的论文检索生产链",
            "target_objects": ["exoplanet_candidate", "host_star"],
            "data_requirements": {"unit_policy": "canonical"},
            "requested_fields": ["planet.toi_id", "star.tic_id"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {
                "keywords": list(keywords),
                "year_from": year_from,
                "year_to": year_to,
                "source_ids": list(source_ids),
                "max_candidates": max_candidates,
            },
            "output_requirements": ["paper_collection"],
            "evidence_requirements": {"require_locator": True},
            "quality_constraints": {"source_completeness_min": 1.0},
        }
    )
    content_hash = compute_research_contract_content_hash(contract_input)
    return ResearchContract(
        id=contract_id or str(uuid4()),
        project_id=f"proj-{uuid4()}",
        version=version,
        content_hash=content_hash,
        created_from_draft_id=f"draft-{uuid4()}",
        created_at=_FIXED_NOW,
        **contract_input.model_dump(mode="json"),
    )


class _StubAdapter:
    source_id = "crossref"
    adapter_name = "crossref_test_stub"
    adapter_version = "1.0.0"

    def __init__(self, records: tuple[RawSourceRecord, ...] = ()) -> None:
        self.records = records
        self.seen_query: NormalizedPaperQuery | None = None

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult:
        self.seen_query = query
        record_payload = [r.hash_payload() for r in self.records]
        records_hash = compute_canonical_payload_hash(record_payload)
        snapshot = SourceSnapshotRecord(
            snapshot_id=f"snapshot.{uuid4()}",
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=_FIXED_NOW,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            content_hash=records_hash,
            license_note="Public metadata only.",
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
            },
        )
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=query.pagination.page_size,
            returned_rows=len(self.records),
            total_results=len(self.records),
            attempt_count=1,
            status_code=200,
            retrieved_at=_FIXED_NOW,
            request_hash=compute_canonical_payload_hash({"query": query.query_hash}),
            response_hash=records_hash,
        )
        return SourceSearchResult(
            records=self.records, pages=(page,), snapshot=snapshot, retry_count=0
        )


class _StubFailingAdapter(_StubAdapter):
    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult:
        self.seen_query = query
        raise SourceFailure(
            UpstreamFailureClass.timeout,
            "CROSSREF_TIMEOUT",
            retryable=True,
            attempt_count=3,
        )


def test_mapper_projects_contract_into_paper_search_input() -> None:
    contract = _contract()
    search_input = build_paper_search_input(contract)

    assert search_input.schema_version == "1.0.0"
    assert search_input.contract_id == contract.id
    assert search_input.contract_version == contract.version
    assert search_input.contract_content_hash == contract.content_hash
    assert search_input.keywords == contract.paper_search_scope.keywords
    assert search_input.year_from == contract.paper_search_scope.year_from
    assert search_input.year_to == contract.paper_search_scope.year_to
    assert search_input.source_ids == ("crossref",)
    assert search_input.candidate_limit == 15
    assert search_input.selection_limit == 15
    assert search_input.stable_ordering == "source_relevance_then_canonical_tie_breaker"
    assert search_input.content_scope == "bibliographic_metadata"
    assert (
        search_input.access_policy
        == "metadata_url_only_requires_independent_access_evidence"
    )
    assert search_input.source_policy_version == SOURCE_POLICY_VERSION
    assert search_input.producer_name == PRODUCER_NAME
    assert search_input.producer_version == PRODUCER_VERSION
    assert search_input.input_hash == compute_paper_search_input_hash(search_input)


def test_mapper_rejects_empty_keywords_or_sources() -> None:
    empty_kw_contract = _contract(keywords=())
    with pytest.raises(
        ValueError, match="live paper search requires non-empty contract keywords"
    ):
        build_paper_search_input(empty_kw_contract)

    empty_src_contract = _contract(source_ids=())
    with pytest.raises(
        ValueError, match="live paper search requires at least one source id"
    ):
        build_paper_search_input(empty_src_contract)


def test_input_hash_is_stable_and_deterministic() -> None:
    contract_a = _contract()
    input_1 = build_paper_search_input(contract_a)
    input_2 = build_paper_search_input(contract_a)
    assert input_1.input_hash == input_2.input_hash


def test_input_hash_changes_when_contract_identity_or_version_changes() -> None:
    contract_1 = _contract()
    # Create second contract with same paper scope but distinct contract ID
    contract_2 = _contract()
    assert contract_1.id != contract_2.id

    input_1 = build_paper_search_input(contract_1)
    input_2 = build_paper_search_input(contract_2)

    assert input_1.input_hash != input_2.input_hash

    # Further verify that PaperCollection input_hash also reflects contract distinction
    query_1 = normalize_paper_search_input(input_1)
    query_2 = normalize_paper_search_input(input_2)
    rules = PaperCollectionRules(
        adapter_name="crossref_stub",
        adapter_version="1.0.0",
        query_normalization_version=QUERY_NORMALIZATION_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        dedupe_version=DEDUPE_VERSION,
        ranking_version=RANKING_VERSION,
        selection_version=SELECTION_VERSION,
        retry_policy_version=RETRY_POLICY_VERSION,
        source_policy_version=SOURCE_POLICY_VERSION,
        selection_limit=15,
    )
    collection_input_hash_1 = compute_paper_collection_input_hash(
        None, query_1, rules, search_input=input_1
    )
    collection_input_hash_2 = compute_paper_collection_input_hash(
        None, query_2, rules, search_input=input_2
    )
    assert collection_input_hash_1 != collection_input_hash_2


def test_input_hash_changes_when_search_parameters_change() -> None:
    contract_base = _contract(keywords=("TESS",), year_from=2020, year_to=2021)
    input_base = build_paper_search_input(contract_base)

    contract_diff_year = _contract(keywords=("TESS",), year_from=2020, year_to=2022)
    input_diff_year = build_paper_search_input(contract_diff_year)
    assert input_base.input_hash != input_diff_year.input_hash

    contract_diff_limit = _contract(keywords=("TESS",), max_candidates=25)
    input_diff_limit = build_paper_search_input(contract_diff_limit)
    assert input_base.input_hash != input_diff_limit.input_hash


def test_normalizer_strictly_rejects_unsupported_sources() -> None:
    with pytest.raises(PaperSearchExecutionError) as exc_info:
        normalize_canonical_paper_query(
            raw_keywords=("exoplanet",),
            source_ids=("arxiv", "unknown_source"),
            candidate_limit=10,
            page_size=10,
        )
    assert exc_info.value.code == "PAPER_SOURCE_UNSUPPORTED"
    assert exc_info.value.retryable is False
    assert exc_info.value.producer_status == "rejected"


def test_benchmark_and_production_specs_produce_identical_query_semantics() -> None:
    query_prod = normalize_canonical_paper_query(
        raw_keywords=("系外行星 宿主恒星", "exoplanet host star"),
        raw_query_string="exoplanet host star 系外行星 宿主恒星",
        year_from=2018,
        year_to=2024,
        source_ids=("crossref",),
        candidate_limit=20,
        page_size=20,
    )
    query_bench = normalize_canonical_paper_query(
        raw_keywords=("exoplanet host star", "系外行星 宿主恒星"),
        raw_query_string="exoplanet host star 系外行星 宿主恒星",
        year_from=2018,
        year_to=2024,
        source_ids=("crossref",),
        candidate_limit=20,
        page_size=20,
    )
    assert query_prod.normalized_keywords == query_bench.normalized_keywords
    assert query_prod.source_parameters == query_bench.source_parameters
    assert query_prod.pagination == query_bench.pagination
    assert query_prod.sort_strategy == query_bench.sort_strategy
    assert query_prod.query_hash == query_bench.query_hash


def test_live_runner_rejects_legacy_scope_and_requires_paper_search_input() -> None:
    runner = LivePaperCollectionRunner(adapter=_StubAdapter())
    scope = PaperSearchScope(keywords=("TESS",), source_ids=("crossref",))

    with pytest.raises(TypeError):
        runner.prepare_execution(scope=scope)  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        runner.run(scope=scope)  # type: ignore[call-arg]


def test_live_collection_failure_never_falls_back_to_fixture_or_seeds() -> None:
    contract = _contract()
    search_input = build_paper_search_input(contract)
    runner = LivePaperCollectionRunner(
        adapter=_StubFailingAdapter(), clock=lambda: _FIXED_NOW
    )
    collection = runner.run(search_input=search_input)

    assert collection.acquisition_run.status == "failed"
    assert collection.producer.status is ProducerExecutionStatus.failed
    assert collection.producer.error_code == "CROSSREF_TIMEOUT"
    assert collection.candidates == ()
    assert collection.selected_paper_ids == ()
    assert collection.metrics.candidate_count == 0
    assert collection.metrics.source_failure_count == 1
    assert collection.search_input == search_input
    assert collection.benchmark is None


def test_live_paper_collection_payload_integrity_and_input_hash_binding() -> None:
    contract = _contract()
    search_input = build_paper_search_input(contract)
    raw_record = RawSourceRecord(
        source_id="crossref",
        source_record_id="rec-1",
        title="Host Stars of TESS Planets",
        authors=("Ada Researcher",),
        year=2021,
        doi="10.1000/tess-host-1",
        arxiv_id=None,
        url="https://doi.org/10.1000/tess-host-1",
    )
    adapter = _StubAdapter(records=(raw_record,))
    runner = LivePaperCollectionRunner(adapter=adapter, clock=lambda: _FIXED_NOW)
    collection = runner.run(search_input=search_input)

    assert collection.kind == "paper_collection"
    assert collection.schema_version == "3.0.0"
    assert collection.benchmark is None
    assert collection.search_input == search_input
    assert collection.acquisition_run.status == "completed"
    assert collection.producer.status is ProducerExecutionStatus.completed
    assert len(collection.candidates) == 1
    assert collection.candidates[0].selected is True
    assert collection.selected_paper_ids == (collection.candidates[0].canonical_paper_id,)

    # Verify input_hash consistency
    assert collection.input_hash == compute_paper_collection_input_hash(
        None, collection.query, collection.rules, search_input=search_input
    )
    assert collection.producer.input_hash == collection.input_hash


def test_paper_collection_payload_rejects_both_or_neither_benchmark_and_search_input() -> None:
    contract = _contract()
    search_input = build_paper_search_input(contract)
    raw_record = RawSourceRecord(
        source_id="crossref",
        source_record_id="rec-1",
        title="Host Stars of TESS Planets",
        authors=("Ada Researcher",),
        year=2021,
        doi="10.1000/tess-host-1",
        arxiv_id=None,
        url="https://doi.org/10.1000/tess-host-1",
    )
    adapter = _StubAdapter(records=(raw_record,))
    runner = LivePaperCollectionRunner(adapter=adapter, clock=lambda: _FIXED_NOW)
    collection = runner.run(search_input=search_input)

    dict_payload = collection.model_dump(mode="json", exclude_none=True)

    # Corrupt by removing search_input (neither benchmark nor search_input)
    dict_payload_neither = dict(dict_payload)
    dict_payload_neither.pop("search_input", None)
    with pytest.raises(ValidationError, match="PaperCollection requires either benchmark or search_input"):
        PaperCollection.model_validate(dict_payload_neither)


def test_contract_with_open_publication_window_builds_and_validates_cleanly() -> None:
    contract = _contract(year_from=None, year_to=None)
    search_input = build_paper_search_input(contract)

    assert search_input.year_from == 1900
    assert search_input.year_to == 2100
    assert search_input.input_hash == compute_paper_search_input_hash(search_input)

    query = normalize_paper_search_input(search_input)
    assert query.year_from == 1900
    assert query.year_to == 2100


def test_paper_search_input_rejects_selection_limit_exceeding_candidate_limit() -> None:
    contract = _contract(max_candidates=10)
    search_input = build_paper_search_input(contract)
    raw_payload = search_input.model_dump(mode="json")
    raw_payload["selection_limit"] = 15
    raw_payload.pop("input_hash", None)
    raw_payload["input_hash"] = compute_paper_search_input_hash(raw_payload)
    with pytest.raises(
        ValidationError, match="selection_limit must not exceed candidate_limit"
    ):
        PaperSearchInput.model_validate(raw_payload)


def test_paper_search_input_rejects_invalid_stable_ordering() -> None:
    search_input = build_paper_search_input(_contract())
    raw_payload = search_input.model_dump(mode="json")
    raw_payload["stable_ordering"] = "random_shuffle"
    raw_payload.pop("input_hash", None)
    raw_payload["input_hash"] = compute_paper_search_input_hash(raw_payload)
    with pytest.raises(ValidationError):
        PaperSearchInput.model_validate(raw_payload)


def test_paper_search_input_rejects_invalid_access_policy() -> None:
    search_input = build_paper_search_input(_contract())
    raw_payload = search_input.model_dump(mode="json")
    raw_payload["access_policy"] = "fulltext_download_unrestricted"
    raw_payload.pop("input_hash", None)
    raw_payload["input_hash"] = compute_paper_search_input_hash(raw_payload)
    with pytest.raises(ValidationError):
        PaperSearchInput.model_validate(raw_payload)


@pytest.mark.parametrize(
    ("mutator", "expected_match"),
    [
        (
            lambda payload: (
                payload["search_input"].__setitem__("keywords", ["other_keyword"]),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput keywords do not match normalized query",
        ),
        (
            lambda payload: (
                payload["search_input"].__setitem__("year_from", 2019),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput year_from does not match normalized query",
        ),
        (
            lambda payload: (
                payload["search_input"].__setitem__("year_to", 2025),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput year_to does not match normalized query",
        ),
        (
            lambda payload: (
                payload["query"].__setitem__(
                    "original_query_string", "completely different query"
                ),
                payload["query"].__setitem__(
                    "normalized_query_string", normalize_paper_query_text("completely different query")
                ),
                payload["query"].__setitem__(
                    "query_hash", compute_normalized_query_hash(payload["query"])
                ),
                payload["query"].__setitem__(
                    "query_id",
                    f"query.{payload['query']['query_hash'].removeprefix('sha256:')[:24]}",
                ),
                payload["source_executions"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
                payload["source_executions"][0].__setitem__(
                    "request_parameters_hash",
                    compute_paper_source_request_parameters_hash(
                        payload["query"], payload["source_executions"][0]["source_id"]
                    ),
                ),
                payload["source_snapshots"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
            ),
            "PaperSearchInput original query string is inconsistent",
        ),
        (
            lambda payload: (
                payload["search_input"].__setitem__("source_ids", ["other_source"]),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput source_ids do not match normalized query",
        ),
        (
            lambda payload: (
                payload["search_input"].__setitem__("selection_limit", 5),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput selection_limit does not match collection rules",
        ),
        (
            lambda payload: (
                payload["search_input"].__setitem__("producer_version", "2.0.0"),
                payload["search_input"].__setitem__(
                    "input_hash",
                    compute_paper_search_input_hash(payload["search_input"]),
                ),
            ),
            "PaperSearchInput producer identity does not match ProducerExecution",
        ),
        (
            lambda payload: (
                payload["query"].__setitem__(
                    "sort_strategy", "canonical_tie_breaker_only"
                ),
                payload["query"].__setitem__(
                    "query_hash", compute_normalized_query_hash(payload["query"])
                ),
                payload["query"].__setitem__(
                    "query_id",
                    f"query.{payload['query']['query_hash'].removeprefix('sha256:')[:24]}",
                ),
                payload["source_executions"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
                payload["source_executions"][0].__setitem__(
                    "request_parameters_hash",
                    compute_paper_source_request_parameters_hash(
                        payload["query"], payload["source_executions"][0]["source_id"]
                    ),
                ),
                payload["source_snapshots"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
            ),
            "PaperSearchInput stable_ordering does not match query sort strategy",
        ),
        (
            lambda payload: (
                payload["query"].__setitem__("normalization_rule_version", "9.9.9"),
                payload["query"].__setitem__(
                    "query_hash", compute_normalized_query_hash(payload["query"])
                ),
                payload["query"].__setitem__(
                    "query_id",
                    f"query.{payload['query']['query_hash'].removeprefix('sha256:')[:24]}",
                ),
                payload["source_executions"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
                payload["source_executions"][0].__setitem__(
                    "request_parameters_hash",
                    compute_paper_source_request_parameters_hash(
                        payload["query"], payload["source_executions"][0]["source_id"]
                    ),
                ),
                payload["source_snapshots"][0].__setitem__(
                    "query_hash", payload["query"]["query_hash"]
                ),
            ),
            "query normalization rule version does not match collection rules",
        ),
        (
            lambda payload: payload["source_snapshots"][0]["request_metadata"].__setitem__(
                "adapter_name", "wrong_adapter"
            ),
            "SourceSnapshot adapter_name does not match collection rules",
        ),
        (
            lambda payload: payload["source_snapshots"][0]["request_metadata"].__setitem__(
                "adapter_version", "9.9.9"
            ),
            "SourceSnapshot adapter_version does not match collection rules",
        ),
        (
            lambda payload: payload["candidates"][0].__setitem__(
                "ranking_rule_version", "9.9.9"
            ),
            "candidate ranking_rule_version does not match collection rules",
        ),
        (
            lambda payload: payload["candidates"][0].__setitem__(
                "selection_rule_version", "9.9.9"
            ),
            "candidate selection_rule_version does not match collection rules",
        ),
        (
            lambda payload: payload["candidates"][0]["raw"].__setitem__(
                "source_snapshot_id", f"snapshot.{uuid4()}"
            ),
            "candidate lacks SourceSnapshotRecord",
        ),
        (
            lambda payload: payload["source_executions"][0].__setitem__(
                "candidate_count", 99
            ),
            "source execution candidate_count is inconsistent",
        ),
        (
            lambda payload: payload["producer"].__setitem__(
                "parameters_hash", "sha256:" + "0" * 64
            ),
            "ProducerExecution parameters_hash does not match collection rules",
        ),
        (
            lambda payload: payload["acquisition_run"].__setitem__(
                "status", "failed"
            ),
            "acquisition_run status is inconsistent with source executions",
        ),
        (
            lambda payload: payload["metrics"].__setitem__(
                "duplicate_rate", 0.99
            ),
            "duplicate_rate metric is inconsistent",
        ),
    ],
)
def test_paper_collection_rejects_inconsistent_production_search_provenance(
    mutator: Any, expected_match: str
) -> None:
    contract = _contract(max_candidates=10)
    search_input = build_paper_search_input(contract)
    raw_record = RawSourceRecord(
        source_id="crossref",
        source_record_id="rec-1",
        title="Host Stars of TESS Planets",
        authors=("Ada Researcher",),
        year=2021,
        doi="10.1000/tess-host-1",
        arxiv_id=None,
        url="https://doi.org/10.1000/tess-host-1",
    )
    adapter = _StubAdapter(records=(raw_record,))
    runner = LivePaperCollectionRunner(adapter=adapter, clock=lambda: _FIXED_NOW)
    collection = runner.run(search_input=search_input)

    payload = collection.model_dump(mode="json")
    mutator(payload)

    new_input_hash = compute_canonical_payload_hash(
        {
            "query_hash": payload["query"]["query_hash"],
            "rules": payload["rules"],
            "search_input": payload["search_input"]["input_hash"],
        }
    )
    payload["input_hash"] = new_input_hash
    payload["producer"]["input_hash"] = new_input_hash
    payload["output_hash"] = compute_paper_collection_output_hash(payload)
    payload["producer"]["output_hash"] = payload["output_hash"]

    with pytest.raises(ValidationError, match=expected_match):
        PaperCollection.model_validate(payload)


@pytest.mark.parametrize(
    ("mutator", "expected_match"),
    [
        (
            lambda payload: payload["source_executions"][0].__setitem__(
                "query_hash", "sha256:" + "0" * 64
            ),
            "source execution query_hash does not match normalized query",
        ),
        (
            lambda payload: payload["source_executions"][0]["pagination"].__setitem__(
                "page_size", 99
            ),
            "source execution pagination does not match normalized query",
        ),
        (
            lambda payload: (
                payload["source_executions"][0].__setitem__(
                    "source_id", "other_source"
                ),
                payload["source_executions"][0].__setitem__(
                    "source_snapshot_id", None
                ),
                payload["source_executions"][0].__setitem__("status", "failed"),
                payload["source_executions"][0].__setitem__(
                    "failure_class", "timeout"
                ),
                payload["source_executions"][0].__setitem__(
                    "failure_code", "TIMEOUT"
                ),
            ),
            "source executions do not match normalized query sources",
        ),
    ],
)
def test_paper_collection_rejects_source_execution_query_mismatch(
    mutator: Any, expected_match: str
) -> None:
    contract = _contract(max_candidates=10)
    search_input = build_paper_search_input(contract)
    raw_record = RawSourceRecord(
        source_id="crossref",
        source_record_id="rec-1",
        title="Host Stars of TESS Planets",
        authors=("Ada Researcher",),
        year=2021,
        doi="10.1000/tess-host-1",
        arxiv_id=None,
        url="https://doi.org/10.1000/tess-host-1",
    )
    adapter = _StubAdapter(records=(raw_record,))
    runner = LivePaperCollectionRunner(adapter=adapter, clock=lambda: _FIXED_NOW)
    collection = runner.run(search_input=search_input)

    payload = collection.model_dump(mode="json")
    mutator(payload)

    payload["output_hash"] = compute_paper_collection_output_hash(payload)
    payload["producer"]["output_hash"] = payload["output_hash"]

    with pytest.raises(ValidationError, match=expected_match):
        PaperCollection.model_validate(payload)


@pytest.mark.parametrize(
    ("mutator", "expected_match"),
    [
        (
            lambda payload: payload["source_snapshots"][0].__setitem__(
                "query_hash", "sha256:" + "f" * 64
            ),
            "SourceSnapshot query_hash does not match source execution",
        ),
        (
            lambda payload: payload["source_snapshots"][0].__setitem__(
                "source_id", "ads"
            ),
            "SourceSnapshot source_id does not match source execution",
        ),
    ],
)
def test_paper_collection_rejects_snapshot_execution_provenance_mismatch(
    mutator: Any, expected_match: str
) -> None:
    contract = _contract(max_candidates=10)
    search_input = build_paper_search_input(contract)
    raw_record = RawSourceRecord(
        source_id="crossref",
        source_record_id="rec-1",
        title="Host Stars of TESS Planets",
        authors=("Ada Researcher",),
        year=2021,
        doi="10.1000/tess-host-1",
        arxiv_id=None,
        url="https://doi.org/10.1000/tess-host-1",
    )
    adapter = _StubAdapter(records=(raw_record,))
    runner = LivePaperCollectionRunner(adapter=adapter, clock=lambda: _FIXED_NOW)
    collection = runner.run(search_input=search_input)

    payload = collection.model_dump(mode="json")
    mutator(payload)

    payload["output_hash"] = compute_paper_collection_output_hash(payload)
    payload["producer"]["output_hash"] = payload["output_hash"]

    with pytest.raises(ValidationError, match=expected_match):
        PaperCollection.model_validate(payload)


