from datetime import UTC, datetime, timedelta

from app.workflow.scientific_provenance import _scientific_source_snapshot_id


def test_source_snapshot_identity_distinguishes_physical_retrievals() -> None:
    retrieved_at = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    identity = {
        "project_id": "00000000-0000-4000-8000-000000000001",
        "source_id": "esa_gaia_dr3",
        "query_hash": "sha256:" + "1" * 64,
        "content_hash": "sha256:" + "2" * 64,
    }

    first = _scientific_source_snapshot_id(
        **identity,
        retrieved_at=retrieved_at,
    )
    second = _scientific_source_snapshot_id(
        **identity,
        retrieved_at=retrieved_at + timedelta(seconds=1),
    )

    assert first != second


def test_source_snapshot_identity_normalizes_equivalent_timezones() -> None:
    retrieved_at = datetime.fromisoformat("2026-08-20T18:00:00+08:00")
    identity = {
        "project_id": "00000000-0000-4000-8000-000000000001",
        "source_id": "esa_gaia_dr3",
        "query_hash": "sha256:" + "1" * 64,
        "content_hash": "sha256:" + "2" * 64,
    }

    assert _scientific_source_snapshot_id(
        **identity,
        retrieved_at=retrieved_at,
    ) == _scientific_source_snapshot_id(
        **identity,
        retrieved_at=retrieved_at.astimezone(UTC),
    )
