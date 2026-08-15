"""Production scientific-document parser adapters.

The module owns the native-first routing policy and maps approved upstream
results directly onto the Canonical ``DocumentParseCandidate`` boundary.  It
does not persist parses or publish artifacts; those remain application/workflow
responsibilities.

PDF parsing reuses the audited docling-parse mapping that was originally
exercised only by the Golden Set harness.  Markdown and UTF-8 plain text use a
small deterministic structural parser because no vendor library adds value for
those already textual formats.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    ParserBackend,
    compute_scientific_document_schema_hash,
)

_NATIVE_PACKAGE = "docling-parse"
_NATIVE_VERSION = "7.11.0"
_PDF_ENGINE = f"{_NATIVE_PACKAGE}=={_NATIVE_VERSION}"
_TEXT_ENGINE = "xingwen-structured-text==1.0.0"
_PROFILE_VERSION = "1.0.0"
_MAX_PDF_BYTES = 64 * 1024 * 1024
_MAX_TEXT_BYTES = 8 * 1024 * 1024
_PDF_MIME_TYPES = frozenset({"application/pdf"})
_MARKDOWN_MIME_TYPES = frozenset({"text/markdown", "text/x-markdown"})
_PLAIN_TEXT_MIME_TYPES = frozenset({"text/plain"})
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^(?:[-+*]|\d+[.)])\s+\S")
_REFERENCE_HEADING = re.compile(
    r"^(?:references|bibliography|参考文献|引用文献)\s*$", re.IGNORECASE
)


class DocumentParserError(ValueError):
    """Base error for rejected document-parser inputs."""


class DocumentParserUnavailableError(DocumentParserError):
    """The selected approved parser dependency is not installed correctly."""


class UnsupportedDocumentMediaError(DocumentParserError):
    """The input MIME type is outside the production parser contract."""


@dataclass(frozen=True, slots=True)
class _TextUnit:
    kind: DocumentBlockKind
    text: str


def parser_configuration_hash(*, native_engine: str) -> str:
    """Return the reproducible identity of the frozen native routing policy."""
    return compute_canonical_payload_hash(
        {
            "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
            "schema_hash": compute_scientific_document_schema_hash(),
            "profile_version": _PROFILE_VERSION,
            "native_engine": native_engine,
            "routing_policy_id": "native-first",
            "resource_policy_id": "bounded-cpu",
            "limits": {
                "pdf_bytes": _MAX_PDF_BYTES,
                "text_bytes": _MAX_TEXT_BYTES,
            },
        }
    )


class ScientificDocumentParser:
    """Native-first production implementation of ``DocumentParserPort``."""

    def parse_document(self, input: DocumentParseInput) -> DocumentParseCandidate:
        if input.input_bytes is None:
            raise DocumentParserError(
                "parser requires content bytes resolved from the immutable content store"
            )
        mime_type = input.mime_type.casefold().split(";", 1)[0].strip()
        if mime_type in _PDF_MIME_TYPES:
            return parse_pdf(input)
        if mime_type in _MARKDOWN_MIME_TYPES:
            return parse_structured_text(input, markdown=True)
        if mime_type in _PLAIN_TEXT_MIME_TYPES:
            return parse_structured_text(input, markdown=False)
        raise UnsupportedDocumentMediaError(
            f"unsupported scientific-document MIME type: {input.mime_type}"
        )


def parse_pdf(input: DocumentParseInput) -> DocumentParseCandidate:
    """Parse one born-digital PDF with the approved docling-parse adapter."""
    content = _validated_bytes(input, max_bytes=_MAX_PDF_BYTES)
    if not content.startswith(b"%PDF-"):
        raise DocumentParserError("application/pdf input is not a PDF byte stream")
    try:
        installed_version = version(_NATIVE_PACKAGE)
    except PackageNotFoundError as exc:
        raise DocumentParserUnavailableError(
            f"PDF parsing requires {_PDF_ENGINE}"
        ) from exc
    if installed_version != _NATIVE_VERSION:
        raise DocumentParserUnavailableError(
            f"PDF parser version drift: expected {_NATIVE_VERSION}, got {installed_version}"
        )
    try:
        from docling_parse.pdf_parser import (  # type: ignore[import-not-found]
            ContentConfig,
            ContentLevel,
            DecodeConfig,
            DoclingPdfParser,
        )
    except ImportError as exc:  # pragma: no cover - package metadata without import
        raise DocumentParserUnavailableError(
            f"PDF parsing requires an importable {_PDF_ENGINE}"
        ) from exc

    parser = DoclingPdfParser(loglevel="fatal")
    pdf_doc = parser.load(
        path_or_stream=io.BytesIO(content),
        decode_config=DecodeConfig(do_sanitization=True, keep_glyphs=False),
        content_config=ContentConfig(
            char_cells_content_level=ContentLevel.SKIP,
            word_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
            line_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
            shapes_content_level=ContentLevel.SKIP,
            bitmaps_content_level=ContentLevel.SKIP,
        ),
    )
    profile_id = "scientific-document-pdf-native"
    config_hash = parser_configuration_hash(native_engine=_PDF_ENGINE)
    pages: list[DocumentPage] = []
    blocks: list[DocumentBlock] = []
    reading_order = 0
    try:
        for page_no, page in pdf_doc.iterate_pages():
            dimension = getattr(page, "dimension", None)
            page_height = float(dimension.height if dimension is not None else 0.0)
            page_width = float(dimension.width if dimension is not None else 0.0)
            if page_height <= 0.0 or page_width <= 0.0:
                raise DocumentParserError(
                    f"native parser returned invalid page geometry for page {page_no}: "
                    f"{page_width}x{page_height}"
                )
            page_block_ids: list[str] = []
            for word in page.iterate_cells(unit_type="word"):  # type: ignore[arg-type]
                text = str(getattr(word, "text", "")).strip()
                if not text:
                    continue
                reading_order += 1
                block_id = f"p{page_no:04d}-w{reading_order:06d}"
                blocks.append(
                    DocumentBlock(
                        block_id=block_id,
                        page_index=page_no,
                        reading_order=reading_order,
                        kind=DocumentBlockKind.paragraph,
                        bbox=_to_top_left_rect(word.rect, page_height),
                        text=text,
                        quality=DocumentParseQuality.accepted,
                        parser_backend=ParserBackend.native,
                        parser_profile_id=profile_id,
                    )
                )
                page_block_ids.append(block_id)
            pages.append(
                DocumentPage(
                    page_index=page_no,
                    width_points=page_width,
                    height_points=page_height,
                    block_ids=tuple(page_block_ids),
                )
            )
    finally:
        close = getattr(pdf_doc, "close", None)
        if callable(close):
            close()

    overall = _overall_quality(pages=pages, blocks=blocks)
    return _candidate(
        input=input,
        profile_id=profile_id,
        native_engine=_PDF_ENGINE,
        native_version=_NATIVE_VERSION,
        config_hash=config_hash,
        pages=pages,
        blocks=blocks,
        overall=overall,
    )


def parse_structured_text(
    input: DocumentParseInput, *, markdown: bool
) -> DocumentParseCandidate:
    """Parse UTF-8 Markdown/plain text without inventing missing sections."""
    content = _validated_bytes(input, max_bytes=_MAX_TEXT_BYTES)
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentParserError("text inputs must be valid UTF-8") from exc
    if "\x00" in text:
        raise DocumentParserError("text input contains NUL bytes")
    units = _markdown_units(text) if markdown else _plain_text_units(text)
    profile_id = "scientific-document-markdown" if markdown else "scientific-document-text"
    config_hash = parser_configuration_hash(native_engine=_TEXT_ENGINE)
    blocks: list[DocumentBlock] = []
    in_references = False
    for index, unit in enumerate(units, start=1):
        if unit.kind is DocumentBlockKind.heading and _REFERENCE_HEADING.fullmatch(
            unit.text
        ):
            in_references = True
        kind = DocumentBlockKind.reference if in_references else unit.kind
        blocks.append(
            DocumentBlock(
                block_id=f"p0000-b{index:06d}",
                page_index=0,
                reading_order=index,
                kind=kind,
                text=unit.text,
                quality=DocumentParseQuality.accepted,
                parser_backend=ParserBackend.native,
                parser_profile_id=profile_id,
            )
        )
    pages = [
        DocumentPage(
            page_index=0,
            width_points=612.0,
            height_points=792.0,
            block_ids=tuple(block.block_id for block in blocks),
        )
    ]
    overall = DocumentParseQuality.accepted if blocks else DocumentParseQuality.unsupported
    return _candidate(
        input=input,
        profile_id=profile_id,
        native_engine=_TEXT_ENGINE,
        native_version="1.0.0",
        config_hash=config_hash,
        pages=pages,
        blocks=blocks,
        overall=overall,
    )


def native_engine_identity() -> tuple[str, str]:
    return _PDF_ENGINE, _NATIVE_VERSION


def _validated_bytes(input: DocumentParseInput, *, max_bytes: int) -> bytes:
    content = input.input_bytes
    if content is None:
        raise DocumentParserError("document input bytes are missing")
    if not content:
        raise DocumentParserError("document input is empty")
    if len(content) > max_bytes:
        raise DocumentParserError(
            f"document exceeds parser byte limit ({len(content)} > {max_bytes})"
        )
    actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    if actual_hash != input.content_hash:
        raise DocumentParserError("document bytes do not match content_hash")
    return content


def _markdown_units(text: str) -> tuple[_TextUnit, ...]:
    units: list[_TextUnit] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if paragraph:
            units.append(_TextUnit(DocumentBlockKind.paragraph, " ".join(paragraph)))
            paragraph.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            if line:
                paragraph.append(line)
            continue
        heading = _HEADING.fullmatch(line)
        if heading:
            flush()
            units.append(_TextUnit(DocumentBlockKind.heading, heading.group(2).strip()))
        elif not line:
            flush()
        elif _LIST_ITEM.match(line):
            flush()
            units.append(_TextUnit(DocumentBlockKind.list, line))
        else:
            paragraph.append(line)
    flush()
    return tuple(unit for unit in units if unit.text)


def _plain_text_units(text: str) -> tuple[_TextUnit, ...]:
    return tuple(
        _TextUnit(DocumentBlockKind.paragraph, normalized)
        for part in re.split(r"\n\s*\n", text)
        if (normalized := " ".join(part.split()))
    )


def _overall_quality(
    *, pages: list[DocumentPage], blocks: list[DocumentBlock]
) -> DocumentParseQuality:
    if not blocks:
        return DocumentParseQuality.unsupported
    if any(not page.block_ids for page in pages):
        return DocumentParseQuality.partial
    return DocumentParseQuality.accepted


def _candidate(
    *,
    input: DocumentParseInput,
    profile_id: str,
    native_engine: str,
    native_version: str,
    config_hash: str,
    pages: list[DocumentPage],
    blocks: list[DocumentBlock],
    overall: DocumentParseQuality,
) -> DocumentParseCandidate:
    profile = DocumentParseProfile(
        parser_profile_id=profile_id,
        parser_profile_version=_PROFILE_VERSION,
        native_backend=native_engine,
        routing_policy_id="native-first",
        resource_policy_id="bounded-cpu",
        configuration_hash=config_hash,
    )
    output_hash = compute_canonical_payload_hash(
        {
            "input_content_hash": input.content_hash,
            "config_hash": config_hash,
            "pages": [page.model_dump(mode="json") for page in pages],
            "blocks": [block.model_dump(mode="json") for block in blocks],
            "overall_quality": overall.value,
        }
    )
    identity_hash = compute_canonical_payload_hash(
        {"input_content_hash": input.content_hash, "config_hash": config_hash}
    )
    return DocumentParseCandidate(
        parse_id=f"parse.{identity_hash[7:31]}",
        research_input_id=input.research_input_id,
        content_hash=input.content_hash,
        profile=profile,
        native_engine=native_engine,
        native_engine_version=native_version,
        config_hash=config_hash,
        canonical_output_hash=output_hash,
        pages=tuple(pages),
        blocks=tuple(blocks),
        overall_quality=overall,
        created_at=datetime.now(UTC).replace(microsecond=0),
    )


def _to_top_left_rect(rect: object, page_height: float) -> DocumentBBox:
    xs = [float(getattr(rect, attr)) for attr in ("r_x0", "r_x1", "r_x2", "r_x3")]
    ys = [float(getattr(rect, attr)) for attr in ("r_y0", "r_y1", "r_y2", "r_y3")]
    return DocumentBBox(
        x1=min(xs),
        y1=page_height - max(ys),
        x2=max(xs),
        y2=page_height - min(ys),
    )


__all__ = [
    "DocumentParserError",
    "DocumentParserUnavailableError",
    "ScientificDocumentParser",
    "UnsupportedDocumentMediaError",
    "native_engine_identity",
    "parse_pdf",
    "parse_structured_text",
    "parser_configuration_hash",
]
