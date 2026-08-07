"""Content-addressed immutable blob storage port (B-19).

Research Input content is never a source of truth inside process memory: it is
stored byte-for-byte behind a ``sha256:<hex>`` content hash in a local,
content-addressed directory. The :class:`ContentStorage` Protocol keeps the
object-store decision open; today only :class:`LocalContentStorage` exists and
no S3/MinIO configuration is introduced without a load basis.
"""

from __future__ import annotations

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
        if blob.is_file():
            try:
                async with aiofiles.open(blob, "rb") as handle:
                    existing_bytes = await handle.read()
                if sha256_content_hash(existing_bytes) == content_hash:
                    return _storage_ref(content_hash)
                blob.unlink(missing_ok=True)
            except Exception:
                blob.unlink(missing_ok=True)

        blob.parent.mkdir(parents=True, exist_ok=True)
        temp_blob = blob.parent / f".tmp_{secrets.token_hex(8)}"
        try:
            async with aiofiles.open(temp_blob, "wb") as handle:
                await handle.write(content)
                await handle.flush()
                os.fsync(handle.fileno())
            temp_blob.replace(blob)
        except Exception:
            if temp_blob.exists():
                temp_blob.unlink(missing_ok=True)
            raise
        return _storage_ref(content_hash)

    async def retrieve(self, content_hash: str) -> bytes | None:
        blob = self._blob_path(content_hash)
        if not blob.is_file():
            return None
        try:
            async with aiofiles.open(blob, "rb") as handle:
                content = await handle.read()
            if sha256_content_hash(content) != content_hash:
                blob.unlink(missing_ok=True)
                return None
            return content
        except Exception:
            return None

    def exists(self, content_hash: str) -> bool:
        blob = self._blob_path(content_hash)
        if not blob.is_file():
            return False
        return True


def _hash_hex(content_hash: str) -> str:
    if not isinstance(content_hash, str) or not _HASH_REGEX.match(content_hash):
        raise ValueError(f"invalid content hash {content_hash!r}")
    return content_hash.removeprefix("sha256:")


def _storage_ref(content_hash: str) -> str:
    hex_value = _hash_hex(content_hash)
    return f"{hex_value[:2]}/{hex_value}"


__all__ = ["ContentStorage", "LocalContentStorage", "sha256_content_hash"]

