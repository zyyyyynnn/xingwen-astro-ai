"""Source-independent and source-specific query normalization."""

from __future__ import annotations

import math
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_benchmark import BenchmarkSearchScenario
from app.schemas.paper_collection import (
    NormalizedPaperQuery,
    PaperQueryPagination,
    PaperSearchInput,
    normalize_paper_query_text,
)

from .constants import OPEN_YEAR_FROM, OPEN_YEAR_TO, QUERY_NORMALIZATION_VERSION
from .errors import PaperSearchExecutionError


_SUPPORTED_SOURCES = frozenset({"crossref"})


def normalize_canonical_paper_query(
    *,
    raw_keywords: tuple[str, ...],
    raw_query_string: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    source_ids: tuple[str, ...],
    candidate_limit: int,
    page_size: int,
) -> NormalizedPaperQuery:
    """Canonical query normalization core for production and benchmark paths.

    Text is Unicode-normalized and whitespace-folded. Keywords are deduped
    and sorted. Unspecified publication years resolve to governed open bounds.
    Source validation is strictly closed-world: unknown sources are rejected
    deterministically without generic fallback.
    """
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between one and 100")
    if candidate_limit < 1 or candidate_limit > 100:
        raise ValueError("candidate_limit must be between one and 100")

    cleaned_keywords = tuple(
        dict.fromkeys(keyword.strip() for keyword in raw_keywords if keyword and keyword.strip())
    )
    if not cleaned_keywords:
        raise ValueError("paper search requires non-empty keywords")

    normalized_source_ids = tuple(sorted(set(source_ids)))
    if not normalized_source_ids:
        raise ValueError("at least one source is required")

    unsupported = set(normalized_source_ids) - _SUPPORTED_SOURCES
    if unsupported:
        raise PaperSearchExecutionError(
            code="PAPER_SOURCE_UNSUPPORTED",
            public_message="研究协议指定了当前论文检索不支持的来源。",
            retryable=False,
            producer_status="rejected",
        )

    normalized_keywords = tuple(
        sorted({normalize_paper_query_text(keyword) for keyword in cleaned_keywords})
    )
    original_query = (
        raw_query_string.strip()
        if raw_query_string is not None and raw_query_string.strip()
        else " ".join(cleaned_keywords)
    )
    normalized_query = normalize_paper_query_text(original_query)
    resolved_year_from = OPEN_YEAR_FROM if year_from is None else year_from
    resolved_year_to = OPEN_YEAR_TO if year_to is None else year_to
    if resolved_year_from > resolved_year_to:
        raise ValueError("query year_from must not exceed year_to")
    if resolved_year_from < OPEN_YEAR_FROM or resolved_year_to > OPEN_YEAR_TO:
        raise ValueError(
            f"query years must be between {OPEN_YEAR_FROM} and {OPEN_YEAR_TO}"
        )

    max_pages = max(1, math.ceil(candidate_limit / page_size))
    pagination = PaperQueryPagination(
        page_size=page_size,
        max_pages=max_pages,
        candidate_limit=candidate_limit,
    )
    source_parameters: dict[str, dict[str, Any]] = {
        "crossref": {
            "query.bibliographic": normalized_query,
            "filter": (
                f"from-pub-date:{resolved_year_from}-01-01,"
                f"until-pub-date:{resolved_year_to}-12-31"
            ),
            "sort": "relevance",
            "order": "desc",
            "select": "DOI,title,author,published,published-print,published-online,URL,resource,alternative-id,abstract",
        }
    }

    hash_payload = {
        "normalization_rule_version": QUERY_NORMALIZATION_VERSION,
        "normalized_keywords": normalized_keywords,
        "normalized_query_string": normalized_query,
        "year_from": resolved_year_from,
        "year_to": resolved_year_to,
        "source_ids": normalized_source_ids,
        "source_parameters": source_parameters,
        "pagination": pagination.model_dump(mode="json"),
        "sort_strategy": "source_relevance_then_canonical_tie_breaker",
    }
    query_hash = compute_canonical_payload_hash(hash_payload)
    return NormalizedPaperQuery(
        query_id=f"query.{query_hash.removeprefix('sha256:')[:24]}",
        normalization_rule_version=QUERY_NORMALIZATION_VERSION,
        original_keywords=cleaned_keywords,
        normalized_keywords=normalized_keywords,
        original_query_string=original_query,
        normalized_query_string=normalized_query,
        year_from=resolved_year_from,
        year_to=resolved_year_to,
        source_ids=normalized_source_ids,
        source_parameters=source_parameters,
        pagination=pagination,
        sort_strategy="source_relevance_then_canonical_tie_breaker",
        query_hash=query_hash,
    )


def normalize_paper_search_input(
    search_input: PaperSearchInput,
    *,
    page_size: int = 20,
) -> NormalizedPaperQuery:
    """Project one confirmed production PaperSearchInput into a normalized query."""
    return normalize_canonical_paper_query(
        raw_keywords=search_input.keywords,
        year_from=search_input.year_from,
        year_to=search_input.year_to,
        source_ids=search_input.source_ids,
        candidate_limit=search_input.candidate_limit,
        page_size=page_size,
    )


def normalize_benchmark_query(
    scenario: BenchmarkSearchScenario,
    *,
    source_ids: tuple[str, ...],
    page_size: int = 20,
) -> NormalizedPaperQuery:
    """Project one frozen BenchmarkSearchScenario into a normalized query."""
    normalized_source_ids = tuple(sorted(set(source_ids)))
    unknown = set(normalized_source_ids) - set(scenario.source_ids)
    if unknown:
        raise ValueError(f"scenario does not permit sources: {sorted(unknown)}")

    return normalize_canonical_paper_query(
        raw_keywords=scenario.query.keywords,
        raw_query_string=scenario.query.query_string,
        year_from=scenario.query.year_from,
        year_to=scenario.query.year_to,
        source_ids=normalized_source_ids,
        candidate_limit=scenario.candidate_limit,
        page_size=page_size,
    )


__all__ = [
    "normalize_benchmark_query",
    "normalize_canonical_paper_query",
    "normalize_paper_search_input",
]
