from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.core import SourceSnapshotDetail
from app.services.paper_summaries import _snapshot_map


QUERY_HASH = "sha256:" + "a" * 64
CONTENT_HASH = "sha256:" + "b" * 64


def _snapshot(
    *,
    source_version_or_etag: str | None,
    cache_version: str | None,
) -> SourceSnapshotDetail:
    return SourceSnapshotDetail(
        id="snapshot-db",
        source_id="crossref",
        source_type="paper_metadata",
        retrieved_at=datetime(2026, 7, 30, 7, 0, tzinfo=UTC),
        query="exoplanet host star",
        query_hash=QUERY_HASH,
        source_version_or_etag=source_version_or_etag,
        content_hash=CONTENT_HASH,
        license_note="Crossref metadata",
        cache_version=cache_version,
        request_metadata={},
    )


@pytest.mark.parametrize(
    ("source_version_or_etag", "cache_version", "expected_version"),
    [
        ('W/"crossref-v1"', None, 'W/"crossref-v1"'),
        (None, "cache-v1", "cache-v1"),
        (None, None, CONTENT_HASH),
    ],
    ids=("upstream-version", "cache-version", "content-hash"),
)
def test_snapshot_map_uses_pipeline_version_fallback_order(
    source_version_or_etag: str | None,
    cache_version: str | None,
    expected_version: str,
) -> None:
    snapshot = _snapshot(
        source_version_or_etag=source_version_or_etag,
        cache_version=cache_version,
    )

    snapshots = _snapshot_map((snapshot,))

    assert snapshots[(snapshot.source_id, expected_version, CONTENT_HASH)] is snapshot
