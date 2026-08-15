"""Source-independent and source-specific query normalization."""

from __future__ import annotations

import math
import re
import unicodedata

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import PaperSearchScope
from app.schemas.paper_benchmark import BenchmarkSearchScenario
from app.schemas.paper_collection import NormalizedPaperQuery, PaperQueryPagination

from .constants import QUERY_NORMALIZATION_VERSION


_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip().casefold()


def normalize_benchmark_query(
    scenario: BenchmarkSearchScenario,
    *,
    source_ids: tuple[str, ...],
    page_size: int,
) -> NormalizedPaperQuery:
    if page_size < 1 or page_size > 100:
        raise ValueError("page_size must be between one and 100")
    normalized_source_ids = tuple(sorted(set(source_ids)))
    if not normalized_source_ids:
        raise ValueError("at least one source is required")
    unknown = set(normalized_source_ids) - set(scenario.source_ids)
    if unknown:
        raise ValueError(f"scenario does not permit sources: {sorted(unknown)}")

    normalized_keywords = tuple(
        sorted({normalize_text(keyword) for keyword in scenario.query.keywords})
    )
    normalized_query = normalize_text(scenario.query.query_string)
    max_pages = max(1, math.ceil(scenario.candidate_limit / page_size))
    pagination = PaperQueryPagination(
        page_size=page_size,
        max_pages=max_pages,
        candidate_limit=scenario.candidate_limit,
    )
    source_parameters: dict[str, dict[str, str | int]] = {}
    for source_id in normalized_source_ids:
        if source_id == "crossref":
            source_parameters[source_id] = {
                "query.bibliographic": normalized_query,
                "filter": (
                    f"from-pub-date:{scenario.query.year_from}-01-01,"
                    f"until-pub-date:{scenario.query.year_to}-12-31"
                ),
                "sort": "relevance",
                "order": "desc",
                "select": "DOI,title,author,published,published-print,published-online,URL,resource,alternative-id",
            }
        else:
            source_parameters[source_id] = {
                "query": normalized_query,
                "year_from": scenario.query.year_from,
                "year_to": scenario.query.year_to,
            }

    hash_payload = {
        "normalization_rule_version": QUERY_NORMALIZATION_VERSION,
        "normalized_keywords": normalized_keywords,
        "normalized_query_string": normalized_query,
        "year_from": scenario.query.year_from,
        "year_to": scenario.query.year_to,
        "source_ids": normalized_source_ids,
        "source_parameters": source_parameters,
        "pagination": pagination.model_dump(mode="json"),
        "sort_strategy": "source_relevance_then_canonical_tie_breaker",
    }
    query_hash = compute_canonical_payload_hash(hash_payload)
    return NormalizedPaperQuery(
        query_id=f"query.{query_hash.removeprefix('sha256:')[:24]}",
        normalization_rule_version=QUERY_NORMALIZATION_VERSION,
        original_keywords=scenario.query.keywords,
        normalized_keywords=normalized_keywords,
        original_query_string=scenario.query.query_string,
        normalized_query_string=normalized_query,
        year_from=scenario.query.year_from,
        year_to=scenario.query.year_to,
        source_ids=normalized_source_ids,
        source_parameters=source_parameters,
        pagination=pagination,
        sort_strategy="source_relevance_then_canonical_tie_breaker",
        query_hash=query_hash,
    )


def normalize_contract_query(
    scope: PaperSearchScope,
    *,
    research_goal: str,
    available_source_ids: tuple[str, ...],
    page_size: int | None = None,
) -> NormalizedPaperQuery:
    """Normalize one production paper search from the immutable Contract.

    The benchmark normalizer deliberately consumes a frozen scenario.  This
    sibling keeps the same hash and Crossref parameter rules while taking its
    search intent from ``ResearchContract.paper_search_scope``.  It does not
    read benchmark files or manufacture a benchmark scenario.
    """

    normalized_available = tuple(sorted(set(available_source_ids)))
    if not normalized_available:
        raise ValueError("at least one paper source adapter is required")
    requested_sources = tuple(sorted(set(scope.source_ids)))
    if not requested_sources:
        raise ValueError("paper search scope requires at least one source_id")
    unknown_sources = set(requested_sources) - set(normalized_available)
    if unknown_sources:
        raise ValueError(
            "paper search source adapter is not configured: "
            + ", ".join(sorted(unknown_sources))
        )
    source_ids = requested_sources

    original_keywords = scope.keywords or (research_goal,)
    original_query = " ".join(original_keywords).strip() or research_goal.strip()
    normalized_keywords = tuple(
        sorted({normalize_text(keyword) for keyword in original_keywords if keyword})
    )
    normalized_query = normalize_text(original_query)
    if not normalized_keywords or not normalized_query:
        raise ValueError("paper search scope must contain a non-empty query")

    year_from = scope.year_from if scope.year_from is not None else 1900
    year_to = scope.year_to if scope.year_to is not None else 2100
    if year_from < 1900 or year_to > 2100:
        raise ValueError("production paper search years must be between 1900 and 2100")
    if year_from > year_to:
        raise ValueError("paper search year_from must not exceed year_to")

    effective_page_size = page_size if page_size is not None else min(20, scope.max_candidates)
    if effective_page_size < 1 or effective_page_size > 100:
        raise ValueError("page_size must be between one and 100")
    max_pages = max(1, math.ceil(scope.max_candidates / effective_page_size))
    pagination = PaperQueryPagination(
        page_size=effective_page_size,
        max_pages=max_pages,
        candidate_limit=scope.max_candidates,
    )
    source_parameters: dict[str, dict[str, str | int]] = {}
    for source_id in source_ids:
        if source_id == "crossref":
            source_parameters[source_id] = {
                "query.bibliographic": normalized_query,
                "filter": (
                    f"from-pub-date:{year_from}-01-01,"
                    f"until-pub-date:{year_to}-12-31"
                ),
                "sort": "relevance",
                "order": "desc",
                "select": "DOI,title,author,published,published-print,published-online,URL,resource,alternative-id",
            }
        else:
            source_parameters[source_id] = {
                "query": normalized_query,
                "year_from": year_from,
                "year_to": year_to,
            }

    hash_payload = {
        "normalization_rule_version": QUERY_NORMALIZATION_VERSION,
        "normalized_keywords": normalized_keywords,
        "normalized_query_string": normalized_query,
        "year_from": year_from,
        "year_to": year_to,
        "source_ids": source_ids,
        "source_parameters": source_parameters,
        "pagination": pagination.model_dump(mode="json"),
        "sort_strategy": "source_relevance_then_canonical_tie_breaker",
    }
    query_hash = compute_canonical_payload_hash(hash_payload)
    return NormalizedPaperQuery(
        query_id=f"query.{query_hash.removeprefix('sha256:')[:24]}",
        normalization_rule_version=QUERY_NORMALIZATION_VERSION,
        original_keywords=original_keywords,
        normalized_keywords=normalized_keywords,
        original_query_string=original_query,
        normalized_query_string=normalized_query,
        year_from=year_from,
        year_to=year_to,
        source_ids=source_ids,
        source_parameters=source_parameters,
        pagination=pagination,
        sort_strategy="source_relevance_then_canonical_tie_breaker",
        query_hash=query_hash,
    )
