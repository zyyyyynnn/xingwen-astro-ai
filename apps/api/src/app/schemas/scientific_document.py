"""Canonical Scientific Document Parsing contract (D-10).

Single authoritative Pydantic authoring source for the Scientific Document
Parsing boundary frozen by #190 D-10. This module defines Xingwen's own
Canonical Domain for parsed scientific documents; it intentionally contains
**no vendor type, no vendor config type, and no third-party import**. The
Parser Port (``services.scientific_document.ports``) is the only place a
production adapter may later map an approved upstream result onto these
models.

Scope (D-10, not D-11/D-12):
- Canonical contract, quality semantics, locator, table/formula/figure.
- Logical identity requirements for later persistence (B-20).
- The ``ScientificDataExtractionCandidate`` extraction stub, which must NOT
  carry canonical mapping / unit normalization / scientific admission — those
  belong to the existing C Pipeline.

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

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import (
    CORE_MODEL_CONFIG,
    ContentHash,
    Identifier,
    NonEmptyString,
    UtcDateTime,
)


#: Schema version for the D-10 Scientific Document Parsing contract.
SCIENTIFIC_DOCUMENT_SCHEMA_VERSION = "1.1.0"

#: Every canonical model that participates in the D-10 contract. The schema
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
    """Vendor-neutral provenance of a parsed element.

    Records whether a block/cell/formula came from the born-digital native
    engine or the visual (OCR/VLM) engine. It never names a vendor package.
    """

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
            raise ValueError(f"text_span requires start <= end (got {self.start}, {self.end})")
        return self


class DocumentLocator(BaseModel):
    """Canonical SINGLE SOURCE OF TRUTH locator back to a parsed element.

    A locator is only complete together with the owning ``DocumentParseCandidate``
    (which carries ``research_input_id`` / input ``content_hash``). It must be
    persistable and verifiable by B-20 without re-parsing the source.

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
    explicit header/body role (D-10 C4). ``row_span``/``column_span`` express
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
    def require_rectangular_rows(self) -> Self:
        if self.rows:
            width = len(self.rows[0])
            if any(len(row) != width for row in self.rows):
                raise ValueError("table rows must be rectangular (uniform column count)")
        return self

    @model_validator(mode="after")
    def require_span_bounds_and_unique_cells(self) -> Self:
        if not self.rows:
            return self
        seen_cell_ids: set[str] = set()
        for r, row in enumerate(self.rows):
            for c, cell in enumerate(row):
                if cell.cell_id in seen_cell_ids:
                    raise ValueError(f"duplicate cell_id within table: {cell.cell_id}")
                seen_cell_ids.add(cell.cell_id)
                if cell.row_index != r or cell.column_index != c:
                    raise ValueError(
                        f"cell at grid [{r}][{c}] has inconsistent "
                        f"row_index={cell.row_index}/column_index={cell.column_index}"
                    )
                if cell.row_index + cell.row_span > self.row_count:
                    raise ValueError(
                        f"cell {cell.cell_id} row_span {cell.row_span} exceeds "
                        f"table row_count {self.row_count}"
                    )
                if cell.column_index + cell.column_span > self.column_count:
                    raise ValueError(
                        f"cell {cell.cell_id} column_span {cell.column_span} exceeds "
                        f"table column_count {self.column_count}"
                    )
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


class DocumentFigure(BaseModel):
    """One canonical figure block (caption/text only — no pixel measurement).

    Phase-1 explicitly forbids plot digitization, curve recovery, scatter-point
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


class DocumentParseProfile(BaseModel):
    """Versioned parser profile / configuration identity (D-10 logical).

    ``configuration_hash`` MUST be stable and reproducible: it must not depend
    on wall-clock time, random ordering, unsorted dicts, floating model aliases
    or machine-specific absolute paths.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="DocumentParseProfile")

    parser_profile_id: Identifier
    parser_profile_version: NonEmptyString
    native_backend: NonEmptyString
    visual_backend: NonEmptyString | None = None
    routing_policy_version: NonEmptyString
    resource_policy_version: NonEmptyString
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


