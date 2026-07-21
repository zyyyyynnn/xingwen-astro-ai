"""Deterministic ranking, representative selection, and exclusion reasons."""

from __future__ import annotations

import re

from app.schemas.paper_collection import PaperCollectionCandidate

from .canonicalize import CandidateDraft
from .constants import RANKING_VERSION, SELECTION_VERSION
from .dedupe import DedupeResult


_WORD = re.compile(r"[\w]+", re.UNICODE)


def rank_and_select(
    candidates: tuple[CandidateDraft, ...],
    dedupe: DedupeResult,
    *,
    normalized_keywords: tuple[str, ...],
    normalized_query: str,
    year_from: int,
    year_to: int,
    selection_limit: int,
) -> tuple[PaperCollectionCandidate, ...]:
    scores = {
        candidate.candidate_id: _relevance_score(
            candidate,
            normalized_keywords=normalized_keywords,
            normalized_query=normalized_query,
            year_from=year_from,
            year_to=year_to,
        )
        for candidate in candidates
    }
    rank_keys = {
        candidate.candidate_id: _rank_key(candidate, scores[candidate.candidate_id])
        for candidate in candidates
    }
    candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}

    representatives: list[str] = []
    for group in dedupe.groups:
        representatives.append(min(group.candidate_ids, key=lambda item: rank_keys[item]))
    representatives.sort(key=lambda item: rank_keys[item])
    selected_representatives = set(representatives[:selection_limit])
    representative_by_group = {
        dedupe.candidate_info[candidate_id].duplicate_group_id: candidate_id
        for candidate_id in representatives
    }

    ranked: list[PaperCollectionCandidate] = []
    for candidate_id in sorted(candidate_by_id, key=lambda item: rank_keys[item]):
        candidate = candidate_by_id[candidate_id]
        info = dedupe.candidate_info[candidate_id]
        representative_id = representative_by_group[info.duplicate_group_id]
        selected = candidate_id in selected_representatives
        if selected:
            selection_reason = "highest ranked representative within selection limit"
            exclusion_reason = None
        elif candidate_id != representative_id:
            selection_reason = None
            exclusion_reason = f"duplicate of higher-ranked candidate {representative_id}"
        else:
            selection_reason = None
            exclusion_reason = "selection limit reached after deterministic ranking"
        ranked.append(
            PaperCollectionCandidate(
                candidate_id=candidate.candidate_id,
                raw=candidate.raw,
                canonical_paper_id=info.canonical_paper_id,
                canonical_identity_basis=candidate.canonical_identity_basis,
                title=candidate.title,
                normalized_title=candidate.normalized_title,
                authors=candidate.authors,
                normalized_authors=candidate.normalized_authors,
                year=candidate.year,
                doi=candidate.doi,
                arxiv_id=candidate.arxiv_id,
                url=candidate.url,
                duplicate_group_id=info.duplicate_group_id,
                dedupe_evidence=info.evidence,
                conflicts=info.conflicts,
                relevance_score=scores[candidate_id],
                ranking_key=rank_keys[candidate_id],
                selected=selected,
                selection_reason=selection_reason,
                exclusion_reason=exclusion_reason,
                ranking_rule_version=RANKING_VERSION,
                selection_rule_version=SELECTION_VERSION,
            )
        )
    return tuple(ranked)


def _relevance_score(
    candidate: CandidateDraft,
    *,
    normalized_keywords: tuple[str, ...],
    normalized_query: str,
    year_from: int,
    year_to: int,
) -> float:
    title = candidate.normalized_title
    phrase_hits = sum(keyword in title for keyword in normalized_keywords)
    phrase_score = phrase_hits / len(normalized_keywords)
    query_tokens = set(_WORD.findall(normalized_query))
    title_tokens = set(_WORD.findall(title))
    token_score = len(query_tokens & title_tokens) / len(query_tokens) if query_tokens else 0.0
    identifier_score = 1.0 if candidate.doi or candidate.arxiv_id else 0.0
    year_score = (
        1.0
        if candidate.year is not None and year_from <= candidate.year <= year_to
        else 0.0
    )
    return round(
        min(1.0, 0.55 * phrase_score + 0.25 * token_score + 0.1 * identifier_score + 0.1 * year_score),
        6,
    )


def _rank_key(candidate: CandidateDraft, score: float) -> str:
    inverse_score = 1.0 - score
    year = candidate.year if candidate.year is not None else 9999
    return (
        f"{inverse_score:0.6f}|{candidate.normalized_title}|{year:04d}|"
        f"{candidate.canonical_paper_id}|{candidate.candidate_id}"
    )
