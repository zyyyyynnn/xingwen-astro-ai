"""Read-only integrity and garbage-collection planning for immutable blobs.

This module deliberately stops at an impact plan.  Writers publish bytes before
their database transaction commits, so deletion without a writer/collector
coordination primitive could race a legitimate publication.  No HTTP endpoint
or destructive filesystem adapter is exposed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.content_storage import (
    ContentBlobInspection,
    ContentStorage,
    content_storage_ref,
)
from app.services.resource_authority import (
    ContentReference,
    ContentReferenceAuthority,
)


@dataclass(frozen=True, slots=True)
class ContentLifecycleFinding:
    """One fail-closed integrity or authority finding."""

    code: Literal[
        "authority_uncertain",
        "reference_invalid",
        "reference_ref_mismatch",
        "reference_size_conflict",
        "blob_missing",
        "blob_hash_mismatch",
        "blob_size_mismatch",
        "blob_unreadable",
        "unexpected_storage_entry",
    ]
    content_hash: str | None
    storage_ref: str | None
    resource_ids: tuple[str, ...]
    expected_size_bytes: int | None = None
    actual_size_bytes: int | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class OrphanBlobImpact:
    """A currently unreferenced, hash-valid blob; no deletion is implied."""

    content_hash: str
    storage_ref: str
    size_bytes: int
    modified_at_ns: int


@dataclass(frozen=True, slots=True)
class ContentLifecycleReport:
    """Deterministic read-only audit and GC impact report."""

    scanned_blob_count: int
    scanned_bytes: int
    referenced_hash_count: int
    reference_count: int
    orphan_blob_count: int
    orphan_bytes: int
    orphans: tuple[OrphanBlobImpact, ...]
    findings: tuple[ContentLifecycleFinding, ...]
    deletion_supported: Literal[False] = False
    deletion_blocker: str = (
        "Blob deletion is disabled until writers and maintenance share an "
        "atomic publication/collection coordination primitive."
    )

    @property
    def integrity_ok(self) -> bool:
        return not self.findings


class ContentLifecycleService:
    """Compute blob integrity and orphan impact from authoritative references."""

    def __init__(
        self,
        *,
        storage: ContentStorage,
        authority: ContentReferenceAuthority,
    ) -> None:
        self._storage = storage
        self._authority = authority

    async def inspect(self) -> ContentLifecycleReport:
        closure = self._authority.content_reference_closure()
        inspections = await self._storage.inspect()
        findings: list[ContentLifecycleFinding] = [
            ContentLifecycleFinding(
                code="authority_uncertain",
                content_hash=None,
                storage_ref=None,
                resource_ids=(issue.resource_id,),
                detail=issue.reason,
            )
            for issue in closure.issues
        ]

        valid_references: list[ContentReference] = []
        referenced_hashes: set[str] = set()
        for reference in closure.references:
            try:
                expected_ref = content_storage_ref(reference.content_hash)
            except ValueError:
                findings.append(
                    ContentLifecycleFinding(
                        code="reference_invalid",
                        content_hash=None,
                        storage_ref=reference.storage_ref,
                        resource_ids=(reference.resource_id,),
                    )
                )
                continue
            referenced_hashes.add(reference.content_hash)
            valid_references.append(reference)
            if reference.storage_ref != expected_ref:
                findings.append(
                    ContentLifecycleFinding(
                        code="reference_ref_mismatch",
                        content_hash=reference.content_hash,
                        storage_ref=reference.storage_ref,
                        resource_ids=(reference.resource_id,),
                    )
                )

        references_by_hash = _group_references(valid_references)
        expected_sizes: dict[str, int] = {}
        for content_hash, references in references_by_hash.items():
            declared_sizes = {
                item.declared_size_bytes
                for item in references
                if item.declared_size_bytes is not None
            }
            if len(declared_sizes) > 1:
                findings.append(
                    ContentLifecycleFinding(
                        code="reference_size_conflict",
                        content_hash=content_hash,
                        storage_ref=content_storage_ref(content_hash),
                        resource_ids=_resource_ids(references),
                    )
                )
            elif declared_sizes:
                expected_sizes[content_hash] = next(iter(declared_sizes))

        inspections_by_hash = {
            item.content_hash: item
            for item in inspections
            if item.content_hash is not None
        }
        for item in inspections:
            findings.extend(_inspection_findings(item, references_by_hash))

        for content_hash, references in references_by_hash.items():
            inspection = inspections_by_hash.get(content_hash)
            if inspection is None:
                findings.append(
                    ContentLifecycleFinding(
                        code="blob_missing",
                        content_hash=content_hash,
                        storage_ref=content_storage_ref(content_hash),
                        resource_ids=_resource_ids(references),
                        expected_size_bytes=expected_sizes.get(content_hash),
                    )
                )
                continue
            expected_size = expected_sizes.get(content_hash)
            if (
                expected_size is not None
                and inspection.size_bytes is not None
                and inspection.size_bytes != expected_size
            ):
                findings.append(
                    ContentLifecycleFinding(
                        code="blob_size_mismatch",
                        content_hash=content_hash,
                        storage_ref=inspection.storage_ref,
                        resource_ids=_resource_ids(references),
                        expected_size_bytes=expected_size,
                        actual_size_bytes=inspection.size_bytes,
                    )
                )

        orphans = tuple(
            OrphanBlobImpact(
                content_hash=item.content_hash,
                storage_ref=item.storage_ref,
                size_bytes=item.size_bytes,
                modified_at_ns=item.modified_at_ns,
            )
            for item in inspections
            if item.status == "ok"
            and item.content_hash is not None
            and item.content_hash not in referenced_hashes
            and item.size_bytes is not None
            and item.modified_at_ns is not None
        )
        scanned = tuple(item for item in inspections if item.content_hash is not None)
        return ContentLifecycleReport(
            scanned_blob_count=len(scanned),
            scanned_bytes=sum(item.size_bytes or 0 for item in scanned),
            referenced_hash_count=len(referenced_hashes),
            reference_count=len(closure.references),
            orphan_blob_count=len(orphans),
            orphan_bytes=sum(item.size_bytes for item in orphans),
            orphans=tuple(sorted(orphans, key=lambda item: item.content_hash)),
            findings=tuple(sorted(findings, key=_finding_sort_key)),
        )


def _group_references(
    references: list[ContentReference],
) -> dict[str, tuple[ContentReference, ...]]:
    grouped: dict[str, list[ContentReference]] = {}
    for reference in references:
        grouped.setdefault(reference.content_hash, []).append(reference)
    return {
        content_hash: tuple(items)
        for content_hash, items in grouped.items()
    }


def _inspection_findings(
    inspection: ContentBlobInspection,
    references_by_hash: dict[str, tuple[ContentReference, ...]],
) -> tuple[ContentLifecycleFinding, ...]:
    references = (
        references_by_hash.get(inspection.content_hash, ())
        if inspection.content_hash is not None
        else ()
    )
    if inspection.status == "unexpected":
        code = "unexpected_storage_entry"
    elif inspection.status == "unreadable":
        code = "blob_unreadable"
    elif inspection.status == "hash_mismatch":
        code = "blob_hash_mismatch"
    else:
        return ()
    return (
        ContentLifecycleFinding(
            code=code,
            content_hash=inspection.content_hash,
            storage_ref=inspection.storage_ref,
            resource_ids=_resource_ids(references),
            actual_size_bytes=inspection.size_bytes,
        ),
    )


def _resource_ids(references: tuple[ContentReference, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.resource_id for item in references}))


def _finding_sort_key(
    finding: ContentLifecycleFinding,
) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        finding.code,
        finding.content_hash or "",
        finding.storage_ref or "",
        finding.resource_ids,
    )


__all__ = [
    "ContentLifecycleFinding",
    "ContentLifecycleReport",
    "ContentLifecycleService",
    "OrphanBlobImpact",
]
