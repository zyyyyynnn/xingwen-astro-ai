"""Application boundary for parsing immutable ResearchInput content."""

from __future__ import annotations

import asyncio

from app.schemas.scientific_document import DocumentParseCandidate, DocumentParseInput
from app.services.content_storage import ContentStorage
from app.services.scientific_document.parser import (
    DocumentParserError,
    ScientificDocumentParser,
)
from app.services.scientific_document.ports import DocumentParserPort


class DocumentContentMissingError(DocumentParserError):
    """The ResearchInput metadata exists but its immutable blob is unavailable."""


class DocumentParsingService:
    """Resolve bytes from CAS, then invoke the single canonical parser port."""

    def __init__(
        self,
        content_storage: ContentStorage,
        parser: DocumentParserPort | None = None,
    ) -> None:
        self._content_storage = content_storage
        self._parser = parser or ScientificDocumentParser()

    async def parse(self, input: DocumentParseInput) -> DocumentParseCandidate:
        if input.input_bytes is not None:
            raise DocumentParserError(
                "production parsing resolves bytes from content storage"
            )
        content = await self._content_storage.retrieve(input.content_hash)
        if content is None:
            raise DocumentContentMissingError(
                "immutable ResearchInput content is unavailable"
            )
        return await asyncio.to_thread(
            self._parser.parse_document,
            input.model_copy(update={"input_bytes": content}),
        )


__all__ = ["DocumentContentMissingError", "DocumentParsingService"]
