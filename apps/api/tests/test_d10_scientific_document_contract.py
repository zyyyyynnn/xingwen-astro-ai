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
    cell = DocumentTableCell(row_index=0, column_index=0, text="x", quality=DocumentParseQuality.accepted)
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            rows=((cell,), (cell, cell)),  # non-rectangular
            quality=DocumentParseQuality.accepted,
        )


def test_table_cell_span_and_no_fabrication() -> None:
    cell = DocumentTableCell(
        row_index=0,
        column_index=0,
        row_span=2,
        column_span=1,
        text=None,  # missing cell is explicit, not guessed
        quality=DocumentParseQuality.partial,
    )
    assert cell.text is None


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


def test_scientific_extraction_candidate_rejects_admission_fields() -> None:
    # The model definition omits admission fields; if a future edit adds them,
    # the validator fails closed. We assert the model has no such fields today.
    forbidden = {
        "canonical_field",
        "canonical_unit",
        "normalized_value",
        "accepted_scientific_value",
        "quality_score_as_scientific_truth",
        "dataset_publication_status",
    }
    assert forbidden & set(ScientificDataExtractionCandidate.model_fields) == set()


def test_scientific_extraction_candidate_valid() -> None:
    cand = ScientificDataExtractionCandidate(
        candidate_id="sc1",
        raw_value="2.1",
        raw_unit="d",
        raw_text="period 2.1 d",
        field_hint="planet.period",
        object_hint="exoplanet_candidate",
        research_input_id="ri1",
        document_parse_id="parse_1",
        page_index=0,
        block_id="b1",
        parse_quality=DocumentParseQuality.accepted,
        locator=DocumentLocator(page_index=0, block_id="b1"),
        created_at="2026-08-07T00:00:00Z",
    )
    assert cand.raw_value == "2.1"


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
