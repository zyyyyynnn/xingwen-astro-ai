"""Canonical schemas for parsed scientific documents.

This is the sole Pydantic authoring source for Xingwen's parsed-document
domain. It contains no vendor type, vendor configuration type, or third-party
import. Production adapters map approved upstream results to these models
through ``services.scientific_document.ports``.

Scope:
- Parse quality semantics, locators, tables, formulas, and figures.
- Logical identity requirements needed by persistence.
- The ``ScientificDataExtractionCandidate`` raw-observation contract, which must not
  perform canonical mapping, unit normalization, or scientific admission;
  those responsibilities belong to the data pipeline.

Coordinate system (authoritative, single source of truth):
- origin: top-left corner of the page, ``(0, 0)``.
- x axis: increases left → right.
- y axis: increases top → bottom.
- units: PDF points (1 point = 1/72 inch), absolute, page-relative.
- NOT normalized (no 0..1 ratios). A locator is meaningful only with its
  owning page's ``page_index`` and geometry.

This schema is exported by ``scripts/export_schemas.py`` and locked by CI
(``--check``). The canonical schema hash below is deterministic over the JSON
Schema of every model in this module, so a semantic schema change is
detectable through a hash/version change without a parallel mechanism.
"""

from __future__ import annotations

import json
import sys
from enum import StrEnum
from typing import Annotated, Self

import pydantic
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import (
    CORE_MODEL_CONFIG,
    ContentHash,
    Identifier,
    NonEmptyString,
    UtcDateTime,
)
from .research_input import ResearchInputType


#: Schema version for the Scientific Document Parsing contract.
SCIENTIFIC_DOCUMENT_SCHEMA_VERSION = "1.3.0"

#: ResearchInput image MIME types accepted by the canonical document parser.
SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/tiff", "image/webp"}
)


def is_supported_scientific_document_input(
    *, input_type: ResearchInputType, mime_type: str | None
) -> bool:
    """Return whether a ResearchInput type and MIME form a supported document."""

    if input_type is ResearchInputType.pdf:
        return mime_type == "application/pdf"
    if input_type is ResearchInputType.image:
        return mime_type in SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES
    return False


#: Every canonical model that participates in the Scientific Document Parsing contract. The schema
#: hash is computed over the JSON Schema of exactly these models, in this
#: order, so additions/changes are reflected deterministically.
CONTRACT_MODEL_NAMES: tuple[str, ...] = (
    "DocumentParseQuality",
    "DocumentBlockKind",
    "ParserBackend",
    "DocumentBBox",
    "TextSpan",
    "DocumentLocator",
    "DocumentPage",
    "DocumentBlock",
    "DocumentTableCell",
    "DocumentTable",
    "DocumentFormula",
    "DocumentFigure",
    "DocumentParseProfile",
    "DocumentParseInput",
    "DocumentParseCandidate",
    "ScientificDataExtractionCandidate",
)


class DocumentParseQuality(StrEnum):
    """Lifecycle quality of a parsed region / whole document.

    ``accepted`` does NOT mean a scientific fact is verified. It means the
    current parser/profile reached admission conditions for the usable region
    and it may become downstream Evidence / input.

    ``partial`` means only part of the content was reliably parsed. Downstream
    may use the clearly valid part, but MUST keep ``unparsed != absent``: a
    missing recognition must never be read as "does not exist in the paper".

    ``unsupported`` means the current parser/profile cannot reliably process
    the region. No fabricated full text may be emitted and no downstream model
    may auto-complete the gap.
    """

    accepted = "accepted"
    partial = "partial"
    unsupported = "unsupported"


class DocumentBlockKind(StrEnum):
    """Stable kind taxonomy for canonical document blocks."""

    heading = "heading"
    paragraph = "paragraph"
    list = "list"
    table = "table"
    formula = "formula"
    figure = "figure"
    caption = "caption"
    reference = "reference"
    footnote = "footnote"


