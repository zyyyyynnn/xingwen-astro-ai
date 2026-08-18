from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os

import pytest

from services.data_pipeline.constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle
from app.schemas.source_acquisition import DataQueryCursor
from services.data_pipeline.query import normalize_toi_query, render_toi_page_query


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    headers: Mapping[str, str]
    body: bytes


class FakeTransport:
    def __init__(self, *steps: FakeResponse | Exception) -> None:
        self.steps = list(steps)
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        *,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "headers": dict(headers),
                "timeout_seconds": timeout_seconds,
            }
        )
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def json_response(
    payload: object,
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> FakeResponse:
    return FakeResponse(
        status_code=status_code,
        headers=headers or {},
        body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    )


def toi_schema_rows(columns: tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "table_name": "toi",
            "column_name": column,
            "datatype": "int" if column == "tid" else "char" if column == "toi" else "double",
        }
        for column in columns
    ]


def toi_record(columns: tuple[str, ...], *, tid: int, toi: str) -> dict[str, object]:
    record = dict.fromkeys(columns)
    record.update(
        {
            "tid": tid,
            "toi": toi,
            "ra": 15.25,
            "dec": -12.5,
            "rowupdate": "2026-07-20",
            "tfopwg_disp": "PC",
        }
    )
    return record


def test_frozen_manifest_loader_pins_case_and_field_manifest_versions() -> None:
    bundle = load_frozen_manifest_bundle()

    assert bundle.case_manifest.case_id == "exoplanet_host_star"
    assert bundle.case_manifest.manifest_version == FROZEN_CASE_MANIFEST_VERSION
    assert bundle.case_manifest.content_hash == FROZEN_CASE_MANIFEST_CONTENT_HASH
    assert bundle.field_manifest.manifest_version == FROZEN_FIELD_MANIFEST_VERSION
    assert bundle.field_manifest.content_hash == FROZEN_FIELD_MANIFEST_CONTENT_HASH


def test_toi_query_is_manifest_driven_and_hash_stable() -> None:
    bundle = load_frozen_manifest_bundle()
    source = next(
        item
        for item in bundle.field_manifest.sources
        if item.source_id == "nasa_exoplanet_archive.toi"
    )

    first = normalize_toi_query(bundle, page_size=25, max_pages=4, record_limit=100)
    second = normalize_toi_query(bundle, page_size=25, max_pages=4, record_limit=100)
    changed = normalize_toi_query(bundle, page_size=20, max_pages=5, record_limit=100)

    assert first.table_source_id == source.source_id
    assert first.selected_columns == source.approved_columns
    assert first.row_key_fields == source.row_key_fields
    assert first.constraints == ("tid is not null", "toi is not null")
    assert first.order_by == ("tid", "toi")
    assert first.query_hash == second.query_hash
    assert first.query_id == second.query_id
    assert changed.query_hash != first.query_hash


def test_toi_query_can_close_a_confirmed_tic_selection() -> None:
    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=100,
        max_pages=1,
        record_limit=100,
        tic_ids=("TIC 307210830", "261136679", "307210830"),
        confirmed_only=True,
    )

    assert query.constraints == (
        "tid is not null",
        "toi is not null",
        "tfopwg_disp = 'CP'",
        "tid in (261136679,307210830)",
    )
    rendered = render_toi_page_query(query, cursor=None, requested_rows=100)
    assert "tfopwg_disp = 'CP'" in rendered
    assert "tid in (261136679,307210830)" in rendered


def test_toi_page_query_uses_bounded_keyset_pagination() -> None:
    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )

    first_page = render_toi_page_query(query, cursor=None, requested_rows=25)
    next_page = render_toi_page_query(
        query,
        cursor=DataQueryCursor(tid=50365310, toi="1000.01"),
        requested_rows=10,
    )

    selected = ",".join(query.selected_columns)
    assert first_page == (
        f"select top 25 {selected} from toi "
        "where tid is not null and toi is not null order by tid,toi"
    )
    assert next_page == (
        f"select top 10 {selected} from toi "
        "where tid is not null and toi is not null "
        "and (tid > 50365310 or (tid = 50365310 and toi > '1000.01')) "
        "order by tid,toi"
    )


