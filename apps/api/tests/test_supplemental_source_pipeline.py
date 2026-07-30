from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os

import pytest
from pydantic import ValidationError

from app.schemas.enums import SourceMode, UpstreamFailureClass
from app.schemas.source_acquisition import (
    DataQueryCursor,
    DataSourceDataLevel,
    DataSourcePage,
    NormalizedSupplementalSourceQuery,
    SupplementalDataQueryCursor,
    compute_normalized_supplemental_query_hash,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle
from services.data_pipeline.sources.base import SourceFailure
from services.data_pipeline.sources.nasa_exoplanet_archive import NASA_TAP_SYNC_URL
from services.data_pipeline.sources.nasa_planetary_systems import (
    NasaPlanetarySystemsSupplementalAdapter,
)
from services.data_pipeline.sources.supplemental_recorded import (
    DEFAULT_RECORDED_PS_FIXTURE_PATH,
    RecordedNasaPsFixture,
    RecordedNasaPsTransport,
    compute_recorded_ps_fixture_hash,
)
from services.data_pipeline.supplemental_query import (
    normalize_ps_supplemental_query,
    render_ps_page_query,
)


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


def ps_schema_rows(columns: tuple[str, ...]) -> list[dict[str, str]]:
    string_columns = {
        "pl_name",
        "pl_refname",
        "hostname",
        "tic_id",
        "gaia_dr3_id",
        "rowupdate",
        "st_refname",
        "sy_refname",
        "pl_bmassprov",
        "st_metratio",
    }
    integer_columns = {column for column in columns if column.endswith("lim")}
    return [
        {
            "table_name": "ps",
            "column_name": column,
            "datatype": (
                "char"
                if column in string_columns
                else "int"
                if column in integer_columns
                else "double"
            ),
        }
        for column in columns
    ]


def ps_record(
    columns: tuple[str, ...],
    *,
    pl_name: str,
    pl_refname: str,
    tic_id: str,
) -> dict[str, object]:
    record: dict[str, object] = dict.fromkeys(columns)
    record.update(
        {
            "pl_name": pl_name,
            "pl_refname": pl_refname,
            "hostname": pl_name.removesuffix(" b"),
            "tic_id": tic_id,
            "gaia_dr3_id": "Gaia DR3 297045096447719040",
            "ra": 21.3033807,
            "dec": 28.5660169,
            "rowupdate": "2018-09-04",
        }
    )
    return record


def ps_query(
    *,
    tic_ids: tuple[str, ...] = ("TIC 18121498",),
    page_size: int = 1,
    max_pages: int = 1,
    record_limit: int = 1,
) -> NormalizedSupplementalSourceQuery:
    return normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=tic_ids,
        page_size=page_size,
        max_pages=max_pages,
        record_limit=record_limit,
    )


def acquire_live(
    query: NormalizedSupplementalSourceQuery,
    transport: FakeTransport,
    **adapter_kwargs: object,
):
    return NasaPlanetarySystemsSupplementalAdapter(
        transport=transport,
        sleeper=lambda _: None,
        **adapter_kwargs,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )


# Query and shared contract boundaries.


