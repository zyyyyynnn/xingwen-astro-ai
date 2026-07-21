"""Enums aligned with API_CONTRACT.md section 2."""

from __future__ import annotations

from enum import StrEnum


class CaseKey(StrEnum):
    exoplanet_host_star = "exoplanet_host_star"


class TaskStatus(StrEnum):
    pending = "pending"
    planning = "planning"
    fetching_data = "fetching_data"
    cleaning_data = "cleaning_data"
    searching_papers = "searching_papers"
    summarizing_papers = "summarizing_papers"
    reasoning_literature = "reasoning_literature"
    building_graph = "building_graph"
    completed = "completed"
    revising = "revising"
    failed = "failed"


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class SourceType(StrEnum):
    database = "database"
    paper_source = "paper_source"
    paper = "paper"
    cache = "cache"
    manual_review = "manual_review"


class SourceMode(StrEnum):
    """Actual origin of an ArtifactVersion-compatible pipeline payload."""

    fixture = "fixture"
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


class PaperAcquisitionStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cached = "cached"


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
    corrected_by_feedback = "corrected_by_feedback"