class ParserBackend(StrEnum):
    """Vendor-neutral parser provenance of a parsed element."""

    native = "native"
    visual = "visual"


class DocumentBBox(BaseModel):
    """Axis-aligned bounding box in absolute PDF points.

    Coordinate system (authoritative):
    - origin: top-left corner of the page, ``(0, 0)``.
    - x axis: increases left → right.
    - y axis: increases top → bottom.
    - units: PDF points (1 point = 1/72 inch).
    - page-relative: coordinates are expressed in the page's own width/height
      space; a locator is only meaningful together with its ``page_index``.
    - normalized: **false** — these are absolute points, not 0..1 ratios.
    - valid range (enforced at the aggregate level, where page geometry is
      known): ``0 <= x1 <= x2 <= page_width`` and
      ``0 <= y1 <= y2 <= page_height``.
    - empty/unknown semantics: ``None`` (the enclosing ``DocumentLocator.bbox``
      is ``None``). A zero-rect MUST NOT be used to mean "unknown".
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentBBox")

    x1: Annotated[float, Field(ge=0.0)]
    y1: Annotated[float, Field(ge=0.0)]
    x2: Annotated[float, Field(ge=0.0)]
    y2: Annotated[float, Field(ge=0.0)]

    @model_validator(mode="after")
    def require_ordered_rect(self) -> Self:
        if self.x1 > self.x2 or self.y1 > self.y2:
            raise ValueError(
                "bbox requires x1 <= x2 and y1 <= y2 "
                f"(got x1={self.x1} x2={self.x2} y1={self.y1} y2={self.y2})"
            )
        return self


class TextSpan(BaseModel):
    """Character-offset span within a block's raw text (0-based, inclusive start)."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="TextSpan")

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def require_ordered_span(self) -> Self:
        if self.start > self.end:
            raise ValueError(
                f"text_span requires start <= end (got {self.start}, {self.end})"
            )
        return self


class DocumentLocator(BaseModel):
    """Canonical SINGLE SOURCE OF TRUTH locator back to a parsed element.

    A locator is only complete together with the owning ``DocumentParseCandidate``
    (which carries ``research_input_id`` / input ``content_hash``). It must be
    persistable and verifiable by DocumentParse Persistence without re-parsing the source.

    This is the ONLY locator representation in the contract. ``page_index``,
    ``block_id``, ``bbox``, ``table_id`` and ``cell_id`` live here and nowhere
    else; the ``ScientificDataExtractionCandidate`` references a parse solely
    through this locator, so contradictory parallel locator fields are
    impossible by construction.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentLocator")

    page_index: Annotated[int, Field(ge=0)]
    block_id: Identifier | None = None
    bbox: DocumentBBox | None = None
    reading_order: Annotated[int, Field(ge=0)] | None = None
    text_span: TextSpan | None = None
    table_id: Identifier | None = None
    cell_id: Identifier | None = None

    @model_validator(mode="after")
    def require_locator_hierarchy(self) -> Self:
        if self.cell_id is not None and self.table_id is None:
            raise ValueError("cell_id requires table_id")
        if self.text_span is not None and self.block_id is None:
            raise ValueError("text_span requires block_id")
        return self


class DocumentPage(BaseModel):
    """One parsed page identity and geometry."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentPage")

    page_index: Annotated[int, Field(ge=0)]
    width_points: Annotated[float, Field(gt=0.0)]
    height_points: Annotated[float, Field(gt=0.0)]
    block_ids: tuple[Identifier, ...] = Field(default=())


