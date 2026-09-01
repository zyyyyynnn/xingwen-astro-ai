from __future__ import annotations

from hashlib import sha256
import io
from pathlib import Path

from PIL import Image

from app.schemas.scientific_document import (
    DocumentBlockKind,
    DocumentParseInput,
    DocumentParseQuality,
    ParserBackend,
)
from app.services.scientific_document.hybrid_parser import (
    HybridScientificDocumentParser,
    VisualPageBlock,
    VisualPageResult,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "services" / "scientific_document" / "fixtures"


class _VisualParser:
    engine_identity = "test visual parser"
    engine_version = "1.6"
    model_id = "PaddleOCR-VL-1.6-0.9B"
    model_revision = "test-revision"
    runtime_binding_hash = "sha256:" + "f" * 64

    def parse_page(self, image_bytes: bytes) -> VisualPageResult:
        assert image_bytes.startswith(b"\x89PNG")
        return VisualPageResult(
            width_pixels=595,
            height_pixels=842,
            blocks=(
                VisualPageBlock("doc_title", "扫描论文", (20, 20, 400, 60), 0),
                VisualPageBlock(
                    "table",
                    "| 波段 | 通量 |\n| --- | --- |\n| g | 1.2 |",
                    (20, 100, 400, 260),
                    1,
                ),
                VisualPageBlock("formula", "F = ma", (20, 300, 180, 350), 2),
                VisualPageBlock("image", "图 1：光变曲线", (20, 380, 500, 700), 3),
            ),
        )


def _input(name: str) -> DocumentParseInput:
    content = (FIXTURES / name).read_bytes()
    return DocumentParseInput(
        research_input_id=f"input-{name}",
        content_hash=f"sha256:{sha256(content).hexdigest()}",
        source_type="upload",
        mime_type="application/pdf",
        filename=name,
        input_bytes=content,
    )


def test_scanned_page_routes_to_visual_parser_and_preserves_structure() -> None:
    parsed = HybridScientificDocumentParser(
        visual_parser=_VisualParser()
    ).parse_document(_input("golden_scanned_like.pdf"))

    assert parsed.overall_quality is DocumentParseQuality.accepted
    assert {block.kind for block in parsed.blocks} >= {
        DocumentBlockKind.heading,
        DocumentBlockKind.table,
        DocumentBlockKind.formula,
        DocumentBlockKind.figure,
    }
    assert all(block.parser_backend is ParserBackend.visual for block in parsed.blocks)
    assert [page.page_index for page in parsed.pages] == [0]
    assert all(block.page_index == 0 for block in parsed.blocks)
    assert parsed.tables[0].rows[1][1].text == "1.2"
    assert parsed.formulas[0].latex == "F = ma"
    assert parsed.figures[0].caption == "图 1：光变曲线"


def test_unavailable_visual_parser_does_not_claim_scanned_content() -> None:
    parsed = HybridScientificDocumentParser().parse_document(
        _input("golden_scanned_like.pdf")
    )

    assert parsed.overall_quality is DocumentParseQuality.unsupported
    assert parsed.blocks == ()


def test_born_digital_structured_page_routes_to_visual_canonicalization() -> None:
    parsed = HybridScientificDocumentParser(
        visual_parser=_VisualParser()
    ).parse_document(_input("golden_complex_table.pdf"))

    assert parsed.tables
    assert parsed.formulas
    assert parsed.figures
    assert all(block.parser_backend is ParserBackend.visual for block in parsed.blocks)


def test_document_image_uses_the_same_canonical_visual_contract() -> None:
    output = io.BytesIO()
    Image.new("RGB", (595, 842), color="white").save(output, format="PNG")
    content = output.getvalue()
    parsed = HybridScientificDocumentParser(
        visual_parser=_VisualParser()
    ).parse_document(
        DocumentParseInput(
            research_input_id="input-document-image",
            content_hash=f"sha256:{sha256(content).hexdigest()}",
            source_type="upload",
            mime_type="image/png",
            filename="document.png",
            input_bytes=content,
        )
    )

    assert parsed.overall_quality is DocumentParseQuality.accepted
    assert len(parsed.pages) == 1
    assert parsed.tables[0].rows[1][1].text == "1.2"
    assert parsed.formulas[0].latex == "F = ma"
    assert parsed.figures[0].caption == "图 1：光变曲线"
