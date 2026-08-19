"""Content-addressed immutable blob storage port (Research Input Ingestion).

Research Input content is never a source of truth inside process memory: it is
stored byte-for-byte behind a ``sha256:<hex>`` content hash in a local,
content-addressed directory. The :class:`ContentStorage` Protocol keeps the
object-store decision open; today only :class:`LocalContentStorage` exists and
no S3/MinIO configuration is introduced without a load basis.

Publication is *non-overwrite* by construction. A final blob is created with an
atomic create-if-absent primitive (``os.link`` -> ``FileExistsError`` when the
target already exists); no code path ever calls ``os.replace`` /
``Path.replace`` against an existing final blob, so a published byte sequence
can never be silently clobbered by a later writer.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import os
import re
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import aiofiles

_HASH_REGEX = re.compile(r"^sha256:[0-9a-f]{64}$")
_STREAM_CHUNK_BYTES = 1024 * 1024
_MAX_RANGE_HEADER_BYTES = 200


@dataclass(frozen=True, slots=True)
class ContentRead:
    """A bounded, lazy read from an immutable content blob.

    ``start`` and ``end`` are inclusive byte offsets.  An empty blob uses
    ``end == -1`` and therefore has a zero ``content_length``.  ``chunks``
    opens the blob lazily and never materializes the selected bytes in memory.
    """

    start: int
    end: int
    total_size: int
    chunks: AsyncIterator[bytes]

    @property
    def content_length(self) -> int:
        return max(0, self.end - self.start + 1)


@dataclass(frozen=True, slots=True)
class ContentBlobInspection:
    """One filesystem entry observed by the read-only integrity scanner.

    Paths are always relative storage references.  Absolute host paths never
    cross this port, including for malformed or unreadable entries.
    """

    storage_ref: str
    content_hash: str | None
    actual_content_hash: str | None
    size_bytes: int | None
    modified_at_ns: int | None
    status: Literal["ok", "hash_mismatch", "unreadable", "unexpected"]


class ContentStorage(Protocol):
    """Immutable content-addressed storage shared by upload, URL and text paths."""

    async def store(self, content: bytes, content_hash: str) -> str:
        """Persist ``content`` under its verified hash and return the storage ref.

        Must verify ``content`` hashes to ``content_hash`` before writing and
        never overwrite an existing blob (same hash reuses the same path).
        """

    async def retrieve(self, content_hash: str) -> bytes | None:
        """Return the exact stored bytes, or ``None`` when the blob is absent."""

    async def open_read(
        self, content_hash: str, *, range_header: str | None = None
    ) -> ContentRead | None:
        """Open a lazy full or single-byte-range read.

        ``range_header`` uses the HTTP ``Range: bytes=...`` grammar.  A
        malformed, multi-range, or unsatisfiable request raises
        :class:`ContentRangeNotSatisfiable`; an absent blob returns ``None``.
        The returned iterator yields bounded chunks and must be consumed by
        the caller to close its underlying read handle.
        """

    def exists(self, content_hash: str) -> bool:
        """Return whether the blob is already stored."""

    async def inspect(self) -> tuple[ContentBlobInspection, ...]:
        """Return a read-only, streaming hash/size inspection of local entries."""


class ContentStorageError(RuntimeError):
    """Raised for I/O failures that must not be mistaken for corruption."""


class ContentRangeNotSatisfiable(ContentStorageError):
    """Raised when a requested single byte range cannot be served."""

    def __init__(self, *, total_size: int) -> None:
        self.total_size = total_size
        super().__init__("requested byte range is not satisfiable")


def sha256_content_hash(content: bytes) -> str:
    """Return the canonical ``sha256:<hex>`` identity of raw content bytes."""

    return "sha256:" + hashlib.sha256(content).hexdigest()


class LocalContentStorage:
    """Filesystem content-addressed store under ``root/{hex[:2]}/{hex}``.

    The ``sha256:`` prefix is intentionally stripped from path segments:
    the colon is not a valid filename character on Windows.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _blob_path(self, content_hash: str) -> Path:
        hex_value = _hash_hex(content_hash)
        return self._root / hex_value[:2] / hex_value

    async def store(self, content: bytes, content_hash: str) -> str:
        if sha256_content_hash(content) != content_hash:
            raise ValueError(f"content does not match content_hash {content_hash}")
        blob = self._blob_path(content_hash)

        # Fast path: an already-published, verified-correct blob is reused. A
        # blob that exists but reads back with the wrong hash is corruption and
        # is repaired below; a blob we cannot read is an I/O fault and is
        # surfaced, never deleted.
        if blob.is_file():
            verdict = self._verify_existing(blob, content_hash)
            if verdict is True:
                return _storage_ref(content_hash)
            if verdict is None:
                # unreadable -> already raised inside _verify_existing
                pass  # pragma: no cover - _verify_existing raises

        blob.parent.mkdir(parents=True, exist_ok=True)
        temp_blob = blob.parent / f".tmp_{secrets.token_hex(8)}"
        try:
            await self._write_temp(temp_blob, content)
            if _publish_no_replace(temp_blob, blob):
                _fsync_dir(blob.parent)
                return _storage_ref(content_hash)
            # Lost the create race, or the final already existed. Re-validate
            # the winning blob; matching bytes are reused, a mismatch is
            # corruption and is repaired against the same no-replace primitive.
            if self._verify_existing(blob, content_hash) is True:
                return _storage_ref(content_hash)
            self._repair_corrupt(blob, content, content_hash, temp_blob)
            return _storage_ref(content_hash)
        finally:
            _unlink_quietly(temp_blob)

    async def retrieve(self, content_hash: str) -> bytes | None:
        blob = self._blob_path(content_hash)
        if not blob.is_file():
            return None
        async with aiofiles.open(blob, "rb") as handle:
            content = await handle.read()
        if sha256_content_hash(content) != content_hash:
            # Immutable blob read back wrong: report, never silently drop.
            raise ContentStorageError(
                f"stored blob for {content_hash} failed integrity check"
            )
        return content

    async def open_read(
        self, content_hash: str, *, range_header: str | None = None
    ) -> ContentRead | None:
        blob = self._blob_path(content_hash)
        try:
            if not blob.is_file():
                return None
            total_size = blob.stat().st_size
        except FileNotFoundError:
            return None
        except (PermissionError, OSError) as exc:
            raise ContentStorageError(
                f"unable to inspect stored blob for {content_hash}"
            ) from exc

        start, end = _resolve_byte_range(range_header, total_size)
        return ContentRead(
            start=start,
            end=end,
            total_size=total_size,
            chunks=_iter_blob_range(
                blob,
                content_hash=content_hash,
                start=start,
                end=end,
            ),
        )

    def exists(self, content_hash: str) -> bool:
        return self._blob_path(content_hash).is_file()

    async def inspect(self) -> tuple[ContentBlobInspection, ...]:
        """Inspect every store entry without following symbolic links.

        Hashing is chunked in a worker thread, so neither a large blob nor a
        large store is copied into the application event loop.  Unexpected
        files (including abandoned temporaries and symlinks) are reported but
        never opened or removed.
        """

        entries = await asyncio.to_thread(_storage_entries, self._root)
        inspections: list[ContentBlobInspection] = []
        for storage_ref, path, expected_hash in entries:
            if expected_hash is None:
                inspections.append(
                    ContentBlobInspection(
                        storage_ref=storage_ref,
                        content_hash=None,
                        actual_content_hash=None,
                        size_bytes=None,
                        modified_at_ns=None,
                        status="unexpected",
                    )
                )
                continue
            try:
                actual_hash, size_bytes, modified_at_ns = await asyncio.to_thread(
                    _hash_file, path
                )
            except (FileNotFoundError, PermissionError, OSError):
                inspections.append(
                    ContentBlobInspection(
                        storage_ref=storage_ref,
                        content_hash=expected_hash,
                        actual_content_hash=None,
                        size_bytes=None,
                        modified_at_ns=None,
                        status="unreadable",
                    )
                )
                continue
            inspections.append(
                ContentBlobInspection(
                    storage_ref=storage_ref,
                    content_hash=expected_hash,
                    actual_content_hash=actual_hash,
                    size_bytes=size_bytes,
                    modified_at_ns=modified_at_ns,
                    status=("ok" if actual_hash == expected_hash else "hash_mismatch"),
                )
            )
        return tuple(sorted(inspections, key=lambda item: item.storage_ref))

    # ---- internals ---------------------------------------------------------

    @staticmethod
    async def _write_temp(temp_blob: Path, content: bytes) -> None:
        async with aiofiles.open(temp_blob, "wb") as handle:
            await handle.write(content)
            await handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _verify_existing(blob: Path, content_hash: str) -> bool | None:
        """Return True (match), False (hash mismatch), or raise on I/O fault.

        A ``PermissionError`` / ``OSError`` is an environment fault, not proof
        of corruption, so the blob is left untouched and the error propagates.
        Only a clean read whose bytes hash wrongly proves corruption.
        """

        try:
            existing = blob.read_bytes()
        except FileNotFoundError:
            return False
        except (PermissionError, OSError) as exc:
            raise ContentStorageError(
                f"unable to read existing blob for {content_hash}"
            ) from exc
        return sha256_content_hash(existing) == content_hash

    def _repair_corrupt(
        self, blob: Path, content: bytes, content_hash: str, temp_blob: Path
    ) -> None:
        """Quarantine a corrupt final and publish the correct bytes.

        The corrupt blob is moved aside to a unique ``.corrupt_*`` name in the
        same directory (never overwritten in place), then the verified content
        is published through the same create-if-absent primitive. A concurrent
        repair that wins the create race is re-validated and reused.
        """

        quarantine = blob.parent / f".corrupt_{content_hash[7:23]}_{secrets.token_hex(8)}"
        try:
            os.replace(blob, quarantine)
        except FileNotFoundError:
            pass  # another writer already moved/removed it
        except (PermissionError, OSError) as exc:
            raise ContentStorageError(
                f"unable to quarantine corrupt blob for {content_hash}"
            ) from exc

        republish = blob.parent / f".tmp_{secrets.token_hex(8)}"
        try:
            with open(republish, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if not _publish_no_replace(republish, blob):
                if self._verify_existing(blob, content_hash) is not True:
                    raise ContentStorageError(
                        f"failed to republish corrupt blob for {content_hash}"
                    )
            _fsync_dir(blob.parent)
        finally:
            _unlink_quietly(republish)
            _unlink_quietly(quarantine)
            _unlink_quietly(temp_blob)


def _publish_no_replace(temp: Path, final: Path) -> bool:
    """Atomically create ``final`` from ``temp`` without ever overwriting.

    Returns ``True`` when this caller published the blob, ``False`` when
    ``final`` already existed (create race lost / blob present). Uses
    ``os.link`` (hard link, same directory guarantees same volume): the link
    creation fails with ``FileExistsError`` when the target exists on both
    POSIX and Windows, giving create-if-absent semantics with no replace.
    """

    try:
        os.link(temp, final)
    except FileExistsError:
        return False
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            return False
        raise
    return True


def _fsync_dir(directory: Path) -> None:
    """Best-effort directory fsync for crash durability (POSIX only).

    Windows does not permit opening a directory handle for fsync via ``os.open``;
    the failure is swallowed explicitly rather than pretending it succeeded.
    """

    if os.name != "posix":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _hash_hex(content_hash: str) -> str:
    if not isinstance(content_hash, str) or not _HASH_REGEX.match(content_hash):
        raise ValueError(f"invalid content hash {content_hash!r}")
    return content_hash.removeprefix("sha256:")


def _storage_ref(content_hash: str) -> str:
    hex_value = _hash_hex(content_hash)
    return f"{hex_value[:2]}/{hex_value}"


def content_storage_ref(content_hash: str) -> str:
    """Return the canonical, backend-independent relative reference for a hash."""

    return _storage_ref(content_hash)


def _storage_entries(
    root: Path,
) -> tuple[tuple[str, Path, str | None], ...]:
    if not root.exists():
        return ()
    entries: list[tuple[str, Path, str | None]] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in tuple(directory_names):
            candidate = current_path / name
            if candidate.is_symlink():
                directory_names.remove(name)
                entries.append((_relative_ref(root, candidate), candidate, None))
        for name in file_names:
            candidate = current_path / name
            storage_ref = _relative_ref(root, candidate)
            expected_hash = _expected_hash_for_ref(storage_ref, candidate)
            entries.append((storage_ref, candidate, expected_hash))
    return tuple(entries)


def _expected_hash_for_ref(storage_ref: str, path: Path) -> str | None:
    if path.is_symlink():
        return None
    parts = storage_ref.split("/")
    if len(parts) != 2:
        return None
    prefix, hex_value = parts
    if (
        len(prefix) != 2
        or len(hex_value) != 64
        or prefix != hex_value[:2]
        or any(character not in "0123456789abcdef" for character in hex_value)
    ):
        return None
    return "sha256:" + hex_value


def _relative_ref(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _hash_file(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_STREAM_CHUNK_BYTES):
            digest.update(chunk)
            size_bytes += len(chunk)
    modified_at_ns = path.stat().st_mtime_ns
    return "sha256:" + digest.hexdigest(), size_bytes, modified_at_ns


def _resolve_byte_range(range_header: str | None, total_size: int) -> tuple[int, int]:
    if range_header is None:
        return (0, total_size - 1) if total_size else (0, -1)
    if len(range_header) > _MAX_RANGE_HEADER_BYTES:
        raise ContentRangeNotSatisfiable(total_size=total_size)

    value = range_header.strip()
    if not value.startswith("bytes="):
        raise ContentRangeNotSatisfiable(total_size=total_size)
    spec = value.removeprefix("bytes=")
    if not spec or "," in spec or "-" not in spec:
        raise ContentRangeNotSatisfiable(total_size=total_size)
    first, last = spec.split("-", maxsplit=1)

    if not first:
        if not _ascii_digits(last):
            raise ContentRangeNotSatisfiable(total_size=total_size)
        suffix_length = int(last)
        if suffix_length <= 0 or total_size == 0:
            raise ContentRangeNotSatisfiable(total_size=total_size)
        suffix_length = min(suffix_length, total_size)
        return total_size - suffix_length, total_size - 1

    if not _ascii_digits(first):
        raise ContentRangeNotSatisfiable(total_size=total_size)
    start = int(first)
    if start >= total_size:
        raise ContentRangeNotSatisfiable(total_size=total_size)
    if not last:
        return start, total_size - 1
    if not _ascii_digits(last):
        raise ContentRangeNotSatisfiable(total_size=total_size)
    end = min(int(last), total_size - 1)
    if end < start:
        raise ContentRangeNotSatisfiable(total_size=total_size)
    return start, end


def _ascii_digits(value: str) -> bool:
    return bool(value) and value.isascii() and value.isdigit()


async def _iter_blob_range(
    blob: Path,
    *,
    content_hash: str,
    start: int,
    end: int,
) -> AsyncIterator[bytes]:
    remaining = max(0, end - start + 1)
    if remaining == 0:
        return
    try:
        async with aiofiles.open(blob, "rb") as handle:
            await handle.seek(start)
            while remaining:
                chunk = await handle.read(min(_STREAM_CHUNK_BYTES, remaining))
                if not chunk:
                    raise ContentStorageError(
                        f"stored blob for {content_hash} ended before requested range"
                    )
                yield chunk
                remaining -= len(chunk)
    except ContentStorageError:
        raise
    except FileNotFoundError as exc:
        raise ContentStorageError(
            f"stored blob for {content_hash} disappeared during read"
        ) from exc
    except (PermissionError, OSError) as exc:
        raise ContentStorageError(
            f"unable to stream stored blob for {content_hash}"
        ) from exc


__all__ = [
    "ContentStorage",
    "ContentRead",
    "ContentRangeNotSatisfiable",
    "ContentBlobInspection",
    "ContentStorageError",
    "LocalContentStorage",
    "content_storage_ref",
    "sha256_content_hash",
]
