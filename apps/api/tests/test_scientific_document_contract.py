"""Contract tests for canonical scientific-document schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentFigure,
    DocumentFormula,
    DocumentLocator,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseInput,
    DocumentParseProfile,
    DocumentParseQuality,
    DocumentTable,
    DocumentTableCell,
    ParserBackend,
    ScientificDataExtractionCandidate,
    TextSpan,
    compute_scientific_document_schema_hash,
)

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64
_HASH_C = "sha256:" + "c" * 64
_HASH_D = "sha256:" + "d" * 64


def _profile() -> DocumentParseProfile:
    return DocumentParseProfile(
        parser_profile_id="p1",
        parser_profile_version="1.1.0",
        native_backend="native-engine==1.0.0",
        routing_policy_id="native-only",
        resource_policy_id="cpu-capable",
        configuration_hash=_HASH_C,
    )


def _block(
    block_id: str = "b1",
    *,
    page_index: int = 0,
    kind: DocumentBlockKind = DocumentBlockKind.paragraph,
    bbox: DocumentBBox | None = None,
    quality: DocumentParseQuality = DocumentParseQuality.accepted,
    reading_order: int | None = 0,
) -> DocumentBlock:
    return DocumentBlock(
        block_id=block_id,
        page_index=page_index,
        reading_order=reading_order,
        kind=kind,
        bbox=bbox,
        text="hello" if quality != DocumentParseQuality.unsupported else None,
        quality=quality,
        parser_backend=ParserBackend.native,
        parser_profile_id="p1",
    )


def _candidate(
    *,
    pages: tuple[DocumentPage, ...] = (),
    blocks: tuple[DocumentBlock, ...] = (),
    tables: tuple[DocumentTable, ...] = (),
    formulas: tuple[DocumentFormula, ...] = (),
    figures: tuple[DocumentFigure, ...] = (),
    quality: DocumentParseQuality = DocumentParseQuality.unsupported,
) -> DocumentParseCandidate:
    return DocumentParseCandidate(
        parse_id="parse_1",
        research_input_id="ri1",
        content_hash=_HASH_B,
        profile=_profile(),
        native_engine="native-engine==1.0.0",
        native_engine_version="1.0.0",
        config_hash=_HASH_C,
        canonical_output_hash=_HASH_D,
        pages=pages,
        blocks=blocks,
        tables=tables,
        formulas=formulas,
        figures=figures,
        overall_quality=quality,
        created_at="2026-08-07T00:00:00Z",
    )


def test_bbox_rejects_unordered_rect() -> None:
    with pytest.raises(ValidationError):
        DocumentBBox(x1=10, y1=10, x2=5, y2=20)


def test_parse_profile_uses_policy_identity_fields_only() -> None:
    assert {"routing_policy_id", "resource_policy_id"} <= set(
        DocumentParseProfile.model_fields
    )
    assert "routing_policy_version" not in DocumentParseProfile.model_fields
    assert "resource_policy_version" not in DocumentParseProfile.model_fields


def test_visual_provenance_must_match_profile_and_be_complete() -> None:
    base = _candidate().model_dump(mode="json")
    base["profile"]["visual_backend"] = "visual-engine"
    with pytest.raises(ValidationError, match="visual_engine presence"):
        DocumentParseCandidate.model_validate(base)

    base["visual_engine"] = "visual-engine"
    with pytest.raises(ValidationError, match="present together"):
        DocumentParseCandidate.model_validate(base)

    base["visual_engine_version"] = "3.6.0"
    base["visual_model_id"] = "PaddlePaddle/PaddleOCR-VL-1.6"
    with pytest.raises(ValidationError, match="present together"):
        DocumentParseCandidate.model_validate(base)

    base["visual_model_revision"] = "cdc88f5feff0e4079e75863205053a68358e52f7"
    candidate = DocumentParseCandidate.model_validate(base)
    assert candidate.profile.visual_backend == candidate.visual_engine


def test_bbox_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        DocumentBBox(x1=-1, y1=0, x2=5, y2=5)


def test_text_span_is_ordered() -> None:
    assert TextSpan(start=0, end=3).end == 3
    with pytest.raises(ValidationError):
        TextSpan(start=4, end=3)


def test_locator_hierarchy_is_fail_closed() -> None:
    loc = DocumentLocator(page_index=0, block_id="b1", table_id="t1", cell_id="c1")
    assert loc.cell_id == "c1"
    assert loc.bbox is None
    with pytest.raises(ValidationError):
        DocumentLocator(page_index=0, cell_id="c1")
    with pytest.raises(ValidationError):
        DocumentLocator(page_index=0, text_span=TextSpan(start=0, end=1))


def test_quality_values() -> None:
    assert {quality.value for quality in DocumentParseQuality} == {
        "accepted",
        "partial",
        "unsupported",
    }


def test_block_kind_coverage() -> None:
    assert {kind.value for kind in DocumentBlockKind} == {
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


def test_table_supports_merged_cells_without_placeholder_cells() -> None:
    header = DocumentTableCell(
        cell_id="header",
        row_index=0,
        column_index=0,
        column_span=2,
        is_header=True,
        text="Host Star",
        quality=DocumentParseQuality.accepted,
    )
    left = DocumentTableCell(
        cell_id="left",
        row_index=1,
        column_index=0,
        text="TOI-99",
        quality=DocumentParseQuality.accepted,
    )
    right = DocumentTableCell(
        cell_id="right",
        row_index=1,
        column_index=1,
        text="5600",
        quality=DocumentParseQuality.accepted,
    )
    table = DocumentTable(
        table_id="t1",
        page_index=0,
        block_id="tb",
        row_count=2,
        column_count=2,
        rows=((header,), (left, right)),
        quality=DocumentParseQuality.accepted,
    )
    assert table.rows[0][0].column_span == 2


def test_table_rejects_declared_row_count_mismatch() -> None:
    cell = DocumentTableCell(
        cell_id="c1",
        row_index=0,
        column_index=0,
        quality=DocumentParseQuality.accepted,
    )
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=2,
            column_count=1,
            rows=((cell,),),
            quality=DocumentParseQuality.accepted,
        )


def test_table_rejects_span_out_of_range_and_overlap() -> None:
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=1,
            column_count=1,
            rows=(
                (
                    DocumentTableCell(
                        cell_id="c1",
                        row_index=0,
                        column_index=0,
                        column_span=2,
                        quality=DocumentParseQuality.accepted,
                    ),
                ),
            ),
            quality=DocumentParseQuality.accepted,
        )

    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t2",
            page_index=0,
            row_count=2,
            column_count=1,
            rows=(
                (
                    DocumentTableCell(
                        cell_id="span",
                        row_index=0,
                        column_index=0,
                        row_span=2,
                        quality=DocumentParseQuality.accepted,
                    ),
                ),
                (
                    DocumentTableCell(
                        cell_id="overlap",
                        row_index=1,
                        column_index=0,
                        quality=DocumentParseQuality.accepted,
                    ),
                ),
            ),
            quality=DocumentParseQuality.accepted,
        )


def test_table_rejects_duplicate_cell_id() -> None:
    with pytest.raises(ValidationError):
        DocumentTable(
            table_id="t1",
            page_index=0,
            row_count=1,
            column_count=2,
            rows=(
                (
                    DocumentTableCell(
                        cell_id="dup",
                        row_index=0,
                        column_index=0,
                        quality=DocumentParseQuality.accepted,
                    ),
                    DocumentTableCell(
                        cell_id="dup",
                        row_index=0,
                        column_index=1,
                        quality=DocumentParseQuality.accepted,
                    ),
                ),
            ),
            quality=DocumentParseQuality.accepted,
        )


def test_unsupported_formula_and_figure_reject_recognized_payload() -> None:
    with pytest.raises(ValidationError):
        DocumentFormula(
            block_id="f1",
            page_index=0,
            raw_text="fabricated",
            quality=DocumentParseQuality.unsupported,
            parser_backend=ParserBackend.visual,
            parser_profile_id="p1",
        )
    with pytest.raises(ValidationError):
        DocumentFigure(
            block_id="fig1",
            page_index=0,
            caption="fabricated",
            quality=DocumentParseQuality.unsupported,
            parser_backend=ParserBackend.visual,
            parser_profile_id="p1",
        )


def test_candidate_rejects_duplicate_page_and_block_ids() -> None:
    page = DocumentPage(page_index=0, width_points=100, height_points=100)
    with pytest.raises(ValidationError):
        _candidate(pages=(page, page))

    block = _block()
    page_with_block = DocumentPage(
        page_index=0,
        width_points=100,
        height_points=100,
        block_ids=("b1", "b1"),
    )
    with pytest.raises(ValidationError):
        _candidate(
            pages=(page_with_block,),
            blocks=(block,),
            quality=DocumentParseQuality.accepted,
        )


def test_candidate_requires_every_block_in_exactly_one_page_membership() -> None:
    block = _block()
    page = DocumentPage(page_index=0, width_points=100, height_points=100)
    with pytest.raises(ValidationError):
        _candidate(
            pages=(page,),
            blocks=(block,),
            quality=DocumentParseQuality.accepted,
        )


def test_candidate_rejects_bbox_outside_page_for_block_and_cell() -> None:
    block = _block(
        bbox=DocumentBBox(x1=0, y1=0, x2=101, y2=10),
    )
    page = DocumentPage(
        page_index=0,
        width_points=100,
        height_points=100,
        block_ids=(block.block_id,),
    )
    with pytest.raises(ValidationError):
        _candidate(
            pages=(page,), blocks=(block,), quality=DocumentParseQuality.accepted
        )

    table_block = _block("tb", kind=DocumentBlockKind.table)
    table_page = DocumentPage(
        page_index=0,
        width_points=100,
        height_points=100,
        block_ids=("tb",),
    )
    table = DocumentTable(
        table_id="t1",
        page_index=0,
        block_id="tb",
        row_count=1,
        column_count=1,
        rows=(
            (
                DocumentTableCell(
                    cell_id="c1",
                    row_index=0,
                    column_index=0,
                    bbox=DocumentBBox(x1=0, y1=0, x2=120, y2=10),
                    quality=DocumentParseQuality.accepted,
                ),
            ),
        ),
        quality=DocumentParseQuality.accepted,
    )
    with pytest.raises(ValidationError):
        _candidate(
            pages=(table_page,),
            blocks=(table_block,),
            tables=(table,),
            quality=DocumentParseQuality.accepted,
        )


def test_candidate_rejects_duplicate_table_and_wrong_formula_figure_kind() -> None:
    table_block = _block("tb", kind=DocumentBlockKind.table)
    page = DocumentPage(
        page_index=0,
        width_points=100,
        height_points=100,
        block_ids=("tb",),
    )
    table = DocumentTable(
        table_id="t1",
        page_index=0,
        block_id="tb",
        row_count=1,
        column_count=1,
        rows=((),),
        quality=DocumentParseQuality.partial,
    )
    with pytest.raises(ValidationError):
        _candidate(
            pages=(page,),
            blocks=(table_block,),
            tables=(table, table),
            quality=DocumentParseQuality.accepted,
        )

    paragraph = _block("x", kind=DocumentBlockKind.paragraph)
    paragraph_page = DocumentPage(
        page_index=0,
        width_points=100,
        height_points=100,
        block_ids=("x",),
    )
    formula = DocumentFormula(
        block_id="x",
        page_index=0,
        raw_text="P^2",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="p1",
    )
    with pytest.raises(ValidationError):
        _candidate(
            pages=(paragraph_page,),
            blocks=(paragraph,),
            formulas=(formula,),
            quality=DocumentParseQuality.accepted,
        )


def test_candidate_rejects_identity_profile_drift() -> None:
    with pytest.raises(ValidationError):
        DocumentParseCandidate(
            parse_id="parse_1",
            research_input_id="ri1",
            content_hash=_HASH_B,
            profile=_profile(),
            native_engine="different-native-engine",
            native_engine_version="1.0.0",
            config_hash=_HASH_C,
            canonical_output_hash=_HASH_D,
            overall_quality=DocumentParseQuality.unsupported,
            created_at="2026-08-07T00:00:00Z",
        )

    with pytest.raises(ValidationError):
        DocumentParseCandidate(
            parse_id="parse_1",
            research_input_id="ri1",
            content_hash=_HASH_B,
            profile=_profile(),
            native_engine="native-engine==1.0.0",
            native_engine_version="1.0.0",
            config_hash=_HASH_A,
            canonical_output_hash=_HASH_D,
            overall_quality=DocumentParseQuality.unsupported,
            created_at="2026-08-07T00:00:00Z",
        )


def test_candidate_rejects_accepted_without_usable_blocks() -> None:
    with pytest.raises(ValidationError):
        _candidate(quality=DocumentParseQuality.accepted)


def test_scientific_extraction_candidate_is_raw_and_locator_only() -> None:
    forbidden = {
        "canonical_field",
        "canonical_unit",
        "normalized_value",
        "accepted_scientific_value",
        "quality_score_as_scientific_truth",
        "dataset_publication_status",
        "page_index",
        "block_id",
        "bbox",
        "table_id",
        "cell_id",
    }
    assert forbidden & set(ScientificDataExtractionCandidate.model_fields) == set()

    candidate = ScientificDataExtractionCandidate(
        candidate_id="sc1",
        raw_value="2.1",
        raw_unit="d",
        raw_text="period 2.1 d",
        field_hint="planet.period",
        object_hint="exoplanet_candidate",
        research_input_id="ri1",
        research_input_content_hash="sha256:" + "1" * 64,
        pipeline_source_snapshot_id="snapshot.pipeline.1",
        pipeline_source_snapshot_content_hash="sha256:" + "2" * 64,
        persisted_source_snapshot_id="00000000-0000-0000-0000-000000000001",
        document_parse_id="parse_1",
        parse_quality=DocumentParseQuality.accepted,
        locator=DocumentLocator(page_index=0, block_id="b1"),
        created_at="2026-08-07T00:00:00Z",
    )
    assert candidate.locator.block_id == "b1"


def test_schema_hash_is_stable_and_versioned() -> None:
    first = compute_scientific_document_schema_hash()
    second = compute_scientific_document_schema_hash()
    assert first == second
    assert first.startswith("sha256:")


def test_input_requires_hash_source_type_and_mime() -> None:
    with pytest.raises(ValidationError):
        DocumentParseInput(
            research_input_id="ri1",
            content_hash="not-a-hash",
            source_type="upload",
            mime_type="application/pdf",
        )
    assert DocumentParseInput.model_fields["source_type"].is_required()
    assert DocumentParseInput.model_fields["mime_type"].is_required()


def test_canonical_schema_imports_are_vendor_free() -> None:
    import ast
    import inspect

    import app.schemas.scientific_document as module

    tree = ast.parse(inspect.getsource(module))
    forbidden_roots = {"docling_parse", "paddleocr", "paddle", "mineru", "grobid"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert (
                not {alias.name.split(".", 1)[0] for alias in node.names}
                & forbidden_roots
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".", 1)[0] not in forbidden_roots
