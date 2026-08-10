"""Hashed contract for paper acquisition and reasoning evaluation.

The models in this module validate static benchmark declarations only. They do
not implement paper retrieval, model calls, reasoning, graph generation, API
resources, or ArtifactVersion publication.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from ._hashing import compute_canonical_model_hash, compute_canonical_payload_hash
from .enums import ClaimType, GraphEdgeType, GraphNodeType, LiteratureRelationType
from .manifest import ContentHash, Identifier, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[str, Field(min_length=1)]
ReviewerIdentity = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_]*:[A-Za-z0-9][A-Za-z0-9._-]*$"),
]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class BenchmarkReviewStatus(StrEnum):
    pending_scientific_review = "pending_scientific_review"
    approved = "approved"
    changes_requested = "changes_requested"


class BenchmarkReviewerType(StrEnum):
    web_gpt = "web_gpt"
    automation = "automation"


class BenchmarkReviewPurpose(StrEnum):
    benchmark_scientific_review = "benchmark_scientific_review"


class BenchmarkReviewVerdict(StrEnum):
    passed = "pass"
    blocked = "blocked"


class BenchmarkReviewTargetType(StrEnum):
    benchmark_package = "benchmark_package"
    source_policy = "source_policy"
    seed_paper = "seed_paper"
    paper_summary = "paper_summary"
    evidence = "evidence"
    claim = "claim"
    relation = "relation"
    reasoning_trace = "reasoning_trace"
    graph_edge = "graph_edge"


class BenchmarkAdmissionStatus(StrEnum):
    candidate = "candidate"
    accepted = "accepted"
    rejected = "rejected"


class BenchmarkEvidenceLevel(StrEnum):
    public_abstract = "public_abstract"
    open_full_text = "open_full_text"
    publisher_metadata = "publisher_metadata"


class BenchmarkFullTextAccess(StrEnum):
    open_preprint = "open_preprint"
    publisher_dependent = "publisher_dependent"
    not_verified = "not_verified"


class BenchmarkMetricId(StrEnum):
    candidate_recall = "candidate_recall"
    schema_pass_rate = "schema_pass_rate"
    evidence_coverage = "evidence_coverage"
    relation_scientific_accuracy = "relation_scientific_accuracy"
    evidence_less_relation_block_rate = "evidence_less_relation_block_rate"


class BenchmarkMaintainer(BaseModel):
    model_config = MODEL_CONFIG

    module: Literal["paper_pipeline"]
    role: Literal["paper_and_graph_pipeline"]


class BenchmarkReviewScope(BaseModel):
    model_config = MODEL_CONFIG

    target_type: BenchmarkReviewTargetType
    target_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_targets(self) -> Self:
        _require_unique(self.target_ids, "review target id")
        return self


class BenchmarkReviewRecord(BaseModel):
    model_config = MODEL_CONFIG

    review_id: Identifier
    reviewed_at: datetime
    reviewer_type: BenchmarkReviewerType
    reviewer_identity: ReviewerIdentity
    reviewer_role: NonEmptyString
    review_purpose: BenchmarkReviewPurpose
    verdict: BenchmarkReviewVerdict
    reviewed_benchmark_version: SemanticVersion
    reviewed_content_hash: ContentHash
    scope: tuple[BenchmarkReviewScope, ...] = Field(min_length=1)
    blocking_findings: tuple[NonEmptyString, ...] = ()
    non_blocking_findings: tuple[NonEmptyString, ...] = ()
    notes: NonEmptyString

    @model_validator(mode="after")
    def validate_review_record(self) -> Self:
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        if (
            self.reviewer_type is BenchmarkReviewerType.automation
            and self.verdict is BenchmarkReviewVerdict.passed
        ):
            raise ValueError("automation cannot issue a formal PASS verdict")
        if (
            self.reviewer_type is BenchmarkReviewerType.web_gpt
            and self.reviewer_identity != "openai:web-gpt"
        ):
            raise ValueError("web_gpt reviewer identity must be openai:web-gpt")
        if self.verdict is BenchmarkReviewVerdict.passed and self.blocking_findings:
            raise ValueError("PASS review must not contain blocking findings")
        if (
            self.verdict is BenchmarkReviewVerdict.blocked
            and not self.blocking_findings
        ):
            raise ValueError("BLOCKED review requires blocking findings")
        return self


class BenchmarkCrossrefRateLimit(BaseModel):
    model_config = MODEL_CONFIG

    pool: Literal["public", "polite"]
    request_class: Literal["all_requests", "single_record", "list_or_search"]
    requests_per_interval: int = Field(gt=0)
    interval_seconds: int = Field(gt=0)
    concurrency_limit: int = Field(gt=0)


class BenchmarkCrossrefDocumentedPolicy(BaseModel):
    model_config = MODEL_CONFIG

    policy_id: Identifier
    official_source_url: HttpUrl
    verified_at: date
    applicability_note: NonEmptyString
    known_conflict_note: NonEmptyString
    limits: tuple[BenchmarkCrossrefRateLimit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_limits(self) -> Self:
        _require_unique(
            tuple((limit.pool, limit.request_class) for limit in self.limits),
            "Crossref documented limit",
        )
        return self


ObservedHeaderInt = Annotated[int, Field(gt=0)] | Literal["unavailable"]


class BenchmarkCrossrefObservedRuntimeLimit(BaseModel):
    model_config = MODEL_CONFIG

    endpoint: HttpUrl
    request_class: Literal["single_record", "list_or_search"]
    retrieved_at: datetime
    x_api_pool: Literal["public", "polite", "plus", "unavailable"]
    rate_limit_ceiling: ObservedHeaderInt
    x_rate_limit_interval: NonEmptyString
    x_concurrency_limit: ObservedHeaderInt
    response_status: int = Field(ge=100, le=599)
    observation_note: NonEmptyString

    @model_validator(mode="after")
    def validate_observation_time(self) -> Self:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("Crossref observed retrieved_at must include a timezone")
        return self


class BenchmarkCrossrefRateLimits(BaseModel):
    model_config = MODEL_CONFIG

    documented_policy: tuple[BenchmarkCrossrefDocumentedPolicy, ...] = Field(
        min_length=2
    )
    observed_runtime_limits: tuple[BenchmarkCrossrefObservedRuntimeLimit, ...] = Field(
        min_length=1
    )
    runtime_uses_response_headers: Literal[True]
    handles_429_with_backoff: Literal[True]
    missing_headers_strategy: Literal["conservative"]
    observation_boundary: NonEmptyString

    @model_validator(mode="after")
    def validate_snapshot_uniqueness(self) -> Self:
        _require_unique_model_ids(
            self.documented_policy, "policy_id", "Crossref documented policy"
        )
        _require_unique(
            tuple(
                (str(observed.endpoint), observed.request_class)
                for observed in self.observed_runtime_limits
            ),
            "Crossref observed runtime limit",
        )
        return self


class BenchmarkSourcePolicy(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    name: NonEmptyString
    access_method: NonEmptyString
    access_url: HttpUrl
    authentication_required: bool
    metadata_public: bool
    abstracts_public: bool
    full_text_boundary: NonEmptyString
    license_boundary: NonEmptyString
    rate_limit_policy: NonEmptyString
    crossref_rate_limits: BenchmarkCrossrefRateLimits | None = None
    public_runtime_risk: NonEmptyString

    @model_validator(mode="after")
    def validate_crossref_rate_limits(self) -> Self:
        if self.source_id == "crossref" and self.crossref_rate_limits is None:
            raise ValueError("Crossref source policy requires structured rate limits")
        if self.source_id != "crossref" and self.crossref_rate_limits is not None:
            raise ValueError("structured Crossref rate limits belong only to Crossref")
        return self


class BenchmarkQueryFixture(BaseModel):
    model_config = MODEL_CONFIG

    keywords: tuple[NonEmptyString, ...] = Field(min_length=1)
    query_string: NonEmptyString
    year_from: int = Field(ge=1900, le=2100)
    year_to: int = Field(ge=1900, le=2100)

    @model_validator(mode="after")
    def validate_year_range(self) -> Self:
        if self.year_from > self.year_to:
            raise ValueError("query year_from must not exceed year_to")
        _require_unique(self.keywords, "query keyword")
        return self


class BenchmarkSearchScenario(BaseModel):
    model_config = MODEL_CONFIG

    scenario_id: Identifier
    purpose: NonEmptyString
    query: BenchmarkQueryFixture
    source_ids: tuple[Identifier, ...] = Field(min_length=1)
    candidate_limit: int = Field(gt=0, le=100)
    dedupe_expectation: NonEmptyString
    ranking_expectation: NonEmptyString
    expected_paper_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_references(self) -> Self:
        _require_unique(self.source_ids, "search source id")
        _require_unique(self.expected_paper_ids, "expected paper id")
        return self


class BenchmarkVerificationSource(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    url: HttpUrl
    verified_at: date
    verified_fields: tuple[NonEmptyString, ...] = Field(min_length=1)


class BenchmarkSeedPaper(BaseModel):
    model_config = MODEL_CONFIG

    paper_id: Identifier
    title: NonEmptyString
    authors: tuple[NonEmptyString, ...] = Field(min_length=1)
    authors_complete: bool
    year: int = Field(ge=1900, le=2100)
    doi: NonEmptyString | None = None
    arxiv_id: NonEmptyString | None = None
    official_url: HttpUrl
    verification_sources: tuple[BenchmarkVerificationSource, ...] = Field(min_length=1)
    intended_uses: tuple[
        Literal["benchmark", "scientific_review", "fixture"], ...
    ] = Field(min_length=1)
    metadata_public: bool
    abstract_public: bool
    full_text_access: BenchmarkFullTextAccess
    authentication_required: bool
    license_or_usage_boundary: NonEmptyString
    rate_limit_or_runtime_risk: NonEmptyString

    @model_validator(mode="after")
    def validate_identifiers_and_uses(self) -> Self:
        if not (self.doi or self.arxiv_id or self.official_url):
            raise ValueError("seed paper requires DOI, arXiv id, or official URL")
        if any(author.casefold().rstrip(".") == "et al" for author in self.authors):
            raise ValueError(
                "authors must contain verified names, not et al. shorthand"
            )
        _require_unique(self.authors, "paper author citation")
        _require_unique(self.intended_uses, "seed intended use")
        return self


class BenchmarkSupportedStatement(BaseModel):
    model_config = MODEL_CONFIG

    statement_id: Identifier
    text: NonEmptyString
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class BenchmarkPaperSummary(BaseModel):
    model_config = MODEL_CONFIG

    summary_id: Identifier
    paper_id: Identifier
    research_goal: NonEmptyString
    method: BenchmarkSupportedStatement | None = None
    dataset: BenchmarkSupportedStatement | None = None
    findings: tuple[BenchmarkSupportedStatement, ...] = Field(min_length=1)
    limitations: tuple[BenchmarkSupportedStatement, ...] = Field(min_length=1)
    future_work: tuple[BenchmarkSupportedStatement, ...] = ()
    review_status: BenchmarkReviewStatus


class BenchmarkPaperTextLocator(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["paper_text"]
    source_url: HttpUrl
    section: Literal["abstract", "full_text"]
    paragraph: int = Field(ge=1)
    text_range: NonEmptyString


class BenchmarkEvidence(BaseModel):
    model_config = MODEL_CONFIG

    evidence_id: Identifier
    paper_id: Identifier
    target_type: Literal["summary_statement", "claim", "relation", "graph_edge"]
    target_id: Identifier
    evidence_type: Literal["paper_text"]
    evidence_level: BenchmarkEvidenceLevel
    locator: BenchmarkPaperTextLocator
    quote_or_value: NonEmptyString
    extraction_method: Literal[
        "manual_transcription_from_verified_source",
        "manual_paraphrase_from_verified_source",
    ]
    confidence: Confidence
    review_status: BenchmarkReviewStatus = (
        BenchmarkReviewStatus.pending_scientific_review
    )


class BenchmarkClaim(BaseModel):
    model_config = MODEL_CONFIG

    claim_id: Identifier
    summary_id: Identifier
    paper_id: Identifier
    claim_type: ClaimType
    text: NonEmptyString
    normalized_text: NonEmptyString
    conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    confidence: Confidence
    status: BenchmarkAdmissionStatus
    rejection_reason: NonEmptyString | None = None
    review_status: BenchmarkReviewStatus

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> Self:
        if (
            self.status is BenchmarkAdmissionStatus.rejected
            and not self.rejection_reason
        ):
            raise ValueError("rejected claim requires rejection_reason")
        if (
            self.status is not BenchmarkAdmissionStatus.rejected
            and self.rejection_reason
        ):
            raise ValueError("only rejected claim may declare rejection_reason")
        return self


class BenchmarkTraceStep(BaseModel):
    model_config = MODEL_CONFIG

    order: int = Field(ge=1)
    statement: NonEmptyString
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class BenchmarkReasoningTrace(BaseModel):
    model_config = MODEL_CONFIG

    trace_id: Identifier
    relation_id: Identifier
    premise_claim_ids: tuple[Identifier, ...] = Field(min_length=2)
    steps: tuple[BenchmarkTraceStep, ...] = Field(min_length=1)
    conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1)
    uncertainty: NonEmptyString
    provenance: Literal["web_gpt_benchmark_draft"]
    rule_version: SemanticVersion
    review_status: BenchmarkReviewStatus

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        _require_unique(self.premise_claim_ids, "trace premise claim id")
        orders = tuple(step.order for step in self.steps)
        if orders != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("trace step order must be contiguous from 1")
        return self


class BenchmarkRelation(BaseModel):
    model_config = MODEL_CONFIG

    relation_id: Identifier
    source_claim_id: Identifier
    target_claim_id: Identifier
    relation_type: LiteratureRelationType
    conditions: tuple[NonEmptyString, ...] = Field(min_length=1)
    comparability_note: NonEmptyString
    reasoning_trace_id: Identifier | None = None
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    confidence: Confidence
    status: BenchmarkAdmissionStatus
    rejection_reason: NonEmptyString | None = None
    review_status: BenchmarkReviewStatus

    @model_validator(mode="after")
    def validate_admission_fields(self) -> Self:
        if self.source_claim_id == self.target_claim_id:
            raise ValueError("relation source and target claims must differ")
        if (
            self.status is BenchmarkAdmissionStatus.accepted
            and not self.reasoning_trace_id
        ):
            raise ValueError("accepted relation requires reasoning_trace_id")
        if (
            self.status is BenchmarkAdmissionStatus.rejected
            and not self.rejection_reason
        ):
            raise ValueError("rejected relation requires rejection_reason")
        if (
            self.status is not BenchmarkAdmissionStatus.rejected
            and self.rejection_reason
        ):
            raise ValueError("only rejected relation may declare rejection_reason")
        return self


class BenchmarkGraphTaxonomy(BaseModel):
    model_config = MODEL_CONFIG

    allowed_node_types: tuple[GraphNodeType, ...] = Field(min_length=1)
    allowed_edge_types: tuple[GraphEdgeType, ...] = Field(min_length=1)
    integrity_rules: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_taxonomy(self) -> Self:
        _require_unique(self.allowed_node_types, "graph node type")
        _require_unique(self.allowed_edge_types, "graph edge type")
        _require_unique(self.integrity_rules, "graph integrity rule")
        return self


class BenchmarkGraphNode(BaseModel):
    model_config = MODEL_CONFIG

    node_id: Identifier
    node_type: GraphNodeType
    label: NonEmptyString
    ref_id: Identifier


class BenchmarkGraphEdge(BaseModel):
    model_config = MODEL_CONFIG

    edge_id: Identifier
    source: Identifier
    target: Identifier
    edge_type: GraphEdgeType
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1)
    cross_document: bool
    relation_id: Identifier | None = None
    reasoning_trace_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_cross_document_bindings(self) -> Self:
        if self.cross_document and not (self.relation_id and self.reasoning_trace_id):
            raise ValueError(
                "cross-document graph edge requires relation and reasoning trace"
            )
        return self


class BenchmarkGraph(BaseModel):
    model_config = MODEL_CONFIG

    nodes: tuple[BenchmarkGraphNode, ...] = Field(min_length=1)
    edges: tuple[BenchmarkGraphEdge, ...] = Field(min_length=1)


class BenchmarkMetricsExpectation(BaseModel):
    model_config = MODEL_CONFIG

    metric_id: BenchmarkMetricId
    numerator_definition: NonEmptyString
    denominator_definition: NonEmptyString
    empty_set_behavior: Literal["report_not_available"]


class BenchmarkPackagePayload(BaseModel):
    model_config = MODEL_CONFIG

    schema_version: SemanticVersion
    benchmark_id: Identifier
    benchmark_version: SemanticVersion
    case_id: Literal["exoplanet_host_star"]
    created_at: date
    maintainers: tuple[BenchmarkMaintainer, ...] = Field(min_length=1)
    review_status: BenchmarkReviewStatus
    scientific_payload_hash: ContentHash
    review_records: tuple[BenchmarkReviewRecord, ...] = Field(default=(), max_length=1)
    source_policies: tuple[BenchmarkSourcePolicy, ...] = Field(min_length=1)
    search_scenarios: tuple[BenchmarkSearchScenario, ...] = Field(min_length=1)
    seed_papers: tuple[BenchmarkSeedPaper, ...] = Field(min_length=5, max_length=8)
    paper_summaries: tuple[BenchmarkPaperSummary, ...] = Field(min_length=1)
    evidence: tuple[BenchmarkEvidence, ...] = Field(min_length=1)
    claims: tuple[BenchmarkClaim, ...] = Field(min_length=5)
    relations: tuple[BenchmarkRelation, ...] = Field(min_length=3)
    reasoning_traces: tuple[BenchmarkReasoningTrace, ...] = Field(min_length=1)
    graph_taxonomy: BenchmarkGraphTaxonomy
    graph: BenchmarkGraph
    metrics_expectations: tuple[BenchmarkMetricsExpectation, ...] = Field(min_length=5)

    @model_validator(mode="after")
    def validate_package_integrity(self) -> Self:
        _require_unique_model_ids(self.review_records, "review_id", "review record")
        _require_unique_model_ids(self.source_policies, "source_id", "source policy")
        _require_unique_model_ids(
            self.search_scenarios, "scenario_id", "search scenario"
        )
        papers = _unique_model_registry(self.seed_papers, "paper_id", "paper")
        summaries = _unique_model_registry(
            self.paper_summaries, "summary_id", "paper summary"
        )
        evidence = _unique_model_registry(self.evidence, "evidence_id", "evidence")
        claims = _unique_model_registry(self.claims, "claim_id", "claim")
        relations = _unique_model_registry(self.relations, "relation_id", "relation")
        traces = _unique_model_registry(
            self.reasoning_traces, "trace_id", "reasoning trace"
        )
        nodes = _unique_model_registry(self.graph.nodes, "node_id", "graph node")
        edges = _unique_model_registry(self.graph.edges, "edge_id", "graph edge")

        review_targets = {
            BenchmarkReviewTargetType.benchmark_package: {self.benchmark_id},
            BenchmarkReviewTargetType.source_policy: {
                source.source_id for source in self.source_policies
            },
            BenchmarkReviewTargetType.seed_paper: set(papers),
            BenchmarkReviewTargetType.paper_summary: set(summaries),
            BenchmarkReviewTargetType.evidence: set(evidence),
            BenchmarkReviewTargetType.claim: set(claims),
            BenchmarkReviewTargetType.relation: set(relations),
            BenchmarkReviewTargetType.reasoning_trace: set(traces),
            BenchmarkReviewTargetType.graph_edge: set(edges),
        }
        for record in self.review_records:
            scope_types = tuple(scope.target_type for scope in record.scope)
            _require_unique(scope_types, "review scope target type")
            for scope in record.scope:
                _require_known(
                    scope.target_ids,
                    review_targets[scope.target_type],
                    f"{scope.target_type.value} review target",
                )

        if self.review_status is BenchmarkReviewStatus.approved:
            scientific_reviews = tuple(
                record
                for record in self.review_records
                if record.reviewer_type is BenchmarkReviewerType.web_gpt
                and record.review_purpose
                is BenchmarkReviewPurpose.benchmark_scientific_review
            )
            if any(
                record.verdict is BenchmarkReviewVerdict.blocked
                for record in scientific_reviews
            ):
                raise ValueError(
                    "BLOCKED scientific review prevents package approval"
                )
            scientific_passes = tuple(
                record
                for record in scientific_reviews
                if record.verdict is BenchmarkReviewVerdict.passed
            )
            if not scientific_passes:
                raise ValueError("approved package requires scientific Review PASS")
            version_matches = tuple(
                record
                for record in scientific_passes
                if record.reviewed_benchmark_version == self.benchmark_version
            )
            if not version_matches:
                raise ValueError("scientific Review PASS has a stale benchmark version")
            current_scientific_passes = tuple(
                record
                for record in version_matches
                if record.reviewed_content_hash == self.scientific_payload_hash
            )
            if not current_scientific_passes:
                raise ValueError(
                    "scientific Review PASS has a stale scientific payload hash"
                )
            scientifically_reviewed_targets = {
                target_type: {
                    target_id
                    for record in current_scientific_passes
                    for scope in record.scope
                    if scope.target_type is target_type
                    for target_id in scope.target_ids
                }
                for target_type in BenchmarkReviewTargetType
            }
            missing_review_targets = {
                target_type.value: sorted(
                    target_ids - scientifically_reviewed_targets[target_type]
                )
                for target_type, target_ids in review_targets.items()
                if target_ids - scientifically_reviewed_targets[target_type]
            }
            if missing_review_targets:
                raise ValueError(
                    "approved package scientific review scope is incomplete: "
                    f"{missing_review_targets}"
                )
            reviewable_objects = (
                *self.paper_summaries,
                *self.evidence,
                *self.claims,
                *self.relations,
                *self.reasoning_traces,
            )
            if any(
                item.review_status is not BenchmarkReviewStatus.approved
                for item in reviewable_objects
            ):
                raise ValueError(
                    "approved package requires approved review status for all "
                    "summaries, evidence, claims, relations, and traces"
                )

        source_ids = {source.source_id for source in self.source_policies}
        for paper in self.seed_papers:
            _require_known(
                tuple(source.source_id for source in paper.verification_sources),
                source_ids,
                "paper verification source",
            )
        for scenario in self.search_scenarios:
            _require_known(scenario.source_ids, source_ids, "scenario source")
            _require_known(scenario.expected_paper_ids, set(papers), "expected paper")

        summary_statements: dict[str, BenchmarkSupportedStatement] = {}
        for summary in self.paper_summaries:
            _require_known((summary.paper_id,), set(papers), "summary paper")
            statements = tuple(
                statement
                for statement in (
                    summary.method,
                    summary.dataset,
                    *summary.findings,
                    *summary.limitations,
                    *summary.future_work,
                )
                if statement is not None
            )
            for statement in statements:
                if statement.statement_id in summary_statements:
                    raise ValueError(
                        f"duplicate summary statement id: {statement.statement_id}"
                    )
                summary_statements[statement.statement_id] = statement
                _require_known(
                    statement.evidence_ids, set(evidence), "summary statement evidence"
                )

        valid_evidence_targets = (
            set(summary_statements) | set(claims) | set(relations) | set(edges)
        )
        evidence_targets_by_type = {
            "summary_statement": set(summary_statements),
            "claim": set(claims),
            "relation": set(relations),
            "graph_edge": set(edges),
        }
        evidence_bindings_by_type = {
            "summary_statement": {
                key: set(value.evidence_ids)
                for key, value in summary_statements.items()
            },
            "claim": {key: set(value.evidence_ids) for key, value in claims.items()},
            "relation": {
                key: set(value.evidence_ids) for key, value in relations.items()
            },
            "graph_edge": {
                key: set(value.evidence_ids) for key, value in edges.items()
            },
        }
        for item in self.evidence:
            _require_known((item.paper_id,), set(papers), "evidence paper")
            _require_known((item.target_id,), valid_evidence_targets, "evidence target")
            _require_known(
                (item.target_id,),
                evidence_targets_by_type[item.target_type],
                f"{item.target_type} evidence target",
            )
            if (
                item.evidence_id
                not in evidence_bindings_by_type[item.target_type][item.target_id]
            ):
                raise ValueError(
                    f"evidence {item.evidence_id} is not bound by its declared target"
                )

        for claim in self.claims:
            _require_known((claim.paper_id,), set(papers), "claim paper")
            _require_known((claim.summary_id,), set(summaries), "claim summary")
            if summaries[claim.summary_id].paper_id != claim.paper_id:
                raise ValueError(f"claim {claim.claim_id} paper/summary mismatch")
            _require_known(claim.evidence_ids, set(evidence), "claim evidence")
            if any(
                evidence[eid].paper_id != claim.paper_id for eid in claim.evidence_ids
            ):
                raise ValueError(
                    f"claim {claim.claim_id} has evidence from another paper"
                )

        required_claim_types = {
            ClaimType.finding,
            ClaimType.method,
            ClaimType.dataset,
            ClaimType.limitation,
        }
        present_claim_types = {claim.claim_type for claim in self.claims}
        if len(present_claim_types & required_claim_types) < 3:
            raise ValueError(
                "benchmark claims must cover at least three required claim types"
            )

        statuses = {relation.status for relation in self.relations}
        if statuses != set(BenchmarkAdmissionStatus):
            raise ValueError(
                "benchmark relations must include candidate, accepted, and rejected"
            )
        required_relation_types = {
            LiteratureRelationType.supports,
            LiteratureRelationType.extends,
            LiteratureRelationType.derived_from,
            LiteratureRelationType.limits,
            LiteratureRelationType.contradicts,
        }
        present_relation_types = {relation.relation_type for relation in self.relations}
        if len(present_relation_types & required_relation_types) < 3:
            raise ValueError(
                "benchmark relations must cover at least three required types"
            )

        for relation in self.relations:
            _require_known(
                (relation.source_claim_id, relation.target_claim_id),
                set(claims),
                "relation claim",
            )
            _require_known(relation.evidence_ids, set(evidence), "relation evidence")
            source_evidence = set(claims[relation.source_claim_id].evidence_ids)
            target_evidence = set(claims[relation.target_claim_id].evidence_ids)
            if relation.reasoning_trace_id is not None:
                _require_known(
                    (relation.reasoning_trace_id,), set(traces), "relation trace"
                )
            if relation.status is BenchmarkAdmissionStatus.accepted:
                if not (source_evidence & set(relation.evidence_ids)):
                    raise ValueError(
                        f"accepted relation {relation.relation_id} lacks source evidence"
                    )
                if not (target_evidence & set(relation.evidence_ids)):
                    raise ValueError(
                        f"accepted relation {relation.relation_id} lacks target evidence"
                    )
            if relation.review_status is BenchmarkReviewStatus.approved:
                source_claim = claims[relation.source_claim_id]
                target_claim = claims[relation.target_claim_id]
                if source_claim.review_status is not BenchmarkReviewStatus.approved:
                    raise ValueError(
                        f"approved relation {relation.relation_id} has unapproved "
                        "source claim"
                    )
                if target_claim.review_status is not BenchmarkReviewStatus.approved:
                    raise ValueError(
                        f"approved relation {relation.relation_id} has unapproved "
                        "target claim"
                    )
                related_evidence_ids = {
                    *relation.evidence_ids,
                    *source_claim.evidence_ids,
                    *target_claim.evidence_ids,
                }
                if relation.reasoning_trace_id is None:
                    raise ValueError(
                        f"approved relation {relation.relation_id} requires approved "
                        "reasoning trace"
                    )
                trace = traces[relation.reasoning_trace_id]
                if trace.review_status is not BenchmarkReviewStatus.approved:
                    raise ValueError(
                        f"approved relation {relation.relation_id} has unapproved "
                        "reasoning trace"
                    )
                related_evidence_ids.update(
                    evidence_id
                    for step in trace.steps
                    for evidence_id in step.evidence_ids
                )
                if any(
                    evidence[evidence_id].review_status
                    is not BenchmarkReviewStatus.approved
                    for evidence_id in related_evidence_ids
                ):
                    raise ValueError(
                        f"approved relation {relation.relation_id} has unapproved evidence"
                    )

        for trace in self.reasoning_traces:
            _require_known((trace.relation_id,), set(relations), "trace relation")
            _require_known(trace.premise_claim_ids, set(claims), "trace premise claim")
            relation = relations[trace.relation_id]
            if relation.reasoning_trace_id != trace.trace_id:
                raise ValueError(f"trace {trace.trace_id} is not pinned by its relation")
            if trace.premise_claim_ids != (
                relation.source_claim_id,
                relation.target_claim_id,
            ):
                raise ValueError(
                    f"trace {trace.trace_id} premises must follow relation direction"
                )
            for step in trace.steps:
                _require_known(step.evidence_ids, set(evidence), "trace step evidence")

        allowed_node_types = set(self.graph_taxonomy.allowed_node_types)
        allowed_edge_types = set(self.graph_taxonomy.allowed_edge_types)
        for node in self.graph.nodes:
            if node.node_type not in allowed_node_types:
                raise ValueError(
                    f"graph node type is outside taxonomy: {node.node_type}"
                )
            if node.node_type is GraphNodeType.paper:
                _require_known((node.ref_id,), set(papers), "graph paper node ref")
            elif node.node_type is GraphNodeType.claim:
                _require_known((node.ref_id,), set(claims), "graph claim node ref")

        for edge in self.graph.edges:
            _require_known((edge.source, edge.target), set(nodes), "graph edge node")
            _require_known(edge.evidence_ids, set(evidence), "graph edge evidence")
            if edge.edge_type not in allowed_edge_types:
                raise ValueError(
                    f"graph edge type is outside taxonomy: {edge.edge_type}"
                )
            if edge.cross_document:
                _require_known(
                    (edge.relation_id,), set(relations), "graph edge relation"
                )
                _require_known(
                    (edge.reasoning_trace_id,), set(traces), "graph edge trace"
                )
                relation = relations[edge.relation_id]
                if relation.status is not BenchmarkAdmissionStatus.accepted:
                    raise ValueError(
                        f"graph edge {edge.edge_id} references non-accepted relation"
                    )
                if relation.reasoning_trace_id != edge.reasoning_trace_id:
                    raise ValueError(
                        f"graph edge {edge.edge_id} relation/trace mismatch"
                    )
                source_node = nodes[edge.source]
                target_node = nodes[edge.target]
                if (
                    source_node.node_type is not GraphNodeType.claim
                    or target_node.node_type is not GraphNodeType.claim
                    or source_node.ref_id != relation.source_claim_id
                    or target_node.ref_id != relation.target_claim_id
                ):
                    raise ValueError(
                        f"graph edge {edge.edge_id} endpoints do not match relation claims"
                    )
                if (
                    claims[relation.source_claim_id].paper_id
                    == claims[relation.target_claim_id].paper_id
                ):
                    raise ValueError(
                        f"graph edge {edge.edge_id} is not actually cross-document"
                    )
                if edge.edge_type.value != relation.relation_type.value:
                    raise ValueError(
                        f"graph edge {edge.edge_id} type does not match relation"
                    )
            elif edge.relation_id or edge.reasoning_trace_id:
                raise ValueError(
                    f"non-cross-document graph edge {edge.edge_id} must not bind relation or trace"
                )

        metric_ids = tuple(metric.metric_id for metric in self.metrics_expectations)
        _require_unique(metric_ids, "benchmark metric")
        if set(metric_ids) != set(BenchmarkMetricId):
            raise ValueError("metrics_expectations must define every required metric")
        return self


class BenchmarkPackage(BenchmarkPackagePayload):
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if len(self.review_records) != 1:
            raise ValueError(
                "benchmark package requires exactly one current scientific review"
            )
        current_review = self.review_records[0]
        if current_review.reviewed_benchmark_version != self.benchmark_version:
            raise ValueError(
                "scientific review must bind the current benchmark version"
            )
        if current_review.reviewed_content_hash != self.scientific_payload_hash:
            raise ValueError(
                "scientific review must bind the current scientific payload hash"
            )
        expected_scientific = compute_benchmark_scientific_payload_hash(self)
        if self.scientific_payload_hash != expected_scientific:
            raise ValueError(
                "scientific_payload_hash does not match canonical scientific "
                f"content: {expected_scientific}"
            )
        expected = compute_benchmark_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(
                f"content_hash does not match canonical benchmark content: {expected}"
            )
        return self


class BenchmarkEvaluationInput(BaseModel):
    """Counts from one evaluator run; this model performs no external calls."""

    model_config = MODEL_CONFIG

    retrieved_expected_paper_ids: tuple[Identifier, ...] = ()
    schema_items_valid: int = Field(ge=0)
    schema_items_total: int = Field(ge=0)
    evidence_requirements_satisfied: int = Field(ge=0)
    evidence_requirements_total: int = Field(ge=0)
    scientifically_reviewed_relations_correct: int = Field(default=0, ge=0)
    scientifically_reviewed_relations_total: int = Field(default=0, ge=0)
    evidence_less_relations_blocked: int = Field(ge=0)
    evidence_less_relations_total: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_numerators(self) -> Self:
        pairs = (
            (self.schema_items_valid, self.schema_items_total, "schema pass rate"),
            (
                self.evidence_requirements_satisfied,
                self.evidence_requirements_total,
                "evidence coverage",
            ),
            (
                self.scientifically_reviewed_relations_correct,
                self.scientifically_reviewed_relations_total,
                "relation scientific accuracy",
            ),
            (
                self.evidence_less_relations_blocked,
                self.evidence_less_relations_total,
                "evidence-less relation block rate",
            ),
        )
        for numerator, denominator, label in pairs:
            if numerator > denominator:
                raise ValueError(f"{label} numerator must not exceed denominator")
        return self


class BenchmarkMetricResult(BaseModel):
    model_config = MODEL_CONFIG

    metric_id: BenchmarkMetricId
    numerator: int
    denominator: int
    value: float | None
    status: Literal["computed", "not_available"]


def compute_benchmark_content_hash(
    value: BenchmarkPackagePayload | BenchmarkPackage | dict[str, object],
) -> str:
    """Compute the canonical Case and Field Manifest-compatible SHA-256 benchmark hash."""

    if isinstance(value, BaseModel):
        raw_payload = value.model_dump(mode="json", exclude={"content_hash"})
    else:
        raw_payload = dict(value)
        raw_payload.pop("content_hash", None)
    payload = BenchmarkPackagePayload.model_validate(raw_payload)
    return compute_canonical_model_hash(payload)


def _normalize_review_statuses(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: (
                BenchmarkReviewStatus.pending_scientific_review.value
                if key == "review_status"
                else _normalize_review_statuses(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_review_statuses(item) for item in value]
    return value


def compute_benchmark_scientific_payload_hash(
    value: BenchmarkPackagePayload | BenchmarkPackage | dict[str, object],
) -> str:
    """Hash scientific content without review metadata or approval state."""

    if isinstance(value, BaseModel):
        raw_payload = value.model_dump(mode="json", exclude_none=True)
    else:
        raw_payload = dict(value)
    raw_payload.pop("content_hash", None)
    normalized_statuses = _normalize_review_statuses(raw_payload)
    if not isinstance(normalized_statuses, dict):
        raise TypeError("benchmark payload must be an object")
    raw_payload = normalized_statuses
    raw_payload["scientific_payload_hash"] = f"sha256:{'0' * 64}"
    raw_payload["review_records"] = []
    normalized = BenchmarkPackagePayload.model_validate(raw_payload)
    scientific_payload = normalized.model_dump(mode="json", exclude_none=True)
    for field in (
        "content_hash",
        "scientific_payload_hash",
        "review_status",
        "review_records",
    ):
        scientific_payload.pop(field, None)
    return compute_canonical_payload_hash(scientific_payload)


def load_benchmark_package(path: str | Path) -> BenchmarkPackage:
    """Load and fully validate one paper acquisition benchmark package."""

    return BenchmarkPackage.model_validate_json(Path(path).read_text(encoding="utf-8"))


def evaluate_benchmark(
    package: BenchmarkPackage,
    evaluation: BenchmarkEvaluationInput,
) -> tuple[BenchmarkMetricResult, ...]:
    """Calculate the five frozen Paper Acquisition Benchmark metrics with explicit empty-set behavior."""

    expected_papers = {
        paper_id
        for scenario in package.search_scenarios
        for paper_id in scenario.expected_paper_ids
    }
    retrieved = set(evaluation.retrieved_expected_paper_ids)
    candidate_numerator = len(expected_papers & retrieved)
    approved_relation_count = sum(
        relation.review_status is BenchmarkReviewStatus.approved
        for relation in package.relations
    )
    relation_accuracy_available = (
        package.review_status is BenchmarkReviewStatus.approved
        and approved_relation_count > 0
    )
    if not relation_accuracy_available:
        if (
            evaluation.scientifically_reviewed_relations_correct != 0
            or evaluation.scientifically_reviewed_relations_total != 0
        ):
            raise ValueError(
                "relation scientific accuracy counts must be zero when approved "
                "benchmark relations are unavailable"
            )
        relation_accuracy_counts = (0, 0)
    else:
        if (
            evaluation.scientifically_reviewed_relations_total
            != approved_relation_count
        ):
            raise ValueError(
                "relation scientific accuracy total must equal the package's approved "
                f"relation count: {approved_relation_count}"
            )
        relation_accuracy_counts = (
            evaluation.scientifically_reviewed_relations_correct,
            evaluation.scientifically_reviewed_relations_total,
        )
    counts = (
        (
            BenchmarkMetricId.candidate_recall,
            candidate_numerator,
            len(expected_papers),
        ),
        (
            BenchmarkMetricId.schema_pass_rate,
            evaluation.schema_items_valid,
            evaluation.schema_items_total,
        ),
        (
            BenchmarkMetricId.evidence_coverage,
            evaluation.evidence_requirements_satisfied,
            evaluation.evidence_requirements_total,
        ),
        (
            BenchmarkMetricId.relation_scientific_accuracy,
            *relation_accuracy_counts,
        ),
        (
            BenchmarkMetricId.evidence_less_relation_block_rate,
            evaluation.evidence_less_relations_blocked,
            evaluation.evidence_less_relations_total,
        ),
    )
    return tuple(_metric_result(*count) for count in counts)


def _metric_result(
    metric_id: BenchmarkMetricId, numerator: int, denominator: int
) -> BenchmarkMetricResult:
    if denominator == 0:
        return BenchmarkMetricResult(
            metric_id=metric_id,
            numerator=numerator,
            denominator=denominator,
            value=None,
            status="not_available",
        )
    return BenchmarkMetricResult(
        metric_id=metric_id,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        status="computed",
    )


def _unique_model_registry(
    values: tuple[BaseModel, ...], attribute: str, label: str
) -> dict[str, BaseModel]:
    result: dict[str, BaseModel] = {}
    for value in values:
        key = str(getattr(value, attribute))
        if key in result:
            raise ValueError(f"duplicate {label} id: {key}")
        result[key] = value
    return result


def _require_unique_model_ids(
    values: tuple[BaseModel, ...], attribute: str, label: str
) -> None:
    _unique_model_registry(values, attribute, label)


def _require_unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _require_known(
    references: tuple[str | None, ...], known: set[str], label: str
) -> None:
    unknown = sorted(
        str(reference) for reference in references if reference not in known
    )
    if unknown:
        raise ValueError(f"unknown {label} reference(s): {unknown}")