class DocumentBlock(BaseModel):
    """One canonical document block with stable identity and locating power."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentBlock")

    block_id: Identifier
    page_index: Annotated[int, Field(ge=0)]
    reading_order: Annotated[int, Field(ge=0)] | None = None
    kind: DocumentBlockKind
    bbox: DocumentBBox | None = None
    text: NonEmptyString | None = None
    quality: DocumentParseQuality
    parser_backend: ParserBackend
    parser_profile_id: Identifier


class DocumentTableCell(BaseModel):
    """One table cell with stable identity, span and (when available) text/quality.

    ``cell_id`` is the canonical, stable identity of the cell within a table; it
    is referenced by ``DocumentLocator.cell_id``. ``is_header`` carries the
    explicit header/body role. ``row_span``/``column_span`` express
    merged cells; out-of-range spans are rejected at the aggregate level.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentTableCell")

    cell_id: Identifier
    row_index: Annotated[int, Field(ge=0)]
    column_index: Annotated[int, Field(ge=0)]
    row_span: Annotated[int, Field(ge=1)] = 1
    column_span: Annotated[int, Field(ge=1)] = 1
    is_header: bool = False
    bbox: DocumentBBox | None = None
    text: NonEmptyString | None = None
    quality: DocumentParseQuality


class DocumentTable(BaseModel):
    """One canonical table; cells are addressed by [row][column].

    ``row_count``/``column_count`` are the table's logical grid dimensions;
    ``row_span``/``column_span`` on a cell MUST NOT exceed them. Every cell
    carries a unique ``cell_id`` within the table.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentTable")

    table_id: Identifier
    page_index: Annotated[int, Field(ge=0)]
    block_id: Identifier | None = None
    caption: NonEmptyString | None = None
    row_count: Annotated[int, Field(ge=1)]
    column_count: Annotated[int, Field(ge=1)]
    rows: tuple[tuple[DocumentTableCell, ...], ...] = Field(default=())
    quality: DocumentParseQuality

    @model_validator(mode="after")
    def validate_grid(self) -> Self:
        if self.rows and len(self.rows) != self.row_count:
            raise ValueError(
                f"table rows length {len(self.rows)} != row_count {self.row_count}"
            )
        if not self.rows:
            return self

        seen_ids: set[str] = set()
        occupied: set[tuple[int, int]] = set()
        for row_index, row in enumerate(self.rows):
            previous_column = -1
            for cell in row:
                if cell.cell_id in seen_ids:
                    raise ValueError(f"duplicate cell_id within table: {cell.cell_id}")
                seen_ids.add(cell.cell_id)
                if cell.row_index != row_index:
                    raise ValueError(
                        f"cell {cell.cell_id} row_index={cell.row_index} does not "
                        f"match owning rows[{row_index}]"
                    )
                if cell.column_index <= previous_column:
                    raise ValueError(
                        f"cells in row {row_index} must be ordered by unique column_index"
                    )
                previous_column = cell.column_index
                if cell.column_index >= self.column_count:
                    raise ValueError(
                        f"cell {cell.cell_id} column_index {cell.column_index} outside "
                        f"column_count {self.column_count}"
                    )
                if cell.row_index + cell.row_span > self.row_count:
                    raise ValueError(
                        f"cell {cell.cell_id} row_span {cell.row_span} exceeds "
                        f"row_count {self.row_count}"
                    )
                if cell.column_index + cell.column_span > self.column_count:
                    raise ValueError(
                        f"cell {cell.cell_id} column_span {cell.column_span} exceeds "
                        f"column_count {self.column_count}"
                    )
                for occupied_row in range(
                    cell.row_index, cell.row_index + cell.row_span
                ):
                    for occupied_column in range(
                        cell.column_index, cell.column_index + cell.column_span
                    ):
                        coordinate = (occupied_row, occupied_column)
                        if coordinate in occupied:
                            raise ValueError(
                                f"cell {cell.cell_id} overlaps another cell at {coordinate}"
                            )
                        occupied.add(coordinate)
        return self


class DocumentFormula(BaseModel):
    """One canonical formula block.

    Both a raw visible representation and a normalized/LaTeX representation may
    coexist. Recognition failure MUST NOT be auto-generated by an LLM.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentFormula")

    block_id: Identifier
    page_index: Annotated[int, Field(ge=0)]
    bbox: DocumentBBox | None = None
    raw_text: NonEmptyString | None = None
    latex: NonEmptyString | None = None
    quality: DocumentParseQuality
    parser_backend: ParserBackend
    parser_profile_id: Identifier

    @model_validator(mode="after")
    def unsupported_has_no_recognized_formula(self) -> Self:
        if self.quality == DocumentParseQuality.unsupported and (
            self.raw_text is not None or self.latex is not None
        ):
            raise ValueError(
                "unsupported formula must not carry recognized formula text"
            )
        return self


