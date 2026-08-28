"""Production native-first parser for scientific PDF and document images.

Born-digital pages are parsed locally with ``docling-parse``. Pages without a
usable text layer, or pages whose bitmap/vector structure indicates that the
native text stream is insufficient, are selectively sent to a configured
PaddleOCR-VL layout-parsing service. Both paths are projected onto the single
Canonical ``DocumentParseCandidate`` contract.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Sized
import hashlib
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from importlib.metadata import version
from typing import Any, Protocol

import httpx
from PIL import Image

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import (
    SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES,
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
LOCAL_PADDLE_ENGINE_IDENTITY = (
    "PaddleOCRVL official in-process pipeline (verified local bundle)"
)
_DEFAULT_VISUAL_MODEL_ID = "PaddleOCR-VL-1.6-0.9B"
_MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
_MAX_VISUAL_BLOCKS = 4096
_MAX_VISUAL_BLOCK_CONTENT_CHARS = 4 * 1024 * 1024
_MAX_VISUAL_TOTAL_CONTENT_CHARS = 16 * 1024 * 1024
_MAX_VISUAL_PAGE_DIMENSION = 100_000
_MAX_TABLE_CONTENT_CHARS = 4 * 1024 * 1024
_MAX_TABLE_ROWS = 512
_MAX_TABLE_COLUMNS = 256
_MAX_TABLE_LOGICAL_CELLS = 65_536
_MAX_VISUAL_GENERATION_TOKENS = 4096
_BLOCK_ATTRIBUTE_NAMES = {
    "block_label": "label",
    "block_content": "content",
    "block_bbox": "bbox",
    "block_order": "order_index",
}


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
    def engine_identity(self) -> str: ...

    @property
    def engine_version(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    @property
    def runtime_binding_hash(self) -> str: ...

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
    def engine_identity(self) -> str:
        return _VISUAL_ENGINE

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_revision(self) -> str:
        return self._model_revision

    @property
    def runtime_binding_hash(self) -> str:
        return compute_canonical_payload_hash(
            {"backend": "http", "base_url": self._base_url}
        )

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
                    "formatBlockContent": True,
                    "maxNewTokens": _MAX_VISUAL_GENERATION_TOKENS,
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
        raw_blocks = pruned.get("parsing_res_list")
        if not isinstance(raw_blocks, list):
            raise VisualParseError("PaddleOCR-VL omitted parsing_res_list")
        return project_visual_page_result(
            width=pruned.get("width"),
            height=pruned.get("height"),
            raw_blocks=raw_blocks,
        )


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
            "visual_engine": (
                self._visual.engine_identity if self._visual is not None else None
            ),
            "visual_model_id": self._visual.model_id if self._visual else None,
            "visual_model_revision": (
                self._visual.model_revision if self._visual else None
            ),
            "visual_runtime_binding_hash": (
                self._visual.runtime_binding_hash if self._visual else None
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
        if mime_type in SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES:
            return self._parse_image(input, content=content, profile=profile)
        if mime_type != "application/pdf":
            raise ValueError(
                "scientific document parser accepts PDF or document images"
            )
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
            raise ValueError(
                "document image parsing requires the configured visual parser"
            )
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
            visual = admit_visual_page_result(
                self._visual.parse_page(output.getvalue())
            )
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
                        visual = admit_visual_page_result(
                            self._visual.parse_page(image_bytes)
                        )
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
                    bbox=bbox,
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
    bbox: DocumentBBox | None,
) -> DocumentTable:
    if len(content or "") > _MAX_TABLE_CONTENT_CHARS:
        raise VisualParseError("visual table content exceeds the configured budget")
    if (content or "").lstrip().lower().startswith("<table"):
        html_rows = _parse_official_html_table(content or "")
        if html_rows:
            cells: list[tuple[DocumentTableCell, ...]] = []
            occupied: set[tuple[int, int]] = set()
            column_count = 0
            for row_index, raw_row in enumerate(html_rows):
                row: list[DocumentTableCell] = []
                column_index = 0
                for text, row_span, column_span, header_tag in raw_row:
                    while (row_index, column_index) in occupied:
                        column_index += 1
                        if column_index >= _MAX_TABLE_COLUMNS:
                            raise VisualParseError(
                                "visual table exceeds the configured column budget"
                            )
                    if column_index + column_span > _MAX_TABLE_COLUMNS:
                        raise VisualParseError(
                            "visual table span exceeds the configured column budget"
                        )
                    occupied_rows = (
                        min(len(html_rows), row_index + row_span) - row_index
                    )
                    if (
                        len(occupied) + occupied_rows * column_span
                        > _MAX_TABLE_LOGICAL_CELLS
                    ):
                        raise VisualParseError(
                            "visual table exceeds the configured logical-cell budget"
                        )
                    for occupied_row in range(
                        row_index, min(len(html_rows), row_index + row_span)
                    ):
                        for occupied_column in range(
                            column_index, column_index + column_span
                        ):
                            occupied.add((occupied_row, occupied_column))
                    row.append(
                        DocumentTableCell(
                            cell_id=(f"{table_id}-r{row_index}-c{column_index}"),
                            row_index=row_index,
                            column_index=column_index,
                            row_span=min(row_span, len(html_rows) - row_index),
                            column_span=column_span,
                            is_header=header_tag or row_index == 0,
                            # Paddle's official HTML table payload supplies only
                            # the enclosing layout block geometry.  Repeating
                            # that rectangle on every logical cell would falsely
                            # claim cell-level geometry.
                            bbox=None,
                            text=text or None,
                            quality=(
                                DocumentParseQuality.accepted
                                if text
                                else DocumentParseQuality.partial
                            ),
                        )
                    )
                    column_index += column_span
                    column_count = max(column_count, column_index)
                cells.append(tuple(row))
            return DocumentTable(
                table_id=table_id,
                page_index=page_index,
                block_id=block_id,
                row_count=len(cells),
                column_count=column_count,
                rows=tuple(cells),
                quality=DocumentParseQuality.accepted,
            )
    raw_rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in (content or "").splitlines()
        if line.strip().count("|") >= 2
    ]
    if len(raw_rows) > _MAX_TABLE_ROWS:
        raise VisualParseError("visual table exceeds the configured row budget")
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
    if column_count > _MAX_TABLE_COLUMNS or sum(map(len, raw_rows)) > (
        _MAX_TABLE_LOGICAL_CELLS
    ):
        raise VisualParseError("visual table exceeds the configured cell budget")
    rows = tuple(
        tuple(
            DocumentTableCell(
                cell_id=f"{table_id}-r{row_index}-c{column_index}",
                row_index=row_index,
                column_index=column_index,
                is_header=row_index == 0,
                bbox=bbox,
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


class _OfficialTableHtmlParser(HTMLParser):
    """Project PaddleOCR-VL's table HTML without importing vendor types."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int, bool]]] = []
        self._row: list[tuple[str, int, int, bool]] | None = None
        self._cell_text: list[str] | None = None
        self._cell_row_span = 1
        self._cell_column_span = 1
        self._cell_is_header = False
        self._cell_count = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.casefold()
        if lowered == "tr":
            if self._row is not None or len(self.rows) >= _MAX_TABLE_ROWS:
                raise VisualParseError("visual table exceeds or nests the row budget")
            self._row = []
        elif lowered in {"td", "th"} and self._row is not None:
            if (
                self._cell_text is not None
                or len(self._row) >= _MAX_TABLE_COLUMNS
                or self._cell_count >= _MAX_TABLE_LOGICAL_CELLS
            ):
                raise VisualParseError("visual table exceeds or nests the cell budget")
            values = {name.casefold(): value for name, value in attrs}
            self._cell_text = []
            self._cell_row_span = _html_span(values.get("rowspan"))
            self._cell_column_span = _html_span(values.get("colspan"))
            self._cell_is_header = lowered == "th"

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"td", "th"} and self._cell_text is not None:
            assert self._row is not None
            self._row.append(
                (
                    " ".join("".join(self._cell_text).split()),
                    self._cell_row_span,
                    self._cell_column_span,
                    self._cell_is_header,
                )
            )
            self._cell_count += 1
            self._cell_text = None
        elif lowered == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _html_span(value: str | None) -> int:
    try:
        parsed = int(value or "1")
    except ValueError:
        return 1
    normalized = max(parsed, 1)
    if normalized > _MAX_TABLE_COLUMNS:
        raise VisualParseError("visual table span exceeds the configured budget")
    return normalized


