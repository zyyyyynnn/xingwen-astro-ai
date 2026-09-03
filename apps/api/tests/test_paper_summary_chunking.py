"""Evidence-preserving chunking and deterministic section reduction."""

from __future__ import annotations

import pytest

from services.paper_pipeline.summary_chunks import (
    SEVEN_SECTIONS,
    ChunkDocumentBlock,
    ChunkSectionExtraction,
    SectionStatement,
    build_summary_chunks,
    missing_section_keys,
    reduce_chunk_sections,
)


def _block(
    block_id: str,
    page: int,
    text: str,
    *,
    section: str | None = None,
    order: int | None = None,
) -> ChunkDocumentBlock:
    return ChunkDocumentBlock(
        block_id=block_id,
        page_index=page,
        text=text,
        section=section,
        reading_order=order,
    )


def test_chunks_preserve_document_order_across_pages():
    blocks = [
        _block("b3", 1, "third", order=2),
        _block("b1", 0, "first", order=0),
        _block("b2", 0, "second", order=1),
    ]
    chunks = build_summary_chunks(blocks, {})
    assert len(chunks) == 1
    assert chunks[0].block_ids == ("b1", "b2", "b3")
    assert chunks[0].text == "first\n\nsecond\n\nthird"


def test_short_adjacent_sections_share_a_bounded_chunk():
    blocks = [
        _block("b1", 0, "intro text", section="Introduction", order=0),
        _block("b2", 0, "method text one", section="Method", order=1),
        _block("b3", 0, "method text two", section="Method", order=2),
    ]
    chunks = build_summary_chunks(blocks, {})
    assert len(chunks) == 1
    assert chunks[0].section_hint == "Introduction / Method"
    assert chunks[0].block_ids == ("b1", "b2", "b3")


def test_character_budget_bounds_mixed_section_chunks():
    filler = "x" * 600
    blocks = [
        _block("b1", 0, filler, section="One", order=0),
        _block("b2", 0, filler, section="One", order=1),
        _block("b3", 0, filler, section="Two", order=2),
    ]
    chunks = build_summary_chunks(
        blocks, {}, max_chunk_characters=1_000, max_chunk_blocks=512
    )
    assert len(chunks) == 3
    assert all(len(chunk.text) <= 1_000 for chunk in chunks)


def test_block_budget_limits_chunk_size():
    blocks = [_block(f"b{i}", 0, f"text {i}", section=None, order=i) for i in range(9)]
    chunks = build_summary_chunks(blocks, {}, max_chunk_blocks=2)
    assert len(chunks) == 5
    assert all(len(chunk.block_ids) <= 2 for chunk in chunks)


def test_character_budget_includes_separators():
    chunks = build_summary_chunks(
        [_block("a", 0, "a" * 500), _block("b", 0, "b" * 500)],
        {},
        max_chunk_characters=1_000,
    )
    assert all(len(chunk.text) <= 1_000 for chunk in chunks)


def test_oversized_block_must_be_split_at_the_evidence_boundary():
    with pytest.raises(ValueError, match="evidence"):
        build_summary_chunks(
            [_block("a", 0, "x" * 1_001)], {}, max_chunk_characters=1_000
        )


def test_evidence_ids_flow_from_blocks_deduplicated():
    blocks = [
        _block("b1", 0, "alpha", section="One", order=0),
        _block("b2", 0, "beta", section="One", order=1),
        _block("b3", 0, "gamma", section="Two", order=2),
    ]
    mapping = {"b1": "evidence.a", "b2": "evidence.a", "b3": "evidence.b"}
    chunks = build_summary_chunks(blocks, mapping)
    assert len(chunks) == 1
    assert chunks[0].evidence_ids == ("evidence.a", "evidence.b")


def test_blocks_without_evidence_produce_empty_evidence_chunk():
    blocks = [_block("b1", 0, "alpha")]
    chunks = build_summary_chunks(blocks, {})
    assert chunks[0].evidence_ids == ()


def test_chunk_ids_are_internal_stable_identities():
    blocks = [_block(f"b{i}", 0, f"text {i}") for i in range(5)]
    chunks = build_summary_chunks(blocks, {}, max_chunk_blocks=2)
    assert [chunk.chunk_id for chunk in chunks] == [
        "chunk.0001",
        "chunk.0002",
        "chunk.0003",
    ]
    assert [chunk.order for chunk in chunks] == [1, 2, 3]