def test_nasa_tap_adapter_preflights_schema_and_builds_paginated_snapshot() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=2,
        record_limit=3,
    )
    first_page = [
        toi_record(query.selected_columns, tid=100, toi="1000.01"),
        toi_record(query.selected_columns, tid=101, toi="1001.01"),
    ]
    second_page = [toi_record(query.selected_columns, tid=102, toi="1002.01")]
    transport = FakeTransport(
        json_response(
            toi_schema_rows(query.selected_columns),
            headers={"X-Request-Id": "req-schema"},
        ),
        json_response(
            first_page,
            headers={"ETag": 'W/"toi-fixture"', "X-Request-Id": "req-page-1"},
        ),
        json_response(second_page),
    )
    adapter = NasaExoplanetArchiveAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    )

    result = adapter.acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert [record.row_key for record in result.records] == [
        (("toi", "1000.01"),),
        (("toi", "1001.01"),),
        (("toi", "1002.01"),),
    ]
    assert all(record.content_hash.startswith("sha256:") for record in result.records)
    assert [page.returned_rows for page in result.pages] == [2, 1]
    assert [page.cursor_after for page in result.pages] == [
        DataQueryCursor(tid=101, toi="1001.01"),
        DataQueryCursor(tid=102, toi="1002.01"),
    ]
    assert len(transport.calls) == 3
    assert "TAP_SCHEMA.columns" in str(transport.calls[0]["params"])
    assert "top 2" in str(transport.calls[1]["params"])
    assert "top 1" in str(transport.calls[2]["params"])
    assert "tid > 101" in str(transport.calls[2]["params"])
    assert result.retry_count == 0
    assert result.snapshot.source_id == "nasa_exoplanet_archive.toi"
    assert result.snapshot.query_hash == query.query_hash
    assert result.snapshot.source_version_or_etag == 'W/"toi-fixture"'
    assert result.snapshot.content_hash.startswith("sha256:")
    assert result.snapshot.request_metadata["producer"] == {
        "name": "xingwen.data_acquisition",
        "version": "1.0.0",
    }
    assert result.snapshot.request_metadata["rule_versions"] == {
        "query_normalization": "1.0.0",
        "retry_policy": "1.0.0",
        "source_policy": "1.0.0",
    }
    assert result.snapshot.request_metadata["pagination_strategy"] == "keyset:tid,toi"
    assert result.snapshot.request_metadata["request_id_status"] == "partially_available"
    assert result.snapshot.request_metadata["schema_preflight"]["status_code"] == 200
    assert result.snapshot.request_metadata["schema_preflight"]["request_id"] == "req-schema"
    assert "TAP_SCHEMA.columns" in result.snapshot.request_metadata["schema_preflight"][
        "adql"
    ]
    assert result.snapshot.request_metadata["pages"][0]["request_id"] == "req-page-1"
    assert result.snapshot.request_metadata["pages"][1]["request_id"] is None
    assert result.snapshot.request_metadata["pages"][1]["cursor_before"] == {
        "tid": 101,
        "toi": "1001.01",
    }
    assert "tid > 101" in result.snapshot.request_metadata["pages"][1]["adql"]


def test_nasa_tap_snapshot_keeps_only_safe_reproducibility_headers() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )
    transport = FakeTransport(
        json_response(toi_schema_rows(query.selected_columns)),
        json_response(
            [],
            headers={
                "Date": "Wed, 22 Jul 2026 04:00:00 GMT",
                "X-Rate-Limit-Remaining": "17",
                "Authorization": "Bearer must-not-be-saved",
            },
        ),
    )
    result = NasaExoplanetArchiveAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    page_metadata = result.snapshot.request_metadata["pages"][0]
    serialized = result.snapshot.model_dump_json()
    assert page_metadata["status_code"] == 200
    assert page_metadata["rate_limit_metadata"] == {
        "x-rate-limit-remaining": "17"
    }
    assert result.snapshot.request_metadata["request_id_status"] == "unavailable"
    assert result.snapshot.request_metadata["source_version_or_etag_status"] == "unavailable"
    assert "must-not-be-saved" not in serialized
    assert "authorization" not in serialized.casefold()


