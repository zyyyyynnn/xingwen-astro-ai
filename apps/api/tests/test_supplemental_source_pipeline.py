from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os

import pytest

from services.data_pipeline.manifest import load_frozen_manifest_bundle
from services.data_pipeline.supplemental_query import (
    normalize_ps_supplemental_query,
    render_ps_page_query,
)
from app.schemas.source_acquisition import (
    NormalizedSupplementalSourceQuery,
    SupplementalDataQueryCursor,
    compute_normalized_supplemental_query_hash,
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
    return [
        {
            "table_name": "ps",
            "column_name": column,
            "datatype": "char" if column in string_columns else "double",
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


def test_ps_query_is_manifest_driven_and_pins_the_supplemental_table() -> None:
    bundle = load_frozen_manifest_bundle()
    source = next(
        item
        for item in bundle.field_manifest.sources
        if item.source_id == "nasa_exoplanet_archive.ps"
    )

    query = normalize_ps_supplemental_query(
        bundle,
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
    assert query.column_contract_snapshot_id == (
        "nasa_exoplanet_archive.column_adjudications.2026-07-19"
    )
    assert query.column_contract_content_hash == source.column_contract.content_hash


def test_ps_query_hashes_are_stable_for_order_and_whitespace() -> None:
    bundle = load_frozen_manifest_bundle()

    first = normalize_ps_supplemental_query(
        bundle,
        tic_ids=(" TIC   18121498 ", "tic 164830162"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )
    reordered = normalize_ps_supplemental_query(
        bundle,
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


def test_ps_query_hashes_change_for_meaningful_parameters() -> None:
    bundle = load_frozen_manifest_bundle()
    baseline = normalize_ps_supplemental_query(
        bundle,
        tic_ids=("TIC 18121498",),
        page_size=10,
        max_pages=2,
        record_limit=20,
    )
    changed_input = normalize_ps_supplemental_query(
        bundle,
        tic_ids=("TIC 164830162",),
        page_size=10,
        max_pages=2,
        record_limit=20,
    )
    changed_pagination = normalize_ps_supplemental_query(
        bundle,
        tic_ids=("TIC 18121498",),
        page_size=5,
        max_pages=4,
        record_limit=20,
    )

    assert changed_input.input_hash != baseline.input_hash
    assert changed_input.query_hash != baseline.query_hash
    assert changed_pagination.input_hash == baseline.input_hash
    assert changed_pagination.query_hash != baseline.query_hash


def test_ps_page_query_uses_bounded_keyset_pagination() -> None:
    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498", "TIC 164830162"),
        page_size=25,
        max_pages=4,
        record_limit=100,
    )

    first_page = render_ps_page_query(query, cursor=None, requested_rows=25)
    next_page = render_ps_page_query(
        query,
        cursor=SupplementalDataQueryCursor(
            pl_name="HD 8574 b",
            pl_refname="O'Brien et al. 2026",
        ),
        requested_rows=10,
    )

    selected = ",".join(query.selected_columns)
    assert first_page == (
        f"select top 25 {selected} from ps "
        "where tic_id in ('TIC 164830162','TIC 18121498') "
        "and pl_name is not null and pl_refname is not null "
        "order by pl_name,pl_refname"
    )
    assert next_page == (
        f"select top 10 {selected} from ps "
        "where tic_id in ('TIC 164830162','TIC 18121498') "
        "and pl_name is not null and pl_refname is not null "
        "and (pl_name > 'HD 8574 b' or "
        "(pl_name = 'HD 8574 b' and "
        "pl_refname > 'O''Brien et al. 2026')) "
        "order by pl_name,pl_refname"
    )


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
        normalize_ps_supplemental_query(
            load_frozen_manifest_bundle(),
            tic_ids=(value,),
            page_size=1,
            max_pages=1,
            record_limit=1,
        )


def test_ps_query_bounds_the_number_of_identity_inputs() -> None:
    with pytest.raises(ValueError, match="at most 100"):
        normalize_ps_supplemental_query(
            load_frozen_manifest_bundle(),
            tic_ids=tuple(range(1, 102)),
            page_size=1,
            max_pages=1,
            record_limit=1,
        )


def test_ps_adapter_builds_independent_paginated_source_snapshot() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_exoplanet_archive import NASA_TAP_SYNC_URL
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498", "TIC 164830162"),
        page_size=2,
        max_pages=2,
        record_limit=3,
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
            headers={"X-Request-Id": "schema-request"},
        ),
        json_response(
            first_page,
            headers={"ETag": 'W/"ps-v1"', "X-Request-Id": "page-request-1"},
        ),
        json_response(second_page),
    )
    adapter = NasaPlanetarySystemsSupplementalAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    )

    result = adapter.acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert [record.row_key for record in result.records] == [
        (("pl_name", "HD 8574 b"), ("pl_refname", "Reference A")),
        (("pl_name", "Kepler-1292 b"), ("pl_refname", "Reference A")),
        (("pl_name", "Kepler-1292 b"), ("pl_refname", "Reference B")),
    ]
    assert [page.returned_rows for page in result.pages] == [2, 1]
    assert [page.cursor_after for page in result.pages] == [
        SupplementalDataQueryCursor(
            pl_name="Kepler-1292 b",
            pl_refname="Reference A",
        ),
        SupplementalDataQueryCursor(
            pl_name="Kepler-1292 b",
            pl_refname="Reference B",
        ),
    ]
    assert len(transport.calls) == 3
    assert transport.calls[0]["url"] == NASA_TAP_SYNC_URL
    assert "TAP_SCHEMA.columns" in str(transport.calls[0]["params"])
    assert "top 2" in str(transport.calls[1]["params"])
    assert "top 1" in str(transport.calls[2]["params"])
    assert "Reference A" in str(transport.calls[2]["params"])

    snapshot = result.snapshot
    assert snapshot.source_id == "nasa_exoplanet_archive.ps"
    assert snapshot.query_hash == query.query_hash
    assert snapshot.source_version_or_etag == 'W/"ps-v1"'
    assert snapshot.content_hash.startswith("sha256:")
    assert snapshot.license_note
    assert snapshot.retrieved_at == datetime(
        2026,
        7,
        30,
        8,
        0,
        tzinfo=timezone.utc,
    )
    assert snapshot.request_metadata["producer"] == {
        "name": "xingwen.data_acquisition",
        "version": "1.0.0",
    }
    assert snapshot.request_metadata["source_mode"] == "live"
    assert snapshot.request_metadata["data_level"] == "live_result"
    assert snapshot.request_metadata["input_hash"] == query.input_hash
    assert snapshot.request_metadata["normalized_parameters"] == {
        "input_identity_field": "star.tic_id",
        "source_filter_field": "tic_id",
        "input_values": ["TIC 164830162", "TIC 18121498"],
        "pagination": {
            "page_size": 2,
            "max_pages": 2,
            "record_limit": 3,
        },
    }
    assert snapshot.request_metadata["schema_preflight"]["status"] == "compatible"
    assert snapshot.request_metadata["schema_preflight"]["request_id"] == (
        "schema-request"
    )
    assert snapshot.request_metadata["locators"]["endpoint"] == NASA_TAP_SYNC_URL
    assert snapshot.request_metadata["locators"]["license_url"].endswith(
        "/docs/acknowledge.html"
    )
    assert len(snapshot.request_metadata["locators"]["request_hashes"]) == 3
    assert snapshot.request_metadata["pages"][0]["request_id"] == "page-request-1"
    assert result.retry_count == 0


def test_ps_snapshot_uses_schema_hash_as_version_evidence_without_etag() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = NasaPlanetarySystemsSupplementalAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert result.snapshot.source_version_or_etag.startswith("tap-schema:sha256:")
    assert result.snapshot.request_metadata["source_version_evidence"]["kind"] == (
        "tap_schema_response_hash"
    )


def test_ps_snapshot_filters_credentials_and_unsafe_response_headers(caplog) -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
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
        result = NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            sleeper=lambda _: None,
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    serialized = result.snapshot.model_dump_json().casefold()
    assert "highly-sensitive" not in serialized
    assert "secret-schema" not in serialized
    assert "secret-page" not in serialized
    assert "authorization" not in serialized
    assert "cookie" not in serialized
    assert "highly-sensitive" not in caplog.text
    assert "secret-schema" not in caplog.text
    assert "secret-page" not in caplog.text


def test_ps_adapter_treats_empty_result_as_success() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=5,
        max_pages=1,
        record_limit=5,
    )
    transport = FakeTransport(
        json_response(ps_schema_rows(query.selected_columns)),
        json_response([]),
    )

    result = NasaPlanetarySystemsSupplementalAdapter(
        transport=transport,
        clock=lambda: datetime(2026, 7, 30, 8, 0, tzinfo=timezone.utc),
        sleeper=lambda _: None,
    ).acquire(
        query,
        source_mode=SourceMode.live,
        data_level=DataSourceDataLevel.live_result,
    )

    assert result.records == ()
    assert len(result.pages) == 1
    assert result.pages[0].returned_rows == 0
    assert result.snapshot.request_metadata["result_status"] == "empty"


def test_ps_adapter_rejects_schema_drift_before_data_query() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    drifted = tuple(
        column for column in query.selected_columns if column != "rowupdate"
    )
    transport = FakeTransport(json_response(ps_schema_rows(drifted)))

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            sleeper=lambda _: None,
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.code == "NASA_PS_SCHEMA_DRIFT"
    assert error.value.retryable is False
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("schema_or_page", "expected_code"),
    [
        ("schema", "NASA_PS_SCHEMA_INVALID_JSON"),
        ("page", "NASA_PS_INVALID_JSON"),
    ],
)
def test_ps_adapter_classifies_invalid_response_without_retry(
    schema_or_page: str,
    expected_code: str,
) -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    steps = (
        (FakeResponse(200, {}, b"not-json"),)
        if schema_or_page == "schema"
        else (
            json_response(ps_schema_rows(query.selected_columns)),
            FakeResponse(200, {}, b"not-json"),
        )
    )
    transport = FakeTransport(*steps)

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            sleeper=lambda _: pytest.fail("invalid response must not be retried"),
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.invalid_response
    assert error.value.code == expected_code
    assert error.value.retryable is False


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
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
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