def _check_referential_integrity(candidate: DocumentParseCandidate) -> None:
    """Validate cross-object references and geometry for a parse candidate.

    Fail-closed on any dangling reference, cross-page reference, duplicate id,
    or bbox that escapes its page geometry.
    """
    pages = {p.page_index: p for p in candidate.pages}
    block_ids: set[str] = set()
    for block in candidate.blocks:
        if block.block_id in block_ids:
            raise _ReferentialIntegrityError(f"duplicate block_id: {block.block_id}")
        block_ids.add(block.block_id)
        page = pages.get(block.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"block {block.block_id} references missing page_index={block.page_index}"
            )
        if block.bbox is not None:
            _check_bbox_in_page(block.bbox, page, f"block {block.block_id}")

    for page in candidate.pages:
        seen: set[str] = set()
        for bid in page.block_ids:
            if bid in seen:
                raise _ReferentialIntegrityError(
                    f"page {page.page_index} lists block_id {bid} more than once"
                )
            seen.add(bid)
            if bid not in block_ids:
                raise _ReferentialIntegrityError(
                    f"page {page.page_index} references unknown block_id {bid}"
                )
            block = next(b for b in candidate.blocks if b.block_id == bid)
            if block.page_index != page.page_index:
                raise _ReferentialIntegrityError(
                    f"block {bid} page_index {block.page_index} != "
                    f"owning page {page.page_index}"
                )

    tables = {t.table_id: t for t in candidate.tables}
    for table in candidate.tables:
        page = pages.get(table.page_index)
        if page is None:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} references missing page_index={table.page_index}"
            )
        if table.block_id is not None:
            block = next((b for b in candidate.blocks if b.block_id == table.block_id), None)
            if block is None:
                raise _ReferentialIntegrityError(
                    f"table {table.table_id} references unknown block_id {table.block_id}"
                )
            if block.kind != DocumentBlockKind.table:
                raise _ReferentialIntegrityError(
                    f"table {table.table_id} block_id {table.block_id} kind={block.kind.value}, "
                    f"expected 'table'"
                )
            if block.page_index != table.page_index:
                raise _ReferentialIntegrityError(
                    f"table {table.table_id} page_index != its block page_index"
                )

    for formula in candidate.formulas:
        _check_block_backed(formula.block_id, formula.page_index, candidate, "formula")

    for figure in candidate.figures:
        _check_block_backed(figure.block_id, figure.page_index, candidate, "figure")


def _check_block_backed(
    block_id: str,
    page_index: int,
    candidate: DocumentParseCandidate,
    kind: str,
) -> None:
    block = next((b for b in candidate.blocks if b.block_id == block_id), None)
    if block is None:
        raise _ReferentialIntegrityError(
            f"{kind} references unknown block_id {block_id}"
        )
    if block.page_index != page_index:
        raise _ReferentialIntegrityError(
            f"{kind} page_index {page_index} != block {block_id} page_index {block.page_index}"
        )


def _check_bbox_in_page(
    bbox: DocumentBBox, page: DocumentPage, where: str
) -> None:
    if bbox.x2 > page.width_points or bbox.y2 > page.height_points:
        raise _ReferentialIntegrityError(
            f"{where} bbox escapes page geometry: "
            f"bbox=({bbox.x1},{bbox.y1},{bbox.x2},{bbox.y2}) "
            f"page={page.width_points}x{page.height_points}"
        )


def _check_quality_invariants(candidate: DocumentParseCandidate) -> None:
    """Quality semantics must not be self-contradictory (D-10 C7)."""
    if candidate.overall_quality == DocumentParseQuality.unsupported:
        accepted = [
            b
            for b in candidate.blocks
            if b.quality == DocumentParseQuality.accepted
        ]
        if accepted:
            raise _ReferentialIntegrityError(
                "whole-document unsupported but contains accepted blocks"
            )
    # Unsupported regions must not carry a fabricated full normalized result.
    for table in candidate.tables:
        if table.quality == DocumentParseQuality.unsupported and table.rows:
            raise _ReferentialIntegrityError(
                f"table {table.table_id} unsupported but carries rows (fabricated)"
            )


class DocumentParseCandidate(BaseModel):
    """Top-level canonical output of one document parse.

    Logical identity (consumed by B-20): the same input + same parser/model/
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
        _check_referential_integrity(self)
        _check_quality_invariants(self)
        return self


class ScientificDataExtractionCandidate(BaseModel):
    """Stub describing one extracted scientific value observation.

    HARD BOUNDARY (D-10 / #20): this candidate describes only the *observed*
    raw value and where it came from. It MUST NOT carry canonical mapping,
    unit normalization, accepted scientific value or dataset publication
    status — those belong to the existing C Pipeline (Field Manifest → mapping
    → unit normalization → quality/admission → Dataset candidate → Publisher).

    Correct chain:
    ``ScientificDataExtractionCandidate`` → existing Field Manifest → existing
    mapping → unit normalization → quality/admission → Dataset candidate.
    Never ``OCR → final Dataset``.

    Location is expressed ONLY through ``locator`` (the single-source-of-truth
    ``DocumentLocator``). No parallel page_index/block_id/bbox/cell_id fields
    exist, so a contradictory locator is impossible.
    """

    model_config = ConfigDict(**CORE_MODEL_CONFIG, title="ScientificDataExtractionCandidate")

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
        # Defense-in-depth: the fields below are intentionally absent from the
        # model definition. If a future edit adds any of them, this validator
        # fails closed so a contract drift cannot silently grant admission.
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
    """Deterministic hash over the JSON Schema of every D-10 contract model.

    Stable for identical schema definitions; changes when any contract model's
    JSON Schema changes. This is the machine-checkable contract fingerprint
    that pairs with ``SCIENTIFIC_DOCUMENT_SCHEMA_VERSION``.
    """
    import json
    import sys

    import pydantic

    module = sys.modules[__name__]
    schemas: list[object] = []
    for name in CONTRACT_MODEL_NAMES:
        model = getattr(module, name, None)
        if model is None:
            raise RuntimeError(f"contract model missing: {name}")
        # Only Pydantic models contribute a JSON Schema; StrEnum members are
        # rendered inline wherever referenced and are not hashed standalone.
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            continue
        # Per-model schema, rendered canonically and sorted so declaration
        # order cannot change the hash.
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