class DocumentFigure(BaseModel):
    """One canonical figure block (caption/text only — no pixel measurement).

    The parsing contract explicitly forbids plot digitization, curve recovery, scatter-point
    recovery and scientific pixel measurement. Only visible/ocr labels and
    surrounding text are captured.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentFigure")

    block_id: Identifier
    page_index: Annotated[int, Field(ge=0)]
    bbox: DocumentBBox | None = None
    caption: NonEmptyString | None = None
    title: NonEmptyString | None = None
    axis_text: NonEmptyString | None = None
    legend_text: NonEmptyString | None = None
    visible_ocr_labels: tuple[NonEmptyString, ...] = Field(default=())
    quality: DocumentParseQuality
    parser_backend: ParserBackend
    parser_profile_id: Identifier

    @model_validator(mode="after")
    def unsupported_has_no_recognized_text(self) -> Self:
        if self.quality == DocumentParseQuality.unsupported and any(
            (
                self.caption,
                self.title,
                self.axis_text,
                self.legend_text,
                self.visible_ocr_labels,
            )
        ):
            raise ValueError(
                "unsupported figure must not carry recognized textual content"
            )
        return self


class DocumentParseProfile(BaseModel):
    """Parser profile with a reproducible configuration identity.

    ``configuration_hash`` MUST be stable and reproducible: it must not depend
    on wall-clock time, random ordering, unsorted dicts, floating model aliases
    or machine-specific absolute paths.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseProfile")

    parser_profile_id: Identifier
    parser_profile_version: NonEmptyString
    native_backend: NonEmptyString
    visual_backend: NonEmptyString | None = None
    routing_policy_id: NonEmptyString
    resource_policy_id: NonEmptyString
    configuration_hash: ContentHash


