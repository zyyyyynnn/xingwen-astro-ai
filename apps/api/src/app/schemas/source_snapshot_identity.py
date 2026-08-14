"""Authoritative query-identity validation for persisted SourceSnapshots."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from .paper_collection import NormalizedPaperQuery
from .source_acquisition import (
    NormalizedDataSourceQuery,
    NormalizedSupplementalSourceQuery,
)


_PRIMARY_DATA_SOURCE_IDS = frozenset({"nasa_exoplanet_archive.toi"})
_SUPPLEMENTAL_DATA_SOURCE_IDS = frozenset({"nasa_exoplanet_archive.ps"})
_PAPER_SOURCE_IDS = frozenset({"crossref"})


def source_snapshot_query_identity_is_valid(
    *,
    source_id: str,
    query: Any,
    query_hash: str,
) -> bool:
    """Rebuild the source-owned typed query identity and fail closed."""

    if not isinstance(query, str):
        return False
    try:
        payload = json.loads(query)
        if source_id in _PRIMARY_DATA_SOURCE_IDS:
            normalized = NormalizedDataSourceQuery.model_validate(payload)
            return (
                normalized.table_source_id == source_id
                and normalized.query_hash == query_hash
            )
        if source_id in _SUPPLEMENTAL_DATA_SOURCE_IDS:
            normalized = NormalizedSupplementalSourceQuery.model_validate(payload)
            return (
                normalized.table_source_id == source_id
                and normalized.query_hash == query_hash
            )
        if source_id in _PAPER_SOURCE_IDS:
            normalized = NormalizedPaperQuery.model_validate(payload)
            return (
                source_id in normalized.source_ids
                and source_id in normalized.source_parameters
                and normalized.query_hash == query_hash
            )
    except (json.JSONDecodeError, TypeError, ValidationError):
        return False
    return False


__all__ = ["source_snapshot_query_identity_is_valid"]
