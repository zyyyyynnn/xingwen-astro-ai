from __future__ import annotations

import inspect
import json
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    SourceMode,
    UpstreamFailureClass,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.paper_benchmark import BenchmarkSearchScenario
from app.schemas.paper_collection import (
    NormalizedPaperQuery,
    PaperCollection,
    PaperCollectionPayload,
    PaperSourcePage,
    compute_paper_collection_output_hash,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.canonicalize import (
    canonicalize_record,
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
    normalize_url,
)
from services.paper_pipeline.constants import (
    FROZEN_BENCHMARK_CONTENT_HASH,
    FROZEN_BENCHMARK_SCHEMA_VERSION,
    FROZEN_BENCHMARK_VERSION,
    FROZEN_SCIENTIFIC_PAYLOAD_HASH,
)
from services.paper_pipeline.dedupe import group_duplicates
from services.paper_pipeline.benchmark_runner import PaperCollectionBenchmarkRunner
from services.paper_pipeline.query import normalize_benchmark_query
from services.paper_pipeline.ranking import rank_and_select
from services.paper_pipeline.sources.base import (
    HttpResponse,
    RawSourceRecord,
    SourceFailure,
    SourceSearchResult,
)


def _persisted_uuid(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, value))
from services.paper_pipeline.sources.crossref import CrossrefAdapter


