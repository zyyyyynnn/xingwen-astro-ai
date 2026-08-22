"""Unique mapper from confirmed ResearchContract to typed PaperSearchInput."""

from __future__ import annotations

from app.schemas.core import ResearchContract
from app.schemas.paper_collection import (
    PaperSearchInput,
    compute_paper_search_input_hash,
)

from .constants import (
    OPEN_YEAR_FROM,
    OPEN_YEAR_TO,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    SOURCE_POLICY_VERSION,
)


def build_paper_search_input(
    contract: ResearchContract,
) -> PaperSearchInput:
    """Project one confirmed ResearchContract into a typed PaperSearchInput.

    The contract's keywords and paper search scope are authoritative;
    defaults and policies are pinned deterministically to guarantee
    identity and provenance across runs.
    """
    scope = contract.paper_search_scope
    raw_keywords = tuple(
        dict.fromkeys(
            keyword.strip()
            for keyword in scope.keywords
            if keyword and keyword.strip()
        )
    )
    if not raw_keywords:
        raise ValueError("live paper search requires non-empty contract keywords")

    raw_source_ids = tuple(sorted(set(scope.source_ids)))
    if not raw_source_ids:
        raise ValueError("live paper search requires at least one source id")

    candidate_limit = scope.max_candidates
    selection_limit = scope.max_candidates
    resolved_year_from = OPEN_YEAR_FROM if scope.year_from is None else scope.year_from
    resolved_year_to = OPEN_YEAR_TO if scope.year_to is None else scope.year_to

    base_payload = {
        "schema_version": "1.0.0",
        "contract_id": contract.id,
        "contract_version": contract.version,
        "contract_content_hash": contract.content_hash,
        "keywords": raw_keywords,
        "year_from": resolved_year_from,
        "year_to": resolved_year_to,
        "source_ids": raw_source_ids,
        "candidate_limit": candidate_limit,
        "selection_limit": selection_limit,
        "stable_ordering": "source_relevance_then_canonical_tie_breaker",
        "content_scope": "bibliographic_metadata",
        "access_policy": "metadata_url_only_requires_independent_access_evidence",
        "source_policy_version": SOURCE_POLICY_VERSION,
        "producer_name": PRODUCER_NAME,
        "producer_version": PRODUCER_VERSION,
    }
    input_hash = compute_paper_search_input_hash(base_payload)
    return PaperSearchInput.model_validate({**base_payload, "input_hash": input_hash})


__all__ = [
    "build_paper_search_input",
]