def test_ps_query_is_manifest_driven_and_pins_runtime_schema() -> None:
    bundle = load_frozen_manifest_bundle()
    source = next(
        item
        for item in bundle.field_manifest.sources
        if item.source_id == "nasa_exoplanet_archive.ps"
    )

    query = ps_query(
        tic_ids=("TIC 164830162", "TIC 18121498"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )

    assert query.provider_source_id == "nasa_exoplanet_archive"
    assert query.table_source_id == source.source_id
    assert query.source_table == source.source_table
    assert query.declared_columns == source.approved_columns
    assert set(query.live_unavailable_columns) == {
        "raerr1",
        "raerr2",
        "decerr1",
        "decerr2",
    }
    assert query.selected_columns == tuple(
        column
        for column in source.approved_columns
        if column not in query.live_unavailable_columns
    )
    assert query.row_key_fields == source.row_key_fields
    assert query.input_identity_field == "star.tic_id"
    assert query.source_filter_field == "tic_id"
    assert query.order_by == source.row_key_fields
    assert query.column_contract_content_hash == source.column_contract.content_hash
    assert query.runtime_schema_contract_id == (
        "nasa_exoplanet_archive.ps.runtime_schema.2026-07-30"
    )
    assert query.runtime_schema_contract_version == "1.0.0"
    assert query.runtime_schema_contract_content_hash.startswith("sha256:")


def test_ps_query_hashes_are_stable_for_order_whitespace_and_duplicates() -> None:
    first = ps_query(
        tic_ids=(" TIC   18121498 ", "tic 164830162"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )
    reordered = ps_query(
        tic_ids=("164830162", "TIC 18121498", "TIC 164830162"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )

    assert first.input_values == ("TIC 164830162", "TIC 18121498")
    assert first.input_values == reordered.input_values
    assert first.input_hash == reordered.input_hash
    assert first.query_hash == reordered.query_hash
    assert first.query_id == reordered.query_id


def test_ps_query_hash_changes_for_input_and_pagination() -> None:
    baseline = ps_query(page_size=10, max_pages=2, record_limit=20)
    changed_input = ps_query(
        tic_ids=("TIC 164830162",),
        page_size=10,
        max_pages=2,
        record_limit=20,
    )
    changed_pagination = ps_query(page_size=5, max_pages=4, record_limit=20)

    assert changed_input.input_hash != baseline.input_hash
    assert changed_input.query_hash != baseline.query_hash
    assert changed_pagination.input_hash == baseline.input_hash
    assert changed_pagination.query_hash != baseline.query_hash


def test_ps_page_query_uses_escaped_bounded_keyset_pagination() -> None:
    query = ps_query(
        tic_ids=("TIC 18121498", "TIC 164830162"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )
    page = render_ps_page_query(
        query,
        cursor=SupplementalDataQueryCursor(
            pl_name="HD 8574 b",
            pl_refname="O'Brien et al. 2026",
        ),
        requested_rows=10,
    )

    assert "select top 10" in page
    assert "tic_id in ('TIC 164830162','TIC 18121498')" in page
    assert "O''Brien et al. 2026" in page
    assert page.endswith("order by pl_name,pl_refname")


@pytest.mark.parametrize(
    "value",
    (
        "",
        "TIC -1",
        "TIC 1 or 1=1",
        "Gaia DR3 123",
        "TIC 000",
        "TIC 99999999999999999999",
    ),
)
def test_ps_query_rejects_invalid_or_unsafe_identity_input(value: str) -> None:
    with pytest.raises(ValueError, match="TIC"):
        ps_query(tic_ids=(value,))


def test_data_source_page_rejects_mixed_cursor_types() -> None:
    with pytest.raises(ValidationError, match="same source-specific type"):
        DataSourcePage(
            page_number=2,
            requested_rows=1,
            returned_rows=1,
            attempt_count=1,
            status_code=200,
            retrieved_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
            latency_ms=1,
            cursor_before=DataQueryCursor(tid=1, toi="1.01"),
            cursor_after=SupplementalDataQueryCursor(
                pl_name="Planet b",
                pl_refname="Reference",
            ),
            request_hash="sha256:" + "1" * 64,
            response_hash="sha256:" + "2" * 64,
        )


# Acquisition, provenance, version, schema, and completion semantics.


def test_ps_adapter_builds_complete_paginated_snapshot() -> None:
    query = ps_query(
        tic_ids=("TIC 18121498", "TIC 164830162"),
        page_size=2,
        max_pages=2,
        record_limit=4,
    )
    first_page = [
        ps_record(
            query.selected_columns,
            pl_name="HD 8574 b",
            pl_refname="Reference A",
            tic_id="TIC 18121498",
        ),
        ps_record(
            query.selected_columns,
            pl_name="Kepler-1292 b",
            pl_refname="Reference A",
            tic_id="TIC 164830162",
        ),
    ]
    second_page = [
        ps_record(
            query.selected_columns,
            pl_name="Kepler-1292 b",
            pl_refname="Reference B",
            tic_id="TIC 164830162",
        )
    ]
    transport = FakeTransport(
        json_response(
            ps_schema_rows(query.selected_columns),
            headers={"ETag": 'W/"schema-v1"', "X-Request-Id": "schema-request"},
        ),
        json_response(
            first_page,
            headers={"ETag": 'W/"ps-v1"', "X-Request-Id": "page-request-1"},
        ),
        json_response(second_page, headers={"ETag": 'W/"ps-v1"'}),
    )

    result = acquire_live(
        query,
        transport,
        clock=lambda: datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc),
    )

    assert [page.returned_rows for page in result.pages] == [2, 1]
    assert len(transport.calls) == 3
    assert result.snapshot.source_version_or_etag == 'W/"ps-v1"'
    metadata = result.snapshot.request_metadata
    assert metadata["source_version_evidence"] == {
        "kind": "data_page_etag",
        "value": 'W/"ps-v1"',
    }
    assert metadata["schema_preflight"]["schema_etag"] == 'W/"schema-v1"'
    assert metadata["schema_preflight"]["response_hash"].startswith("sha256:")
    assert metadata["completion_status"] == "complete"
    assert metadata["continuation_cursor"] is None
    assert metadata["runtime_schema_contract"]["datatype_categories"][
        "st_mass"
    ] == "number"
    assert metadata["runtime_schema_contract"]["datatype_categories"][
        "st_masslim"
    ] == "integer"
    assert metadata["pages"][0]["request_id"] == "page-request-1"


def test_ps_snapshot_keeps_schema_hash_separate_when_data_etag_is_absent() -> None:
    query = ps_query()
    transport = FakeTransport(
        json_response(
            ps_schema_rows(query.selected_columns),
            headers={"ETag": 'W/"schema-only"'},
        ),
        json_response([]),
    )

    result = acquire_live(query, transport)

    assert result.snapshot.source_version_or_etag is None
    metadata = result.snapshot.request_metadata
    assert metadata["source_version_or_etag_status"] == "unavailable"
    assert metadata["source_version_evidence"] == {
        "kind": "unavailable",
        "value": None,
    }
    assert metadata["schema_preflight"]["schema_etag"] == 'W/"schema-only"'
    assert metadata["schema_preflight"]["response_hash"].startswith("sha256:")


def test_ps_adapter_rejects_data_version_change_between_pages() -> None:
    query = ps_query(page_size=1, max_pages=2, record_limit=2)
    first = ps_record(
        query.selected_columns,
        pl_name="Planet A b",
        pl_refname="Reference A",
        tic_id="TIC 18121498",
    )
    second = ps_record(
        query.selected_columns,
        pl_name="Planet B b",
        pl_refname="Reference B",
        tic_id="TIC 18121498",
    )
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([first], headers={"ETag": 'W/"v1"'}),
        json_response([second], headers={"ETag": 'W/"v2"'}),
    )

    with pytest.raises(SourceFailure) as error:
        acquire_live(query, transport)

    assert error.value.classification is UpstreamFailureClass.invalid_response
    assert error.value.code == "NASA_PS_SOURCE_VERSION_CHANGED"


def test_ps_adapter_rejects_non_cursor_column_datatype_drift() -> None:
    query = ps_query()
    rows = ps_schema_rows(query.selected_columns)
    for row in rows:
        if row["column_name"] == "st_mass":
            row["datatype"] = "char"
            break
    transport = FakeTransport(json_response(rows))

    with pytest.raises(SourceFailure) as error:
        acquire_live(query, transport)

    assert error.value.code == "NASA_PS_SCHEMA_DRIFT"
    assert len(transport.calls) == 1


def test_ps_adapter_rejects_integer_category_drift() -> None:
    query = ps_query()
    rows = ps_schema_rows(query.selected_columns)
    for row in rows:
        if row["column_name"] == "st_masslim":
            row["datatype"] = "double"
            break
    transport = FakeTransport(json_response(rows))

    with pytest.raises(SourceFailure) as error:
        acquire_live(query, transport)

    assert error.value.code == "NASA_PS_SCHEMA_DRIFT"


def test_ps_adapter_treats_empty_result_as_complete_success() -> None:
    query = ps_query(page_size=5, max_pages=1, record_limit=5)
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = acquire_live(query, transport)

    assert result.records == ()
    assert result.pages[0].returned_rows == 0
    assert result.snapshot.request_metadata["result_status"] == "empty"
    assert result.snapshot.request_metadata["completion_status"] == "complete"


def test_ps_adapter_marks_full_bounded_result_as_truncated() -> None:
    query = ps_query()
    record = ps_record(
        query.selected_columns,
        pl_name="Planet b",
        pl_refname="Reference",
        tic_id="TIC 18121498",
    )
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([record]),
    )

    result = acquire_live(query, transport)

    metadata = result.snapshot.request_metadata
    assert metadata["completion_status"] == "truncated"
    assert metadata["continuation_cursor"] == {
        "pl_name": "Planet b",
        "pl_refname": "Reference",
    }


def test_ps_snapshot_filters_credentials_and_unsafe_response_headers(caplog) -> None:
    query = ps_query()
    transport = FakeTransport(
        json_response(
            ps_schema_rows(query.selected_columns),
            headers={
                "Date": "Thu, 30 Jul 2026 08:00:00 GMT",
                "Set-Cookie": "session=secret-schema",
            },
        ),
        json_response(
            [],
            headers={
                "Authorization": "Bearer highly-sensitive",
                "Cookie": "session=secret-page",
                "X-Request-Id": "safe-request-id",
            },
        ),
    )

    with caplog.at_level(logging.WARNING):
        result = acquire_live(query, transport)

    serialized = result.snapshot.model_dump_json().casefold()
    assert "highly-sensitive" not in serialized
    assert "secret-schema" not in serialized
    assert "secret-page" not in serialized
    assert "authorization" not in serialized
    assert "cookie" not in serialized
    assert "secret" not in caplog.text


# Retry, error, and policy semantics.


@pytest.mark.parametrize(
    ("failure_step", "expected_delay"),
    [
        (TimeoutError("slow upstream"), 0.5),
        (FakeResponse(429, {"Retry-After": "1.5"}, b"{}"), 1.5),
        (FakeResponse(503, {}, b"{}"), 0.5),
        (OSError("temporary network failure"), 0.5),
    ],
)
def test_ps_adapter_retries_bounded_recoverable_failures(
    failure_step: FakeResponse | Exception,
    expected_delay: float,
) -> None:
    query = ps_query()
    delays: list[float] = []
    transport = FakeTransport(
        failure_step,
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = NasaPlanetarySystemsSupplementalAdapter(
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


def test_ps_adapter_stops_after_retry_bound() -> None:
    query = ps_query()
    delays: list[float] = []
    transport = FakeTransport(
        TimeoutError("first"),
        TimeoutError("second"),
        TimeoutError("third"),
    )

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            max_attempts=3,
            sleeper=delays.append,
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.timeout
    assert error.value.code == "NASA_PS_TIMEOUT"
    assert error.value.attempt_count == 3
    assert delays == [0.5, 1.0]


def test_ps_adapter_does_not_retry_permanent_request_errors() -> None:
    query = ps_query()
    transport = FakeTransport(FakeResponse(400, {}, b"bad query"))

    with pytest.raises(SourceFailure) as error:
        acquire_live(query, transport)

    assert error.value.classification is UpstreamFailureClass.upstream_client
    assert error.value.code == "NASA_PS_UPSTREAM_CLIENT_ERROR"
    assert error.value.status_code == 400
    assert len(transport.calls) == 1


def test_ps_adapter_classifies_interrupted_pagination() -> None:
    query = ps_query(page_size=1, max_pages=2, record_limit=2)
    first_page = [
        ps_record(
            query.selected_columns,
            pl_name="HD 8574 b",
            pl_refname="Reference A",
            tic_id="TIC 18121498",
        )
    ]
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response(first_page),
        TimeoutError("page two failed"),
        TimeoutError("page two failed again"),
    )

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            max_attempts=2,
            sleeper=lambda _: None,
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.timeout
    assert error.value.code == "NASA_PS_PAGINATION_INTERRUPTED"
    assert error.value.attempt_count == 2
    assert error.value.__cause__ is not None


@pytest.mark.parametrize(
    ("source_mode", "data_level"),
    [
        ("live", "recorded_response"),
        ("live", "fixture"),
        ("live", "seed"),
        ("fixture", "live_result"),
        ("cached", "live_result"),
    ],
)
def test_ps_adapter_rejects_source_origin_masquerading(
    source_mode: str,
    data_level: str,
) -> None:
    query = ps_query()
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(transport=transport).acquire(
            query,
            source_mode=SourceMode(source_mode),
            data_level=DataSourceDataLevel(data_level),
        )

    assert error.value.classification is UpstreamFailureClass.policy_violation
    assert error.value.code == "NASA_PS_SOURCE_MODE_DATA_LEVEL_MISMATCH"
    assert transport.calls == []


def test_ps_adapter_rejects_query_contract_tampering_before_transport() -> None:
    query = ps_query()
    payload = query.model_dump(mode="json")
    payload["source_table"] = "ps where 1=1"
    query_hash = compute_normalized_supplemental_query_hash(payload)
    payload["query_hash"] = query_hash
    payload["query_id"] = f"query.{query_hash.removeprefix('sha256:')[:24]}"
    tampered = NormalizedSupplementalSourceQuery.model_validate(payload)
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(transport=transport).acquire(
            tampered,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_PS_QUERY_CONTRACT_MISMATCH"
    assert transport.calls == []


# Recorded fixture and CLI boundaries.


def test_recorded_ps_response_runs_without_live_or_cached_label() -> None:
    query = ps_query(
        tic_ids=("TIC 219698776",),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )
    transport = RecordedNasaPsTransport.from_path(
        DEFAULT_RECORDED_PS_FIXTURE_PATH,
        query=query,
    )

    result = NasaPlanetarySystemsSupplementalAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.fixture,
        data_level=DataSourceDataLevel.recorded_response,
    )

    assert len(result.records) == 2
    assert result.snapshot.source_version_or_etag is None
    assert result.snapshot.request_metadata["source_mode"] == "fixture"
    assert result.snapshot.request_metadata["data_level"] == "recorded_response"
    assert result.snapshot.request_metadata["fixture"]["fixture_id"] == (
        "fixture.nasa-ps.by-tic-first-page.2026-07-30"
    )
    assert result.snapshot.request_metadata["completion_status"] == "truncated"
    assert result.snapshot.cache_version is None
    assert transport.remaining_responses == 0


def test_recorded_ps_fixture_rejects_content_tampering() -> None:
    payload = json.loads(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["records"][0]["hostname"] = "tampered"

    with pytest.raises(ValidationError, match="response hash mismatch"):
        RecordedNasaPsFixture.model_validate(payload)


def test_recorded_ps_fixture_rejects_sensitive_response_headers() -> None:
    payload = json.loads(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["page_safe_response_headers"] = {"Set-Cookie": "session=secret"}
    payload["content_hash"] = compute_recorded_ps_fixture_hash(payload)

    with pytest.raises(ValidationError, match="unsafe response header"):
        RecordedNasaPsFixture.model_validate(payload)


def test_recorded_ps_fixture_rejects_multi_page_profile() -> None:
    payload = json.loads(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["pagination"] = {
        "page_size": 1,
        "max_pages": 2,
        "record_limit": 2,
    }

    with pytest.raises(ValidationError, match="one page"):
        RecordedNasaPsFixture.model_validate(payload)


def test_fixture_origin_requires_versioned_provenance_before_request() -> None:
    query = ps_query()
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(transport=transport).acquire(
            query,
            source_mode=SourceMode.fixture,
            data_level=DataSourceDataLevel.recorded_response,
        )

    assert error.value.code == "NASA_PS_FIXTURE_PROVENANCE_MISSING"
    assert transport.calls == []


def test_recorded_ps_cli_exports_reproducible_completion_metadata(
    tmp_path,
    capsys,
) -> None:
    from services.data_pipeline.supplemental_cli import main

    output_path = tmp_path / "nasa-ps-recorded.json"
    exit_code = main(["--mode", "recorded", "--output", str(output_path)])

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    summary = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert exported["source_mode"] == "fixture"
    assert exported["data_level"] == "recorded_response"
    assert len(exported["records"]) == 2
    assert exported["snapshot"]["request_metadata"]["completion_status"] == (
        "truncated"
    )
    assert summary["record_count"] == 2
    assert summary["completion_status"] == "truncated"
    assert summary["research_run_advanced"] is False


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS") != "1",
    reason=(
        "set XINGWEN_RUN_LIVE_SUPPLEMENTAL_SOURCE_TESTS=1 "
        "for the bounded NASA PS TAP smoke"
    ),
)
def test_ps_live_smoke_returns_manifest_conformant_records() -> None:
    query = ps_query(
        tic_ids=("TIC 219698776",),
        page_size=2,
        max_pages=1,
        record_limit=2,
    )

    result = NasaPlanetarySystemsSupplementalAdapter(
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