FIXED_TIME = datetime(2026, 7, 21, 9, 0, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, outcomes: list[HttpResponse | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        *,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FixtureAdapter:
    source_id = "crossref"
    adapter_name = "crossref_fixture"
    adapter_version = "1.0.0"

    def __init__(
        self,
        records: tuple[RawSourceRecord, ...],
        *,
        retrieved_at: datetime = FIXED_TIME,
    ) -> None:
        self.records = records
        self.retrieved_at = retrieved_at

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        record_payload = [record.hash_payload() for record in self.records]
        response_hash = compute_canonical_payload_hash(record_payload)
        page = PaperSourcePage(
            page_number=1,
            offset=0,
            requested_rows=query.pagination.page_size,
            returned_rows=len(self.records),
            total_results=len(self.records),
            attempt_count=1,
            status_code=200,
            retrieved_at=self.retrieved_at,
            request_hash=compute_canonical_payload_hash(
                {"query_hash": query.query_hash, "page": 1}
            ),
            response_hash=response_hash,
        )
        content_hash = compute_canonical_payload_hash(
            {"query_hash": query.query_hash, "records": record_payload}
        )
        snapshot = SourceSnapshotRecord(
            snapshot_id=f"snapshot.crossref.{content_hash[-24:]}",
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=self.retrieved_at,
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            content_hash=content_hash,
            license_note="Fixture contains public bibliographic metadata only.",
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
                "data_level": data_level.value,
            },
        )
        return SourceSearchResult(
            records=self.records,
            pages=(page,),
            snapshot=snapshot,
            retry_count=0,
        )


class FailureAdapter:
    source_id = "crossref"
    adapter_name = "crossref_failure_fixture"
    adapter_version = "1.0.0"

    def search(self, query, *, source_mode, data_level):  # type: ignore[no-untyped-def]
        raise SourceFailure(
            UpstreamFailureClass.timeout,
            "CROSSREF_TIMEOUT",
            retryable=True,
            attempt_count=3,
        )


def _scenario() -> BenchmarkSearchScenario:
    return load_frozen_benchmark().search_scenarios[0]


def _query(page_size: int = 20):
    return normalize_benchmark_query(
        _scenario(), source_ids=("crossref",), page_size=page_size
    )


def _response(
    items: list[dict[str, object]],
    *,
    total: int | None = None,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> HttpResponse:
    payload = {
        "status": "ok",
        "message": {
            "items": items,
            "total-results": len(items) if total is None else total,
        },
    }
    return HttpResponse(
        status_code=status,
        headers=headers or {},
        body=json.dumps(payload).encode("utf-8"),
    )


def _item(
    doi: str,
    title: str,
    year: int,
    *,
    authors: tuple[tuple[str, str], ...] = (("George", "Ricker"),),
    url: str | None = None,
    abstract: str | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "DOI": doi,
        "title": [title],
        "author": [
            {"given": given, "family": family} for given, family in authors
        ],
        "published": {"date-parts": [[year]]},
        "URL": url or f"https://doi.org/{doi}",
    }
    if abstract is not None:
        item["abstract"] = abstract
    return item


def _record(
    record_id: str,
    title: str,
    year: int | None,
    *,
    doi: str | None = None,
    arxiv_id: str | None = None,
    authors: tuple[str, ...] = ("George R. Ricker",),
    url: str | None = None,
) -> RawSourceRecord:
    return RawSourceRecord(
        source_id="crossref",
        source_record_id=record_id,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
    )


def _adapter(
    transport: FakeTransport,
    *,
    sleeper=lambda _: None,
    max_attempts: int = 3,
) -> CrossrefAdapter:
    return CrossrefAdapter(
        license_note="Public metadata only; linked full text remains provider-governed.",
        transport=transport,
        timeout_seconds=2.5,
        max_attempts=max_attempts,
        clock=lambda: FIXED_TIME,
        sleeper=sleeper,
    )


def test_frozen_benchmark_pin_is_exact() -> None:
    package = load_frozen_benchmark()
    assert package.schema_version == FROZEN_BENCHMARK_SCHEMA_VERSION
    assert package.benchmark_version == FROZEN_BENCHMARK_VERSION
    assert package.scientific_payload_hash == FROZEN_SCIENTIFIC_PAYLOAD_HASH
    assert package.content_hash == FROZEN_BENCHMARK_CONTENT_HASH


def test_query_normalization_and_hash_ignore_case_and_whitespace() -> None:
    original = _scenario()
    payload = original.model_dump(mode="json")
    payload["query"]["keywords"] = [
        f"  {keyword.upper()}  " for keyword in payload["query"]["keywords"]
    ]
    payload["query"]["query_string"] = (
        "  " + payload["query"]["query_string"].upper().replace(" ", "   ") + "  "
    )
    variant = BenchmarkSearchScenario.model_validate(payload)
    left = normalize_benchmark_query(
        original, source_ids=("crossref",), page_size=10
    )
    right = normalize_benchmark_query(
        variant, source_ids=("crossref",), page_size=10
    )
    assert left.normalized_keywords == right.normalized_keywords
    assert left.normalized_query_string == right.normalized_query_string
    assert left.query_hash == right.query_hash
    assert left.query_id == right.query_id
    assert left.source_parameters["crossref"]["sort"] == "relevance"
    assert "abstract" in str(left.source_parameters["crossref"]["select"]).split(",")


def test_crossref_pagination_merges_pages_and_records_metadata() -> None:
    first = _response(
        [
            _item("10.1/one", "One", 2015),
            _item("10.1/two", "Two", 2016),
        ],
        total=3,
        headers={"X-Rate-Limit-Limit": "5", "X-Rate-Limit-Interval": "1s"},
    )
    second = _response([_item("10.1/three", "Three", 2017)], total=3)
    transport = FakeTransport([first, second])
    delays: list[float] = []
    query = _query(page_size=2)
    result = _adapter(transport, sleeper=delays.append).search(
        query,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )
    assert [call["params"]["offset"] for call in transport.calls] == [0, 2]
    assert len(result.records) == 3
    assert [page.returned_rows for page in result.pages] == [2, 1]
    assert delays == [0.2]
    assert NormalizedPaperQuery.model_validate_json(result.snapshot.query) == query
    assert result.snapshot.request_metadata["pagination_strategy"] == "offset"
    assert "authorization" not in json.dumps(
        result.snapshot.request_metadata
    ).casefold()


def test_crossref_timeout_has_bounded_retries_and_backoff() -> None:
    transport = FakeTransport([TimeoutError("secret=abc")] * 3)
    delays: list[float] = []
    with pytest.raises(SourceFailure) as captured:
        _adapter(transport, sleeper=delays.append).search(
            _query(),
            source_mode=SourceMode.fixture,
            data_level=PaperDataLevel.recorded_response,
        )
    assert captured.value.classification is UpstreamFailureClass.timeout
    assert captured.value.attempt_count == 3
    assert len(transport.calls) == 3
    assert delays == [0.25, 0.5]


def test_crossref_rate_limit_retries_with_retry_after() -> None:
    rate_limited = HttpResponse(
        status_code=429,
        headers={"Retry-After": "0.75"},
        body=b'{"token":"must-not-log"}',
    )
    transport = FakeTransport([rate_limited, _response([], total=0)])
    delays: list[float] = []
    result = _adapter(transport, sleeper=delays.append).search(
        _query(),
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )
    assert result.retry_count == 1
    assert delays == [0.75]


def test_crossref_non_retryable_client_error_stops_immediately() -> None:
    transport = FakeTransport([HttpResponse(403, {}, b"forbidden")])
    with pytest.raises(SourceFailure) as captured:
        _adapter(transport).search(
            _query(),
            source_mode=SourceMode.fixture,
            data_level=PaperDataLevel.recorded_response,
        )
    assert captured.value.classification is UpstreamFailureClass.upstream_client
    assert captured.value.retryable is False
    assert len(transport.calls) == 1


def test_crossref_empty_result_is_success_not_failure() -> None:
    result = _adapter(FakeTransport([_response([], total=0)])).search(
        _query(),
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )
    assert result.records == ()
    assert len(result.pages) == 1
    assert result.snapshot.content_hash.startswith("sha256:")


@pytest.mark.parametrize(
    "body,code",
    [
        (b"not-json", "CROSSREF_INVALID_JSON"),
        (json.dumps({"message": {"total-results": 1}}).encode(), "CROSSREF_INVALID_PAGE"),
        (
            json.dumps(
                {"message": {"total-results": 1, "items": [{"DOI": "10.1/x"}]}}
            ).encode(),
            "CROSSREF_ITEM_TITLE_MISSING",
        ),
        (
            json.dumps(
                {
                    "message": {
                        "total-results": 1,
                        "items": [{"title": ["No stable identifier"]}],
                    }
                }
            ).encode(),
            "CROSSREF_ITEM_IDENTIFIER_MISSING",
        ),
    ],
)
def test_crossref_malformed_response_is_classified(body: bytes, code: str) -> None:
    with pytest.raises(SourceFailure) as captured:
        _adapter(FakeTransport([HttpResponse(200, {}, body)])).search(
            _query(),
            source_mode=SourceMode.fixture,
            data_level=PaperDataLevel.recorded_response,
        )
    assert captured.value.classification is UpstreamFailureClass.invalid_response
    assert captured.value.code == code


def test_crossref_sanitizes_html_and_drops_sensitive_headers() -> None:
    transport = FakeTransport(
        [
            _response(
                [
                    _item(
                        "10.1/x",
                        "<b>TESS</b>\x00 catalog",
                        2020,
                        abstract=(
                            "<jats:p>Nearby &amp; confirmed planets at &lt;10 pc; "
                            "the following finding must remain visible.</jats:p>"
                        ),
                    )
                ],
                headers={
                    "Authorization": "Bearer secret",
                    "Set-Cookie": "session=secret",
                    "X-Api-Pool": "public",
                },
            )
        ]
    )
    result = _adapter(transport).search(
        _query(),
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.recorded_response,
    )
    assert result.records[0].title == "TESS catalog"
    assert result.records[0].abstract == (
        "Nearby & confirmed planets at <10 pc; the following finding must remain visible."
    )
    serialized = result.snapshot.model_dump_json().casefold()
    assert "bearer secret" not in serialized
    assert "session=secret" not in serialized
    assert "public" in serialized


@pytest.mark.parametrize(
    "value",
    [
        "DOI:10.3847/1538-3881/AAD050",
        "https://doi.org/10.3847/1538-3881/aad050",
        "http://dx.doi.org/10.3847/1538-3881/aad050",
    ],
)
def test_doi_forms_normalize_to_one_value(value: str) -> None:
    assert normalize_doi(value) == "10.3847/1538-3881/aad050"


@pytest.mark.parametrize(
    "value",
    [
        "arXiv:1706.00495v2",
        "https://arxiv.org/abs/1706.00495",
        "https://arxiv.org/pdf/1706.00495v3.pdf",
    ],
)
def test_arxiv_forms_and_versions_normalize_to_one_value(value: str) -> None:
    assert normalize_arxiv_id(value) == "1706.00495"


def test_title_and_url_normalization_are_stable() -> None:
    assert normalize_title("ＴＥＳＳ — Input: Catalog") == normalize_title(
        "tess input catalog"
    )
    assert (
        normalize_url(
            "HTTPS://EXAMPLE.COM/paper/?utm_source=test&b=2&a=1#section"
        )
        == "https://example.com/paper?a=1&b=2"
    )
    assert normalize_url("https://user:secret@example.com/paper") is None


def test_title_year_duplicate_group_is_stable_across_input_order() -> None:
    left = canonicalize_record(
        _record("a", "The TESS Input Catalog", 2018, authors=("Keivan Stassun",)),
        snapshot_id="snapshot.crossref.test",
    )
    right = canonicalize_record(
        _record("b", "The TESS Input Catalog.", 2018, authors=("K. Stassun",)),
        snapshot_id="snapshot.crossref.test",
    )
    first = group_duplicates((left, right))
    second = group_duplicates((right, left))
    assert len(first.groups) == 1
    assert first.groups[0].duplicate_group_id == second.groups[0].duplicate_group_id
    assert first.groups[0].match_basis == ("title_year_author_match",)


def test_exact_identifier_group_retains_year_and_author_conflicts() -> None:
    left = canonicalize_record(
        _record(
            "a",
            "Same Paper",
            2018,
            doi="10.1000/same",
            authors=("Alice Alpha",),
        ),
        snapshot_id="snapshot.crossref.test",
    )
    right = canonicalize_record(
        _record(
            "b",
            "Same Paper",
            2019,
            doi="https://doi.org/10.1000/SAME",
            authors=("Bob Beta",),
        ),
        snapshot_id="snapshot.crossref.test",
    )
    result = group_duplicates((left, right))
    assert len(result.groups) == 1
    assert len(result.groups[0].candidate_ids) == 2
    assert {conflict.field for conflict in result.groups[0].conflicts} >= {
        "year",
        "authors",
    }
    assert all(result.candidate_info[item].conflicts for item in result.groups[0].candidate_ids)


def test_uncertain_title_year_match_is_not_claimed_as_duplicate() -> None:
    left = canonicalize_record(
        _record("a", "Shared Title", 2020, authors=("Alice Alpha",)),
        snapshot_id="snapshot.crossref.test",
    )
    right = canonicalize_record(
        _record("b", "Shared Title", 2020, authors=("Bob Beta",)),
        snapshot_id="snapshot.crossref.test",
    )
    result = group_duplicates((left, right))
    assert len(result.groups) == 2
    assert len(result.potential_duplicates) == 1
    assert result.potential_duplicates[0].reason == "title/year match has conflicting authors"


def test_ranking_has_final_tie_breaker_and_complete_reasons() -> None:
    records = (
        _record("b", "TESS Input Catalog", 2018, doi="10.1/b"),
        _record("a", "TESS Input Catalog", 2018, doi="10.1/a"),
        _record("duplicate-a", "TESS Input Catalog", 2018, doi="10.1/a"),
    )
    drafts = tuple(
        canonicalize_record(
            record,
            snapshot_id="snapshot.crossref.test",
            occurrence_index=index,
        )
        for index, record in enumerate(records)
    )
    dedupe = group_duplicates(drafts)
    ranked = rank_and_select(
        drafts,
        dedupe,
        normalized_keywords=("tess input catalog",),
        normalized_query="tess input catalog",
        year_from=2014,
        year_to=2021,
        selection_limit=1,
    )
    assert [candidate.ranking_key for candidate in ranked] == sorted(
        candidate.ranking_key for candidate in ranked
    )
    assert sum(candidate.selected for candidate in ranked) == 1
    assert all(
        candidate.selection_reason if candidate.selected else candidate.exclusion_reason
        for candidate in ranked
    )


def test_pipeline_schema_provenance_metrics_and_hashes_are_stable() -> None:
    first_run_id = "722862b3-69f3-4b23-b3c4-248a1989396d"
    second_run_id = _persisted_uuid("paper-collection.second-run")
    records = (
        _record(
            "ricker",
            "Transiting Exoplanet Survey Satellite",
            2015,
            doi="https://doi.org/10.1117/1.JATIS.1.1.014003",
            arxiv_id="1406.0151v2",
        ),
        _record(
            "ricker-duplicate",
            "Transiting Exoplanet Survey Satellite",
            2015,
            doi="10.1117/1.jatis.1.1.014003",
            authors=("George R. Ricker", "Joshua N. Winn"),
        ),
        _record("topical", "A TESS host stars study", 2020, doi="10.1/topical"),
    )
    first = PaperCollectionBenchmarkRunner(
        adapter=FixtureAdapter(records, retrieved_at=FIXED_TIME),
        clock=lambda: FIXED_TIME,
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        page_size=20,
        selection_limit=2,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
        run_id=first_run_id,
    )
    later = FIXED_TIME + timedelta(days=1)
    second = PaperCollectionBenchmarkRunner(
        adapter=FixtureAdapter(records, retrieved_at=later),
        clock=lambda: later,
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        page_size=20,
        selection_limit=2,
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
        run_id=second_run_id,
    )
    assert PaperCollection.model_validate_json(first.model_dump_json()) == first
    assert first.input_hash == second.input_hash
    assert first.output_hash == second.output_hash
    assert first.producer.output_hash == first.output_hash
    assert first.producer.run_id == first_run_id
    assert first.metrics.candidate_count == 3
    assert first.metrics.duplicate_candidate_count == 1
    assert first.metrics.duplicate_rate == pytest.approx(1 / 3, abs=1e-6)
    assert first.metrics.recalled_expected_candidate_count == 1
    assert all(
        candidate.raw.source_snapshot_id in first.source_snapshot_ids
        for candidate in first.candidates
    )
    assert first.rules.canonicalization_version == "1.0.0"
    assert first.acquisition_run.status == "completed"


def test_live_failure_records_truth_and_never_falls_back_to_seed() -> None:
    collection = PaperCollectionBenchmarkRunner(
        adapter=FailureAdapter(), clock=lambda: FIXED_TIME
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.live,
        data_level=PaperDataLevel.live_result,
    )
    assert collection.acquisition_run.status == "failed"
    assert collection.candidates == ()
    assert collection.source_snapshots == ()
    assert collection.metrics.source_failure_count == 1
    assert collection.source_executions[0].failure_class is UpstreamFailureClass.timeout
    assert collection.source_executions[0].retry_count == 2
    assert collection.source_executions[0].status is PaperSourceExecutionStatus.failed
    assert collection.source_executions[0].query_hash == collection.query.query_hash
    assert collection.source_executions[0].pagination == collection.query.pagination


def test_pipeline_empty_result_has_distinct_metrics() -> None:
    collection = PaperCollectionBenchmarkRunner(
        adapter=FixtureAdapter(()), clock=lambda: FIXED_TIME
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
    )
    assert collection.acquisition_run.status == "completed"
    assert collection.metrics.source_empty_result_count == 1
    assert collection.metrics.source_failure_count == 0
    assert collection.metrics.candidate_count == 0
    assert collection.metrics.candidate_recall == 0.0


def test_output_hash_tampering_fails_schema_validation() -> None:
    collection = PaperCollectionBenchmarkRunner(
        adapter=FixtureAdapter(()), clock=lambda: FIXED_TIME
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
    )
    payload = collection.model_dump(mode="json")
    payload["output_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="output_hash does not match"):
        PaperCollection.model_validate(payload)


def test_source_snapshot_rejects_sensitive_request_metadata() -> None:
    with pytest.raises(ValidationError, match="sensitive keys"):
        SourceSnapshotRecord(
            snapshot_id="snapshot.crossref.test",
            source_id="crossref",
            source_type="paper_metadata",
            retrieved_at=FIXED_TIME,
            query="tess",
            query_hash="sha256:" + "1" * 64,
            content_hash="sha256:" + "2" * 64,
            license_note="metadata only",
            request_metadata={"headers": {"Authorization": "Bearer secret"}},
        )


def test_source_mode_and_data_level_cannot_be_misrepresented() -> None:
    collection = PaperCollectionBenchmarkRunner(
        adapter=FixtureAdapter(()), clock=lambda: FIXED_TIME
    ).run(
        scenario_id="search.tess_mission_and_catalogs",
        source_mode=SourceMode.fixture,
        data_level=PaperDataLevel.fixture,
    )
    live_payload = collection.model_dump(mode="json")
    live_payload["source_executions"][0]["source_mode"] = "live"
    with pytest.raises(ValidationError, match="live_result"):
        PaperCollection.model_validate(live_payload)

    cached_payload = collection.model_dump(mode="json")
    cached_payload["source_executions"][0]["source_mode"] = "cached"
    cached_payload["source_executions"][0]["data_level"] = "real_run_cache"
    with pytest.raises(ValidationError, match="cache_applicability"):
        PaperCollection.model_validate(cached_payload)

    cached_payload["source_executions"][0]["cache_applicability"] = (
        "query_hash matches the cached acquisition run"
    )
    with pytest.raises(
        ValidationError, match="live_failure_class and live_failure_code"
    ):
        PaperCollection.model_validate(cached_payload)

    cached_payload["source_executions"][0]["live_failure_class"] = "timeout"
    cached_payload["source_executions"][0]["live_failure_code"] = "CROSSREF_TIMEOUT"
    with pytest.raises(ValidationError, match="real origin Run and ArtifactVersion"):
        PaperCollection.model_validate(cached_payload)

    snapshot_id = cached_payload["source_executions"][0]["source_snapshot_id"]
    for snapshot in cached_payload["source_snapshots"]:
        if snapshot["snapshot_id"] == snapshot_id:
            snapshot["request_metadata"] = {
                **snapshot["request_metadata"],
                "origin_run_id": "run_origin_01",
                "origin_artifact_version_id": "artv_origin_01",
            }
    with pytest.raises(ValidationError, match="cache_version"):
        PaperCollection.model_validate(cached_payload)

    for snapshot in cached_payload["source_snapshots"]:
        if snapshot["snapshot_id"] == snapshot_id:
            snapshot["cache_version"] = "cache_fixture"

    def seal(payload: dict[str, object]) -> dict[str, object]:
        candidate = json.loads(json.dumps(payload))
        candidate.pop("output_hash", None)
        candidate["producer"]["output_hash"] = None
        staged = PaperCollectionPayload.model_validate(candidate)
        output_hash = compute_paper_collection_output_hash(staged)
        sealed = staged.model_dump(mode="json", exclude_none=False)
        sealed["producer"]["output_hash"] = output_hash
        sealed["output_hash"] = output_hash
        return sealed

    valid_cached = seal(cached_payload)
    assert PaperCollection.model_validate(valid_cached)

    for target, field in (
        ("execution", "cache_applicability"),
        ("execution", "live_failure_code"),
        ("snapshot", "cache_version"),
    ):
        blank = json.loads(json.dumps(valid_cached))
        records = (
            blank["source_executions"]
            if target == "execution"
            else blank["source_snapshots"]
        )
        records[0][field] = "   "
        with pytest.raises(ValidationError, match=field):
            PaperCollection.model_validate(seal(blank))


def test_failure_logs_do_not_include_credentials_or_response_body(caplog) -> None:
    transport = FakeTransport([OSError("API_KEY=super-secret")] * 3)
    with caplog.at_level("WARNING"), pytest.raises(SourceFailure):
        _adapter(transport).search(
            _query(),
            source_mode=SourceMode.fixture,
            data_level=PaperDataLevel.recorded_response,
        )
    assert "super-secret" not in caplog.text
    assert "api_key" not in caplog.text.casefold()
    assert "CROSSREF_TRANSPORT_ERROR" in caplog.text


def test_pipeline_has_no_research_run_state_dependency() -> None:
    source = inspect.getsource(PaperCollectionBenchmarkRunner)
    assert "ResearchRun" not in source
    assert "state_machine" not in source
    assert "ArtifactVersion" not in source


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("XINGWEN_RUN_LIVE_PAPER_TEST") != "1",
    reason="set XINGWEN_RUN_LIVE_PAPER_TEST=1 for explicit Crossref live smoke",
)
def test_frozen_benchmark_query_runs_against_real_crossref() -> None:
    collection = PaperCollectionBenchmarkRunner(timeout_seconds=20.0).run(
        scenario_id="search.tess_mission_and_catalogs",
        page_size=25,
        selection_limit=10,
        source_mode=SourceMode.live,
        data_level=PaperDataLevel.live_result,
    )
    assert collection.acquisition_run.status == "completed"
    assert collection.metrics.source_failure_count == 0
    assert collection.source_executions[0].data_level is PaperDataLevel.live_result
    assert collection.source_snapshots[0].source_id == "crossref"
