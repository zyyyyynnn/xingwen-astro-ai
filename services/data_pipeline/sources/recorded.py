"""Validated replay transport for the versioned C-02 NASA TOI fixture."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.manifest import ContentHash, Identifier, SemanticVersion
from app.schemas.source_acquisition import (
    DataQueryPagination,
    NormalizedDataSourceQuery,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ..constants import (
    FROZEN_CASE_MANIFEST_CONTENT_HASH,
    FROZEN_CASE_MANIFEST_VERSION,
    FROZEN_FIELD_MANIFEST_CONTENT_HASH,
    FROZEN_FIELD_MANIFEST_VERSION,
)
from ..query import render_toi_page_query
from .base import HttpResponse
from .nasa_exoplanet_archive import (
    NASA_TAP_SYNC_URL,
    SAFE_RESPONSE_HEADERS,
    TransportPolicyError,
    render_toi_schema_query,
)


DEFAULT_RECORDED_TOI_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "exoplanet_host_star"
    / "nasa-toi-first-page.recorded.v1.json"
)
_MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_NonEmptyString = Annotated[str, Field(min_length=1)]


class RecordedNasaToiFixture(BaseModel):
    model_config = _MODEL_CONFIG

    fixture_id: Identifier
    schema_version: SemanticVersion
    scenario: Identifier
    recorded_at: AwareDatetime
    source_endpoint: _NonEmptyString
    source_mode: Literal["fixture"]
    data_level: Literal["recorded_response"]
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    pagination: DataQueryPagination
    provenance_note: _NonEmptyString
    tap_schema: tuple[dict[str, str], ...] = Field(min_length=1)
    records: tuple[dict[str, Any], ...] = Field(min_length=1)
    safe_response_headers: dict[str, str] = Field(default_factory=dict)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_frozen_fixture(self) -> Self:
        if self.schema_version != "1.0.0":
            raise ValueError("unsupported recorded fixture schema_version")
        if self.source_endpoint != NASA_TAP_SYNC_URL:
            raise ValueError("recorded fixture endpoint is not the NASA TAP sync endpoint")
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
            raise ValueError("recorded fixture does not match the frozen C-02 manifests")
        unsafe_headers = sorted(
            key
            for key in self.safe_response_headers
            if key.casefold() not in SAFE_RESPONSE_HEADERS
        )
        if unsafe_headers:
            raise ValueError(f"recorded fixture contains unsafe response header: {unsafe_headers}")
        expected_hash = compute_recorded_fixture_hash(self)
        if self.content_hash != expected_hash:
            raise ValueError(f"recorded fixture content_hash mismatch: {expected_hash}")
        return self

    def metadata(self) -> dict[str, str]:
        return {
            "fixture_id": self.fixture_id,
            "schema_version": self.schema_version,
            "scenario": self.scenario,
            "recorded_at": self.recorded_at.isoformat(),
            "content_hash": self.content_hash,
            "provenance_note": self.provenance_note,
            "case_manifest_version": self.case_manifest_version,
            "case_manifest_content_hash": self.case_manifest_content_hash,
            "field_manifest_version": self.field_manifest_version,
            "field_manifest_content_hash": self.field_manifest_content_hash,
        }


def compute_recorded_fixture_hash(
    value: RecordedNasaToiFixture | dict[str, Any],
) -> str:
    payload = (
        value.model_dump(mode="json")
        if isinstance(value, BaseModel)
        else dict(value)
    )
    payload.pop("content_hash", None)
    return compute_canonical_payload_hash(payload)


class RecordedNasaToiTransport:
    """Replay exactly one recorded schema response and one bounded data page."""

    def __init__(
        self,
        fixture: RecordedNasaToiFixture,
        *,
        query: NormalizedDataSourceQuery,
    ) -> None:
        if query.pagination != fixture.pagination:
            raise ValueError("recorded fixture pagination does not match normalized query")
        self.fixture = fixture
        self.fixture_metadata = fixture.metadata()
        self._expected_requests = (
            {
                "query": render_toi_schema_query(query),
                "format": "json",
            },
            {
                "query": render_toi_page_query(
                    query,
                    cursor=None,
                    requested_rows=query.pagination.record_limit,
                ),
                "format": "json",
            },
        )
        self._responses = (fixture.tap_schema, fixture.records)
        self._request_index = 0

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        query: NormalizedDataSourceQuery,
    ) -> Self:
        fixture = RecordedNasaToiFixture.model_validate_json(
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
        del headers, timeout_seconds
        if url != NASA_TAP_SYNC_URL:
            raise TransportPolicyError("recorded fixture endpoint mismatch")
        if self._request_index >= len(self._expected_requests):
            raise TransportPolicyError("recorded fixture request count exceeded")
        expected = self._expected_requests[self._request_index]
        if dict(params) != expected:
            raise TransportPolicyError("recorded fixture request does not match capture")
        payload = self._responses[self._request_index]
        self._request_index += 1
        return HttpResponse(
            status_code=200,
            headers=self.fixture.safe_response_headers,
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )
