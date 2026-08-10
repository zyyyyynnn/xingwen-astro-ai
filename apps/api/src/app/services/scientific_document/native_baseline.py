"""Benchmark-only native parser harness; not a production adapter.

This module uses the APPROVED native upstream ``docling-parse==7.11.0`` to
produce a Canonical ``DocumentParseCandidate`` for a legal fixture. Its purpose
is to validate the canonical contract, the Golden/Fixture runner, and the
upstream native package API. It does not define routing or control
policy. It is imported only by the benchmark runner, never by the API runtime
or any production path, so the heavy docling-parse dependency stays optional and
out of core startup.

Coordinate note: docling-parse reports word rects in PDF bottom-left origin;
the Canonical ``DocumentBBox`` uses top-left origin, so this harness converts.

The single input boundary is ``DocumentParseInput`` (from the Parser Port); this
module maps the approved upstream result onto the Canonical contract and never
leaks vendor types into the returned candidate.
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
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    Identifier,
    ParserBackend,
)

_NATIVE_PACKAGE = "docling-parse"
_NATIVE_VERSION = "7.11.0"
_NATIVE_ENGINE = f"{_NATIVE_PACKAGE}=={_NATIVE_VERSION}"


def _to_top_left_rect(rect: object, page_height: float) -> DocumentBBox:
    """Convert a docling-parse bottom-left rect to Canonical top-left bbox."""
    xs = [float(getattr(rect, attr)) for attr in ("r_x0", "r_x1", "r_x2", "r_x3")]
    ys = [float(getattr(rect, attr)) for attr in ("r_y0", "r_y1", "r_y2", "r_y3")]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return DocumentBBox(
        x1=min_x,
        y1=page_height - max_y,
        x2=max_x,
        y2=page_height - min_y,
    )


def parse_native_baseline(
    input: DocumentParseInput,
    *,
    parser_profile_id: str = "scientific_document-native-baseline",
    config_hash: str,
) -> DocumentParseCandidate:
    """Run the approved native upstream and map onto a Canonical candidate."""
    if input.input_bytes is None:
        raise ValueError("native baseline requires input.input_bytes (legal fixture)")

    try:
        from docling_parse.pdf_parser import (  # type: ignore[import-not-found]
            ContentConfig,
            ContentLevel,
            DecodeConfig,
            DoclingPdfParser,
        )
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise ImportError(
            f"native baseline requires the optional dependency {_NATIVE_ENGINE}; "
            "install the benchmark dependency group to run it"
        ) from exc

    parser = DoclingPdfParser(loglevel="fatal")
    pdf_doc = parser.load(
        path_or_stream=io.BytesIO(input.input_bytes),
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
        dimension = getattr(page, "dimension", None)
        page_height = float(dimension.height if dimension is not None else 0.0)
        page_width = float(dimension.width if dimension is not None else 0.0)
        if page_height <= 0.0 or page_width <= 0.0:
            raise ValueError(
                f"native parser returned invalid page geometry for page {page_no}: "
                f"{page_width}x{page_height}"
            )

        page_block_ids: list[Identifier] = []
        for word in page.iterate_cells(unit_type="word"):  # type: ignore[arg-type]
            text = str(getattr(word, "text", "")).strip()
            if not text:
                continue
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
                    text=text,
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
        routing_policy_id="native-only",
        resource_policy_id="cpu-capable",
        configuration_hash=config_hash,
    )
    overall = (
        DocumentParseQuality.accepted if blocks else DocumentParseQuality.unsupported
    )
    return DocumentParseCandidate(
        parse_id=f"parse_{input.research_input_id}",
        research_input_id=input.research_input_id,
        content_hash=input.content_hash,
        profile=profile,
        native_engine=_NATIVE_ENGINE,
        native_engine_version=_NATIVE_VERSION,
        config_hash=config_hash,
        canonical_output_hash=_content_hash_of(
            pages, blocks, overall, config_hash, input.content_hash
        ),
        pages=tuple(pages),
        blocks=tuple(blocks),
        overall_quality=overall,
        created_at=datetime.now(timezone.utc).replace(microsecond=0),
    )


class NativeBaselineParser:
    """Benchmark-only structural implementation of ``DocumentParserPort``."""

    def __init__(
        self,
        *,
        config_hash: str,
        parser_profile_id: str = "scientific_document-native-baseline",
    ) -> None:
        if not config_hash:
            raise ValueError("NativeBaselineParser requires an explicit config_hash")
        self._parser_profile_id = parser_profile_id
        self._config_hash = config_hash

    def parse_document(self, input: DocumentParseInput) -> DocumentParseCandidate:
        return parse_native_baseline(
            input,
            parser_profile_id=self._parser_profile_id,
            config_hash=self._config_hash,
        )


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
            hashlib.sha256(block.text.encode("utf-8")).hexdigest()[:16]
            for block in blocks
            if block.text is not None
        ],
    }
    return compute_canonical_payload_hash(payload)


def native_engine_identity() -> tuple[str, str]:
    """Return ``(engine_identity, exact_package_version)``."""
    return _NATIVE_ENGINE, _NATIVE_VERSION


__all__ = [
    "parse_native_baseline",
    "NativeBaselineParser",
    "native_engine_identity",
]