def test_duplicate_block_ids_are_rejected():
    blocks = [_block("b1", 0, "a"), _block("b1", 1, "b")]
    with pytest.raises(ValueError, match="duplicate block_id"):
        build_summary_chunks(blocks, {})


def test_empty_documents_are_rejected():
    with pytest.raises(ValueError, match="at least one block"):
        build_summary_chunks([], {})


def test_chunk_budget_is_enforced():
    blocks = [_block(f"b{i}", 0, f"text {i}", section=f"S{i}") for i in range(5)]
    with pytest.raises(ValueError, match="chunk budget"):
        build_summary_chunks(blocks, {}, max_chunks=2, max_chunk_blocks=1)


def test_reduction_merges_statements_in_chunk_order():
    first = ChunkSectionExtraction(
        chunk_id="chunk.0001",
        chunk_evidence_ids=("e1",),
        sections={
            "background": (SectionStatement(text="first claim", evidence_ids=("e1",)),)
        },
    )
    second = ChunkSectionExtraction(
        chunk_id="chunk.0002",
        chunk_evidence_ids=("e2", "e3"),
        sections={
            "background": (
                SectionStatement(text="second claim", evidence_ids=("e2",)),
            ),
            "methodology": (
                SectionStatement(text="method claim", evidence_ids=("e3",)),
            ),
        },
    )
    reduced = reduce_chunk_sections((second, first))
    by_section = {item.section: item for item in reduced}
    assert tuple(item.text for item in by_section["background"].statements) == (
        "first claim",
        "second claim",
    )
    assert tuple(item.text for item in by_section["methodology"].statements) == (
        "method claim",
    )
    assert set(by_section) == set(SEVEN_SECTIONS)


def test_reduction_refuses_invented_evidence_ids():
    extraction = ChunkSectionExtraction(
        chunk_id="chunk.0001",
        chunk_evidence_ids=("e1",),
        sections={
            "background": (SectionStatement(text="claim", evidence_ids=("e9",)),)
        },
    )
    with pytest.raises(ValueError, match="outside its chunk"):
        reduce_chunk_sections((extraction,))


def test_reduction_refuses_empty_statements():
    extraction = ChunkSectionExtraction(
        chunk_id="chunk.0001",
        chunk_evidence_ids=("e1",),
        sections={
            "background": (SectionStatement(text="   ", evidence_ids=()),),
        },
    )
    with pytest.raises(ValueError, match="empty statement"):
        reduce_chunk_sections((extraction,))


def test_missing_sections_are_reported_not_fabricated():
    chunk_one = ChunkSectionExtraction(
        chunk_id="chunk.0001",
        chunk_evidence_ids=("e1",),
        sections={
            "background": (
                SectionStatement(text="only background", evidence_ids=("e1",)),
            )
        },
    )
    empty_second = ChunkSectionExtraction(chunk_id="chunk.0002", sections={})
    reduced = reduce_chunk_sections((chunk_one, empty_second))
    missing = missing_section_keys(reduced)
    assert "background" not in missing
    assert set(missing) == set(SEVEN_SECTIONS) - {"background"}


def test_long_paper_multichunk_round_trip():
    blocks = []
    for index in range(60):
        blocks.append(
            _block(
                f"b{index:03d}",
                index // 10,
                f"paragraph {index} " + "y" * 120,
                section=f"Section {index // 10}",
                order=index % 10,
            )
        )
    evidence = {block.block_id: f"evidence.{block.block_id}" for block in blocks}
    chunks = build_summary_chunks(
        blocks, evidence, max_chunk_characters=2_000, max_chunk_blocks=10
    )
    assert len(chunks) >= 6
    assert [chunk.order for chunk in chunks] == list(range(1, len(chunks) + 1))
    all_evidence = [item for chunk in chunks for item in chunk.evidence_ids]
    assert len(all_evidence) == 60
    extractions = tuple(
        ChunkSectionExtraction(
            chunk_id=chunk.chunk_id,
            chunk_evidence_ids=chunk.evidence_ids,
            sections={
                "background": (
                    SectionStatement(
                        text=f"claim from {chunk.chunk_id}",
                        evidence_ids=chunk.evidence_ids[:1],
                    ),
                ),
            },
        )
        for chunk in chunks
    )
    reduced = reduce_chunk_sections(extractions)
    background = next(item for item in reduced if item.section == "background")
    assert len(background.statements) == len(chunks)
    assert "background" not in missing_section_keys(reduced)
