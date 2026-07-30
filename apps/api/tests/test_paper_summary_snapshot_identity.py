from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.core import SourceSnapshotDetail
from app.security import SecurityProblem
from app.services.paper_summaries import _collection_snapshot_keys, _snapshot_map
from services.paper_pipeline.demo_fixture import build_demo_collection
from services.paper_pipeline.demo_summary_fixture import build_demo_summary


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


def test_collection_snapshot_keys_cover_the_complete_pinned_registry() -> None:
    collection = build_demo_collection()
    summary = build_demo_summary()

    keys = _collection_snapshot_keys(collection, summary)

    assert set(keys) == {
        snapshot.snapshot_id for snapshot in collection.source_snapshots
    }
    assert set(keys.values()) == {
        (reference.source_id, reference.source_version, reference.content_hash)
        for reference in summary.input_versions.source_snapshots
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_snapshot_id", "snapshot.unknown"),
        ("source_id", "semantic-scholar"),
        ("source_version", "cache-stale"),
        ("content_hash", QUERY_HASH),
    ],
)
def test_collection_snapshot_keys_reject_tampered_references(
    field: str,
    value: str,
) -> None:
    collection = build_demo_collection()
    summary = build_demo_summary()
    reference = summary.input_versions.source_snapshots[0].model_copy(
        update={field: value}
    )
    input_versions = summary.input_versions.model_copy(
        update={"source_snapshots": (reference,)}
    )
    tampered_summary = summary.model_copy(update={"input_versions": input_versions})

    with pytest.raises(SecurityProblem) as exc_info:
        _collection_snapshot_keys(collection, tampered_summary)

    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"


def test_collection_snapshot_keys_reject_omitted_references() -> None:
    collection = build_demo_collection()
    summary = build_demo_summary()
    input_versions = summary.input_versions.model_copy(update={"source_snapshots": ()})
    incomplete_summary = summary.model_copy(update={"input_versions": input_versions})

    with pytest.raises(SecurityProblem) as exc_info:
        _collection_snapshot_keys(collection, incomplete_summary)

    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"
