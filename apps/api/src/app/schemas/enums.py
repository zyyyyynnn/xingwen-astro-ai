"""Scientific pipeline enums shared by current domain contracts."""

from __future__ import annotations

from enum import StrEnum


class SourceMode(StrEnum):
    """Actual origin of an ArtifactVersion-compatible pipeline payload."""

    fixture = "fixture"
    recorded = "recorded"
    live = "live"
    cached = "cached"


class PaperDataLevel(StrEnum):
    """Scientific data level, kept separate from ``source_mode``."""

    live_result = "live_result"
    real_run_cache = "real_run_cache"
    fixture = "fixture"
    recorded_response = "recorded_response"
    benchmark = "benchmark"
    manual_review = "manual_review"


class PaperSourceExecutionStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class ProducerExecutionStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class UpstreamFailureClass(StrEnum):
    timeout = "timeout"
    rate_limited = "rate_limited"
    transport = "transport"
    upstream_server = "upstream_server"
    upstream_client = "upstream_client"
    invalid_response = "invalid_response"
    policy_violation = "policy_violation"


class ClaimType(StrEnum):
    goal = "goal"
    method = "method"
    dataset = "dataset"
    finding = "finding"
    limitation = "limitation"
    future_work = "future_work"


class LiteratureRelationType(StrEnum):
    supports = "supports"
    extends = "extends"
    derived_from = "derived_from"
    limits = "limits"
    contradicts = "contradicts"
    uses_same_dataset = "uses_same_dataset"
    compares_method = "compares_method"


class EvidenceType(StrEnum):
    database_query = "database_query"
    paper_search = "paper_search"
    paper_metadata = "paper_metadata"
    paper_text = "paper_text"
    model_extraction = "model_extraction"
    reasoning_trace = "reasoning_trace"
    user_feedback = "user_feedback"
    cache_record = "cache_record"


class GraphNodeType(StrEnum):
    research_goal = "research_goal"
    dataset = "dataset"
    field = "field"
    source = "source"
    paper = "paper"
    finding = "finding"
    claim = "claim"
    relation = "relation"
    reasoning_trace = "reasoning_trace"
    evidence = "evidence"


class GraphEdgeType(StrEnum):
    uses_dataset = "uses_dataset"
    provides_field = "provides_field"
    supports_finding = "supports_finding"
    cites = "cites"
    derived_from = "derived_from"
    supports = "supports"
    extends = "extends"
    limits = "limits"
    contradicts = "contradicts"
    uses_same_dataset = "uses_same_dataset"
    compares_method = "compares_method"
    corrected_by_feedback = "corrected_by_feedback"
