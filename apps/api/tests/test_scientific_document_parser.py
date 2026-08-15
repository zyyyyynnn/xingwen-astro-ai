"""Production scientific-document parser behavior."""

from __future__ import annotations

import hashlib

import pytest

from app.schemas.scientific_document import (
    DocumentBlockKind,
    DocumentParseInput,
    DocumentParseQuality,
)
from app.services.scientific_document.parser import (
    DocumentParserError,
    ScientificDocumentParser,
    UnsupportedDocumentMediaError,
)
from app.services.document_parsing import (
    DocumentContentMissingError,
    DocumentParsingService,
)


def _input(content: bytes, *, mime_type: str) -> DocumentParseInput:
    return DocumentParseInput(
        research_input_id="research-input-1",
        content_hash="sha256:" + hashlib.sha256(content).hexdigest(),
        source_type="upload",
        mime_type=mime_type,
        filename="paper.md",
        input_bytes=content,
    )


def test_markdown_parser_preserves_structure_without_fabricating_sections() -> None:
    content = (
        "# Transit Search\n\n"
        "We searched the light curve.\n\n"
        "## Methods\n\n"
        "- Remove flagged cadences\n"
        "- Fit the transit\n\n"
        "## References\n\n"
        "Smith et al. 2025.\n"
    ).encode()

    parsed = ScientificDocumentParser().parse_document(
        _input(content, mime_type="text/markdown; charset=utf-8")
    )

    assert parsed.overall_quality is DocumentParseQuality.accepted
    assert [block.kind for block in parsed.blocks] == [
        DocumentBlockKind.heading,
        DocumentBlockKind.paragraph,
        DocumentBlockKind.heading,
        DocumentBlockKind.list,
        DocumentBlockKind.list,
        DocumentBlockKind.reference,
        DocumentBlockKind.reference,
    ]
    assert [block.text for block in parsed.blocks].count("Transit Search") == 1


def test_markdown_without_headings_remains_one_observed_paragraph() -> None:
    parsed = ScientificDocumentParser().parse_document(
        _input(b"Observed text only.", mime_type="text/markdown")
    )
    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].text == "Observed text only."
    assert parsed.blocks[0].kind is DocumentBlockKind.paragraph


def test_plain_text_rejects_invalid_utf8_and_hash_drift() -> None:
    parser = ScientificDocumentParser()
    with pytest.raises(DocumentParserError, match="valid UTF-8"):
        parser.parse_document(_input(b"\xff", mime_type="text/plain"))

    request = _input(b"hello", mime_type="text/plain").model_copy(
        update={"content_hash": "sha256:" + "0" * 64}
    )
    with pytest.raises(DocumentParserError, match="content_hash"):
        parser.parse_document(request)


def test_empty_and_unsupported_inputs_fail_closed() -> None:
    parser = ScientificDocumentParser()
    with pytest.raises(DocumentParserError, match="empty"):
        parser.parse_document(_input(b"", mime_type="text/plain"))
    with pytest.raises(UnsupportedDocumentMediaError):
        parser.parse_document(_input(b"{}", mime_type="application/json"))


def test_parser_requires_content_store_materialization() -> None:
    request = _input(b"content", mime_type="text/plain").model_copy(
        update={"input_bytes": None}
    )
    with pytest.raises(DocumentParserError, match="content bytes"):
        ScientificDocumentParser().parse_document(request)


class _Storage:
    def __init__(self, content: bytes | None) -> None:
        self.content = content

    async def retrieve(self, content_hash: str) -> bytes | None:
        return self.content

    async def store(self, content: bytes, content_hash: str) -> str:
        raise AssertionError("parse is read-only")

    def exists(self, content_hash: str) -> bool:
        return self.content is not None


@pytest.mark.anyio
async def test_application_service_reads_only_from_content_store() -> None:
    content = b"Observed paragraph."
    request = _input(content, mime_type="text/plain").model_copy(
        update={"input_bytes": None}
    )
    parsed = await DocumentParsingService(_Storage(content)).parse(request)
    assert parsed.blocks[0].text == "Observed paragraph."

    with pytest.raises(DocumentContentMissingError):
        await DocumentParsingService(_Storage(None)).parse(request)

    with pytest.raises(DocumentParserError, match="resolves bytes"):
        await DocumentParsingService(_Storage(content)).parse(
            request.model_copy(update={"input_bytes": content})
        )
