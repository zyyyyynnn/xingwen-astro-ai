"""Validated replay transport for the versioned C-07 NASA PS fixture."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.manifest import ContentHash, Identifier, SemanticVersion
from app.schemas.source_acquisition import (
    DataQueryPagination,
    NormalizedSupplementalSourceQuery,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ..constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)
from ..manifest import load_frozen_manifest_bundle
from ..supplemental_query import (
    normalize_ps_supplemental_query,
    render_ps_page_query,
)
from .base import HttpResponse
from .nasa_exoplanet_archive import (
    NASA_TAP_SYNC_URL,
    SAFE_RESPONSE_HEADERS,
    TransportPolicyError,
)
from .nasa_planetary_systems import (
    NASA_PS_ACKNOWLEDGEMENT_URL,
    NASA_PS_DOCUMENTATION_URL,
    NASA_PS_LICENSE_NOTE,
    render_ps_schema_query,
)


DEFAULT_RECORDED_PS_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "exoplanet_host_star"
    / "nasa-ps-by-tic-first-page.recorded.v1.json"
)
_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_NonEmptyString = Annotated[str, Field(min_length=1)]


class RecordedNasaPsFixture(BaseModel):
    model_config = _MODEL_CONFIG

    fixture_id: Identifier
    schema_version: SemanticVersion
    scenario: Identifier
    recorded_at: AwareDatetime
    source_endpoint: _NonEmptyString
    source_documentation_url: _NonEmptyString
    source_acknowledgement_url: _NonEmptyString
    source_version_or_etag: _NonEmptyString | None
    license_note: _NonEmptyString
    source_mode: Literal["fixture"]
    data_level: Literal["recorded_response"]
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    column_contract_snapshot_id: Identifier
    column_contract_snapshot_version: SemanticVersion
    column_contract_content_hash: ContentHash
    runtime_schema_contract_id: Identifier
    runtime_schema_contract_version: SemanticVersion
    runtime_schema_contract_content_hash: ContentHash
    input_identity_field: Literal["star.tic_id"]
    input_values: tuple[_NonEmptyString, ...] = Field(min_length=1)
    pagination: DataQueryPagination
    input_hash: ContentHash
    query_hash: ContentHash
    schema_response_hash: ContentHash
    page_response_hash: ContentHash
    provenance_note: _NonEmptyString
    tap_schema: tuple[dict[str, str], ...] = Field(min_length=1)
    records: tuple[dict[str, Any], ...] = Field(min_length=1)
    schema_safe_response_headers: dict[str, str] = Field(default_factory=dict)
    page_safe_response_headers: dict[str, str] = Field(default_factory=dict)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_frozen_fixture(self) -> Self:
        if self.schema_version != "1.0.0":
            raise ValueError("unsupported recorded fixture schema_version")
        if self.source_endpoint != NASA_TAP_SYNC_URL:
            raise ValueError(
                "recorded fixture endpoint is not the NASA TAP sync endpoint"
            )
        if self.source_documentation_url != NASA_PS_DOCUMENTATION_URL:
            raise ValueError("recorded fixture documentation URL is not NASA PS")
        if self.source_acknowledgement_url != NASA_PS_ACKNOWLEDGEMENT_URL:
            raise ValueError("recorded fixture acknowledgement URL is not NASA PS")
        if self.license_note != NASA_PS_LICENSE_NOTE:
            raise ValueError("recorded fixture license note does not match the adapter")
        if (
            self.pagination.max_pages != 1
            or self.pagination.page_size != self.pagination.record_limit
        ):
            raise ValueError(
                "recorded PS fixture must use one page with page_size=record_limit"
            )
        expected_pins = (
            FROZEN_CASE_MANIFEST_VERSION,
            FROZEN_CASE_MANIFEST_CONTENT_HASH,
            FROZEN_FIELD_MANIFEST_VERSION,
            FROZEN_FIELD_MANIFEST_CONTENT_HASH,
        )
        actual_pins = (
            self.case_manifest_version,
            self.case_manifest_content_hash,
            self.field_manifest_version,
            self.field_manifest_content_hash,
        )
        if actual_pins != expected_pins:
            raise ValueError("recorded fixture does not match the frozen manifests")

        query = normalize_ps_supplemental_query(
            load_frozen_manifest_bundle(),
            tic_ids=self.input_values,
            page_size=self.pagination.page_size,
            max_pages=self.pagination.max_pages,
            record_limit=self.pagination.record_limit,
        )
        expected_column_contract = (
            query.column_contract_snapshot_id,
            query.column_contract_snapshot_version,
            query.column_contract_content_hash,
        )
        actual_column_contract = (
            self.column_contract_snapshot_id,
            self.column_contract_snapshot_version,
            self.column_contract_content_hash,
        )
        if actual_column_contract != expected_column_contract:
            raise ValueError("recorded fixture column contract pins do not match")
        expected_runtime_contract = (
            query.runtime_schema_contract_id,
            query.runtime_schema_contract_version,
            query.runtime_schema_contract_content_hash,
        )
        actual_runtime_contract = (
            self.runtime_schema_contract_id,
            self.runtime_schema_contract_version,
            self.runtime_schema_contract_content_hash,
        )
        if actual_runtime_contract != expected_runtime_contract:
            raise ValueError("recorded fixture runtime schema pins do not match")
        if self.input_values != query.input_values:
            raise ValueError("recorded fixture inputs are not normalized")
        if self.input_hash != query.input_hash or self.query_hash != query.query_hash:
            raise ValueError("recorded fixture query hashes do not match normalization")
        if len(self.records) > self.pagination.page_size:
            raise ValueError("recorded fixture exceeds its one-page bound")
        expected_columns = set(query.selected_columns)
        if any(set(record) != expected_columns for record in self.records):
            raise ValueError("recorded fixture record columns do not match query")
        schema_hash = compute_canonical_payload_hash(self.tap_schema)
        page_hash = compute_canonical_payload_hash(self.records)
        if self.schema_response_hash != schema_hash:
            raise ValueError("recorded fixture schema response hash mismatch")
        if self.page_response_hash != page_hash:
            raise ValueError("recorded fixture page response hash mismatch")
        page_etag = _header_value(self.page_safe_response_headers, "etag")
        if self.source_version_or_etag != page_etag:
            raise ValueError(
                "recorded fixture source version must match the data page ETag"
            )
        unsafe_headers = sorted(
            key
            for headers in (
                self.schema_safe_response_headers,
                self.page_safe_response_headers,
            )
            for key in headers
            if key.casefold() not in SAFE_RESPONSE_HEADERS
        )
        if unsafe_headers:
            raise ValueError(
                f"recorded fixture contains unsafe response header: {unsafe_headers}"
            )
        expected_hash = compute_recorded_ps_fixture_hash(self)
        if self.content_hash != expected_hash:
            raise ValueError(f"recorded fixture content_hash mismatch: {expected_hash}")
        return self

    def metadata(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "schema_version": self.schema_version,
            "scenario": self.scenario,
            "recorded_at": self.recorded_at.isoformat(),
            "content_hash": self.content_hash,
            "provenance_note": self.provenance_note,
            "data_level": self.data_level,
            "source_version_or_etag": self.source_version_or_etag,
            "source_acknowledgement_url": self.source_acknowledgement_url,
            "license_note": self.license_note,
            "input_hash": self.input_hash,
            "query_hash": self.query_hash,
            "schema_response_hash": self.schema_response_hash,
            "page_response_hash": self.page_response_hash,
            "case_manifest_version": self.case_manifest_version,
            "case_manifest_content_hash": self.case_manifest_content_hash,
            "field_manifest_version": self.field_manifest_version,
            "field_manifest_content_hash": self.field_manifest_content_hash,
            "column_contract_snapshot_id": self.column_contract_snapshot_id,
            "column_contract_snapshot_version": (
                self.column_contract_snapshot_version
            ),
            "column_contract_content_hash": self.column_contract_content_hash,
            "runtime_schema_contract_id": self.runtime_schema_contract_id,
            "runtime_schema_contract_version": (
                self.runtime_schema_contract_version
            ),
            "runtime_schema_contract_content_hash": (
                self.runtime_schema_contract_content_hash
            ),
        }


def compute_recorded_ps_fixture_hash(
    value: RecordedNasaPsFixture | dict[str, Any],
) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else dict(value)
    )
    payload.pop("content_hash", None)
    return compute_canonical_payload_hash(payload)


class RecordedNasaPsTransport:
    """Replay one captured schema response and one bounded PS data page."""

    def __init__(
        self,
        fixture: RecordedNasaPsFixture,
        *,
        query: NormalizedSupplementalSourceQuery,
    ) -> None:
        validated = RecordedNasaPsFixture.model_validate(
            fixture.model_dump(mode="json")
        )
        expected_query = normalize_ps_supplemental_query(
            load_frozen_manifest_bundle(),
            tic_ids=validated.input_values,
            page_size=validated.pagination.page_size,
            max_pages=validated.pagination.max_pages,
            record_limit=validated.pagination.record_limit,
        )
        if query != expected_query:
            raise ValueError("recorded fixture does not match normalized query")
        self._fixture_metadata_items = tuple(validated.metadata().items())
        self._response_header_items = tuple(
            tuple(headers.items())
            for headers in (
                validated.schema_safe_response_headers,
                validated.page_safe_response_headers,
            )
        )
        self._expected_requests = (
            {
                "query": render_ps_schema_query(query),
                "format": "json",
            },
            {
                "query": render_ps_page_query(
                    query,
                    cursor=None,
                    requested_rows=query.pagination.page_size,
                ),
                "format": "json",
            },
        )
        self._response_bodies = tuple(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            for payload in (validated.tap_schema, validated.records)
        )
        self._request_index = 0

    @property
    def fixture_metadata(self) -> dict[str, Any]:
        return dict(self._fixture_metadata_items)

    @property
    def remaining_responses(self) -> int:
        return len(self._response_bodies) - self._request_index

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        query: NormalizedSupplementalSourceQuery,
    ) -> Self:
        fixture = RecordedNasaPsFixture.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        return cls(fixture, query=query)

    def request(
        self,
        *,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        del timeout_seconds
        if url != NASA_TAP_SYNC_URL:
            raise TransportPolicyError("recorded fixture endpoint mismatch")
        if any(
            key.casefold() in {"authorization", "cookie", "set-cookie"}
            for key in headers
        ):
            raise TransportPolicyError("recorded fixture received credential headers")
        if self._request_index >= len(self._expected_requests):
            raise TransportPolicyError("recorded fixture request count exceeded")
        expected = self._expected_requests[self._request_index]
        if dict(params) != expected:
            raise TransportPolicyError(
                "recorded fixture request does not match capture"
            )
        body = self._response_bodies[self._request_index]
        response_headers = dict(self._response_header_items[self._request_index])
        self._request_index += 1
        return HttpResponse(
            status_code=200,
            headers=response_headers,
            body=body,
        )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.casefold()
    for key, value in headers.items():
        if key.casefold() == target:
            return value
    return None
