"""Manifest-driven NASA Exoplanet Archive query normalization."""

from __future__ import annotations

from collections.abc import Iterable
import re

from app.schemas.manifest import ManifestBundle
from app.schemas.source_acquisition import (
    DataQueryCursor,
    DataQueryPagination,
    NormalizedDataSourceQuery,
    compute_normalized_data_query_hash,
)

from .constants import QUERY_NORMALIZATION_VERSION


_TOI_SOURCE_ID = "nasa_exoplanet_archive.toi"
_ADQL_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_TIC_IDENTIFIER = re.compile(r"^(?:tic\s*)?([1-9][0-9]{0,18})$", re.IGNORECASE)
_MAX_TIC_IDENTIFIERS = 100


def normalize_toi_query(
    bundle: ManifestBundle,
    *,
    page_size: int,
    max_pages: int,
    record_limit: int,
    tic_ids: Iterable[str | int] | None = None,
    confirmed_only: bool = False,
) -> NormalizedDataSourceQuery:
    source = next(
        (item for item in bundle.field_manifest.sources if item.source_id == _TOI_SOURCE_ID),
        None,
    )
    if source is None:
        raise ValueError("frozen Field Manifest does not define the TOI source")
    if source.provider_source_id not in bundle.case_manifest.allowed_source_ids:
        raise ValueError("TOI provider is not allowed by the frozen Case Manifest")

    normalized_tic_ids: set[int] = set()
    for input_count, value in enumerate(tic_ids or (), start=1):
        if input_count > _MAX_TIC_IDENTIFIERS:
            raise ValueError("at most 100 TIC identifiers are allowed")
        match = _TIC_IDENTIFIER.fullmatch(str(value).strip())
        if match is None:
            raise ValueError(f"invalid TIC identifier: {value!r}")
        normalized_tic_ids.add(int(match.group(1)))

    constraints = ["tid is not null", "toi is not null"]
    if confirmed_only:
        constraints.append("tfopwg_disp = 'CP'")
    if normalized_tic_ids:
        constraints.append(
            "tid in (" + ",".join(str(value) for value in sorted(normalized_tic_ids)) + ")"
        )

    pagination = DataQueryPagination(
        page_size=page_size,
        max_pages=max_pages,
        record_limit=record_limit,
    )
    payload = {
        "normalization_rule_version": QUERY_NORMALIZATION_VERSION,
        "case_id": bundle.case_manifest.case_id,
        "case_manifest_version": bundle.case_manifest.manifest_version,
        "case_manifest_content_hash": bundle.case_manifest.content_hash,
        "field_manifest_id": bundle.field_manifest.manifest_id,
        "field_manifest_version": bundle.field_manifest.manifest_version,
        "field_manifest_content_hash": bundle.field_manifest.content_hash,
        "provider_source_id": source.provider_source_id,
        "table_source_id": source.source_id,
        "source_table": source.source_table,
        "selected_columns": source.approved_columns,
        "row_key_fields": source.row_key_fields,
        "constraints": tuple(constraints),
        "order_by": ("tid", "toi"),
        "pagination": pagination.model_dump(mode="json"),
    }
    query_hash = compute_normalized_data_query_hash(payload)
    return NormalizedDataSourceQuery(
        query_id=f"query.{query_hash.removeprefix('sha256:')[:24]}",
        query_hash=query_hash,
        **payload,
    )


def render_toi_page_query(
    query: NormalizedDataSourceQuery,
    *,
    cursor: DataQueryCursor | None,
    requested_rows: int,
) -> str:
    if requested_rows < 1 or requested_rows > query.pagination.page_size:
        raise ValueError("requested_rows must fit within the normalized page size")
    identifiers = (
        query.source_table,
        *query.selected_columns,
        *query.order_by,
    )
    if any(not _ADQL_IDENTIFIER.fullmatch(value) for value in identifiers):
        raise ValueError("query contains an unsafe ADQL identifier")

    constraints = list(query.constraints)
    if cursor is not None:
        constraints.append(
            "(tid > "
            f"{cursor.tid} or (tid = {cursor.tid} and toi > '{cursor.toi}'))"
        )
    return (
        f"select top {requested_rows} {','.join(query.selected_columns)} "
        f"from {query.source_table} where {' and '.join(constraints)} "
        f"order by {','.join(query.order_by)}"
    )
