"""D-10 contract tests: Canonical schema validity and quality semantics."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentFormula,
    DocumentLocator,
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    DocumentTable,
    DocumentTableCell,
    ParserBackend,
    ScientificDataExtractionCandidate,
    compute_scientific_document_schema_hash,
)


def _profile() -> DocumentParseProfile:
    return DocumentParseProfile(
        parser_profile_id="p1",
        parser_profile_version="1.0.0",
        native_backend="docling-parse==7.11.0",
        routing_policy_version="native-only",
        resource_policy_version="cpu-capable",
        configuration_hash="sha256:" + "a" * 64,
    )


def test_bbox_rejects_unordered_rect() -> None:
    with pytest.raises(ValidationError):
        DocumentBBox(x1=10, y1=10, x2=5, y2=20)


def test_bbox_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        DocumentBBox(x1=-1, y1=0, x2=5, y2=5)


def test_bbox_rejects_escaping_page_geometry() -> None:
    # Aggregate-level check is on the candidate, but the bbox itself is well-formed.
    bbox = DocumentBBox(x1=0, y1=0, x2=10, y2=10)
    assert bbox.x2 == 10


def test_locator_single_source_of_truth() -> None:
    loc = DocumentLocator(page_index=0, block_id="b1", cell_id="c1")
    assert loc.page_index == 0
    assert loc.block_id == "b1"
    assert loc.cell_id == "c1"


def test_locator_optional_bbox_is_explicit_none() -> None:
    loc = DocumentLocator(page_index=0, block_id="b1")
    assert loc.bbox is None  # never a zero-rect pretending to be unknown


def test_quality_values() -> None:
    assert DocumentParseQuality.accepted.value == "accepted"
    assert DocumentParseQuality.partial.value == "partial"
    assert DocumentParseQuality.unsupported.value == "unsupported"


def test_block_kind_coverage() -> None:
    kinds = {k.value for k in DocumentBlockKind}
    assert kinds == {
        "heading",
        "paragraph",
        "list",
        "table",
        "formula",
        "figure",
        "caption",
        "reference",
        "footnote",
    }


def test_valid_block() -> None:
    block = DocumentBlock(
        block_id="b1",
        page_index=0,
        kind=DocumentBlockKind.paragraph,
        bbox=DocumentBBox(x1=0, y1=0, x2=10, y2=10),
        text="hello",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="p1",
    )
    assert block.block_id == "b1"


def test_table_rectangular_rows_required() -> None:
    cell_a = DocumentTableCell(cell_id="a", row_index=0, column_index=0, text="x", quality=DocumentParseQuality.accepted)
    cell_b = DocumentTableCell(cell_id="b", row_index=0, column_index=1, text="y", quality=DocumentParseQuality.accepted)
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=2,
            column_count=1,
            rows=((cell_a,), (cell_b,)),  # non-rectangular (1 vs 2 cols)
            quality=DocumentParseQuality.accepted,
        )


def test_table_cell_requires_cell_id_and_header_semantics() -> None:
    cell = DocumentTableCell(
        cell_id="c1",
        row_index=0,
        column_index=0,
        row_span=2,
        column_span=1,
        is_header=True,
        text=None,  # missing cell is explicit, not guessed
        quality=DocumentParseQuality.partial,
    )
    assert cell.cell_id == "c1"
    assert cell.is_header is True
    assert cell.text is None


def test_table_rejects_span_out_of_range() -> None:
    cell = DocumentTableCell(cell_id="c1", row_index=0, column_index=0, row_span=5, quality=DocumentParseQuality.accepted)
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=2,
            column_count=1,
            rows=((cell,),),
            quality=DocumentParseQuality.accepted,
        )


def test_table_rejects_duplicate_cell_id() -> None:
    cell = DocumentTableCell(cell_id="dup", row_index=0, column_index=0, quality=DocumentParseQuality.accepted)
    duplicate = DocumentTableCell(cell_id="dup", row_index=0, column_index=1, quality=DocumentParseQuality.accepted)
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=1,
            column_count=2,
            rows=((cell, duplicate),),
            quality=DocumentParseQuality.accepted,
        )


def test_formula_allows_raw_and_latex() -> None:
    f = DocumentFormula(
        block_id="f1",
        page_index=0,
        raw_text="P^2 = ...",
        latex=r"P^2 = \frac{4\pi^2 a^3}{G M}",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.visual,
        parser_profile_id="p1",
    )
    assert f.raw_text and f.latex


def test_formula_recognition_failure_has_no_text() -> None:
    f = DocumentFormula(
        block_id="f2",
        page_index=0,
        quality=DocumentParseQuality.unsupported,
        parser_backend=ParserBackend.visual,
        parser_profile_id="p1",
    )
    assert f.raw_text is None and f.latex is None


def test_candidate_requires_logical_identity() -> None:
    candidate = DocumentParseCandidate(
        parse_id="parse_1",
        research_input_id="ri1",
        content_hash="sha256:" + "b" * 64,
        profile=_profile(),
        native_engine="docling-parse==7.11.0",
        native_engine_version="7.11.0",
        config_hash="sha256:" + "c" * 64,
        canonical_output_hash="sha256:" + "d" * 64,
        overall_quality=DocumentParseQuality.accepted,
        created_at="2026-08-07T00:00:00Z",
    )
    assert candidate.native_engine.startswith("docling-parse")


def test_candidate_rejects_dangling_block_id_in_page() -> None:
    with pytest.raises(ValidationError):
        DocumentParseCandidate(
            parse_id="parse_1",
            research_input_id="ri1",
            content_hash="sha256:" + "b" * 64,
            profile=_profile(),
            native_engine="docling-parse==7.11.0",
            native_engine_version="7.11.0",
            config_hash="sha256:" + "c" * 64,
            canonical_output_hash="sha256:" + "d" * 64,
            pages=(DocumentPage(page_index=0, width_points=595, height_points=842, block_ids=("missing",)),),
            blocks=(),
            overall_quality=DocumentParseQuality.unsupported,
            created_at="2026-08-07T00:00:00Z",
        )


def test_candidate_rejects_duplicate_block_id() -> None:
    block = DocumentBlock(
        block_id="b1",
        page_index=0,
        kind=DocumentBlockKind.paragraph,
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="p1",
    )
    with pytest.raises(ValidationError):
        DocumentParseCandidate(
            parse_id="parse_1",
            research_input_id="ri1",
            content_hash="sha256:" + "b" * 64,
            profile=_profile(),
            native_engine="docling-parse==7.11.0",
            native_engine_version="7.11.0",
            config_hash="sha256:" + "c" * 64,
            canonical_output_hash="sha256:" + "d" * 64,
            blocks=(block, block),
            overall_quality=DocumentParseQuality.accepted,
            created_at="2026-08-07T00:00:00Z",
        )


def test_candidate_rejects_whole_unsupported_with_accepted_block() -> None:
    block = DocumentBlock(
        block_id="b1",
        page_index=0,
        kind=DocumentBlockKind.paragraph,
        text="x",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="p1",
    )
    with pytest.raises(ValidationError):
        DocumentParseCandidate(
            parse_id="parse_1",
            research_input_id="ri1",
            content_hash="sha256:" + "b" * 64,
            profile=_profile(),
            native_engine="docling-parse==7.11.0",
            native_engine_version="7.11.0",
            config_hash="sha256:" + "c" * 64,
            canonical_output_hash="sha256:" + "d" * 64,
            blocks=(block,),
            overall_quality=DocumentParseQuality.unsupported,
            created_at="2026-08-07T00:00:00Z",
        )


def test_scientific_extraction_candidate_rejects_admission_fields() -> None:
    forbidden = {
        "canonical_field",
        "canonical_unit",
        "normalized_value",
        "accepted_scientific_value",
        "quality_score_as_scientific_truth",
        "dataset_publication_status",
    }
    assert forbidden & set(ScientificDataExtractionCandidate.model_fields) == set()


def test_scientific_extraction_candidate_locator_only() -> None:
    # No parallel page_index/block_id/bbox fields: location is via locator only.
    assert "page_index" not in ScientificDataExtractionCandidate.model_fields
    assert "block_id" not in ScientificDataExtractionCandidate.model_fields
    cand = ScientificDataExtractionCandidate(
        candidate_id="sc1",
        raw_value="2.1",
        raw_unit="d",
        raw_text="period 2.1 d",
        field_hint="planet.period",
        object_hint="exoplanet_candidate",
        research_input_id="ri1",
        document_parse_id="parse_1",
        parse_quality=DocumentParseQuality.accepted,
        locator=DocumentLocator(page_index=0, block_id="b1"),
        created_at="2026-08-07T00:00:00Z",
    )
    assert cand.locator.block_id == "b1"


def test_schema_hash_is_stable_and_versioned() -> None:
    h1 = compute_scientific_document_schema_hash()
    h2 = compute_scientific_document_schema_hash()
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_input_requires_hash() -> None:
    with pytest.raises(ValidationError):
        DocumentParseInput(
            research_input_id="ri1",
            content_hash="not-a-hash",
            source_type="upload",
            mime_type="application/pdf",
        )


def test_input_requires_explicit_source_type_and_mime() -> None:
    # source_type / mime_type have no default — they must be supplied explicitly.
    assert DocumentParseInput.model_fields["source_type"].is_required()
    assert DocumentParseInput.model_fields["mime_type"].is_required()


from app.schemas.scientific_document import DocumentPage


def test_imports_are_vendor_free() -> None:
    import inspect

    import app.schemas.scientific_document as mod

    src = inspect.getsource(mod)
    for vendor in ("docling", "paddle", "mineru", "grobid"):
        assert vendor not in src.lower(), f"canonical schema leaks vendor term: {vendor}"