def test_nasa_tap_adapter_rejects_duplicate_manifest_row_keys_across_pages() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=2,
        record_limit=2,
    )
    transport = FakeTransport(
        json_response(toi_schema_rows(query.selected_columns)),
        json_response([toi_record(query.selected_columns, tid=100, toi="1000.01")]),
        json_response([toi_record(query.selected_columns, tid=101, toi="1000.01")]),
    )

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(
            transport=transport,
            clock=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
            sleeper=lambda _: None,
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_TAP_DUPLICATE_ROW_KEY"
    assert error.value.retryable is False


def test_nasa_tap_adapter_rejects_tap_schema_drift_before_data_query() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    drifted_columns = tuple(
        column for column in query.selected_columns if column != "rowupdate"
    )
    transport = FakeTransport(json_response(toi_schema_rows(drifted_columns)))

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport, sleeper=lambda _: None).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_TAP_SCHEMA_DRIFT"
    assert error.value.retryable is False
    assert len(transport.calls) == 1


def test_nasa_tap_adapter_rejects_page_larger_than_requested_bound() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport(
        json_response(toi_schema_rows(query.selected_columns)),
        json_response(
            [
                toi_record(query.selected_columns, tid=100, toi="1000.01"),
                toi_record(query.selected_columns, tid=101, toi="1001.01"),
            ]
        ),
    )

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport, sleeper=lambda _: None).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_TAP_PAGE_SIZE_EXCEEDED"
    assert error.value.retryable is False