class DocumentParseInput(BaseModel):
    """SINGLE input boundary handed to a parser port.

    ``input_bytes`` is carried only by benchmark/probe harnesses against legal
    fixtures; production ingestion receives the immutable content via
    ``research_input_id`` + ``content_hash`` and resolves bytes from the
    content-addressed store. ``source_type`` and ``mime_type`` MUST be supplied
    explicitly by the caller (no guessing / defaulting).
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseInput")

    research_input_id: Identifier
    content_hash: ContentHash
    source_type: NonEmptyString
    mime_type: NonEmptyString
    filename: NonEmptyString | None = None
    input_bytes: bytes | None = None


class _ReferentialIntegrityError(ValueError):
    """Sentinel error type for aggregate referential validation."""


def _check_bbox_in_page(bbox: DocumentBBox, page: DocumentPage, where: str) -> None:
    if bbox.x2 > page.width_points or bbox.y2 > page.height_points:
        raise _ReferentialIntegrityError(
            f"{where} bbox escapes page geometry: "
            f"bbox=({bbox.x1},{bbox.y1},{bbox.x2},{bbox.y2}) "
            f"page={page.width_points}x{page.height_points}"
        )


def _check_block_backed(
    *,
    block_id: str,
    page_index: int,
    candidate: DocumentParseCandidate,
    expected_kind: DocumentBlockKind,
    label: str,
) -> DocumentBlock:
    block = next((item for item in candidate.blocks if item.block_id == block_id), None)
    if block is None:
        raise _ReferentialIntegrityError(
            f"{label} references unknown block_id {block_id}"
        )
    if block.page_index != page_index:
        raise _ReferentialIntegrityError(
            f"{label} page_index {page_index} != block {block_id} page_index "
            f"{block.page_index}"
        )
    if block.kind != expected_kind:
        raise _ReferentialIntegrityError(
            f"{label} block_id {block_id} kind={block.kind.value}, expected "
            f"{expected_kind.value}"
        )
    return block


def _check_identity_consistency(candidate: DocumentParseCandidate) -> None:
    if candidate.config_hash != candidate.profile.configuration_hash:
        raise _ReferentialIntegrityError(
            "candidate config_hash must equal profile.configuration_hash"
        )
    if candidate.native_engine != candidate.profile.native_backend:
        raise _ReferentialIntegrityError(
            "candidate native_engine must equal profile.native_backend"
        )
    profile_visual = candidate.profile.visual_backend
    if (candidate.visual_engine is None) != (profile_visual is None):
        raise _ReferentialIntegrityError(
            "candidate visual_engine presence must match profile.visual_backend"
        )
    if (
        candidate.visual_engine is not None
        and candidate.visual_engine != profile_visual
    ):
        raise _ReferentialIntegrityError(
            "candidate visual_engine must equal profile.visual_backend"
        )
    if (candidate.visual_engine is None) != (candidate.visual_engine_version is None):
        raise _ReferentialIntegrityError(
            "visual_engine and visual_engine_version must be present together"
        )
    if (candidate.visual_model_id is None) != (candidate.visual_model_revision is None):
        raise _ReferentialIntegrityError(
            "visual_model_id and visual_model_revision must be present together"
        )
    if candidate.visual_model_id is not None and candidate.visual_engine is None:
        raise _ReferentialIntegrityError(
            "visual model provenance requires visual_engine"
        )


def _check_referential_integrity(candidate: DocumentParseCandidate) -> None:
    page_indices = [page.page_index for page in candidate.pages]
    if len(page_indices) != len(set(page_indices)):
        raise _ReferentialIntegrityError("duplicate page_index values are not allowed")
    pages = {page.page_index: page for page in candidate.pages}

    blocks_by_id: dict[str, DocumentBlock] = {}
    for block in candidate.blocks:
        if block.block_id in blocks_by_id:
            raise _ReferentialIntegrityError(f"duplicate block_id: {block.block_id}")
        blocks_by_id[block.block_id] = block
        page = pages.get(block.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"block {block.block_id} references missing page_index={block.page_index}"
            )
        if block.parser_profile_id != candidate.profile.parser_profile_id:
            raise _ReferentialIntegrityError(
                f"block {block.block_id} parser_profile_id does not match candidate profile"
            )
        if block.bbox is not None:
            _check_bbox_in_page(block.bbox, page, f"block {block.block_id}")

    membership: dict[str, int] = {}
    for page in candidate.pages:
        seen_on_page: set[str] = set()
        reading_orders: set[int] = set()
        for block_id in page.block_ids:
            if block_id in seen_on_page:
                raise _ReferentialIntegrityError(
                    f"page {page.page_index} lists block_id {block_id} more than once"
                )
            seen_on_page.add(block_id)
            block = blocks_by_id.get(block_id)
            if block is None:
                raise _ReferentialIntegrityError(
                    f"page {page.page_index} references unknown block_id {block_id}"
                )
            if block.page_index != page.page_index:
                raise _ReferentialIntegrityError(
                    f"block {block_id} page_index {block.page_index} != owning page "
                    f"{page.page_index}"
                )
            membership[block_id] = membership.get(block_id, 0) + 1
            if block.reading_order is not None:
                if block.reading_order in reading_orders:
                    raise _ReferentialIntegrityError(
                        f"page {page.page_index} has duplicate reading_order "
                        f"{block.reading_order}"
                    )
                reading_orders.add(block.reading_order)

    for block_id in blocks_by_id:
        if membership.get(block_id, 0) != 1:
            raise _ReferentialIntegrityError(
                f"block {block_id} must appear exactly once in its page.block_ids"
            )

    table_ids: set[str] = set()
    for table in candidate.tables:
        if table.table_id in table_ids:
            raise _ReferentialIntegrityError(f"duplicate table_id: {table.table_id}")
        table_ids.add(table.table_id)
        page = pages.get(table.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} references missing page_index={table.page_index}"
            )
        if table.block_id is None:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} must reference its canonical table block"
            )
        _check_block_backed(
            block_id=table.block_id,
            page_index=table.page_index,
            candidate=candidate,
            expected_kind=DocumentBlockKind.table,
            label=f"table {table.table_id}",
        )
        for row in table.rows:
            for cell in row:
                if cell.bbox is not None:
                    _check_bbox_in_page(
                        cell.bbox,
                        page,
                        f"table {table.table_id} cell {cell.cell_id}",
                    )

    for formula in candidate.formulas:
        page = pages.get(formula.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"formula references missing page_index={formula.page_index}"
            )
        _check_block_backed(
            block_id=formula.block_id,
            page_index=formula.page_index,
            candidate=candidate,
            expected_kind=DocumentBlockKind.formula,
            label="formula",
        )
        if formula.parser_profile_id != candidate.profile.parser_profile_id:
            raise _ReferentialIntegrityError(
                f"formula {formula.block_id} parser_profile_id does not match candidate profile"
            )
        if formula.bbox is not None:
            _check_bbox_in_page(formula.bbox, page, f"formula {formula.block_id}")

    for figure in candidate.figures:
        page = pages.get(figure.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"figure references missing page_index={figure.page_index}"
            )
        _check_block_backed(
            block_id=figure.block_id,
            page_index=figure.page_index,
            candidate=candidate,
            expected_kind=DocumentBlockKind.figure,
            label="figure",
        )
        if figure.parser_profile_id != candidate.profile.parser_profile_id:
            raise _ReferentialIntegrityError(
                f"figure {figure.block_id} parser_profile_id does not match candidate profile"
            )
        if figure.bbox is not None:
            _check_bbox_in_page(figure.bbox, page, f"figure {figure.block_id}")


def _check_quality_invariants(candidate: DocumentParseCandidate) -> None:
    """Quality semantics must not be self-contradictory."""
    if (
        candidate.overall_quality == DocumentParseQuality.accepted
        and not candidate.blocks
    ):
        raise _ReferentialIntegrityError(
            "accepted document parse must contain usable blocks"
        )
    if candidate.overall_quality == DocumentParseQuality.unsupported:
        accepted = [
            block
            for block in candidate.blocks
            if block.quality == DocumentParseQuality.accepted
        ]
        if accepted:
            raise _ReferentialIntegrityError(
                "whole-document unsupported but contains accepted blocks"
            )
    for table in candidate.tables:
        if table.quality == DocumentParseQuality.unsupported and table.rows:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} unsupported but carries rows (fabricated)"
            )


class DocumentParseCandidate(BaseModel):
    """Top-level canonical output of one document parse.

    Logical identity (consumed by DocumentParse Persistence): the same input + same parser/model/
    config MUST yield a deterministic, reusable identity; a different config or
    revision MUST yield a different identity. ``canonical_output_hash`` is the
    content-addressed hash over the frozen canonical payload.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseCandidate")

    parse_id: Identifier
    research_input_id: Identifier
    content_hash: ContentHash
    profile: DocumentParseProfile
    native_engine: NonEmptyString
    native_engine_version: NonEmptyString
    visual_engine: NonEmptyString | None = None
    visual_engine_version: NonEmptyString | None = None
    visual_model_id: NonEmptyString | None = None
    visual_model_revision: NonEmptyString | None = None
    config_hash: ContentHash
    canonical_output_hash: ContentHash
    pages: tuple[DocumentPage, ...] = Field(default=())
    blocks: tuple[DocumentBlock, ...] = Field(default=())
    tables: tuple[DocumentTable, ...] = Field(default=())
    formulas: tuple[DocumentFormula, ...] = Field(default=())
    figures: tuple[DocumentFigure, ...] = Field(default=())
    overall_quality: DocumentParseQuality
    created_at: UtcDateTime

    @model_validator(mode="after")
    def validate_referential_integrity(self) -> Self:
        _check_identity_consistency(self)
        _check_referential_integrity(self)
        _check_quality_invariants(self)
        return self


