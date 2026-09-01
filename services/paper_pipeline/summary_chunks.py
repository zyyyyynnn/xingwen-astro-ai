"""Bounded document-order chunks and Evidence-preserving section reduction.

Adjacent sections can share a chunk: section metadata belongs to the source
blocks, not to a mandatory model-call boundary. The narrow input projection
keeps the pipeline independent of parser internals.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

SEVEN_SECTIONS = (
    "background",
    "methodology",
    "dataset",
    "experiments",
    "discussion",
    "limitations",
    "research_questions",
)

DEFAULT_MAX_CHUNK_CHARACTERS = 12_000
DEFAULT_MAX_CHUNK_BLOCKS = 256
DEFAULT_MAX_CHUNKS = 200


@dataclass(frozen=True, slots=True)
class ChunkDocumentBlock:
    """Narrow stable projection of a parsed document block."""

    block_id: str
    page_index: int
    text: str
    section: str | None = None
    reading_order: int | None = None


@dataclass(frozen=True, slots=True)
class SummaryChunk:
    chunk_id: str
    order: int
    section_hint: str
    block_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class SectionStatement:
    text: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChunkSectionExtraction:
    """Model output for one chunk, already validated against chunk evidence."""

    chunk_id: str
    chunk_evidence_ids: tuple[str, ...] = ()
    sections: Mapping[str, tuple[SectionStatement, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReducedSection:
    section: str
    statements: tuple[SectionStatement, ...]


def _block_sort_key(block: ChunkDocumentBlock) -> tuple[int, int, str]:
    return (
        block.page_index,
        block.reading_order if block.reading_order is not None else 0,
        block.block_id,
    )


def build_summary_chunks(
    blocks: Sequence[ChunkDocumentBlock],
    evidence_by_block: Mapping[str, str],
    *,
    max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    max_chunk_blocks: int = DEFAULT_MAX_CHUNK_BLOCKS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> tuple[SummaryChunk, ...]:
    """Construct ordered section-aware chunks from document blocks.

    Adjacent sections share available capacity within the character and block
    budgets. Every contributing block keeps its Evidence identity, and the
    section hint records each represented section in document order.
    """

    if not 1_000 <= max_chunk_characters <= 64_000:
        raise ValueError("max_chunk_characters must be between 1000 and 64000")
    if not 1 <= max_chunk_blocks <= 512:
        raise ValueError("max_chunk_blocks must be between 1 and 512")
    if not 1 <= max_chunks <= 1_000:
        raise ValueError("max_chunks must be between 1 and 1000")

    seen: set[str] = set()
    ordered: list[ChunkDocumentBlock] = []
    for block in sorted(blocks, key=_block_sort_key):
        if not block.block_id or not block.text.strip():
            raise ValueError("every block requires a block_id and non-empty text")
        if block.block_id in seen:
            raise ValueError(f"duplicate block_id: {block.block_id}")
        seen.add(block.block_id)
        if len(block.text.strip()) > max_chunk_characters:
            raise ValueError(
                "oversized block must be split into bounded evidence excerpts before chunking"
            )
        ordered.append(block)

    if not ordered:
        raise ValueError("summary chunking requires at least one block")

    chunks: list[SummaryChunk] = []
    current_blocks: list[ChunkDocumentBlock] = []
    current_characters = 0
    current_section: str | None = None
    current_sections: list[str] = []

    def flush() -> None:
        nonlocal current_blocks, current_characters, current_sections
        if not current_blocks:
            return
        if len(chunks) >= max_chunks:
            raise ValueError(
                f"document exceeds the {max_chunks} chunk budget; increase limits"
            )
        block_ids = tuple(block.block_id for block in current_blocks)
        evidence_ids = tuple(
            dict.fromkeys(
                evidence_by_block[block_id]
                for block_id in block_ids
                if block_id in evidence_by_block
            )
        )
        chunks.append(
            SummaryChunk(
                chunk_id=f"chunk.{len(chunks) + 1:04d}",
                order=len(chunks) + 1,
                section_hint=" / ".join(current_sections),
                block_ids=block_ids,
                evidence_ids=evidence_ids,
                text="\n\n".join(block.text.strip() for block in current_blocks),
            )
        )
        current_blocks = []
        current_characters = 0
        current_sections = []

    for block in ordered:
        if block.section is not None:
            current_section = block.section
        size = len(block.text.strip())
        if (
            current_blocks and current_characters + 2 + size > max_chunk_characters
        ) or len(current_blocks) >= max_chunk_blocks:
            flush()
        section = current_section or "document"
        if section not in current_sections:
            current_sections.append(section)
        current_characters += size + (2 if current_blocks else 0)
        current_blocks.append(block)
    flush()
    return tuple(chunks)


def reduce_chunk_sections(
    extractions: Sequence[ChunkSectionExtraction],
) -> tuple[ReducedSection, ...]:
    """Deterministically merge per-chunk extractions into seven sections.

    Statements keep chunk order then statement order.  Every statement's
    evidence ids must belong to that chunk's own evidence set; the reducer
    refuses to invent or silently drop evidence identity.
    """

    merged: dict[str, list[SectionStatement]] = {
        section: [] for section in SEVEN_SECTIONS
    }
    for extraction in sorted(extractions, key=lambda item: item.chunk_id):
        allowed = set(extraction.chunk_evidence_ids)
        for section in SEVEN_SECTIONS:
            for statement in extraction.sections.get(section, ()):
                if not statement.text.strip():
                    raise ValueError(
                        f"{extraction.chunk_id} produced an empty statement"
                    )
                unknown = set(statement.evidence_ids) - allowed
                if unknown:
                    raise ValueError(
                        f"{extraction.chunk_id} references evidence ids outside"
                        f" its chunk: {sorted(unknown)}"
                    )
                merged[section].append(statement)

    return tuple(
        ReducedSection(section=section, statements=tuple(statements))
        for section, statements in merged.items()
    )


def missing_section_keys(
    reduced: Sequence[ReducedSection],
) -> tuple[str, ...]:
    """Sections without any supported statements, reported honestly."""

    return tuple(section.section for section in reduced if not section.statements)


__all__ = [
    "ChunkDocumentBlock",
    "ChunkSectionExtraction",
    "ReducedSection",
    "SEVEN_SECTIONS",
    "SectionStatement",
    "SummaryChunk",
    "build_summary_chunks",
    "missing_section_keys",
    "reduce_chunk_sections",
]
