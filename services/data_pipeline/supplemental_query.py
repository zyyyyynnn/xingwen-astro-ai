"""Manifest-driven NASA Planetary Systems supplemental query normalization."""

from __future__ import annotations

from collections.abc import Iterable
import re

from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import (
    DataQueryPagination,
    NormalizedSupplementalSourceQuery,
    SupplementalDataQueryCursor,
    compute_normalized_supplemental_query_hash,
    compute_supplemental_input_hash,
)

from .constants import SUPPLEMENTAL_QUERY_NORMALIZATION_VERSION
from .source_contract import load_source_column_runtime_contract


_PS_SOURCE_ID = "nasa_exoplanet_archive.ps"
_INPUT_IDENTITY_FIELD = "star.tic_id"
_SOURCE_FILTER_FIELD = "tic_id"
_ADQL_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_TIC_IDENTIFIER = re.compile(
    r"^(?:tic\s*)?([1-9][0-9]{0,18})$",
    re.IGNORECASE,
)
_MAX_TIC_IDENTIFIERS = 100


def normalize_ps_supplemental_query(
    bundle: ManifestBundle,
    *,
    tic_ids: Iterable[str | int],
    page_size: int,
    max_pages: int,
    record_limit: int,
) -> NormalizedSupplementalSourceQuery:
    source = next(
        (
            item
            for item in bundle.field_manifest.sources
            if item.source_id == _PS_SOURCE_ID
        ),
        None,
    )
    if source is None:
        raise ValueError("frozen Field Manifest does not define the PS source")
    if source.provider_source_id not in bundle.case_manifest.allowed_source_ids:
        raise ValueError("PS provider is not allowed by the frozen Case Manifest")

    identity_field = bundle.field_manifest.field_by_id(_INPUT_IDENTITY_FIELD)
    aliases = identity_field.source_aliases_for(source.source_id)
    if not any(
        alias.raw_field == _SOURCE_FILTER_FIELD
        and alias.source_table == source.source_table
        for alias in aliases
    ):
        raise ValueError("frozen Field Manifest does not map star.tic_id to PS.tic_id")
    if not any(
        _INPUT_IDENTITY_FIELD in target.identity_fields
        for target in bundle.case_manifest.target_objects
    ):
        raise ValueError(
            "frozen Case Manifest does not declare star.tic_id as identity"
        )
    column_contract = load_source_column_runtime_contract(source)

    normalized_identifiers: set[str] = set()
    for input_count, value in enumerate(tic_ids, start=1):
        if input_count > _MAX_TIC_IDENTIFIERS:
            raise ValueError("at most 100 TIC identifiers are allowed")
        normalized_identifiers.add(_normalize_tic_id(value))
    normalized_values = tuple(sorted(normalized_identifiers))
    if not normalized_values:
        raise ValueError("at least one TIC identifier is required")

    pagination = DataQueryPagination(
        page_size=page_size,
        max_pages=max_pages,
        record_limit=record_limit,
    )
    payload = {
        "normalization_rule_version": SUPPLEMENTAL_QUERY_NORMALIZATION_VERSION,
        "case_id": bundle.case_manifest.case_id,
        "case_manifest_version": bundle.case_manifest.manifest_version,
        "case_manifest_content_hash": bundle.case_manifest.content_hash,
        "field_manifest_id": bundle.field_manifest.manifest_id,
        "field_manifest_version": bundle.field_manifest.manifest_version,
        "field_manifest_content_hash": bundle.field_manifest.content_hash,
        "provider_source_id": source.provider_source_id,
        "table_source_id": source.source_id,
        "source_table": source.source_table,
        "column_contract_snapshot_id": column_contract.snapshot_id,
        "column_contract_snapshot_version": column_contract.snapshot_version,
        "column_contract_content_hash": column_contract.content_hash,
        "runtime_schema_contract_id": column_contract.runtime_schema_contract_id,
        "runtime_schema_contract_version": (
            column_contract.runtime_schema_contract_version
        ),
        "runtime_schema_contract_content_hash": (
            column_contract.runtime_schema_contract_content_hash
        ),
        "input_identity_field": _INPUT_IDENTITY_FIELD,
        "source_filter_field": _SOURCE_FILTER_FIELD,
        "input_values": normalized_values,
        "declared_columns": column_contract.declared_columns,
        "live_unavailable_columns": column_contract.live_unavailable_columns,
        "selected_columns": tuple(
            column
            for column in column_contract.declared_columns
            if column not in column_contract.live_unavailable_columns
        ),
        "row_key_fields": source.row_key_fields,
        "constraints": tuple(
            f"{field} is not null" for field in source.row_key_fields
        ),
        "order_by": source.row_key_fields,
        "pagination": pagination.model_dump(mode="json"),
    }
    input_hash = compute_supplemental_input_hash(payload)
    payload["input_hash"] = input_hash
    query_hash = compute_normalized_supplemental_query_hash(payload)
    return NormalizedSupplementalSourceQuery(
        query_id=f"query.{query_hash.removeprefix('sha256:')[:24]}",
        query_hash=query_hash,
        **payload,
    )


def render_ps_page_query(
    query: NormalizedSupplementalSourceQuery,
    *,
    cursor: SupplementalDataQueryCursor | None,
    requested_rows: int,
) -> str:
    if requested_rows < 1 or requested_rows > query.pagination.page_size:
        raise ValueError("requested_rows must fit within the normalized page size")
    identifiers = (
        query.source_table,
        query.source_filter_field,
        *query.selected_columns,
        *query.order_by,
    )
    if any(not _ADQL_IDENTIFIER.fullmatch(value) for value in identifiers):
        raise ValueError("query contains an unsafe ADQL identifier")

    input_values = ",".join(
        f"'{_escape_adql_string(value)}'" for value in query.input_values
    )
    constraints = [
        f"{query.source_filter_field} in ({input_values})",
        *query.constraints,
    ]
    if cursor is not None:
        pl_name = _escape_adql_string(cursor.pl_name)
        pl_refname = _escape_adql_string(cursor.pl_refname)
        constraints.append(
            f"(pl_name > '{pl_name}' or "
            f"(pl_name = '{pl_name}' and pl_refname > '{pl_refname}'))"
        )
    return (
        f"select top {requested_rows} {','.join(query.selected_columns)} "
        f"from {query.source_table} where {' and '.join(constraints)} "
        f"order by {','.join(query.order_by)}"
    )


def _normalize_tic_id(value: str | int) -> str:
    normalized = " ".join(str(value).strip().split())
    match = _TIC_IDENTIFIER.fullmatch(normalized)
    if match is None:
        raise ValueError(f"invalid TIC identifier: {value!r}")
    return f"TIC {int(match.group(1))}"


def _escape_adql_string(value: str) -> str:
    return value.replace("'", "''")