class ScientificDataExtractionCandidate(BaseModel):
    """Candidate describing one raw scientific-value observation.

    HARD BOUNDARY: this candidate describes only the *observed*
    raw value and where it came from. It MUST NOT carry canonical mapping,
    unit normalization, accepted scientific value or dataset publication
    status — those belong to the data pipeline (Field Manifest → mapping
    → unit normalization → quality/admission → Dataset candidate → Publisher).

    Correct chain:
    ``ScientificDataExtractionCandidate`` → existing Field Manifest → existing
    mapping → unit normalization → quality/admission → Dataset candidate.
    Never ``OCR → final Dataset``.

    Location is expressed ONLY through ``locator`` (the single-source-of-truth
    ``DocumentLocator``). No parallel page_index/block_id/bbox/cell_id fields
    exist, so a contradictory locator is impossible.
    """

    model_config = ConfigDict(
        **CORE_MODEL_CONFIG,
        title="ScientificDataExtractionCandidate",
    )

    candidate_id: Identifier
    raw_value: NonEmptyString | None = None
    raw_unit: NonEmptyString | None = None
    raw_text: NonEmptyString | None = None
    field_hint: Identifier | None = None
    object_hint: Identifier | None = None
    research_input_id: Identifier
    research_input_content_hash: ContentHash
    pipeline_source_snapshot_id: Identifier
    pipeline_source_snapshot_content_hash: ContentHash
    persisted_source_snapshot_id: Identifier
    document_parse_id: Identifier
    parse_quality: DocumentParseQuality
    locator: DocumentLocator
    created_at: UtcDateTime

    @model_validator(mode="after")
    def reject_scientific_admission_fields(self) -> Self:
        forbidden = {
            "canonical_field",
            "canonical_unit",
            "normalized_value",
            "accepted_scientific_value",
            "quality_score_as_scientific_truth",
            "dataset_publication_status",
        }
        present = forbidden & set(type(self).model_fields)
        if present:
            raise ValueError(
                f"ScientificDataExtractionCandidate must not carry scientific "
                f"admission fields: {sorted(present)}"
            )
        return self


