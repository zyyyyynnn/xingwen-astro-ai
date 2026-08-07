"""Benchmark-only native baseline for D-10 (NOT a production parser adapter).

This module uses the APPROVED native upstream ``docling-parse==7.11.0`` to
produce a Canonical ``DocumentParseCandidate`` for a legal fixture. Its purpose
is to validate the D-10 Canonical Contract, the Golden/Fixture runner and the
upstream native package API/feasibility — establishing the later hybrid control
baseline. It is imported only by the benchmark runner, never by the API runtime
or any production path, so the heavy docling-parse dependency stays optional and
out of core startup (per D-10 #31).

Coordinate note: docling-parse reports word rects in PDF bottom-left origin;
the Canonical ``DocumentBBox`` uses top-left origin, so this harness converts.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseProfile,
    DocumentParseQuality,
    Identifier,
    ParserBackend,
)
from app.services.scientific_document.ports import ParseRequest

_NATIVE_PACKAGE = "docling-parse"
_NATIVE_VERSION = "7.11.0"
_NATIVE_ENGINE = f"{_NATIVE_PACKAGE}=={_NATIVE_VERSION}"


def _to_top_left_rect(rect: object, page_height: float) -> DocumentBBox:
    """Convert a docling-parse bottom-left rect to Canonical top-left bbox."""
    x0 = float(getattr(rect, "r_x0"))
    y0 = float(getattr(rect, "r_y0"))
    x1 = float(getattr(rect, "r_x1"))
    y1 = float(getattr(rect, "r_y1"))
    top = page_height - max(y0, y1)
    bottom = page_height - min(y0, y1)
    left = min(x0, x1)
    right = max(x0, x1)
    return DocumentBBox(x1=left, y1=top, x2=right, y2=bottom)


def parse_native_baseline(
    request: ParseRequest,
    *,
    parser_profile_id: str = "d10-native-baseline",
    config_hash: str,
) -> DocumentParseCandidate:
    """Run the approved native upstream and map onto a Canonical candidate.

    Raises ``ImportError`` if the optional native dependency is not installed
    (CI must not require it unless the benchmark opts in).
    """
    try:
        from docling_parse.pdf_parser import (  # type: ignore[import-not-found]
            ContentConfig,
            ContentLevel,
            DecodeConfig,
            DoclingPdfParser,
        )
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise ImportError(
            "native baseline requires the optional dependency "
            f"{_NATIVE_ENGINE}; install it to run the native benchmark"
        ) from exc

    parser = DoclingPdfParser(loglevel="fatal")
    pdf_doc = parser.load(
        path_or_stream=io.BytesIO(request.input_bytes),
        decode_config=DecodeConfig(do_sanitization=True, keep_glyphs=False),
        content_config=ContentConfig(
            char_cells_content_level=ContentLevel.SKIP,
            word_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
            line_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
            shapes_content_level=ContentLevel.SKIP,
            bitmaps_content_level=ContentLevel.SKIP,
        ),
    )

    pages: list[DocumentPage] = []
    blocks: list[DocumentBlock] = []
    block_seq = 0
    for page_no, page in pdf_doc.iterate_pages():
        page_height = float(getattr(page, "dimension", None).height or 0.0)
        page_width = float(getattr(page, "dimension", None).width or 0.0)
        page_block_ids: list[Identifier] = []
        for word in page.iterate_cells(unit_type="word"):  # type: ignore[arg-type]
            block_seq += 1
            block_id = f"p{page_no:03d}-w{block_seq:04d}"
            bbox = _to_top_left_rect(word.rect, page_height)
            blocks.append(
                DocumentBlock(
                    block_id=block_id,
                    page_index=page_no,
                    reading_order=block_seq,
                    kind=DocumentBlockKind.paragraph,
                    bbox=bbox,
                    text=word.text,
                    quality=DocumentParseQuality.accepted,
                    parser_backend=ParserBackend.native,
                    parser_profile_id=parser_profile_id,
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

    profile = DocumentParseProfile(
        parser_profile_id=parser_profile_id,
        parser_profile_version="1.0.0",
        native_backend=_NATIVE_ENGINE,
        routing_policy_version="native-only",
        resource_policy_version="cpu-capable",
        configuration_hash=config_hash,
    )
    overall = (
        DocumentParseQuality.accepted
        if blocks
        else DocumentParseQuality.unsupported
    )
    candidate = DocumentParseCandidate(
        parse_id=f"parse_{request.research_input_id}",
        research_input_id=request.research_input_id,
        content_hash=request.content_hash,
        profile=profile,
        native_engine=_NATIVE_ENGINE,
        native_engine_version=_NATIVE_VERSION,
        config_hash=config_hash,
        canonical_output_hash=_content_hash_of(
            pages, blocks, overall, config_hash, request.content_hash
        ),
        pages=tuple(pages),
        blocks=tuple(blocks),
        overall_quality=overall,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )
    return candidate


def _content_hash_of(
    pages: list[DocumentPage],
    blocks: list[DocumentBlock],
    overall: DocumentParseQuality,
    config_hash: str,
    content_hash: str,
) -> str:
    payload = {
        "content_hash": content_hash,
        "config_hash": config_hash,
        "overall_quality": overall.value,
        "page_count": len(pages),
        "block_count": len(blocks),
        "block_text_hashes": [
            hashlib.sha256(b.text.encode("utf-8")).hexdigest()[:16]
            for b in blocks
            if b.text is not None
        ],
    }
    return compute_canonical_payload_hash(payload)


def native_engine_identity() -> tuple[str, str]:
    """Return (engine string, version) for the approved native upstream."""
    return _NATIVE_ENGINE, _NATIVE_VERSION


__all__ = [
    "parse_native_baseline",
    "native_engine_identity",
    "NATIVE_PACKAGE",
    "NATIVE_VERSION",
]
