"""Typed C-02 source acquisition query contract."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .manifest import ContentHash, Identifier, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[str, Field(min_length=1)]


class DataSourceDataLevel(StrEnum):
    """Acquisition evidence level, kept separate from the source origin."""

    live_result = "live_result"
    recorded_response = "recorded_response"
    fixture = "fixture"
    seed = "seed"


class DataQueryPagination(BaseModel):
    model_config = MODEL_CONFIG

    page_size: int = Field(gt=0, le=1000)
    max_pages: int = Field(gt=0, le=100)
    record_limit: int = Field(gt=0, le=100_000)

    @model_validator(mode="after")
    def validate_capacity(self) -> Self:
        if self.page_size * self.max_pages < self.record_limit:
            raise ValueError("pagination capacity must cover record_limit")
        return self


class DataQueryCursor(BaseModel):
    model_config = MODEL_CONFIG

    tid: int = Field(ge=0)
    toi: Annotated[str, Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")]


class SupplementalDataQueryCursor(BaseModel):
    model_config = MODEL_CONFIG

    pl_name: NonEmptyString
    pl_refname: NonEmptyString


class RawDataSourceRecord(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    payload: dict[str, Any]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        expected = compute_raw_data_record_hash(
            source_id=self.source_id,
            row_key=self.row_key,
            payload=self.payload,
        )
        if self.content_hash != expected:
            raise ValueError(f"content_hash does not match raw record: {expected}")
        return self


class DataSourcePage(BaseModel):
    model_config = MODEL_CONFIG

    page_number: int = Field(gt=0)
    requested_rows: int = Field(gt=0, le=1000)
    returned_rows: int = Field(ge=0)
    attempt_count: int = Field(gt=0)
    status_code: int = Field(ge=100, le=599)
    retrieved_at: AwareDatetime
    latency_ms: int = Field(ge=0)
    cursor_before: DataQueryCursor | SupplementalDataQueryCursor | None = None
    cursor_after: DataQueryCursor | SupplementalDataQueryCursor | None = None
    request_hash: ContentHash
    response_hash: ContentHash
    response_metadata: dict[str, str | int | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_row_count(self) -> Self:
        if self.returned_rows > self.requested_rows:
            raise ValueError("returned_rows cannot exceed requested_rows")
        if self.returned_rows and self.cursor_after is None:
            raise ValueError("non-empty page requires cursor_after")
        if not self.returned_rows and self.cursor_after is not None:
            raise ValueError("empty page must not advance cursor")
        return self


class NormalizedDataSourceQuery(BaseModel):
    model_config = MODEL_CONFIG

    query_id: Identifier
    normalization_rule_version: SemanticVersion
    case_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    provider_source_id: Identifier
    table_source_id: Identifier
    source_table: NonEmptyString
    selected_columns: tuple[NonEmptyString, ...] = Field(min_length=1)
    row_key_fields: tuple[NonEmptyString, ...] = Field(min_length=1)
    constraints: tuple[NonEmptyString, ...] = Field(min_length=1)
    order_by: tuple[NonEmptyString, ...] = Field(min_length=1)
    pagination: DataQueryPagination
    query_hash: ContentHash

    @model_validator(mode="after")
    def validate_normalized_query(self) -> Self:
        selected = set(self.selected_columns)
        if len(selected) != len(self.selected_columns):
            raise ValueError("selected_columns must be unique")
        if not set(self.row_key_fields).issubset(selected):
            raise ValueError("row_key_fields must be selected")
        if not set(self.order_by).issubset(selected):
            raise ValueError("order_by fields must be selected")
        expected_hash = compute_normalized_data_query_hash(self)
        if self.query_hash != expected_hash:
            raise ValueError(f"query_hash does not match normalized query: {expected_hash}")
        expected_id = f"query.{expected_hash.removeprefix('sha256:')[:24]}"
        if self.query_id != expected_id:
            raise ValueError(f"query_id does not match normalized query: {expected_id}")
        return self


class NormalizedSupplementalSourceQuery(BaseModel):
    model_config = MODEL_CONFIG

    query_id: Identifier
    normalization_rule_version: SemanticVersion
    case_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    provider_source_id: Identifier
    table_source_id: Identifier
    source_table: NonEmptyString
    column_contract_snapshot_id: Identifier
    column_contract_snapshot_version: SemanticVersion
    column_contract_content_hash: ContentHash
    input_identity_field: NonEmptyString
    source_filter_field: NonEmptyString
    input_values: tuple[NonEmptyString, ...] = Field(
        min_length=1,
        max_length=100,
    )
    declared_columns: tuple[NonEmptyString, ...] = Field(min_length=1)
    live_unavailable_columns: tuple[NonEmptyString, ...]
    selected_columns: tuple[NonEmptyString, ...] = Field(min_length=1)
    row_key_fields: tuple[NonEmptyString, ...] = Field(min_length=1)
    constraints: tuple[NonEmptyString, ...] = Field(min_length=1)
    order_by: tuple[NonEmptyString, ...] = Field(min_length=1)
    pagination: DataQueryPagination
    input_hash: ContentHash
    query_hash: ContentHash

    @model_validator(mode="after")
    def validate_normalized_query(self) -> Self:
        declared = set(self.declared_columns)
        selected = set(self.selected_columns)
        unavailable = set(self.live_unavailable_columns)
        if len(declared) != len(self.declared_columns):
            raise ValueError("declared_columns must be unique")
        if len(unavailable) != len(self.live_unavailable_columns):
            raise ValueError("live_unavailable_columns must be unique")
        if not unavailable.issubset(declared):
            raise ValueError("live_unavailable_columns must be declared")
        expected_selected = tuple(
            column
            for column in self.declared_columns
            if column not in unavailable
        )
        if self.selected_columns != expected_selected:
            raise ValueError(
                "selected_columns must be the declared live-queryable columns"
            )
        if len(selected) != len(self.selected_columns):
            raise ValueError("selected_columns must be unique")
        if len(set(self.input_values)) != len(self.input_values):
            raise ValueError("input_values must be unique")
        if tuple(sorted(self.input_values)) != self.input_values:
            raise ValueError("input_values must use canonical order")
        if not set(self.row_key_fields).issubset(selected):
            raise ValueError("row_key_fields must be selected")
        if not set(self.order_by).issubset(selected):
            raise ValueError("order_by fields must be selected")
        if self.source_filter_field not in selected:
            raise ValueError("source_filter_field must be selected")
        expected_input_hash = compute_supplemental_input_hash(self)
        if self.input_hash != expected_input_hash:
            raise ValueError(
                f"input_hash does not match normalized input: {expected_input_hash}"
            )
        expected_query_hash = compute_normalized_supplemental_query_hash(self)
        if self.query_hash != expected_query_hash:
            raise ValueError(
                f"query_hash does not match normalized query: {expected_query_hash}"
            )
        expected_id = f"query.{expected_query_hash.removeprefix('sha256:')[:24]}"
        if self.query_id != expected_id:
            raise ValueError(f"query_id does not match normalized query: {expected_id}")
        return self


def compute_normalized_data_query_hash(
    value: NormalizedDataSourceQuery | dict[str, Any],
) -> str:
    payload = (
        deepcopy(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else deepcopy(value)
    )
    payload.pop("query_id", None)
    payload.pop("query_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_supplemental_input_hash(
    value: NormalizedSupplementalSourceQuery | dict[str, Any],
) -> str:
    payload = (
        value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, BaseModel)
        else value
    )
    return compute_canonical_payload_hash(
        {
            "case_id": payload["case_id"],
            "case_manifest_version": payload["case_manifest_version"],
            "case_manifest_content_hash": payload["case_manifest_content_hash"],
            "field_manifest_id": payload["field_manifest_id"],
            "field_manifest_version": payload["field_manifest_version"],
            "field_manifest_content_hash": payload["field_manifest_content_hash"],
            "input_identity_field": payload["input_identity_field"],
            "input_values": payload["input_values"],
        }
    )


def compute_normalized_supplemental_query_hash(
    value: NormalizedSupplementalSourceQuery | dict[str, Any],
) -> str:
    payload = (
        deepcopy(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else deepcopy(value)
    )
    payload.pop("query_id", None)
    payload.pop("query_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_raw_data_record_hash(
    *,
    source_id: str,
    row_key: tuple[tuple[str, str], ...],
    payload: dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(
        {
            "source_id": source_id,
            "row_key": row_key,
            "payload": payload,
        }
    )