def compute_scientific_document_schema_hash() -> str:
    """Deterministic hash over the JSON Schema of every Scientific Document Parsing contract model.

    Stable for identical schema definitions; changes when any contract model's
    JSON Schema changes. This is the machine-checkable contract fingerprint
    that pairs with ``SCIENTIFIC_DOCUMENT_SCHEMA_VERSION``.
    """
    module = sys.modules[__name__]
    schemas: list[object] = []
    for name in CONTRACT_MODEL_NAMES:
        model = getattr(module, name, None)
        if model is None:
            raise RuntimeError(f"contract model missing: {name}")
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        schema_json = pydantic.TypeAdapter(model).json_schema(mode="serialization")
        schemas.append(json.loads(json.dumps(schema_json, sort_keys=True)))
    schemas.sort(key=lambda schema: json.dumps(schema, sort_keys=True))
    payload = {
        "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
        "models": schemas,
    }
    return compute_canonical_payload_hash(payload)


__all__ = [
    "SCIENTIFIC_DOCUMENT_SCHEMA_VERSION",
    "SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES",
    "is_supported_scientific_document_input",
    "CONTRACT_MODEL_NAMES",
    "DocumentParseQuality",
    "DocumentBlockKind",
    "ParserBackend",
    "DocumentBBox",
    "TextSpan",
    "DocumentLocator",
    "DocumentPage",
    "DocumentBlock",
    "DocumentTableCell",
    "DocumentTable",
    "DocumentFormula",
    "DocumentFigure",
    "DocumentParseProfile",
    "DocumentParseInput",
    "DocumentParseCandidate",
    "ScientificDataExtractionCandidate",
    "compute_scientific_document_schema_hash",
]
