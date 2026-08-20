"""Read-only content-addressed storage integrity through ContentLifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.content_lifecycle import ContentLifecycleService
from app.services.content_storage import (
    LocalContentStorage,
    content_storage_ref,
    sha256_content_hash,
)
from app.services.resource_authority import (
    ContentReference,
    InMemoryResourceAuthority,
)

HEALTHY_BYTES = b"healthy referenced blob"
ORPHAN_BYTES = b"valid orphan blob"


def _reference(
    *,
    content_hash: str,
    resource_id: str,
    declared_size_bytes: int | None = None,
) -> ContentReference:
    return ContentReference(
        project_id="project-1",
        resource_type="research_input_content",
        resource_id=resource_id,
        content_hash=content_hash,
        storage_ref=content_storage_ref(content_hash),
        declared_size_bytes=declared_size_bytes,
    )


def _service(
    tmp_path: Path, authority: InMemoryResourceAuthority
) -> tuple[ContentLifecycleService, LocalContentStorage]:
    storage = LocalContentStorage(tmp_path / "store")
    service = ContentLifecycleService(storage=storage, authority=authority)
    return service, storage


def _blob_path(root: Path, content_hash: str) -> Path:
    hex_value = content_hash.removeprefix("sha256:")
    return root / hex_value[:2] / hex_value


def test_healthy_referenced_blob_closes_integrity(tmp_path: Path) -> None:
    authority = InMemoryResourceAuthority()
    service, storage = _service(tmp_path, authority)
    content_hash = sha256_content_hash(HEALTHY_BYTES)
    asyncio.run(storage.store(HEALTHY_BYTES, content_hash))
    authority.register_content_reference(
        _reference(
            content_hash=content_hash,
            resource_id="input-1",
            declared_size_bytes=len(HEALTHY_BYTES),
        )
    )

    report = asyncio.run(service.inspect())

    assert report.integrity_ok
    assert report.findings == ()
    assert report.reference_count == 1
    assert report.orphan_blob_count == 0
    assert report.deletion_supported is False


def test_referenced_blob_missing_is_a_finding(tmp_path: Path) -> None:
    authority = InMemoryResourceAuthority()
    service, _storage = _service(tmp_path, authority)
    content_hash = sha256_content_hash(HEALTHY_BYTES)
    authority.register_content_reference(
        _reference(content_hash=content_hash, resource_id="input-1")
    )

    report = asyncio.run(service.inspect())

    assert not report.integrity_ok
    codes = [finding.code for finding in report.findings]
    assert "blob_missing" in codes
    missing = next(
        finding for finding in report.findings if finding.code == "blob_missing"
    )
    assert missing.content_hash == content_hash
    assert missing.resource_ids == ("input-1",)


def test_hash_mismatch_is_a_finding(tmp_path: Path) -> None:
    authority = InMemoryResourceAuthority()
    service, storage = _service(tmp_path, authority)
    content_hash = sha256_content_hash(HEALTHY_BYTES)
    asyncio.run(storage.store(HEALTHY_BYTES, content_hash))
    authority.register_content_reference(
        _reference(content_hash=content_hash, resource_id="input-1")
    )
    # Simulate on-disk corruption: the immutable blob reads back wrongly.
    _blob_path(tmp_path / "store", content_hash).write_bytes(b"corrupted")

    report = asyncio.run(service.inspect())

    assert not report.integrity_ok
    codes = [finding.code for finding in report.findings]
    assert "blob_hash_mismatch" in codes


def test_valid_orphan_is_reported_but_never_deleted(tmp_path: Path) -> None:
    authority = InMemoryResourceAuthority()
    service, storage = _service(tmp_path, authority)
    referenced_hash = sha256_content_hash(HEALTHY_BYTES)
    orphan_hash = sha256_content_hash(ORPHAN_BYTES)
    asyncio.run(storage.store(HEALTHY_BYTES, referenced_hash))
    asyncio.run(storage.store(ORPHAN_BYTES, orphan_hash))
    authority.register_content_reference(
        _reference(content_hash=referenced_hash, resource_id="input-1")
    )

    report = asyncio.run(service.inspect())

    assert report.integrity_ok
    assert report.orphan_blob_count == 1
    orphan = report.orphans[0]
    assert orphan.content_hash == orphan_hash
    assert orphan.size_bytes == len(ORPHAN_BYTES)
    assert report.deletion_supported is False
    # The audit is read-only: the orphan blob must remain on disk untouched.
    assert _blob_path(tmp_path / "store", orphan_hash).read_bytes() == ORPHAN_BYTES


def test_cli_module_exposes_read_only_audit_entrypoint() -> None:
    from app.commands import content_storage_audit

    assert callable(content_storage_audit.main)
    # No destructive surface may exist on this boundary.
    for forbidden in ("delete_orphans", "gc", "cleanup"):
        assert not hasattr(content_storage_audit, forbidden)
        assert not hasattr(ContentLifecycleService, forbidden)
