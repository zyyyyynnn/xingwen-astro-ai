"""Pure domain policy for research-input ingestion.

This module is the single authority for the content rules of the ingestion
boundary: MIME sniffing from magic bytes, declared-type/MIME compatibility,
filename sanitization and the canonical request fingerprint used for
``Idempotency-Key`` replay.

It is deliberately dependency-free with respect to the transport and the
persistence layers: no FastAPI, no Starlette ``Request``, no SQLAlchemy
``Session``, no dynamic ``app.config.settings`` import, no network and no
filesystem I/O. Every configurable value arrives through
:class:`ResearchInputPolicy`, which the application service constructs from
settings exactly once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.schemas.research_input import ResearchInputType
from app.security import canonical_request_hash

_MAX_FILENAME_LENGTH = 255

#: MIME prefixes accepted per declared ResearchInputType.
_TYPE_MIME_FAMILIES: dict[ResearchInputType, tuple[str, ...]] = {
    ResearchInputType.url: (
        "application/pdf",
        "text/csv",
        "application/json",
        "image/",
        "text/plain",
    ),
    ResearchInputType.pdf: ("application/pdf",),
    ResearchInputType.csv: ("text/csv",),
    ResearchInputType.json: ("application/json",),
    ResearchInputType.image: ("image/",),
    ResearchInputType.text: ("text/plain",),
}

_FILENAME_EXTENSION_MIME: dict[str, tuple[str, ...]] = {
    "pdf": ("application/pdf",),
    "csv": ("text/csv",),
    "json": ("application/json",),
    "png": ("image/png",),
    "jpg": ("image/jpeg",),
    "jpeg": ("image/jpeg",),
    "gif": ("image/gif",),
    "webp": ("image/webp",),
    "txt": ("text/plain",),
}

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_ANY_CHARACTER_BUT_SEPARATORS = re.compile(r"[^/\\]+$")


@dataclass(frozen=True, slots=True)
class ResearchInputPolicy:
    """Immutable ingestion policy resolved from configuration once at wiring.

    Holding the allowed MIME set here is what removes the domain -> global
    settings back-dependency: the policy is injected, never looked up.
    """

    allowed_mimes: frozenset[str]
    max_size_bytes: int

    @classmethod
    def from_values(
        cls, *, allowed_mime_types: object, max_size_bytes: int
    ) -> ResearchInputPolicy:
        """Build a policy from raw configuration values (normalizing MIMEs)."""

        if isinstance(allowed_mime_types, str):
            raw_items: tuple[str, ...] = tuple(
                item for item in allowed_mime_types.split(",") if item.strip()
            )
        else:
            raw_items = tuple(str(item) for item in allowed_mime_types or ())
        return cls(
            allowed_mimes=frozenset(normalize_mime(item) for item in raw_items),
            max_size_bytes=max_size_bytes,
        )


def sniff_mime_type(content: bytes) -> str | None:
    """Classify raw bytes from magic signatures; ``None`` means unknown."""

    if content.startswith(b"%PDF"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    stripped = content.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith((b"{", b"[")):
        return "application/json"
    if _looks_like_text(content):
        if _looks_like_csv(content):
            return "text/csv"
        return "text/plain"
    return None


def validate_declared_mime(
    *,
    declared_type: ResearchInputType,
    sniffed_mime: str | None,
    client_mime: str | None,
    allowed_mimes: frozenset[str],
) -> str | None:
    """Return the authoritative MIME or ``None`` when the content is rejected.

    Bytes are authoritative. The declared type must be consistent with the
    sniffed content, and a client-supplied MIME hint (never trusted on its own)
    must agree as well. ``allowed_mimes`` is always supplied by the caller.
    """

    if sniffed_mime is None:
        return None
    if not mime_matches_type(sniffed_mime, declared_type):
        return None
    if client_mime is not None and normalize_mime(client_mime) != sniffed_mime:
        return None
    if sniffed_mime not in allowed_mimes:
        return None
    return sniffed_mime


def sanitize_filename(raw: str | None) -> str | None:
    """Return a display-safe basename, or ``None`` when the name is unusable."""

    if raw is None:
        return None
    if not raw:
        return None
    cleaned = _CONTROL_CHARACTERS.sub("", raw).strip()
    cleaned = cleaned.replace("\\", "/")
    basename = _ANY_CHARACTER_BUT_SEPARATORS.search(cleaned)
    if basename is None:
        return None
    cleaned = basename.group(0).strip()
    if not cleaned or cleaned in {".", ".."}:
        return None
    if len(cleaned) > _MAX_FILENAME_LENGTH:
        return None
    return cleaned


def filename_extension_matches(filename: str, sniffed_mime: str) -> bool:
    """Enforce filename-extension/MIME consistency when an extension exists."""

    dot = filename.rfind(".")
    if dot <= 0:
        return True
    extension = filename[dot + 1 :].lower()
    allowed = _FILENAME_EXTENSION_MIME.get(extension)
    return allowed is None or sniffed_mime in allowed


def mime_matches_type(mime: str, declared_type: ResearchInputType) -> bool:
    """Return whether a sniffed MIME belongs to the declared type's family."""

    families = _TYPE_MIME_FAMILIES[declared_type]
    return any(mime.startswith(family) for family in families)


def normalize_mime(value: str) -> str:
    """Strip parameters and case from a MIME declaration."""

    return value.split(";", 1)[0].strip().lower()


# ---- request fingerprint ---------------------------------------------------
#
# The request fingerprint answers "is this the same HTTP request?" for
# Idempotency-Key replay. It is deliberately NOT the content dedup identity:
# two different keys may carry the same bytes, and the same key must never
# carry different bytes. For upload and text the fingerprint therefore binds
# the *content hash* (real byte identity), not just the filename. For URL it
# binds the submitted URL, because replay must be decidable before any network
# fetch happens.


def canonical_research_input_request_hash(
    *,
    project_id: str,
    input_type: ResearchInputType,
    content_hash: str | None = None,
    url: str | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
) -> str:
    """Return the canonical ``sha256:`` fingerprint of one create request."""

    payload: dict[str, Any] = {
        "project_id": project_id,
        "type": input_type.value,
        "content_hash": content_hash,
        "url": url,
        "filename": filename,
        "mime_type": normalize_mime(mime_type) if mime_type is not None else None,
    }
    return canonical_request_hash(payload)


def _looks_like_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    sample = content[:4096]
    if not sample:
        return False
    binary_bytes = sum(1 for byte in sample if byte < 9 or 13 < byte < 32 or byte == 127)
    return binary_bytes * 20 < len(sample)


def _looks_like_csv(content: bytes) -> bool:
    head = content[:8192]
    has_newline = b"\n" in head or b"\r" in head
    has_delimiter = any(byte in head for byte in b",;\t")
    return has_newline and has_delimiter


__all__ = [
    "ResearchInputPolicy",
    "canonical_research_input_request_hash",
    "filename_extension_matches",
    "mime_matches_type",
    "normalize_mime",
    "sanitize_filename",
    "sniff_mime_type",
    "validate_declared_mime",
]
