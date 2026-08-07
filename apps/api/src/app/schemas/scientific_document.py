"""Canonical Scientific Document Parsing contract (D-10).

Single authoritative Pydantic authoring source for the Scientific Document
Parsing boundary frozen by #190 D-10. This module defines Xingwen's own
Canonical Domain for parsed scientific documents; it intentionally contains no
vendor type, vendor config type, or third-party parser import.

Scope (D-10, not D-11/D-12):
- Canonical contract, quality semantics, locator, table/formula/figure.
- Logical identity requirements for later persistence (B-20).
- ``ScientificDataExtractionCandidate`` as a raw extraction candidate only;
  canonical mapping/unit normalization/scientific admission remain in C.

Coordinate system (authoritative, single source of truth):
- origin: top-left corner of the page, ``(0, 0)``;
- x increases left to right; y increases top to bottom;
- units: absolute PDF points (1 point = 1/72 inch), page-relative;
- NOT normalized. Unknown geometry is ``None``, never a zero rectangle.
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

SCIENTIFIC_DOCUMENT_SCHEMA_VERSION = "1.1.0"

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
    """Parser admission quality, never scientific truth."""

    accepted = "accepted"
    partial = "partial"
    unsupported = "unsupported"


class DocumentBlockKind(StrEnum):
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
    """Vendor-neutral origin of a canonical parsed element."""

    native = "native"
    visual = "visual"


class DocumentBBox(BaseModel):
    """Axis-aligned bounding box in absolute, page-relative PDF points."""

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
    """Half-open character span ``[start, end)`` within canonical block text."""

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
    """Single-source-of-truth locator for Evidence provenance."""

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
    """One canonical document block with stable identity and location."""

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
    """One anchored table cell; spans occupy a rectangular logical grid."""

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
    """Canonical table grid represented by anchor cells grouped by start row.

    ``rows`` contains one tuple per logical row. Each inner tuple contains cells
    whose ``row_index`` equals that row; ``column_index`` is the cell's anchor
    column and may skip positions occupied by earlier spans. This supports merged
    cells without inventing placeholder cells.
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

                for r in range(cell.row_index, cell.row_index + cell.row_span):
                    for c in range(
                        cell.column_index, cell.column_index + cell.column_span
                    ):
                        coordinate = (r, c)
                        if coordinate in occupied:
                            raise ValueError(
                                f"cell {cell.cell_id} overlaps another cell at {coordinate}"
                            )
                        occupied.add(coordinate)
        return self


class DocumentFormula(BaseModel):
    """Canonical formula; recognition failure is never auto-completed."""

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
            raise ValueError("unsupported formula must not carry recognized formula text")
        return self


class DocumentFigure(BaseModel):
    """Phase-1 figure text/caption only; no scientific pixel measurement."""

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
            raise ValueError("unsupported figure must not carry recognized textual content")
        return self


class DocumentParseProfile(BaseModel):
    """Versioned parser/profile/config identity used by deterministic parsing."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseProfile")

    parser_profile_id: Identifier
    parser_profile_version: NonEmptyString
    native_backend: NonEmptyString
    visual_backend: NonEmptyString | None = None
    routing_policy_version: NonEmptyString
    resource_policy_version: NonEmptyString
    configuration_hash: ContentHash


class DocumentParseInput(BaseModel):
    """Single parser input boundary; source and MIME are explicit, never guessed."""

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseInput")

    research_input_id: Identifier
    content_hash: ContentHash
    source_type: NonEmptyString
    mime_type: NonEmptyString
    filename: NonEmptyString | None = None
    input_bytes: bytes | None = None


class _ReferentialIntegrityError(ValueError):
    pass


def _check_bbox_in_page(
    bbox: DocumentBBox, page: DocumentPage, where: str
) -> None:
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
        raise _ReferentialIntegrityError(f"{label} references unknown block_id {block_id}")
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
    if candidate.visual_engine is not None and candidate.visual_engine != profile_visual:
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
        raise _ReferentialIntegrityError("visual model provenance requires visual_engine")


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
    if candidate.overall_quality == DocumentParseQuality.accepted and not candidate.blocks:
        raise _ReferentialIntegrityError("accepted document parse must contain usable blocks")
    if candidate.overall_quality == DocumentParseQuality.unsupported:
        if any(
            block.quality == DocumentParseQuality.accepted
            for block in candidate.blocks
        ):
            raise _ReferentialIntegrityError(
                "whole-document unsupported but contains accepted blocks"
            )
    for table in candidate.tables:
        if table.quality == DocumentParseQuality.unsupported and table.rows:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} unsupported but carries structured rows"
            )


class DocumentParseCandidate(BaseModel):
    """Top-level canonical output and deterministic parse identity."""

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
    def validate_aggregate(self) -> Self:
        _check_identity_consistency(self)
        _check_referential_integrity(self)
        _check_quality_invariants(self)
        return self


class ScientificDataExtractionCandidate(BaseModel):
    """Raw observed scientific-value candidate; never a scientific admission."""

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
    source_snapshot_id: Identifier | None = None
    document_parse_id: Identifier | None = None
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
                "ScientificDataExtractionCandidate must not carry scientific "
                f"admission fields: {sorted(present)}"
            )
        return self


def compute_scientific_document_schema_hash() -> str:
    """Deterministic fingerprint of the exported D-10 Pydantic schemas."""
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
    return compute_canonical_payload_hash(
        {
            "schema_version": SCIENTIFIC_DOCUMENT_SCHEMA_VERSION,
            "models": schemas,
        }
    )


__all__ = [
    "SCIENTIFIC_DOCUMENT_SCHEMA_VERSION",
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
