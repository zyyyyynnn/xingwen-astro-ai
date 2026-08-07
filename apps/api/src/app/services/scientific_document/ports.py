"""Vendor-neutral Parser Port for Scientific Document Parsing (D-10).

This module defines the *capability* Xingwen needs from a document parser. It
contains NO vendor package import, NO vendor result type and NO vendor config
type. A production adapter (D-11) implements ``DocumentParser`` by calling an
approved upstream and mapping its result onto the Canonical
``DocumentParseCandidate`` from ``app.schemas.scientific_document``.

The port is intentionally small: parse one input into one canonical candidate.
Routing policy, hybrid fallback and resource budget are expressed through the
``DocumentParseProfile`` carried on the candidate, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.schemas.scientific_document import DocumentParseCandidate, DocumentParseInput


@dataclass(frozen=True, slots=True)
class ParseRequest:
    """One parse request already resolved off the transport/store layer."""

    research_input_id: str
    content_hash: str
    source_type: str
    mime_type: str
    filename: str | None
    input_bytes: bytes


@dataclass(frozen=True, slots=True)
class ParseResult:
    """One canonical parse result produced by a parser implementation."""

    candidate: DocumentParseCandidate


class DocumentParser(ABC):
    """Vendor-neutral capability: produce a Canonical DocumentParseCandidate."""

    @abstractmethod
    def parse(self, request: ParseRequest) -> ParseResult:
        """Parse ``request`` into a Canonical ``DocumentParseCandidate``.

        Implementations must map every upstream element onto the Canonical
        schema and MUST NOT leak vendor types into the returned candidate.
        """
        raise NotImplementedError


def to_parse_input(candidate: DocumentParseCandidate) -> DocumentParseInput:
    """Build the Canonical ``DocumentParseInput`` that produced a candidate."""
    return DocumentParseInput(
        research_input_id=candidate.research_input_id,
        content_hash=candidate.content_hash,
        source_type=candidate.source_type if hasattr(candidate, "source_type") else "upload",
        mime_type=candidate.mime_type if hasattr(candidate, "mime_type") else "application/pdf",
        filename=candidate.filename if hasattr(candidate, "filename") else None,
    )


__all__ = [
    "ParseRequest",
    "ParseResult",
    "DocumentParser",
    "to_parse_input",
]
