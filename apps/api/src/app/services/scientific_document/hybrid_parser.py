"""Production native-first parser for scientific PDF and document images.

Born-digital pages are parsed locally with ``docling-parse``. Pages without a
usable text layer, or pages whose bitmap/vector structure indicates that the
native text stream is insufficient, are selectively sent to a configured
PaddleOCR-VL layout-parsing service. Both paths are projected onto the single
Canonical ``DocumentParseCandidate`` contract.
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any, Protocol

import httpx
from PIL import Image

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentFigure,
    DocumentFormula,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    DocumentTable,
    DocumentTableCell,
    ParserBackend,
)

_NATIVE_PACKAGE = "docling-parse"
_PARSER_PROFILE_ID = "scientific-document-hybrid"
_PARSER_PROFILE_VERSION = "1.1.0"
_ROUTING_POLICY_ID = "native-first-page-hybrid"
_RESOURCE_POLICY_ID = "bounded-document-pages"
_VISUAL_ENGINE = "PaddleOCR-VL layout-parsing service"
_DEFAULT_VISUAL_MODEL_ID = "PaddleOCR-VL-1.6-0.9B"
_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/tiff", "image/webp"})


class VisualParseError(RuntimeError):
    """The configured visual parser did not return a usable canonical page."""


@dataclass(frozen=True, slots=True)
class VisualPageBlock:
    label: str
    content: str | None
    bbox: tuple[float, float, float, float] | None
    order: int


@dataclass(frozen=True, slots=True)
class VisualPageResult:
    width_pixels: int
    height_pixels: int
    blocks: tuple[VisualPageBlock, ...]


class VisualPageParserPort(Protocol):
    @property
    def engine_version(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    def parse_page(self, image_bytes: bytes) -> VisualPageResult: ...


class PaddleOcrVlClient:
    """Narrow client for PaddleOCR-VL's official ``/layout-parsing`` API."""

    def __init__(
        self,
        *,
        base_url: str,
        model_revision: str,
        timeout_seconds: float = 60.0,
        model_id: str = _DEFAULT_VISUAL_MODEL_ID,
        client: httpx.Client | None = None,
    ) -> None:
        normalized_url = base_url.strip().rstrip("/")
        if not normalized_url.startswith(("http://", "https://")):
            raise ValueError("PaddleOCR-VL base URL must use HTTP or HTTPS")
        if not model_revision.strip():
            raise ValueError("PaddleOCR-VL model revision must be explicit")
        self._base_url = normalized_url
        self._model_revision = model_revision.strip()
        self._model_id = model_id.strip()
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def engine_version(self) -> str:
        return "1.6"

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_revision(self) -> str:
        return self._model_revision

    def parse_page(self, image_bytes: bytes) -> VisualPageResult:
        try:
            response = self._client.post(
                f"{self._base_url}/layout-parsing",
                json={
                    "file": base64.b64encode(image_bytes).decode("ascii"),
                    "fileType": 1,
                    "useLayoutDetection": True,
                    "useChartRecognition": False,
                    "useSealRecognition": False,
                    "formatBlockContent": False,
                    "returnMarkdownImages": False,
                    "visualize": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VisualParseError("PaddleOCR-VL request failed") from exc

        if payload.get("errorCode") not in (None, 0):
            raise VisualParseError("PaddleOCR-VL rejected the page")
        results = payload.get("result", {}).get("layoutParsingResults")
        if not isinstance(results, list) or len(results) != 1:
            raise VisualParseError("PaddleOCR-VL returned an invalid page count")
        pruned = results[0].get("prunedResult")
        if not isinstance(pruned, dict):
            raise VisualParseError("PaddleOCR-VL omitted prunedResult")
        width = _positive_int(pruned.get("width"), "width")
        height = _positive_int(pruned.get("height"), "height")
        raw_blocks = pruned.get("parsing_res_list")
        if not isinstance(raw_blocks, list):
            raise VisualParseError("PaddleOCR-VL omitted parsing_res_list")
        blocks: list[VisualPageBlock] = []
        for index, raw in enumerate(raw_blocks):
            if not isinstance(raw, dict):
                raise VisualParseError("PaddleOCR-VL returned a malformed block")
            label = str(raw.get("block_label") or "text").strip().lower()
            content = str(raw.get("block_content") or "").strip() or None
            blocks.append(
                VisualPageBlock(
                    label=label,
                    content=content,
                    bbox=_visual_bbox(raw.get("block_bbox"), width, height),
                    order=_non_negative_int(raw.get("block_order"), index),
                )
            )
        return VisualPageResult(width, height, tuple(blocks))


class HybridScientificDocumentParser:
    """Canonical native-first parser with selective page-level visual routing."""

    def __init__(
        self,
        *,
        visual_parser: VisualPageParserPort | None = None,
        min_native_characters: int = 80,
        max_pages: int = 200,
    ) -> None:
        if min_native_characters < 1 or max_pages < 1:
            raise ValueError("document parser limits must be positive")
        self._visual = visual_parser
        self._min_native_characters = min_native_characters
        self._max_pages = max_pages

    @property
    def profile(self) -> DocumentParseProfile:
        native_version = version(_NATIVE_PACKAGE)
        configuration = {
            "profile_version": _PARSER_PROFILE_VERSION,
            "native_engine": f"{_NATIVE_PACKAGE}=={native_version}",
            "visual_engine": _VISUAL_ENGINE if self._visual is not None else None,
            "visual_model_id": self._visual.model_id if self._visual else None,
            "visual_model_revision": (
                self._visual.model_revision if self._visual else None
            ),
            "min_native_characters": self._min_native_characters,
            "max_pages": self._max_pages,
            "max_document_bytes": _MAX_DOCUMENT_BYTES,
        }
        return DocumentParseProfile(
            parser_profile_id=_PARSER_PROFILE_ID,
            parser_profile_version=_PARSER_PROFILE_VERSION,
            native_backend=configuration["native_engine"],
            visual_backend=configuration["visual_engine"],
            routing_policy_id=_ROUTING_POLICY_ID,
            resource_policy_id=_RESOURCE_POLICY_ID,
            configuration_hash=compute_canonical_payload_hash(configuration),
        )

    def parse_document(self, input: DocumentParseInput) -> DocumentParseCandidate:
        if input.input_bytes is None:
            raise ValueError(
                "production document parsing requires resolved input bytes"
            )
        content = input.input_bytes
        if not content:
            raise ValueError("scientific document input is empty")
        if len(content) > _MAX_DOCUMENT_BYTES:
            raise ValueError("document exceeds the configured byte budget")
        if "sha256:" + hashlib.sha256(content).hexdigest() != input.content_hash:
            raise ValueError("document bytes do not match the immutable content hash")
        mime_type = input.mime_type.casefold().split(";", 1)[0].strip()
        profile = self.profile
        if mime_type in _IMAGE_MIME_TYPES:
            return self._parse_image(input, content=content, profile=profile)
        if mime_type != "application/pdf":
            raise ValueError("scientific document parser accepts PDF or document images")
        if not content.startswith(b"%PDF-"):
            raise ValueError("application/pdf input is not a PDF byte stream")

        from docling_core.types.doc.page import TextCellUnit
        from docling_parse.pdf_parser import (
            ContentConfig,
            ContentLevel,
            DecodeConfig,
            DoclingPdfParser,
        )

        document = DoclingPdfParser(loglevel="fatal").load(
            path_or_stream=io.BytesIO(content),
            decode_config=DecodeConfig(do_sanitization=True, keep_glyphs=False),
            content_config=ContentConfig(
                char_cells_content_level=ContentLevel.SKIP,
                word_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
                line_cells_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
                shapes_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
                bitmaps_content_level=ContentLevel.COMPUTE_AND_MATERIALIZE,
            ),
        )

        try:
            (
                pages,
                blocks,
                tables,
                formulas,
                figures,
                unresolved_pages,
            ) = self._parse_pages(
                document,
                profile=profile,
                text_unit=TextCellUnit,
            )
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        overall = self._overall_quality(blocks, unresolved_pages=unresolved_pages)
        return self._candidate(
            input,
            profile=profile,
            pages=pages,
            blocks=blocks,
            tables=tables,
            formulas=formulas,
            figures=figures,
            overall=overall,
        )

    def _parse_image(
        self,
        input: DocumentParseInput,
        *,
        content: bytes,
        profile: DocumentParseProfile,
    ) -> DocumentParseCandidate:
        if self._visual is None:
            raise ValueError("document image parsing requires the configured visual parser")
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                output = io.BytesIO()
                image.convert("RGB").save(output, format="PNG")
        except (OSError, ValueError) as exc:
            raise ValueError("document image is not a valid supported image") from exc
        if width < 1 or height < 1:
            raise ValueError("document image has invalid geometry")
        try:
            visual = self._visual.parse_page(output.getvalue())
            blocks, tables, formulas, figures = _canonical_visual_page(
                visual,
                page_index=1,
                page_width=float(width),
                page_height=float(height),
                profile_id=profile.parser_profile_id,
            )
        except VisualParseError:
            blocks, tables, formulas, figures = (), (), (), ()
        pages = (
            DocumentPage(
                page_index=1,
                width_points=float(width),
                height_points=float(height),
                block_ids=tuple(block.block_id for block in blocks),
            ),
        )
        return self._candidate(
            input,
            profile=profile,
            pages=pages,
            blocks=blocks,
            tables=tables,
            formulas=formulas,
            figures=figures,
            overall=self._overall_quality(blocks, unresolved_pages=not blocks),
        )

    @staticmethod
    def _overall_quality(
        blocks: list[DocumentBlock] | tuple[DocumentBlock, ...],
        *,
        unresolved_pages: int | bool,
    ) -> DocumentParseQuality:
        if not blocks:
            return DocumentParseQuality.unsupported
        if unresolved_pages:
            return DocumentParseQuality.partial
        return DocumentParseQuality.accepted

    def _candidate(
        self,
        input: DocumentParseInput,
        *,
        profile: DocumentParseProfile,
        pages: list[DocumentPage] | tuple[DocumentPage, ...],
        blocks: list[DocumentBlock] | tuple[DocumentBlock, ...],
        tables: list[DocumentTable] | tuple[DocumentTable, ...],
        formulas: list[DocumentFormula] | tuple[DocumentFormula, ...],
        figures: list[DocumentFigure] | tuple[DocumentFigure, ...],
        overall: DocumentParseQuality,
    ) -> DocumentParseCandidate:
        canonical_payload = {
            "research_input_id": input.research_input_id,
            "content_hash": input.content_hash,
            "profile": profile.model_dump(mode="json"),
            "pages": [page.model_dump(mode="json") for page in pages],
            "blocks": [block.model_dump(mode="json") for block in blocks],
            "tables": [table.model_dump(mode="json") for table in tables],
            "formulas": [formula.model_dump(mode="json") for formula in formulas],
            "figures": [figure.model_dump(mode="json") for figure in figures],
            "overall_quality": overall.value,
        }
        native_version = version(_NATIVE_PACKAGE)
        parse_identity = compute_canonical_payload_hash(
            {
                "research_input_id": input.research_input_id,
                "content_hash": input.content_hash,
                "configuration_hash": profile.configuration_hash,
            }
        )
        return DocumentParseCandidate(
            parse_id=f"parse.{parse_identity.removeprefix('sha256:')[:24]}",
            research_input_id=input.research_input_id,
            content_hash=input.content_hash,
            profile=profile,
            native_engine=profile.native_backend,
            native_engine_version=native_version,
            visual_engine=profile.visual_backend,
            visual_engine_version=(
                self._visual.engine_version if self._visual is not None else None
            ),
            visual_model_id=(
                self._visual.model_id if self._visual is not None else None
            ),
            visual_model_revision=(
                self._visual.model_revision if self._visual is not None else None
            ),
            config_hash=profile.configuration_hash,
            canonical_output_hash=compute_canonical_payload_hash(canonical_payload),
            pages=tuple(pages),
            blocks=tuple(blocks),
            tables=tuple(tables),
            formulas=tuple(formulas),
            figures=tuple(figures),
            overall_quality=overall,
            created_at=datetime.now(UTC).replace(microsecond=0),
        )

    def _parse_pages(
        self,
        document: Any,
        *,
        profile: DocumentParseProfile,
        text_unit: Any,
    ) -> tuple[
        list[DocumentPage],
        list[DocumentBlock],
        list[DocumentTable],
        list[DocumentFormula],
        list[DocumentFigure],
        int,
    ]:
        pages: list[DocumentPage] = []
        blocks: list[DocumentBlock] = []
        tables: list[DocumentTable] = []
        formulas: list[DocumentFormula] = []
        figures: list[DocumentFigure] = []
        unresolved_pages = 0
        for page_count, (page_index, page) in enumerate(
            document.iterate_pages(), start=1
        ):
            if page_count > self._max_pages:
                raise ValueError("PDF exceeds the configured document page budget")
            dimension = page.dimension
            page_width = float(dimension.width)
            page_height = float(dimension.height)
            if page_width <= 0 or page_height <= 0:
                raise ValueError("native parser returned invalid page geometry")

            native = _native_page_blocks(
                page,
                page_index=page_index,
                page_height=page_height,
                profile_id=profile.parser_profile_id,
                text_unit=text_unit,
            )
            native_characters = sum(len(block.text or "") for block in native)
            needs_visual = (
                native_characters < self._min_native_characters
                or len(page.bitmap_resources) > 0
                or len(page.shapes) > 0
            )
            page_blocks = native
            page_tables: tuple[DocumentTable, ...] = ()
            page_formulas: tuple[DocumentFormula, ...] = ()
            page_figures: tuple[DocumentFigure, ...] = ()
            if needs_visual:
                if self._visual is None:
                    unresolved_pages += 1
                else:
                    try:
                        image_bytes = _render_page_png(page, text_unit)
                        visual = self._visual.parse_page(image_bytes)
                        (
                            page_blocks,
                            page_tables,
                            page_formulas,
                            page_figures,
                        ) = _canonical_visual_page(
                            visual,
                            page_index=page_index,
                            page_width=page_width,
                            page_height=page_height,
                            profile_id=profile.parser_profile_id,
                        )
                        if not page_blocks:
                            unresolved_pages += 1
                            page_blocks = native
                    except VisualParseError:
                        unresolved_pages += 1

            blocks.extend(page_blocks)
            tables.extend(page_tables)
            formulas.extend(page_formulas)
            figures.extend(page_figures)
            pages.append(
                DocumentPage(
                    page_index=page_index,
                    width_points=page_width,
                    height_points=page_height,
                    block_ids=tuple(block.block_id for block in page_blocks),
                )
            )
        return pages, blocks, tables, formulas, figures, unresolved_pages


def _native_page_blocks(
    page: Any,
    *,
    page_index: int,
    page_height: float,
    profile_id: str,
    text_unit: Any,
) -> tuple[DocumentBlock, ...]:
    cells = list(page.iterate_cells(text_unit.LINE))
    if not cells:
        cells = list(page.iterate_cells(text_unit.WORD))
    blocks: list[DocumentBlock] = []
    for order, cell in enumerate(cells):
        text = str(cell.text).strip()
        if not text:
            continue
        blocks.append(
            DocumentBlock(
                block_id=f"p{page_index:04d}-n{order:04d}",
                page_index=page_index,
                reading_order=order,
                kind=DocumentBlockKind.paragraph,
                bbox=_native_bbox(cell.rect, page_height),
                text=text,
                quality=DocumentParseQuality.accepted,
                parser_backend=ParserBackend.native,
                parser_profile_id=profile_id,
            )
        )
    return tuple(blocks)


def _native_bbox(rect: Any, page_height: float) -> DocumentBBox:
    xs = [float(getattr(rect, name)) for name in ("r_x0", "r_x1", "r_x2", "r_x3")]
    ys = [float(getattr(rect, name)) for name in ("r_y0", "r_y1", "r_y2", "r_y3")]
    return DocumentBBox(
        x1=min(xs),
        y1=page_height - max(ys),
        x2=max(xs),
        y2=page_height - min(ys),
    )


def _render_page_png(page: Any, text_unit: Any) -> bytes:
    image: Image.Image = page.render_as_image(
        text_unit.WORD,
        draw_cells_bbox=False,
        draw_cells_text=True,
        draw_cells_bl=False,
        draw_cells_tr=False,
        draw_bitmap_resources=True,
        draw_shapes=True,
        draw_annotations=False,
        draw_widgets=False,
        draw_hyperlinks=False,
        draw_crop_box=False,
    )
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG")
    return output.getvalue()


def _canonical_visual_page(
    result: VisualPageResult,
    *,
    page_index: int,
    page_width: float,
    page_height: float,
    profile_id: str,
) -> tuple[
    tuple[DocumentBlock, ...],
    tuple[DocumentTable, ...],
    tuple[DocumentFormula, ...],
    tuple[DocumentFigure, ...],
]:
    blocks: list[DocumentBlock] = []
    tables: list[DocumentTable] = []
    formulas: list[DocumentFormula] = []
    figures: list[DocumentFigure] = []
    for index, item in enumerate(sorted(result.blocks, key=lambda block: block.order)):
        kind = _block_kind(item.label)
        block_id = f"p{page_index:04d}-v{index:04d}"
        bbox = _scale_bbox(
            item.bbox,
            source_width=result.width_pixels,
            source_height=result.height_pixels,
            page_width=page_width,
            page_height=page_height,
        )
        quality = (
            DocumentParseQuality.accepted
            if item.content is not None
            else DocumentParseQuality.partial
        )
        blocks.append(
            DocumentBlock(
                block_id=block_id,
                page_index=page_index,
                reading_order=index,
                kind=kind,
                bbox=bbox,
                text=item.content,
                quality=quality,
                parser_backend=ParserBackend.visual,
                parser_profile_id=profile_id,
            )
        )
        if kind is DocumentBlockKind.table:
            tables.append(
                _markdown_table(
                    item.content,
                    table_id=f"table-{block_id}",
                    block_id=block_id,
                    page_index=page_index,
                )
            )
        elif kind is DocumentBlockKind.formula:
            formulas.append(
                DocumentFormula(
                    block_id=block_id,
                    page_index=page_index,
                    bbox=bbox,
                    raw_text=item.content,
                    latex=item.content,
                    quality=quality,
                    parser_backend=ParserBackend.visual,
                    parser_profile_id=profile_id,
                )
            )
        elif kind is DocumentBlockKind.figure:
            figures.append(
                DocumentFigure(
                    block_id=block_id,
                    page_index=page_index,
                    bbox=bbox,
                    caption=item.content,
                    quality=quality,
                    parser_backend=ParserBackend.visual,
                    parser_profile_id=profile_id,
                )
            )
    return tuple(blocks), tuple(tables), tuple(formulas), tuple(figures)


def _block_kind(label: str) -> DocumentBlockKind:
    if label in {"doc_title", "paragraph_title", "title", "section_title"}:
        return DocumentBlockKind.heading
    if "table" in label:
        return DocumentBlockKind.table
    if "formula" in label or "equation" in label:
        return DocumentBlockKind.formula
    if label in {"image", "figure", "chart"}:
        return DocumentBlockKind.figure
    if "caption" in label or label in {"figure_title", "table_title"}:
        return DocumentBlockKind.caption
    if "reference" in label:
        return DocumentBlockKind.reference
    if label in {"footnote", "header", "footer", "number"}:
        return DocumentBlockKind.footnote
    if "list" in label:
        return DocumentBlockKind.list
    return DocumentBlockKind.paragraph


def _markdown_table(
    content: str | None,
    *,
    table_id: str,
    block_id: str,
    page_index: int,
) -> DocumentTable:
    raw_rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in (content or "").splitlines()
        if line.strip().count("|") >= 2
    ]
    if len(raw_rows) >= 2 and all(
        set(cell.replace(":", "").replace("-", "").strip()) == set()
        for cell in raw_rows[1]
    ):
        raw_rows.pop(1)
    if not raw_rows:
        return DocumentTable(
            table_id=table_id,
            page_index=page_index,
            block_id=block_id,
            row_count=1,
            column_count=1,
            quality=DocumentParseQuality.partial,
        )
    column_count = max(len(row) for row in raw_rows)
    rows = tuple(
        tuple(
            DocumentTableCell(
                cell_id=f"{table_id}-r{row_index}-c{column_index}",
                row_index=row_index,
                column_index=column_index,
                is_header=row_index == 0,
                text=cell or None,
                quality=(
                    DocumentParseQuality.accepted
                    if cell
                    else DocumentParseQuality.partial
                ),
            )
            for column_index, cell in enumerate(row)
        )
        for row_index, row in enumerate(raw_rows)
    )
    return DocumentTable(
        table_id=table_id,
        page_index=page_index,
        block_id=block_id,
        row_count=len(rows),
        column_count=column_count,
        rows=rows,
        quality=DocumentParseQuality.accepted,
    )


def _scale_bbox(
    bbox: tuple[float, float, float, float] | None,
    *,
    source_width: int,
    source_height: int,
    page_width: float,
    page_height: float,
) -> DocumentBBox | None:
    if bbox is None:
        return None
    x1, y1, x2, y2 = bbox
    return DocumentBBox(
        x1=max(0.0, min(page_width, x1 * page_width / source_width)),
        y1=max(0.0, min(page_height, y1 * page_height / source_height)),
        x2=max(0.0, min(page_width, x2 * page_width / source_width)),
        y2=max(0.0, min(page_height, y2 * page_height / source_height)),
    )


def _visual_bbox(
    value: Any, width: int, height: int
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4:
        raise VisualParseError("PaddleOCR-VL returned an invalid block_bbox")
    try:
        x1, y1, x2, y2 = (float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise VisualParseError(
            "PaddleOCR-VL returned a non-numeric block_bbox"
        ) from exc
    if not (0 <= x1 <= x2 <= width and 0 <= y1 <= y2 <= height):
        raise VisualParseError("PaddleOCR-VL block_bbox escapes page geometry")
    return x1, y1, x2, y2


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise VisualParseError(f"PaddleOCR-VL returned an invalid {field}")
    return value


def _non_negative_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VisualParseError("PaddleOCR-VL returned an invalid block_order")
    return value


def native_engine_identity() -> tuple[str, str]:
    """Return the exact native runtime identity used by the production parser."""

    native_version = version(_NATIVE_PACKAGE)
    return f"{_NATIVE_PACKAGE}=={native_version}", native_version


__all__ = [
    "HybridScientificDocumentParser",
    "native_engine_identity",
    "PaddleOcrVlClient",
    "VisualPageBlock",
    "VisualPageParserPort",
    "VisualPageResult",
    "VisualParseError",
]