def test_ps_adapter_stops_after_the_configured_retry_bound() -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
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
    assert len(transport.calls) == 3


def test_ps_adapter_does_not_retry_permanent_request_errors() -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport(FakeResponse(400, {}, b"bad query"))

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(
            transport=transport,
            sleeper=lambda _: pytest.fail("permanent failure must not be retried"),
        ).acquire(
            query,
            source_mode=SourceMode.live,
            data_level=DataSourceDataLevel.live_result,
        )

    assert error.value.classification is UpstreamFailureClass.upstream_client
    assert error.value.code == "NASA_PS_UPSTREAM_CLIENT_ERROR"
    assert error.value.status_code == 400
    assert len(transport.calls) == 1


def test_ps_adapter_classifies_interrupted_pagination() -> None:
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=2,
        record_limit=2,
    )
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
    assert error.value.retryable is False
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
    from app.schemas.enums import SourceMode, UpstreamFailureClass
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
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
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
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
    assert error.value.retryable is False
    assert transport.calls == []


def test_recorded_ps_response_runs_without_a_live_or_cached_label() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )
    from services.data_pipeline.sources.supplemental_recorded import (
        DEFAULT_RECORDED_PS_FIXTURE_PATH,
        RecordedNasaPsTransport,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
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
    assert {record.payload["tic_id"] for record in result.records} == {
        "TIC 219698776"
    }
    assert result.snapshot.request_metadata["source_mode"] == "fixture"
    assert result.snapshot.request_metadata["data_level"] == "recorded_response"
    assert result.snapshot.request_metadata["fixture"]["fixture_id"] == (
        "fixture.nasa-ps.by-tic-first-page.2026-07-30"
    )
    assert result.snapshot.request_metadata["fixture"]["content_hash"].startswith(
        "sha256:"
    )
    assert result.snapshot.request_metadata["schema_preflight"]["response_date"] == (
        "Thu, 30 Jul 2026 05:56:09 GMT"
    )
    assert result.snapshot.request_metadata["pages"][0]["response_date"] == (
        "Thu, 30 Jul 2026 05:56:12 GMT"
    )
    assert result.snapshot.cache_version is None
    assert transport.remaining_responses == 0


def test_recorded_ps_fixture_rejects_content_tampering() -> None:
    from pydantic import ValidationError
    from services.data_pipeline.sources.supplemental_recorded import (
        DEFAULT_RECORDED_PS_FIXTURE_PATH,
        RecordedNasaPsFixture,
    )

    payload = json.loads(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["records"][0]["hostname"] = "tampered"

    with pytest.raises(ValidationError, match="response hash mismatch"):
        RecordedNasaPsFixture.model_validate(payload)


def test_recorded_ps_fixture_rejects_sensitive_response_headers() -> None:
    from pydantic import ValidationError
    from services.data_pipeline.sources.supplemental_recorded import (
        DEFAULT_RECORDED_PS_FIXTURE_PATH,
        RecordedNasaPsFixture,
        compute_recorded_ps_fixture_hash,
    )

    payload = json.loads(
        DEFAULT_RECORDED_PS_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    payload["page_safe_response_headers"] = {
        "Set-Cookie": "session=secret"
    }
    payload["content_hash"] = compute_recorded_ps_fixture_hash(payload)

    with pytest.raises(ValidationError, match="unsafe response header"):
        RecordedNasaPsFixture.model_validate(payload)


def test_fixture_origin_requires_versioned_provenance_before_any_request() -> None:
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.base import SourceFailure
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
        tic_ids=("TIC 18121498",),
        page_size=1,
        max_pages=1,
        record_limit=1,
    )
    transport = FakeTransport()

    with pytest.raises(SourceFailure) as error:
        NasaPlanetarySystemsSupplementalAdapter(transport=transport).acquire(
            query,
            source_mode=SourceMode.fixture,
            data_level=DataSourceDataLevel.recorded_response,
        )

    assert error.value.code == "NASA_PS_FIXTURE_PROVENANCE_MISSING"
    assert transport.calls == []


def test_recorded_ps_cli_exports_a_reproducible_smoke_result(
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
    assert exported["snapshot"]["request_metadata"]["fixture"]["fixture_id"] == (
        "fixture.nasa-ps.by-tic-first-page.2026-07-30"
    )
    assert summary["record_count"] == 2
    assert summary["source_mode"] == "fixture"
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
    from app.schemas.enums import SourceMode
    from app.schemas.source_acquisition import DataSourceDataLevel
    from services.data_pipeline.sources.nasa_planetary_systems import (
        NasaPlanetarySystemsSupplementalAdapter,
    )

    query = normalize_ps_supplemental_query(
        load_frozen_manifest_bundle(),
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
