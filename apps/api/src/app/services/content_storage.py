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

import errno
import hashlib
import os
import re
import secrets
from pathlib import Path
from typing import Protocol

import aiofiles

_HASH_REGEX = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContentStorage(Protocol):
    """Immutable content-addressed storage shared by upload, URL and text paths."""

    async def store(self, content: bytes, content_hash: str) -> str:
        """Persist ``content`` under its verified hash and return the storage ref.

        Must verify ``content`` hashes to ``content_hash`` before writing and
        never overwrite an existing blob (same hash reuses the same path).
        """

    async def retrieve(self, content_hash: str) -> bytes | None:
        """Return the exact stored bytes, or ``None`` when the blob is absent."""

    def exists(self, content_hash: str) -> bool:
        """Return whether the blob is already stored."""


class ContentStorageError(RuntimeError):
    """Raised for I/O failures that must not be mistaken for corruption."""


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

    def exists(self, content_hash: str) -> bool:
        return self._blob_path(content_hash).is_file()

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


__all__ = [
    "ContentStorage",
    "ContentStorageError",
    "LocalContentStorage",
    "sha256_content_hash",
]