def _parse_official_html_table(
    content: str,
) -> tuple[tuple[tuple[str, int, int, bool], ...], ...]:
    if len(content) > _MAX_TABLE_CONTENT_CHARS:
        raise VisualParseError("visual table content exceeds the configured budget")
    parser = _OfficialTableHtmlParser()
    parser.feed(content)
    parser.close()
    if parser._row is not None or parser._cell_text is not None:
        raise VisualParseError("visual table contains an unterminated row or cell")
    return tuple(tuple(row) for row in parser.rows)


def admit_visual_page_result(result: VisualPageResult) -> VisualPageResult:
    """Bound untrusted visual output before canonical scientific projection."""
    if len(result.blocks) > _MAX_VISUAL_BLOCKS:
        raise VisualParseError("visual page exceeds the configured block budget")
    total_content = 0
    for block in result.blocks:
        content_size = len(block.content or "")
        if content_size > _MAX_VISUAL_BLOCK_CONTENT_CHARS:
            raise VisualParseError(
                "visual block content exceeds the configured character budget"
            )
        total_content += content_size
        if total_content > _MAX_VISUAL_TOTAL_CONTENT_CHARS:
            raise VisualParseError(
                "visual page content exceeds the configured character budget"
            )
    return result


def project_visual_page_result(
    *,
    width: object,
    height: object,
    raw_blocks: object,
) -> VisualPageResult:
    """Project bounded HTTP or official in-process blocks into the visual port."""

    page_width = _positive_int(width, "width")
    page_height = _positive_int(height, "height")
    if (
        not isinstance(raw_blocks, Iterable)
        or isinstance(raw_blocks, (str, bytes, bytearray, dict))
    ):
        raise VisualParseError("PaddleOCR-VL omitted parsing_res_list")
    if isinstance(raw_blocks, Sized) and len(raw_blocks) > _MAX_VISUAL_BLOCKS:
        raise VisualParseError("visual page exceeds the configured block budget")

    blocks: list[VisualPageBlock] = []
    total_content = 0
    for index, raw in enumerate(raw_blocks):
        if index >= _MAX_VISUAL_BLOCKS:
            raise VisualParseError("visual page exceeds the configured block budget")
        if not _is_visual_block(raw):
            raise VisualParseError("PaddleOCR-VL returned a malformed block")
        raw_content = _visual_block_field(raw, "block_content")
        content = (
            (str(raw_content).strip() or None) if raw_content is not None else None
        )
        content_size = len(content or "")
        if content_size > _MAX_VISUAL_BLOCK_CONTENT_CHARS:
            raise VisualParseError(
                "visual block content exceeds the configured character budget"
            )
        total_content += content_size
        if total_content > _MAX_VISUAL_TOTAL_CONTENT_CHARS:
            raise VisualParseError(
                "visual page content exceeds the configured character budget"
            )
        blocks.append(
            VisualPageBlock(
                label=str(_visual_block_field(raw, "block_label") or "text")
                .strip()
                .lower(),
                content=content,
                bbox=_visual_bbox(
                    _visual_block_field(raw, "block_bbox"),
                    page_width,
                    page_height,
                ),
                order=_non_negative_int(
                    _visual_block_field(raw, "block_order"), index
                ),
            )
        )
    return VisualPageResult(page_width, page_height, tuple(blocks))


def _is_visual_block(item: object) -> bool:
    get = getattr(item, "get", None)
    return isinstance(item, dict) or callable(get) or any(
        hasattr(item, attribute) for attribute in _BLOCK_ATTRIBUTE_NAMES.values()
    )


def _visual_block_field(item: object, name: str) -> object:
    if isinstance(item, dict):
        return item.get(name)
    get = getattr(item, "get", None)
    if callable(get):
        return get(name)
    return getattr(item, _BLOCK_ATTRIBUTE_NAMES[name], None)


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
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > _MAX_VISUAL_PAGE_DIMENSION
    ):
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
    "LOCAL_PADDLE_ENGINE_IDENTITY",
    "admit_visual_page_result",
    "HybridScientificDocumentParser",
    "native_engine_identity",
    "PaddleOcrVlClient",
    "project_visual_page_result",
    "VisualPageBlock",
    "VisualPageParserPort",
    "VisualPageResult",
    "VisualParseError",
]