@pytest.mark.parametrize(
    ("failure_step", "expected_delay"),
    [
        (TimeoutError("slow upstream"), 0.5),
        (FakeResponse(429, {"Retry-After": "1.5"}, b"{}"), 1.5),
        (FakeResponse(503, {}, b"{}"), 0.5),
    ],
)
def test_nasa_tap_adapter_retries_bounded_retryable_failures(
    failure_step: FakeResponse | Exception,
    expected_delay: float,
) -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    delays: list[float] = []
    transport = FakeTransport(
        failure_step,
        json_response(toi_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = NasaExoplanetArchiveAdapter(
        transport=transport,
        max_attempts=2,
        sleeper=delays.append,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert result.retry_count == 1
    assert delays == [expected_delay]
    assert len(transport.calls) == 3


def test_nasa_tap_adapter_does_not_retry_upstream_client_errors() -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport(FakeResponse(400, {}, b"bad query"))

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(
            transport=transport,
            max_attempts=3,
            sleeper=lambda _: pytest.fail("non-retryable failure slept"),
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.upstream_client
    assert error.value.code == "NASA_TAP_UPSTREAM_CLIENT_ERROR"
    assert error.value.status_code == 400
    assert error.value.attempt_count == 1
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("steps", "expected_code"),
    [
        ((FakeResponse(200, {}, b"not-json"),), "NASA_TAP_SCHEMA_INVALID_JSON"),
        (
            (
                "valid-schema",
                FakeResponse(200, {}, b"not-json"),
            ),
            "NASA_TAP_INVALID_JSON",
        ),
    ],
)
def test_nasa_tap_adapter_classifies_invalid_json_without_retry(
    steps: tuple[FakeResponse | str, ...],
    expected_code: str,
) -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    resolved_steps = tuple(
        json_response(toi_schema_rows(query.selected_columns))
        if step == "valid-schema"
        else step
        for step in steps
    )
    transport = FakeTransport(*resolved_steps)  # type: ignore[arg-type]

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport, sleeper=lambda _: None).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.invalid_response
    assert error.value.code == expected_code
    assert error.value.retryable is False


def test_nasa_tap_adapter_rejects_non_finite_json_numbers() -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    record = toi_record(query.selected_columns, tid=100, toi="1000.01")
    record["ra"] = float("nan")
    transport = FakeTransport(
        json_response(toi_schema_rows(query.selected_columns)),
        FakeResponse(200, {}, json.dumps([record]).encode("utf-8")),
    )

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(
            transport=transport,
            max_attempts=3,
            sleeper=lambda _: pytest.fail("invalid JSON must not be retried"),
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.invalid_response
    assert error.value.code == "NASA_TAP_INVALID_JSON"
    assert error.value.retryable is False
    assert len(transport.calls) == 2


def test_nasa_tap_adapter_treats_empty_result_as_success() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import (
        DataSourceCompletion,
        DataSourceDataLevel,
    )
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=5,
        max_pages=1,
        record_limit=5,
    )
    transport = FakeTransport(
        json_response(toi_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = NasaExoplanetArchiveAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert result.records == ()
    assert len(result.pages) == 1
    assert result.pages[0].returned_rows == 0
    assert result.completion == DataSourceCompletion(status="complete")
    assert result.snapshot.content_hash.startswith("sha256:")
    assert result.snapshot.request_metadata["pages"][0]["returned_rows"] == 0


def test_recorded_response_is_explicit_fixture_not_live_or_cached() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )
    from services.data_pipeline.sources.recorded import (
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        RecordedNasaToiTransport,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )
    transport = RecordedNasaToiTransport.from_path(
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        query=query,
    )

    result = NasaExoplanetArchiveAdapter(
        transport=transport,
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.recorded_response,
    )

    assert result.snapshot.request_metadata["source_mode"] == "fixture"
    assert result.snapshot.request_metadata["data_level"] == "recorded_response"
    assert result.snapshot.request_metadata["fixture"]["fixture_id"] == (
        "fixture.nasa-toi.first-page.2026-07-22"
    )
    assert result.snapshot.request_metadata["fixture"]["content_hash"].startswith(
        "sha256:"
    )
    assert [record.row_key for record in result.records] == [
        (("toi", "1000.01"),),
        (("toi", "1001.01"),),
    ]
    assert result.snapshot.cache_version is None


def test_recorded_fixture_rejects_content_tampering() -> None:
    from pydantic import ValidationError
    from services.data_pipeline.sources.recorded import (
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        RecordedNasaToiFixture,
    )

    payload = json.loads(DEFAULT_RECORDED_TOI_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["records"][0]["tfopwg_disp"] = "tampered"

    with pytest.raises(ValidationError, match="content_hash mismatch"):
        RecordedNasaToiFixture.model_validate(payload)


def test_recorded_transport_revalidates_fixture_before_replay() -> None:
    from pydantic import ValidationError
    from services.data_pipeline.sources.recorded import (
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        RecordedNasaToiFixture,
        RecordedNasaToiTransport,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )
    fixture = RecordedNasaToiFixture.model_validate_json(
        DEFAULT_RECORDED_TOI_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    fixture.records[0]["ra"] = "tampered-after-validation"

    with pytest.raises(ValidationError, match="content_hash mismatch"):
        RecordedNasaToiTransport(fixture, query=query)


def test_recorded_transport_detaches_replay_payload_and_metadata() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )
    from services.data_pipeline.sources.recorded import (
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        RecordedNasaToiFixture,
        RecordedNasaToiTransport,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )
    fixture = RecordedNasaToiFixture.model_validate_json(
        DEFAULT_RECORDED_TOI_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    original_ra = fixture.records[0]["ra"]
    original_hash = fixture.content_hash
    transport = RecordedNasaToiTransport(fixture, query=query)

    fixture.records[0]["ra"] = "tampered-after-transport-init"
    transport.fixture_metadata["content_hash"] = "sha256:" + "0" * 64

    result = NasaExoplanetArchiveAdapter(
        transport=transport,
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.recorded_response,
    )

    assert result.records[0].payload["ra"] == original_ra
    assert result.snapshot.request_metadata["fixture"]["content_hash"] == original_hash


def test_recorded_fixture_rejects_sensitive_response_headers() -> None:
    from pydantic import ValidationError
    from services.data_pipeline.sources.recorded import (
        DEFAULT_RECORDED_TOI_FIXTURE_PATH,
        RecordedNasaToiFixture,
        compute_recorded_fixture_hash,
    )

    payload = json.loads(DEFAULT_RECORDED_TOI_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["safe_response_headers"] = {"Authorization": "Bearer secret"}
    payload.pop("content_hash")
    payload["content_hash"] = compute_recorded_fixture_hash(payload)

    with pytest.raises(ValidationError, match="unsafe response header"):
        RecordedNasaToiFixture.model_validate(payload)


def test_fixture_origin_requires_versioned_provenance_before_any_request() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport).acquire(
            query,
            source_mode=SourceMode.fixture,
            data_level=DataSourceDataLevel.recorded_response,
        )

    assert error.value.code == "NASA_TAP_FIXTURE_PROVENANCE_MISSING"
    assert transport.calls == []


@pytest.mark.parametrize(
    ("source_mode", "data_level"),
    [
        ("live", "fixture"),
        ("fixture", "live_result"),
        ("cached", "live_result"),
    ],
)
def test_nasa_tap_adapter_rejects_source_origin_masquerading(
    source_mode: str,
    data_level: str,
) -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport).acquire(
            query,
            source_mode=SourceMode(source_mode),
            data_level=DataSourceDataLevel(data_level),
        )

    assert error.value.classification is UpstreamFailureClass.policy_violation
    assert error.value.code == "NASA_TAP_SOURCE_MODE_DATA_LEVEL_MISMATCH"
    assert transport.calls == []


def test_nasa_tap_adapter_rejects_query_contract_tampering_before_transport() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import (
        DataSourceDataLevel,
        NormalizedDataSourceQuery,
        compute_normalized_data_query_hash,
    )
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    payload = query.model_dump(mode="json")
    payload["source_table"] = "toi where 1=1"
    query_hash = compute_normalized_data_query_hash(payload)
    payload["query_hash"] = query_hash
    payload["query_id"] = f"query.{query_hash.removeprefix('sha256:')[:24]}"
    tampered_query = NormalizedDataSourceQuery.model_validate(payload)
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaExoplanetArchiveAdapter(transport=transport).acquire(
            tampered_query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_TAP_QUERY_CONTRACT_MISMATCH"
    assert error.value.retryable is False
    assert transport.calls == []


def test_recorded_cli_exports_reproducible_fixture_result(
    tmp_path,
    capsys,
) -> None:
    from services.data_pipeline.__main__ import main

    output_path = tmp_path / "nasa-toi-recorded.json"

    exit_code = main(["--mode", "recorded", "--output", str(output_path)])

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert exported["source_mode"] == "fixture"
    assert exported["data_level"] == "recorded_response"
    assert len(exported["records"]) == 2
    assert exported["snapshot"]["request_metadata"]["fixture"]["fixture_id"] == (
        "fixture.nasa-toi.first-page.2026-07-22"
    )
    assert summary["record_count"] == 2
    assert summary["source_mode"] == "fixture"
    assert summary["research_run_advanced"] is False


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("XINGWEN_RUN_LIVE_DATA_SOURCE_TESTS") != "1",
    reason="set XINGWEN_RUN_LIVE_DATA_SOURCE_TESTS=1 for the bounded NASA TAP smoke",
)
def test_nasa_tap_live_smoke_returns_manifest_conformant_records() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import (
        NasaExoplanetArchiveAdapter,
    )

    query = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )

    result = NasaExoplanetArchiveAdapter(
        timeout_seconds=30,
        page_delay_seconds=0,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert 0 <= len(result.records) <= 2
    assert all(
        set(record.payload) == set(query.selected_columns)
        for record in result.records
    )
    assert result.snapshot.request_metadata["source_mode"] == "live"
    assert result.snapshot.request_metadata["data_level"] == "live_result"
    assert result.snapshot.request_metadata.get("fixture") is None
