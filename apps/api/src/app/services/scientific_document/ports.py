"""Vendor-neutral port for scientific-document parsers.

This module defines the *capability* Xingwen needs from a document parser. It
contains NO vendor package import, NO vendor result type and NO vendor config
type. A production adapter implements ``DocumentParserPort`` by calling an
approved upstream and mapping its result onto the canonical
``DocumentParseCandidate`` from ``app.schemas.scientific_document``.

The port has exactly ONE input boundary (``DocumentParseInput``) and ONE output
boundary (``DocumentParseCandidate``). There is deliberately no second,
nearly-identical ``ParseRequest``/``ParseResult`` pair and no
output→input reconstruction: the Canonical contract is the single boundary.

Routing policy and resource budget are expressed through the
``DocumentParseProfile`` carried on the candidate, not here.
"""

from __future__ import annotations

from typing import Protocol

from app.schemas.scientific_document import (
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
)


class DocumentParserPort(Protocol):
    """Vendor-neutral capability: produce a Canonical ``DocumentParseCandidate``.

    Implementations must map every upstream element onto the Canonical schema
    and MUST NOT leak vendor types into the returned candidate. All required
    fields of ``DocumentParseInput`` (including ``source_type`` and
    ``mime_type``) MUST be supplied explicitly by the caller; an implementation
    MUST NOT guess or default them.
    """

    @property
    def profile(self) -> DocumentParseProfile:
        """Return the immutable parser configuration used for input identity."""
        ...

    def parse_document(self, input: DocumentParseInput) -> DocumentParseCandidate:
        """Parse ``input`` into a Canonical ``DocumentParseCandidate``.

        Implementations must map every upstream element onto the Canonical
        schema and MUST NOT leak vendor types into the returned candidate.
        """
        ...


__all__ = [
    "DocumentParserPort",
]
