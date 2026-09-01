"""Strict contracts for evidence-graph publication.

This module is the only Pydantic authoring source for publisher-ready Evidence
Graph artifacts. Only its sealed typed candidate can satisfy this publication contract.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    StringConstraints,
    model_validator,
)

from ._graph_seal import (
    GraphAdmissionSnapshot,
    GraphPublicationSeal,
    build_graph_admission_snapshot as _build_graph_admission_snapshot,
    graph_artifact_candidate_is_sealed,
)
from ._hashing import compute_canonical_payload_hash
from .enums import EvidenceType, GraphEdgeType, GraphNodeType, SourceMode
from .persistence import PersistedUuid


GRAPH_SCHEMA_VERSION = "2.0.0"
GRAPH_TAXONOMY_VERSION = "2.0.0"
GRAPH_IDENTITY_POLICY_VERSION = "2.0.0"
GRAPH_INTEGRITY_POLICY_VERSION = "2.0.0"
GRAPH_CAPACITY_POLICY_VERSION = "2.0.0"
GRAPH_FILTER_POLICY_VERSION = "2.0.0"
GRAPH_AGGREGATION_POLICY_VERSION = "2.0.0"
GRAPH_PROGRESSIVE_POLICY_VERSION = "2.0.0"
GRAPH_PRODUCER_VERSION = "2.0.0"
GRAPH_BENCHMARK_PAPER_BENCHMARK_IDENTITY = (
    "2.0.0",
    "2.0.0",
    "sha256:1a9969d31f80198f73c008eb78cdba70cb4411570345f0829552da4bcda87db9",
    "sha256:a315b54f934bb3b37e8273a9a766d5c87bd494089d99d7e82b6920b782e8ad57",
)
GRAPH_BENCHMARK_DISCLAIMER = (
    "This Benchmark only demonstrates frozen human labels, Graph integrity "
    "admission, and deterministic regression; it does not represent online "
    "scientific quality, generalization, real-time data capability, or new "
    "scientific discovery."
)

MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    allow_inf_nan=False,
    str_strip_whitespace=True,
)

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    ),
]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
SemanticVersion = Annotated[
    str,
    StringConstraints(pattern=r"^[1-9]\d*\.\d+\.\d+$", max_length=32),
]
ContentHash = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$", max_length=71),
]


def _coerce_source_mode(value: SourceMode | str) -> SourceMode:
    return value if isinstance(value, SourceMode) else SourceMode(value)


GraphSourceMode = Annotated[SourceMode, BeforeValidator(_coerce_source_mode)]


def _json_compatible(value: Any) -> Any:
    """Normalize nested model payloads before canonical hashing.

    Hash helpers also accept dictionaries assembled by admission code and tests;
    those dictionaries can legitimately contain nested Pydantic models.  A plain
    ``json.dumps`` cannot serialize those models and would make the dictionary
    and model forms of the same contract behave differently.
    """

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    normalized = _json_compatible(value)
    payload = json.loads(json.dumps(normalized, ensure_ascii=False, allow_nan=False))
    if not isinstance(payload, dict):
        raise TypeError("Graph hash payload must be a JSON object")
    return payload


def _require_sorted_unique(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{label} must use sorted unique order")


class GraphInputRole(StrEnum):
    literature_claims = "literature_claims"
    literature_relations = "literature_relations"
    dataset = "dataset"
    field_dictionary = "field_dictionary"


class GraphIntegrityStatus(StrEnum):
    passed = "passed"
    failed = "failed"


class GraphIntegrityStage(StrEnum):
    input_schema = "input_schema"
    artifact_version = "artifact_version"
    ownership = "ownership"
    taxonomy = "taxonomy"
    identity = "identity"
    endpoint = "endpoint"
    evidence_snapshot = "evidence_snapshot"
    relation_trace = "relation_trace"
    direction_type = "direction_type"
    capacity_progressive = "capacity_progressive"
    hash_commitment = "hash_commitment"


class GraphRejectionReason(StrEnum):
    invalid_json = "invalid_json"
    schema_invalid = "schema_invalid"
    input_version_unknown = "input_version_unknown"
    input_version_unpublished = "input_version_unpublished"
    wrong_artifact_kind = "wrong_artifact_kind"
    unsupported_schema_version = "unsupported_schema_version"
    content_hash_mismatch = "content_hash_mismatch"
    input_hash_mismatch = "input_hash_mismatch"
    producer_execution_mismatch = "producer_execution_mismatch"
    cross_project_ownership = "cross_project_ownership"
    cross_version_reference = "cross_version_reference"
    taxonomy_violation = "taxonomy_violation"
    duplicate_node_identity = "duplicate_node_identity"
    duplicate_edge_identity = "duplicate_edge_identity"
    identity_collision = "identity_collision"
    dangling_endpoint = "dangling_endpoint"
    evidence_missing = "evidence_missing"
    evidence_unknown = "evidence_unknown"
    evidence_inconsistent = "evidence_inconsistent"
    source_snapshot_missing = "source_snapshot_missing"
    source_snapshot_unknown = "source_snapshot_unknown"
    source_snapshot_inconsistent = "source_snapshot_inconsistent"
    relation_not_accepted = "relation_not_accepted"
    reasoning_trace_missing = "reasoning_trace_missing"
    reasoning_trace_mismatch = "reasoning_trace_mismatch"
    reasoning_trace_incomplete = "reasoning_trace_incomplete"
    wrong_direction = "wrong_direction"
    relation_type_mismatch = "relation_type_mismatch"
    provenance_version_mismatch = "provenance_version_mismatch"
    evidence_hidden_by_filter = "evidence_hidden_by_filter"
    aggregation_incomplete = "aggregation_incomplete"
    size_limit_exceeded = "size_limit_exceeded"
    silent_truncation = "silent_truncation"
    progressive_input_incomplete = "progressive_input_incomplete"
    candidate_hash_mismatch = "candidate_hash_mismatch"
    report_hash_mismatch = "report_hash_mismatch"
    admission_commitment_mismatch = "admission_commitment_mismatch"


_STAGE_PRIORITY = {
    GraphIntegrityStage.input_schema: 100,
    GraphIntegrityStage.artifact_version: 200,
    GraphIntegrityStage.ownership: 300,
    GraphIntegrityStage.taxonomy: 400,
    GraphIntegrityStage.identity: 500,
    GraphIntegrityStage.endpoint: 600,
    GraphIntegrityStage.evidence_snapshot: 700,
    GraphIntegrityStage.relation_trace: 800,
    GraphIntegrityStage.direction_type: 900,
    GraphIntegrityStage.capacity_progressive: 1000,
    GraphIntegrityStage.hash_commitment: 1100,
}


class GraphArtifactVersionReference(BaseModel):
    model_config = MODEL_CONFIG

    role: GraphInputRole
    artifact_id: PersistedUuid
    artifact_version_id: PersistedUuid
    project_id: PersistedUuid
    version_number: int = Field(ge=1)
    kind: Literal[
        "literature_claims",
        "literature_relations",
        "dataset",
        "field_dictionary",
    ]
    schema_version: SemanticVersion
    content_hash: ContentHash
    input_hash: ContentHash
    output_hash: ContentHash
    source_mode: GraphSourceMode
    producer_type: Literal["pipeline", "model", "algorithm"]
    producer_name: Identifier
    producer_version: SemanticVersion
    parameters_hash: ContentHash

    @model_validator(mode="after")
    def validate_role_kind(self) -> Self:
        if self.role.value != self.kind:
            raise ValueError("Graph input role must exactly match Artifact kind")
        return self


class GraphInputVersionClosure(BaseModel):
    model_config = MODEL_CONFIG

    project_id: PersistedUuid
    versions: tuple[GraphArtifactVersionReference, ...] = Field(
        min_length=2,
        max_length=256,
    )

    @model_validator(mode="after")
    def validate_versions(self) -> Self:
        ids = tuple(item.artifact_version_id for item in self.versions)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError(
                "Graph input ArtifactVersions must use sorted unique order"
            )
        if any(item.project_id != self.project_id for item in self.versions):
            raise ValueError("Graph inputs must belong to one Project")
        roles = {item.role for item in self.versions}
        if (
            GraphInputRole.literature_claims not in roles
            or sum(
                item.role is GraphInputRole.literature_relations
                for item in self.versions
            )
            != 1
        ):
            raise ValueError(
                "Graph input closure requires LiteratureClaims and LiteratureRelations"
            )
        data_roles = roles & {GraphInputRole.dataset, GraphInputRole.field_dictionary}
        if data_roles not in (
            set(),
            {GraphInputRole.dataset, GraphInputRole.field_dictionary},
        ):
            raise ValueError("Dataset and FieldDictionary must form one exact pair")
        non_claim_roles = tuple(
            item.role
            for item in self.versions
            if item.role is not GraphInputRole.literature_claims
        )
        if len(non_claim_roles) != len(set(non_claim_roles)):
            raise ValueError("Graph non-Claim input roles must be unique")
        return self


GRAPH_TAXONOMY_NODE_TYPES = tuple(
    sorted(
        (
            GraphNodeType.research_goal,
            GraphNodeType.dataset,
            GraphNodeType.field,
            GraphNodeType.paper,
            GraphNodeType.claim,
        ),
        key=lambda item: item.value,
    )
)
GRAPH_TAXONOMY_STRUCTURAL_EDGE_TYPES = frozenset(
    {
        GraphEdgeType.uses_dataset,
        GraphEdgeType.provides_field,
        GraphEdgeType.supports_finding,
    }
)
GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES = frozenset(
    {
        GraphEdgeType.supports,
        GraphEdgeType.extends,
        GraphEdgeType.derived_from,
        GraphEdgeType.limits,
        GraphEdgeType.contradicts,
        GraphEdgeType.uses_same_dataset,
        GraphEdgeType.compares_method,
    }
)
GRAPH_TAXONOMY_EDGE_TYPES = tuple(
    sorted(
        GRAPH_TAXONOMY_STRUCTURAL_EDGE_TYPES | GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES,
        key=lambda item: item.value,
    )
)

# Keep the exported JSON Schema as strict as the runtime Evidence Graph contract.  A
# broad ``GraphNodeType``/``GraphEdgeType`` annotation followed by an
# ``after`` validator is not sufficient here because JSON Schema consumers do
# not execute Pydantic validators.
GraphNodeContractType = Literal[
    GraphNodeType.research_goal,
    GraphNodeType.dataset,
    GraphNodeType.field,
    GraphNodeType.paper,
    GraphNodeType.claim,
]
GraphLiteratureEdgeContractType = Literal[
    GraphEdgeType.supports,
    GraphEdgeType.extends,
    GraphEdgeType.derived_from,
    GraphEdgeType.limits,
    GraphEdgeType.contradicts,
    GraphEdgeType.uses_same_dataset,
    GraphEdgeType.compares_method,
]
GraphEdgeContractType = Literal[
    GraphEdgeType.uses_dataset,
    GraphEdgeType.provides_field,
    GraphEdgeType.supports_finding,
    GraphEdgeType.supports,
    GraphEdgeType.extends,
    GraphEdgeType.derived_from,
    GraphEdgeType.limits,
    GraphEdgeType.contradicts,
    GraphEdgeType.uses_same_dataset,
    GraphEdgeType.compares_method,
]
GraphTaxonomyNodeTypes = tuple[
    Literal[GraphNodeType.claim],
    Literal[GraphNodeType.dataset],
    Literal[GraphNodeType.field],
    Literal[GraphNodeType.paper],
    Literal[GraphNodeType.research_goal],
]
GraphTaxonomyEdgeTypes = tuple[
    Literal[GraphEdgeType.compares_method],
    Literal[GraphEdgeType.contradicts],
    Literal[GraphEdgeType.derived_from],
    Literal[GraphEdgeType.extends],
    Literal[GraphEdgeType.limits],
    Literal[GraphEdgeType.provides_field],
    Literal[GraphEdgeType.supports],
    Literal[GraphEdgeType.supports_finding],
    Literal[GraphEdgeType.uses_dataset],
    Literal[GraphEdgeType.uses_same_dataset],
]


class GraphTaxonomy(BaseModel):
    model_config = MODEL_CONFIG

    taxonomy_id: Literal["taxonomy.graph.evidence_graph"] = (
        "taxonomy.graph.evidence_graph"
    )
    schema_version: Literal["2.0.0"] = "2.0.0"
    version: Literal["2.0.0"] = "2.0.0"
    node_types: GraphTaxonomyNodeTypes
    edge_types: GraphTaxonomyEdgeTypes
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_taxonomy(self) -> Self:
        if self.node_types != GRAPH_TAXONOMY_NODE_TYPES:
            raise ValueError("Evidence Graph node_types must equal its exact authority")
        if self.edge_types != GRAPH_TAXONOMY_EDGE_TYPES:
            raise ValueError("Evidence Graph edge_types must equal its exact authority")
        expected = compute_canonical_payload_hash(
            self.model_dump(mode="json", exclude={"content_hash"})
        )
        if self.content_hash != expected:
            raise ValueError(f"Graph taxonomy content_hash mismatch: {expected}")
        return self


class GraphCapacityPolicy(BaseModel):
    model_config = MODEL_CONFIG

    version: Literal["2.0.0"] = "2.0.0"
    max_input_versions: int = Field(default=256, ge=2, le=256)
    max_nodes: int = Field(default=10_000, ge=1, le=10_000)
    max_edges: int = Field(default=20_000, ge=1, le=20_000)
    max_evidence_uses: int = Field(default=50_000, ge=1, le=50_000)
    max_evidence_uses_per_edge: int = Field(default=5_000, ge=1, le=5_000)
    max_serialized_bytes: int = Field(default=4_194_304, ge=1, le=4_194_304)
    max_progressive_chunks: int = Field(default=256, ge=1, le=256)
    max_items_per_chunk: int = Field(default=10_000, ge=1, le=10_000)
    max_label_length: int = Field(default=256, ge=1, le=256)
    max_metadata_length: int = Field(default=2_048, ge=1, le=2_048)


class GraphPolicySet(BaseModel):
    model_config = MODEL_CONFIG

    identity_policy_version: Literal["2.0.0"] = "2.0.0"
    taxonomy_policy_version: Literal["2.0.0"] = "2.0.0"
    integrity_policy_version: Literal["2.0.0"] = "2.0.0"
    capacity_policy: GraphCapacityPolicy = Field(default_factory=GraphCapacityPolicy)
    filter_policy_version: Literal["2.0.0"] = "2.0.0"
    filter_policy: Literal["complete_scope_no_hidden_evidence"] = (
        "complete_scope_no_hidden_evidence"
    )
    aggregation_policy_version: Literal["2.0.0"] = "2.0.0"
    aggregation_policy: Literal["full_upstream_evidence_union"] = (
        "full_upstream_evidence_union"
    )
    progressive_policy_version: Literal["2.0.0"] = "2.0.0"
    progressive_policy: Literal["complete_set_order_independent"] = (
        "complete_set_order_independent"
    )


class GraphStructuralEdgeRequest(BaseModel):
    model_config = MODEL_CONFIG

    edge_type: Literal[GraphEdgeType.supports_finding]
    source_paper_id: Identifier
    target_claim_id: Identifier


class GraphBuildScope(BaseModel):
    model_config = MODEL_CONFIG

    literature_paper_ids: tuple[Identifier, ...] = ()
    literature_claim_ids: tuple[Identifier, ...] = ()
    accepted_relation_ids: tuple[Identifier, ...] = ()
    structural_edges: tuple[GraphStructuralEdgeRequest, ...] = ()
    include_data: bool = False
    research_goal_id: Identifier | None = None
    filtered_item_count: int = Field(default=0, ge=0, le=50_000)
    excluded_item_count: int = Field(default=0, ge=0, le=50_000)
    exclusion_reasons: tuple[Identifier, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        for values, label in (
            (self.literature_paper_ids, "paper"),
            (self.literature_claim_ids, "Claim"),
            (self.accepted_relation_ids, "Relation"),
        ):
            _require_sorted_unique(values, label)
        keys = tuple(
            (item.edge_type.value, item.source_paper_id, item.target_claim_id)
            for item in self.structural_edges
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("structural edge requests must use sorted unique order")
        _require_sorted_unique(self.exclusion_reasons, "scope exclusion reason")
        if self.research_goal_id is not None:
            raise ValueError(
                "Evidence Graph has no pinned ResearchGoal input and cannot infer uses_dataset"
            )
        return self


class GraphProgressiveChunk(BaseModel):
    model_config = MODEL_CONFIG

    chunk_index: int = Field(ge=0)
    item_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> Self:
        _require_sorted_unique(self.item_ids, "progressive chunk item")
        return self


class GraphProgressiveInput(BaseModel):
    model_config = MODEL_CONFIG

    progressive_id: Identifier
    chunk_count: int = Field(ge=1, le=256)
    chunks: tuple[GraphProgressiveChunk, ...] = Field(min_length=1, max_length=256)
    complete: bool

    @model_validator(mode="after")
    def validate_chunks(self) -> Self:
        ordered = tuple(sorted(self.chunks, key=lambda item: item.chunk_index))
        object.__setattr__(self, "chunks", ordered)
        if self.chunk_count != len(ordered):
            raise ValueError("progressive chunk_count does not match chunks")
        if tuple(item.chunk_index for item in ordered) != tuple(
            range(self.chunk_count)
        ):
            raise ValueError("progressive chunk indexes must be contiguous from zero")
        all_items = tuple(item_id for chunk in ordered for item_id in chunk.item_ids)
        if len(all_items) != len(set(all_items)):
            raise ValueError("progressive chunks contain duplicate items")
        return self


class GraphLayoutHint(BaseModel):
    model_config = MODEL_CONFIG

    strategy: Literal["none", "group_by_node_type", "group_by_domain"] = "none"
    group_order: tuple[GraphNodeType, ...] = ()

    @model_validator(mode="after")
    def validate_layout(self) -> Self:
        values = tuple(item.value for item in self.group_order)
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise ValueError("layout group_order must use sorted unique order")
        if self.strategy == "none" and self.group_order:
            raise ValueError("layout strategy none cannot declare groups")
        return self


class GraphBuildRequest(BaseModel):
    model_config = MODEL_CONFIG

    project_id: PersistedUuid
    literature_claims_artifact_version_ids: tuple[PersistedUuid, ...] = Field(
        min_length=1,
        max_length=253,
    )
    literature_relations_artifact_version_id: PersistedUuid
    dataset_artifact_version_id: PersistedUuid | None = None
    field_dictionary_artifact_version_id: PersistedUuid | None = None
    scope: GraphBuildScope
    policies: GraphPolicySet = Field(default_factory=GraphPolicySet)
    progressive: GraphProgressiveInput
    layout_hint: GraphLayoutHint = Field(default_factory=GraphLayoutHint)

    @model_validator(mode="after")
    def validate_data_pair(self) -> Self:
        _require_sorted_unique(
            self.literature_claims_artifact_version_ids,
            "LiteratureClaims ArtifactVersion",
        )
        pair = (
            self.dataset_artifact_version_id,
            self.field_dictionary_artifact_version_id,
        )
        if (pair[0] is None) != (pair[1] is None):
            raise ValueError("Dataset and FieldDictionary version ids form one pair")
        if self.scope.include_data != (pair[0] is not None):
            raise ValueError("scope.include_data must match the selected data pair")
        return self


class GraphLogicalReferencePart(BaseModel):
    model_config = MODEL_CONFIG

    name: Identifier
    value: Identifier


class GraphNodeVersionBinding(BaseModel):
    model_config = MODEL_CONFIG

    artifact_version_id: PersistedUuid
    domain_object_id: Identifier


class GraphArtifactNode(BaseModel):
    model_config = MODEL_CONFIG

    node_id: Identifier
    node_type: GraphNodeContractType
    label: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    logical_reference: tuple[GraphLogicalReferencePart, ...] = Field(min_length=1)
    version_bindings: tuple[GraphNodeVersionBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_node(self) -> Self:
        if self.node_type in {
            GraphNodeType.source,
            GraphNodeType.finding,
            GraphNodeType.relation,
            GraphNodeType.reasoning_trace,
            GraphNodeType.evidence,
        }:
            raise ValueError("Evidence Graph does not generate this Graph node type")
        reference_keys = tuple(
            (item.name, item.value) for item in self.logical_reference
        )
        if reference_keys != tuple(sorted(reference_keys)) or len(
            reference_keys
        ) != len(set(reference_keys)):
            raise ValueError("node logical references must use sorted unique order")
        binding_keys = tuple(
            (item.artifact_version_id, item.domain_object_id)
            for item in self.version_bindings
        )
        if binding_keys != tuple(sorted(binding_keys)) or len(binding_keys) != len(
            set(binding_keys)
        ):
            raise ValueError("node version bindings must use sorted unique order")
        return self


class GraphRelationTraceBinding(BaseModel):
    model_config = MODEL_CONFIG

    relation_id: Identifier
    relation_artifact_version_id: PersistedUuid
    relation_status: Literal["accepted"] = "accepted"
    relation_type: GraphLiteratureEdgeContractType
    source_claim_id: Identifier
    target_claim_id: Identifier
    reasoning_trace_id: Identifier
    premise_claim_ids: tuple[Identifier, Identifier]
    trace_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if self.relation_type not in GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES:
            raise ValueError(
                "RelationTrace relation_type is outside the Evidence Graph Literature taxonomy"
            )
        if self.premise_claim_ids != (
            self.source_claim_id,
            self.target_claim_id,
        ):
            raise ValueError("ReasoningTrace premises must preserve Relation direction")
        _require_sorted_unique(self.trace_evidence_ids, "ReasoningTrace Evidence")
        return self


class GraphDataEdgeAggregation(BaseModel):
    """Stable Dataset/Field provenance counts for one ``provides_field`` edge."""

    model_config = MODEL_CONFIG

    projected_row_count: int = Field(ge=1)
    mapped_outcome_count: int = Field(ge=0)
    declared_null_outcome_count: int = Field(ge=0)
    unresolved_outcome_count: int = Field(ge=0)
    retained_candidate_count: int = Field(ge=0)
    selected_candidate_count: int = Field(ge=0)
    unselected_candidate_count: int = Field(ge=0)
    conflict_count: int = Field(ge=0)
    upstream_evidence_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            self.mapped_outcome_count
            + self.declared_null_outcome_count
            + self.unresolved_outcome_count
            != self.projected_row_count
        ):
            raise ValueError("data edge outcome counts must cover every projected row")
        if (
            self.selected_candidate_count + self.unselected_candidate_count
            != self.retained_candidate_count
        ):
            raise ValueError("data edge candidate counts must preserve every candidate")
        if self.selected_candidate_count > self.mapped_outcome_count:
            raise ValueError("only mapped outcomes may select a source candidate")
        return self


class GraphArtifactEdge(BaseModel):
    model_config = MODEL_CONFIG

    edge_id: Identifier
    edge_type: GraphEdgeContractType
    source_node_id: Identifier
    target_node_id: Identifier
    evidence_use_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=5_000)
    relation_trace: GraphRelationTraceBinding | None = None
    data_aggregation: GraphDataEdgeAggregation | None = None

    @model_validator(mode="after")
    def validate_edge(self) -> Self:
        if self.source_node_id == self.target_node_id:
            raise ValueError("Graph edges cannot be self-referential")
        _require_sorted_unique(self.evidence_use_ids, "edge Evidence-use")
        if self.edge_type in GRAPH_TAXONOMY_STRUCTURAL_EDGE_TYPES:
            if self.relation_trace is not None:
                raise ValueError(
                    "structural edges have no Relation/Trace; Literature edges require one"
                )
        elif self.edge_type in GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES:
            if self.relation_trace is None:
                raise ValueError(
                    "structural edges have no Relation/Trace; Literature edges require one"
                )
        else:
            raise ValueError(
                "Graph edge_type is outside the exact Evidence Graph taxonomy"
            )
        if (self.edge_type is GraphEdgeType.provides_field) != (
            self.data_aggregation is not None
        ):
            raise ValueError(
                "only provides_field edges require Dataset/Field aggregation metadata"
            )
        return self


class GraphSourceSnapshotReference(BaseModel):
    model_config = MODEL_CONFIG

    source_snapshot_id: Identifier
    persisted_source_snapshot_id: PersistedUuid
    source_id: Identifier
    source_version: ShortText
    content_hash: ContentHash
    project_id: PersistedUuid


class GraphEvidenceUse(BaseModel):
    model_config = MODEL_CONFIG

    evidence_use_id: Identifier
    graph_edge_id: Identifier
    upstream_artifact_version_id: PersistedUuid
    upstream_evidence_id: PersistedUuid
    upstream_target_type: Identifier
    upstream_target_id: Identifier
    source_snapshot_id: Identifier
    evidence_type: EvidenceType
    upstream_evidence_hash: ContentHash
    upstream_is_restricted: bool


class GraphIntegrityFinding(BaseModel):
    model_config = MODEL_CONFIG

    stage: GraphIntegrityStage
    reason: GraphRejectionReason
    priority: int = Field(ge=100, le=1100)
    path: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    message: ShortText

    @model_validator(mode="after")
    def validate_priority(self) -> Self:
        if self.priority != _STAGE_PRIORITY[self.stage]:
            raise ValueError("integrity finding priority must match its stable stage")
        return self


class GraphIntegrityCounts(BaseModel):
    model_config = MODEL_CONFIG

    input_version_count: int = Field(ge=1, le=256)
    node_count: int = Field(ge=0, le=10_000)
    edge_count: int = Field(ge=0, le=20_000)
    evidence_use_count: int = Field(ge=0, le=50_000)
    source_snapshot_count: int = Field(ge=0)
    relation_edge_count: int = Field(ge=0)


class GraphIntegrityReport(BaseModel):
    model_config = MODEL_CONFIG

    policy_version: Literal["2.0.0"] = "2.0.0"
    status: GraphIntegrityStatus
    findings: tuple[GraphIntegrityFinding, ...]
    first_failure_stage: GraphIntegrityStage | None = None
    first_rejection_reason: GraphRejectionReason | None = None
    counts: GraphIntegrityCounts
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        keys = tuple(
            (item.priority, item.stage.value, item.path, item.reason.value)
            for item in self.findings
        )
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("integrity findings must use stable unique order")
        if self.status is GraphIntegrityStatus.passed:
            if self.findings or self.first_failure_stage or self.first_rejection_reason:
                raise ValueError("passed integrity report cannot contain failures")
        else:
            if not self.findings:
                raise ValueError("failed integrity report requires findings")
            first = self.findings[0]
            if (
                self.first_failure_stage is not first.stage
                or self.first_rejection_reason is not first.reason
            ):
                raise ValueError(
                    "first Graph failure must equal the stable first finding"
                )
        expected = compute_graph_integrity_report_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"integrity report content_hash mismatch: {expected}")
        return self


class GraphAlgorithmProducer(BaseModel):
    model_config = MODEL_CONFIG

    producer_type: Literal["algorithm"] = "algorithm"
    producer_name: Literal["evidence-graph-pipeline"] = "evidence-graph-pipeline"
    producer_version: Literal["2.0.0"] = "2.0.0"
    identity_policy_version: Literal["2.0.0"] = "2.0.0"
    taxonomy_policy_version: Literal["2.0.0"] = "2.0.0"
    integrity_policy_version: Literal["2.0.0"] = "2.0.0"
    capacity_policy_version: Literal["2.0.0"] = "2.0.0"
    filter_policy_version: Literal["2.0.0"] = "2.0.0"
    aggregation_policy_version: Literal["2.0.0"] = "2.0.0"
    progressive_policy_version: Literal["2.0.0"] = "2.0.0"
    parameters_hash: ContentHash


class GraphArtifactCandidate(BaseModel):
    """The only Evidence Graph candidate accepted by the generic Publisher port."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: GraphPublicationSeal | None = PrivateAttr(default=None)
    _artifact_publication_context: GraphAdmissionSnapshot | None = PrivateAttr(
        default=None
    )

    kind: Literal["graph"] = "graph"
    schema_version: Literal["2.0.0"] = "2.0.0"
    graph_id: Identifier
    project_id: PersistedUuid
    input_versions: GraphInputVersionClosure
    taxonomy: GraphTaxonomy
    policies: GraphPolicySet
    scope: GraphBuildScope
    nodes: tuple[GraphArtifactNode, ...] = Field(min_length=1, max_length=10_000)
    edges: tuple[GraphArtifactEdge, ...] = Field(min_length=1, max_length=20_000)
    evidence_uses: tuple[GraphEvidenceUse, ...] = Field(min_length=1, max_length=50_000)
    source_snapshots: tuple[GraphSourceSnapshotReference, ...] = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=50_000)
    source_snapshot_ids: tuple[Identifier, ...] = Field(min_length=1)
    integrity_report: GraphIntegrityReport
    progressive: GraphProgressiveInput
    layout_hint: GraphLayoutHint
    producer: GraphAlgorithmProducer
    input_hash: ContentHash
    scientific_hash: ContentHash
    layout_hash: ContentHash
    report_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.project_id != self.input_versions.project_id:
            raise ValueError("Graph Project must match its input version closure")
        if self.integrity_report.status is not GraphIntegrityStatus.passed:
            raise ValueError("publisher candidate requires a passed integrity report")
        if not self.progressive.complete:
            raise ValueError(
                "incomplete progressive input cannot become a Graph candidate"
            )

        node_ids = tuple(item.node_id for item in self.nodes)
        edge_ids = tuple(item.edge_id for item in self.edges)
        use_ids = tuple(item.evidence_use_id for item in self.evidence_uses)
        use_bindings = tuple(
            (
                item.graph_edge_id,
                item.upstream_artifact_version_id,
                item.upstream_evidence_id,
            )
            for item in self.evidence_uses
        )
        snapshot_ids = tuple(item.source_snapshot_id for item in self.source_snapshots)
        for values, label in (
            (node_ids, "node"),
            (edge_ids, "edge"),
            (use_ids, "Evidence-use"),
            (snapshot_ids, "SourceSnapshot"),
        ):
            _require_sorted_unique(values, label)
        if len(use_bindings) != len(set(use_bindings)):
            raise ValueError(
                "Graph Evidence-use edge/version/Evidence bindings must be unique"
            )
        if self.evidence_ids != use_ids:
            raise ValueError(
                "candidate evidence_ids must equal its Evidence-use registry"
            )
        if self.source_snapshot_ids != snapshot_ids:
            raise ValueError(
                "candidate source_snapshot_ids must equal its SourceSnapshot registry"
            )
        if any(item.project_id != self.project_id for item in self.source_snapshots):
            raise ValueError("Graph SourceSnapshots must belong to the input Project")

        nodes = {item.node_id: item for item in self.nodes}
        uses = {item.evidence_use_id: item for item in self.evidence_uses}
        input_version_ids = {
            item.artifact_version_id for item in self.input_versions.versions
        }
        snapshot_registry = set(snapshot_ids)
        relation_edges = 0
        for edge in self.edges:
            source = nodes.get(edge.source_node_id)
            target = nodes.get(edge.target_node_id)
            if source is None or target is None:
                raise ValueError("Graph edge contains a dangling endpoint")
            if edge.edge_type in GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES:
                expected_endpoints = (GraphNodeType.claim, GraphNodeType.claim)
            else:
                expected_endpoints = {
                    GraphEdgeType.uses_dataset: (
                        GraphNodeType.research_goal,
                        GraphNodeType.dataset,
                    ),
                    GraphEdgeType.provides_field: (
                        GraphNodeType.dataset,
                        GraphNodeType.field,
                    ),
                    GraphEdgeType.supports_finding: (
                        GraphNodeType.paper,
                        GraphNodeType.claim,
                    ),
                }.get(edge.edge_type)
                if expected_endpoints is None:
                    raise ValueError(
                        "Graph edge lies outside the exact Evidence Graph taxonomy"
                    )
            if (source.node_type, target.node_type) != expected_endpoints:
                raise ValueError(
                    "Graph edge violates its authoritative endpoint direction"
                )
            edge_uses = tuple(
                item
                for item in self.evidence_uses
                if item.graph_edge_id == edge.edge_id
            )
            if (
                tuple(item.evidence_use_id for item in edge_uses)
                != edge.evidence_use_ids
            ):
                raise ValueError("Graph edge Evidence-use closure is incomplete")
            if edge.relation_trace is not None:
                relation_edges += 1
                binding = edge.relation_trace
                if (
                    edge.edge_type is not binding.relation_type
                    or source.logical_reference[-1].value != binding.source_claim_id
                    or target.logical_reference[-1].value != binding.target_claim_id
                    or binding.relation_artifact_version_id not in input_version_ids
                ):
                    raise ValueError(
                        "Literature edge Relation/Trace endpoint closure mismatch"
                    )
            if any(use_id not in uses for use_id in edge.evidence_use_ids):
                raise ValueError("Graph edge references unknown Evidence-use")
        if {item.graph_edge_id for item in self.evidence_uses} != set(edge_ids):
            raise ValueError("every Graph edge requires at least one Evidence-use")
        if not {item.node_type for item in self.nodes} <= set(self.taxonomy.node_types):
            raise ValueError("Graph node lies outside the pinned taxonomy")
        if not {item.edge_type for item in self.edges} <= set(self.taxonomy.edge_types):
            raise ValueError("Graph edge lies outside the pinned taxonomy")
        if len(
            {item.persisted_source_snapshot_id for item in self.source_snapshots}
        ) != len(self.source_snapshots):
            raise ValueError("persisted Graph SourceSnapshot bindings must be unique")
        for item in self.evidence_uses:
            if (
                item.upstream_artifact_version_id not in input_version_ids
                or item.source_snapshot_id not in snapshot_registry
            ):
                raise ValueError(
                    "Graph Evidence-use escapes its input provenance closure"
                )

        counts = self.integrity_report.counts
        expected_counts = GraphIntegrityCounts(
            input_version_count=len(self.input_versions.versions),
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            evidence_use_count=len(self.evidence_uses),
            source_snapshot_count=len(self.source_snapshots),
            relation_edge_count=relation_edges,
        )
        if counts != expected_counts:
            raise ValueError("Graph integrity counts do not match candidate registries")
        capacity = self.policies.capacity_policy
        if (
            len(self.input_versions.versions) > capacity.max_input_versions
            or len(self.nodes) > capacity.max_nodes
            or len(self.edges) > capacity.max_edges
            or len(self.evidence_uses) > capacity.max_evidence_uses
            or any(
                len(item.evidence_use_ids) > capacity.max_evidence_uses_per_edge
                for item in self.edges
            )
            or len(self.progressive.chunks) > capacity.max_progressive_chunks
            or any(
                len(item.item_ids) > capacity.max_items_per_chunk
                for item in self.progressive.chunks
            )
        ):
            raise ValueError("Graph candidate exceeds its declared capacity policy")
        expected_parameters_hash = compute_graph_algorithm_parameters_hash(
            self.policies,
            self.taxonomy,
        )
        if self.producer.parameters_hash != expected_parameters_hash:
            raise ValueError(
                "Graph producer parameters_hash does not match taxonomy/policies"
            )

        expected_hashes = (
            ("input_hash", compute_graph_input_hash(self)),
            ("scientific_hash", compute_graph_scientific_hash(self)),
            ("layout_hash", compute_graph_layout_hash(self)),
            ("report_hash", self.integrity_report.content_hash),
            ("output_hash", compute_graph_output_hash(self)),
        )
        for field, expected in expected_hashes:
            if getattr(self, field) != expected:
                raise ValueError(f"{field} does not match Graph candidate: {expected}")
        expected_graph_id = f"graph.{self.scientific_hash.removeprefix('sha256:')[:24]}"
        if self.graph_id != expected_graph_id:
            raise ValueError(
                f"graph_id does not match scientific identity: {expected_graph_id}"
            )
        serialized_size = len(
            json.dumps(
                self.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        if serialized_size > capacity.max_serialized_bytes:
            raise ValueError("Graph candidate exceeds max_serialized_bytes")
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return graph_artifact_candidate_is_sealed(
            self,
            self._artifact_publication_seal,
            self._artifact_publication_context,
            public_payload_hash=compute_graph_public_payload_hash(self),
        )


class GraphAdmissionResult(BaseModel):
    model_config = MODEL_CONFIG

    status: GraphIntegrityStatus
    report: GraphIntegrityReport
    candidate: GraphArtifactCandidate | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status is not self.report.status:
            raise ValueError("Graph admission status must match integrity report")
        if (self.status is GraphIntegrityStatus.passed) != (self.candidate is not None):
            raise ValueError("only passed Graph admission returns a candidate")
        return self


class GraphBenchmarkCaseKind(StrEnum):
    scientific_graph = "scientific_graph"
    data_mapping_fixture = "data_mapping_fixture"
    rejection_case = "rejection_case"
    size_boundary = "size_boundary"


class GraphBenchmarkDenominatorScope(StrEnum):
    paper_benchmark_scientific_graph_cases = "paper_benchmark_scientific_graph_cases"
    paper_benchmark_expected_nodes = "paper_benchmark_expected_nodes"
    paper_benchmark_expected_edges = "paper_benchmark_expected_edges"
    paper_benchmark_edge_evidence_uses = "paper_benchmark_edge_evidence_uses"
    paper_benchmark_accepted_relations = "paper_benchmark_accepted_relations"
    paper_benchmark_reasoning_traces = "paper_benchmark_reasoning_traces"
    paper_benchmark_nonaccepted_relations = "paper_benchmark_nonaccepted_relations"
    schema_valid_expected_pass_cases = "schema_valid_expected_pass_cases"
    data_mapping_fixture_cases = "data_mapping_fixture_cases"
    rejection_fixture_cases = "rejection_fixture_cases"
    size_boundary_fixture_cases = "size_boundary_fixture_cases"
    all_cases = "all_cases"


class GraphBenchmarkVersionSet(BaseModel):
    model_config = MODEL_CONFIG

    graph_schema_version: Literal["2.0.0"] = "2.0.0"
    taxonomy_policy_version: Literal["2.0.0"] = "2.0.0"
    identity_policy_version: Literal["2.0.0"] = "2.0.0"
    integrity_policy_version: Literal["2.0.0"] = "2.0.0"
    capacity_policy_version: Literal["2.0.0"] = "2.0.0"
    filter_policy_version: Literal["2.0.0"] = "2.0.0"
    aggregation_policy_version: Literal["2.0.0"] = "2.0.0"
    progressive_policy_version: Literal["2.0.0"] = "2.0.0"
    producer_version: Literal["2.0.0"] = "2.0.0"


class GraphBenchmarkEvaluationCase(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    kind: GraphBenchmarkCaseKind
    data_level: Literal["benchmark", "fixture"]
    input_json: Annotated[str, StringConstraints(min_length=1, max_length=4_194_304)]
    expected_status: GraphIntegrityStatus
    expected_failure_stage: GraphIntegrityStage | None = None
    expected_rejection_reason: GraphRejectionReason | None = None
    expected_node_ids: tuple[Identifier, ...] = ()
    expected_edge_ids: tuple[Identifier, ...] = ()
    expected_evidence_use_count: int = Field(default=0, ge=0, le=50_000)
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_case(self) -> Self:
        _require_sorted_unique(self.expected_node_ids, "benchmark expected node")
        _require_sorted_unique(self.expected_edge_ids, "benchmark expected edge")
        rejected = self.expected_status is GraphIntegrityStatus.failed
        if rejected != (
            self.expected_failure_stage is not None
            and self.expected_rejection_reason is not None
        ):
            raise ValueError("failed benchmark cases require exact stage and reason")
        if self.kind is GraphBenchmarkCaseKind.scientific_graph:
            if self.data_level != "benchmark" or rejected:
                raise ValueError("scientific Graph case must be passing Benchmark data")
        elif self.kind is GraphBenchmarkCaseKind.data_mapping_fixture:
            if self.data_level != "fixture" or rejected:
                raise ValueError("data mapping case must be a passing Fixture")
        elif self.data_level != "fixture":
            raise ValueError("negative and size cases must be labeled Fixture")
        expected = compute_graph_benchmark_case_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"Graph benchmark case content_hash mismatch: {expected}")
        return self


class GraphBenchmarkCaseResult(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    kind: GraphBenchmarkCaseKind
    data_level: Literal["benchmark", "fixture"]
    case_content_hash: ContentHash
    schema_valid: bool
    expected_status: GraphIntegrityStatus
    expected_failure_stage: GraphIntegrityStage | None = None
    expected_rejection_reason: GraphRejectionReason | None = None
    status: GraphIntegrityStatus
    failure_stage: GraphIntegrityStage | None = None
    rejection_reason: GraphRejectionReason | None = None
    expected_node_count: int = Field(ge=0)
    actual_node_count: int = Field(ge=0)
    matched_node_count: int = Field(ge=0)
    unexpected_node_count: int = Field(ge=0)
    expected_edge_count: int = Field(ge=0)
    actual_edge_count: int = Field(ge=0)
    matched_edge_count: int = Field(ge=0)
    unexpected_edge_count: int = Field(ge=0)
    expected_evidence_use_count: int = Field(ge=0)
    actual_evidence_use_count: int = Field(ge=0)
    matched_evidence_use_count: int = Field(ge=0)
    expected_accepted_relation_count: int = Field(ge=0)
    matched_accepted_relation_count: int = Field(ge=0)
    expected_reasoning_trace_count: int = Field(ge=0)
    matched_reasoning_trace_count: int = Field(ge=0)
    expected_nonaccepted_relation_count: int = Field(ge=0)
    excluded_nonaccepted_relation_count: int = Field(ge=0)
    node_exact_match: bool
    edge_exact_match: bool
    stable_order_pass: bool
    expected_result_pass: bool
    input_hash: ContentHash
    scientific_hash: ContentHash | None = None
    layout_hash: ContentHash | None = None
    report_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        failed = self.status is GraphIntegrityStatus.failed
        if failed != (
            self.failure_stage is not None and self.rejection_reason is not None
        ):
            raise ValueError("failed Graph benchmark result requires stage and reason")
        expected_failed = self.expected_status is GraphIntegrityStatus.failed
        if expected_failed != (
            self.expected_failure_stage is not None
            and self.expected_rejection_reason is not None
        ):
            raise ValueError(
                "failed Graph benchmark expectation requires stage and reason"
            )
        count_bounds = (
            (self.matched_node_count, self.expected_node_count, self.actual_node_count),
            (self.matched_edge_count, self.expected_edge_count, self.actual_edge_count),
            (
                self.matched_evidence_use_count,
                self.expected_evidence_use_count,
                self.actual_evidence_use_count,
            ),
            (
                self.matched_accepted_relation_count,
                self.expected_accepted_relation_count,
                self.expected_accepted_relation_count,
            ),
            (
                self.matched_reasoning_trace_count,
                self.expected_reasoning_trace_count,
                self.expected_reasoning_trace_count,
            ),
            (
                self.excluded_nonaccepted_relation_count,
                self.expected_nonaccepted_relation_count,
                self.expected_nonaccepted_relation_count,
            ),
        )
        if any(
            matched > min(expected, actual)
            for matched, expected, actual in count_bounds
        ):
            raise ValueError("Graph benchmark matched count exceeds its applicable set")
        expected_node_exact = (
            self.matched_node_count == self.expected_node_count
            and self.actual_node_count == self.expected_node_count
            and self.unexpected_node_count == 0
        )
        expected_edge_exact = (
            self.matched_edge_count == self.expected_edge_count
            and self.actual_edge_count == self.expected_edge_count
            and self.unexpected_edge_count == 0
        )
        if self.node_exact_match != expected_node_exact:
            raise ValueError("Graph benchmark node exact flag disagrees with counts")
        if self.edge_exact_match != expected_edge_exact:
            raise ValueError("Graph benchmark edge exact flag disagrees with counts")
        expected_pass = (
            self.status is self.expected_status
            and self.failure_stage is self.expected_failure_stage
            and self.rejection_reason is self.expected_rejection_reason
        )
        if self.expected_status is GraphIntegrityStatus.passed:
            expected_pass = (
                expected_pass
                and self.node_exact_match
                and self.edge_exact_match
                and self.matched_evidence_use_count
                == self.expected_evidence_use_count
                == self.actual_evidence_use_count
                and self.matched_accepted_relation_count
                == self.expected_accepted_relation_count
                and self.matched_reasoning_trace_count
                == self.expected_reasoning_trace_count
                and self.excluded_nonaccepted_relation_count
                == self.expected_nonaccepted_relation_count
                and self.stable_order_pass
            )
        if self.expected_result_pass != expected_pass:
            raise ValueError(
                "Graph benchmark expected-result flag disagrees with case facts"
            )
        if self.status is GraphIntegrityStatus.passed and None in (
            self.scientific_hash,
            self.layout_hash,
        ):
            raise ValueError(
                "passing Graph result requires all stable candidate hashes"
            )
        return self


class GraphBenchmarkMetric(BaseModel):
    model_config = MODEL_CONFIG

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    rate: float | None = Field(default=None, ge=0.0, le=1.0)
    denominator_scope: GraphBenchmarkDenominatorScope
    empty_set_semantics: Literal["null"] = "null"

    @model_validator(mode="after")
    def validate_rate(self) -> Self:
        expected = None if self.denominator == 0 else self.numerator / self.denominator
        if self.numerator > self.denominator or self.rate != expected:
            raise ValueError(
                "Graph benchmark rate does not match numerator/denominator"
            )
        return self


class GraphBenchmarkReport(BaseModel):
    model_config = MODEL_CONFIG

    report_schema_version: Literal["2.0.0"] = "2.0.0"
    disclaimer: Literal[GRAPH_BENCHMARK_DISCLAIMER] = GRAPH_BENCHMARK_DISCLAIMER
    paper_benchmark_schema_version: SemanticVersion
    paper_benchmark_version: SemanticVersion
    paper_benchmark_scientific_payload_hash: ContentHash
    paper_benchmark_content_hash: ContentHash
    graph_versions: GraphBenchmarkVersionSet
    taxonomy_node_types: tuple[GraphNodeType, ...]
    taxonomy_edge_types: tuple[GraphEdgeType, ...]
    expected_scientific_node_count: int = Field(ge=0)
    expected_scientific_edge_count: int = Field(ge=0)
    cases: tuple[GraphBenchmarkCaseResult, ...] = Field(min_length=1)
    full_graph_exact_match_rate: GraphBenchmarkMetric
    node_exact_match_rate: GraphBenchmarkMetric
    edge_exact_match_rate: GraphBenchmarkMetric
    evidence_coverage_rate: GraphBenchmarkMetric
    accepted_relation_coverage_rate: GraphBenchmarkMetric
    reasoning_trace_coverage_rate: GraphBenchmarkMetric
    nonaccepted_relation_exclusion_rate: GraphBenchmarkMetric
    stable_identity_order_rate: GraphBenchmarkMetric
    data_mapping_fixture_pass_rate: GraphBenchmarkMetric
    rejection_case_pass_rate: GraphBenchmarkMetric
    size_boundary_pass_rate: GraphBenchmarkMetric
    schema_pass_rate: GraphBenchmarkMetric
    unexpected_node_count: int = Field(ge=0)
    unexpected_edge_count: int = Field(ge=0)
    integrity_pass_count: int = Field(ge=0)
    integrity_fail_count: int = Field(ge=0)
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if (
            self.paper_benchmark_schema_version,
            self.paper_benchmark_version,
            self.paper_benchmark_scientific_payload_hash,
            self.paper_benchmark_content_hash,
        ) != GRAPH_BENCHMARK_PAPER_BENCHMARK_IDENTITY:
            raise ValueError(
                "Graph benchmark frozen Paper Acquisition Benchmark identity mismatch"
            )
        case_ids = tuple(item.case_id for item in self.cases)
        _require_sorted_unique(case_ids, "Graph benchmark case")
        if self.taxonomy_node_types != tuple(
            sorted(self.taxonomy_node_types, key=lambda item: item.value)
        ) or self.taxonomy_edge_types != tuple(
            sorted(self.taxonomy_edge_types, key=lambda item: item.value)
        ):
            raise ValueError("Graph benchmark taxonomy must use canonical order")
        scientific = tuple(
            item
            for item in self.cases
            if item.kind is GraphBenchmarkCaseKind.scientific_graph
        )
        data_mapping = tuple(
            item
            for item in self.cases
            if item.kind is GraphBenchmarkCaseKind.data_mapping_fixture
        )
        rejections = tuple(
            item
            for item in self.cases
            if item.kind is GraphBenchmarkCaseKind.rejection_case
        )
        size_cases = tuple(
            item
            for item in self.cases
            if item.kind is GraphBenchmarkCaseKind.size_boundary
        )
        stable_applicable = tuple(
            item
            for item in self.cases
            if item.expected_status is GraphIntegrityStatus.passed and item.schema_valid
        )

        def metric(
            numerator: int,
            denominator: int,
            scope: GraphBenchmarkDenominatorScope,
        ) -> GraphBenchmarkMetric:
            return GraphBenchmarkMetric(
                numerator=numerator,
                denominator=denominator,
                rate=None if denominator == 0 else numerator / denominator,
                denominator_scope=scope,
            )

        expected_metrics = {
            "full_graph_exact_match_rate": metric(
                sum(
                    item.expected_result_pass
                    and item.node_exact_match
                    and item.edge_exact_match
                    and item.matched_evidence_use_count
                    == item.expected_evidence_use_count
                    == item.actual_evidence_use_count
                    and item.matched_accepted_relation_count
                    == item.expected_accepted_relation_count
                    and item.matched_reasoning_trace_count
                    == item.expected_reasoning_trace_count
                    and item.excluded_nonaccepted_relation_count
                    == item.expected_nonaccepted_relation_count
                    for item in scientific
                ),
                len(scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_scientific_graph_cases,
            ),
            "node_exact_match_rate": metric(
                sum(item.matched_node_count for item in scientific),
                sum(item.expected_node_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_expected_nodes,
            ),
            "edge_exact_match_rate": metric(
                sum(item.matched_edge_count for item in scientific),
                sum(item.expected_edge_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_expected_edges,
            ),
            "evidence_coverage_rate": metric(
                sum(item.matched_evidence_use_count for item in scientific),
                sum(item.expected_evidence_use_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_edge_evidence_uses,
            ),
            "accepted_relation_coverage_rate": metric(
                sum(item.matched_accepted_relation_count for item in scientific),
                sum(item.expected_accepted_relation_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_accepted_relations,
            ),
            "reasoning_trace_coverage_rate": metric(
                sum(item.matched_reasoning_trace_count for item in scientific),
                sum(item.expected_reasoning_trace_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_reasoning_traces,
            ),
            "nonaccepted_relation_exclusion_rate": metric(
                sum(item.excluded_nonaccepted_relation_count for item in scientific),
                sum(item.expected_nonaccepted_relation_count for item in scientific),
                GraphBenchmarkDenominatorScope.paper_benchmark_nonaccepted_relations,
            ),
            "stable_identity_order_rate": metric(
                sum(item.stable_order_pass for item in stable_applicable),
                len(stable_applicable),
                GraphBenchmarkDenominatorScope.schema_valid_expected_pass_cases,
            ),
            "data_mapping_fixture_pass_rate": metric(
                sum(item.expected_result_pass for item in data_mapping),
                len(data_mapping),
                GraphBenchmarkDenominatorScope.data_mapping_fixture_cases,
            ),
            "rejection_case_pass_rate": metric(
                sum(item.expected_result_pass for item in rejections),
                len(rejections),
                GraphBenchmarkDenominatorScope.rejection_fixture_cases,
            ),
            "size_boundary_pass_rate": metric(
                sum(item.expected_result_pass for item in size_cases),
                len(size_cases),
                GraphBenchmarkDenominatorScope.size_boundary_fixture_cases,
            ),
            "schema_pass_rate": metric(
                sum(item.schema_valid for item in self.cases),
                len(self.cases),
                GraphBenchmarkDenominatorScope.all_cases,
            ),
        }
        for field, expected_metric in expected_metrics.items():
            if getattr(self, field) != expected_metric:
                raise ValueError(f"Graph benchmark {field} does not match case facts")
        expected_scalars = {
            "expected_scientific_node_count": sum(
                item.expected_node_count for item in scientific
            ),
            "expected_scientific_edge_count": sum(
                item.expected_edge_count for item in scientific
            ),
            "unexpected_node_count": sum(
                item.unexpected_node_count for item in scientific
            ),
            "unexpected_edge_count": sum(
                item.unexpected_edge_count for item in scientific
            ),
            "integrity_pass_count": sum(
                item.status is GraphIntegrityStatus.passed for item in self.cases
            ),
            "integrity_fail_count": sum(
                item.status is GraphIntegrityStatus.failed for item in self.cases
            ),
        }
        for field, expected_scalar in expected_scalars.items():
            if getattr(self, field) != expected_scalar:
                raise ValueError(f"Graph benchmark {field} does not match case facts")
        expected_input_hash = compute_canonical_payload_hash(
            {
                "paper_benchmark_schema_version": self.paper_benchmark_schema_version,
                "paper_benchmark_version": self.paper_benchmark_version,
                "paper_benchmark_scientific_payload_hash": self.paper_benchmark_scientific_payload_hash,
                "paper_benchmark_content_hash": self.paper_benchmark_content_hash,
                "graph_versions": self.graph_versions.model_dump(mode="json"),
                "taxonomy_node_types": [
                    item.value for item in self.taxonomy_node_types
                ],
                "taxonomy_edge_types": [
                    item.value for item in self.taxonomy_edge_types
                ],
                "case_content_hashes": [item.case_content_hash for item in self.cases],
            }
        )
        if self.input_hash != expected_input_hash:
            raise ValueError(
                f"Graph benchmark input_hash mismatch: {expected_input_hash}"
            )
        expected = compute_graph_benchmark_output_hash(self)
        if self.output_hash != expected:
            raise ValueError(f"Graph benchmark output_hash mismatch: {expected}")
        return self


def compute_graph_upstream_evidence_hash(
    value: BaseModel | dict[str, Any] | Any,
    *,
    is_restricted: bool | None = None,
) -> str:
    """Hash stable persisted Evidence facts, excluding project/time/runtime fields."""

    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    elif isinstance(value, dict):
        data = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    else:
        data = {
            name: getattr(value, name)
            for name in (
                "artifact_version_id",
                "target_type",
                "target_id",
                "evidence_type",
                "source_snapshot_id",
                "paper_id",
                "locator",
                "quote_or_value",
                "extraction_method",
                "confidence",
                "is_restricted",
            )
            if hasattr(value, name)
        }
    if is_restricted is not None:
        data["is_restricted"] = is_restricted
    fields = (
        "artifact_version_id",
        "target_type",
        "target_id",
        "evidence_type",
        "source_snapshot_id",
        "paper_id",
        "locator",
        "quote_or_value",
        "extraction_method",
        "confidence",
        "is_restricted",
    )
    if set(fields) - data.keys() or type(data.get("is_restricted")) is not bool:
        raise ValueError("upstream Evidence hash requires every stable persisted fact")
    return compute_canonical_payload_hash({field: data[field] for field in fields})


def compute_graph_integrity_report_hash(
    value: GraphIntegrityReport | dict[str, Any],
) -> str:
    payload = _payload(value)
    payload.pop("content_hash", None)
    return compute_canonical_payload_hash(payload)


def graph_algorithm_parameters(
    policies: GraphPolicySet,
    taxonomy: GraphTaxonomy,
) -> dict[str, str | int]:
    """Return the scalar-only manifest accepted by ProducerExecutionStore."""

    capacity = policies.capacity_policy
    return {
        "taxonomy_id": taxonomy.taxonomy_id,
        "taxonomy_version": taxonomy.version,
        "taxonomy_content_hash": taxonomy.content_hash,
        "identity_policy_version": policies.identity_policy_version,
        "taxonomy_policy_version": policies.taxonomy_policy_version,
        "integrity_policy_version": policies.integrity_policy_version,
        "capacity_policy_version": capacity.version,
        "filter_policy_version": policies.filter_policy_version,
        "filter_policy": policies.filter_policy,
        "aggregation_policy_version": policies.aggregation_policy_version,
        "aggregation_policy": policies.aggregation_policy,
        "progressive_policy_version": policies.progressive_policy_version,
        "progressive_policy": policies.progressive_policy,
        "max_input_versions": capacity.max_input_versions,
        "max_nodes": capacity.max_nodes,
        "max_edges": capacity.max_edges,
        "max_evidence_uses": capacity.max_evidence_uses,
        "max_evidence_uses_per_edge": capacity.max_evidence_uses_per_edge,
        "max_serialized_bytes": capacity.max_serialized_bytes,
        "max_progressive_chunks": capacity.max_progressive_chunks,
        "max_items_per_chunk": capacity.max_items_per_chunk,
        "max_label_length": capacity.max_label_length,
        "max_metadata_length": capacity.max_metadata_length,
    }


def compute_graph_algorithm_parameters_hash(
    policies: GraphPolicySet,
    taxonomy: GraphTaxonomy,
) -> str:
    return compute_canonical_payload_hash(
        graph_algorithm_parameters(policies, taxonomy)
    )


def compute_graph_input_hash(value: GraphArtifactCandidate | dict[str, Any]) -> str:
    payload = _payload(value)
    return compute_canonical_payload_hash(
        {
            "project_id": payload.get("project_id"),
            "input_versions": payload.get("input_versions"),
            "taxonomy": payload.get("taxonomy"),
            "policies": payload.get("policies"),
            "producer": payload.get("producer"),
            "scope": payload.get("scope"),
            "evidence_uses": payload.get("evidence_uses"),
            "source_snapshots": payload.get("source_snapshots"),
        }
    )


def compute_graph_scientific_hash(
    value: GraphArtifactCandidate | dict[str, Any],
) -> str:
    payload = _payload(value)
    return compute_canonical_payload_hash(
        {
            "kind": payload.get("kind"),
            "schema_version": payload.get("schema_version"),
            "project_id": payload.get("project_id"),
            "input_versions": payload.get("input_versions"),
            "taxonomy": payload.get("taxonomy"),
            "policies": payload.get("policies"),
            "scope": payload.get("scope"),
            "nodes": payload.get("nodes"),
            "edges": payload.get("edges"),
            "evidence_uses": payload.get("evidence_uses"),
            "source_snapshots": payload.get("source_snapshots"),
        }
    )


def compute_graph_layout_hash(value: GraphArtifactCandidate | dict[str, Any]) -> str:
    return compute_canonical_payload_hash(
        {"layout_hint": _payload(value).get("layout_hint")}
    )


def compute_graph_output_hash(value: GraphArtifactCandidate | dict[str, Any]) -> str:
    payload = _payload(value)
    payload.pop("output_hash", None)
    # Progressive chunks are an admission/delivery envelope. Their completeness and
    # capacity are validated before candidate assembly, but a different partition of
    # the same complete logical item set must not create a different final Graph.
    payload.pop("progressive", None)
    return compute_canonical_payload_hash(payload)


def compute_graph_public_payload_hash(
    value: GraphArtifactCandidate | dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(_payload(value))


def compute_graph_benchmark_case_hash(
    value: GraphBenchmarkEvaluationCase | dict[str, Any],
) -> str:
    payload = _payload(value)
    payload.pop("content_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_graph_benchmark_output_hash(
    value: GraphBenchmarkReport | dict[str, Any],
) -> str:
    payload = _payload(value)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def build_graph_admission_snapshot(
    candidate: GraphArtifactCandidate,
    *,
    input_json: str,
) -> GraphAdmissionSnapshot:
    return _build_graph_admission_snapshot(
        candidate,
        input_json=input_json,
        public_payload_hash=compute_graph_public_payload_hash(candidate),
    )


__all__ = [
    "GraphAdmissionResult",
    "GraphAlgorithmProducer",
    "GraphArtifactCandidate",
    "GraphArtifactEdge",
    "GraphArtifactNode",
    "GraphArtifactVersionReference",
    "GraphBenchmarkCaseKind",
    "GraphBenchmarkCaseResult",
    "GraphBenchmarkEvaluationCase",
    "GraphBenchmarkMetric",
    "GraphBenchmarkReport",
    "GraphBuildRequest",
    "GraphBuildScope",
    "GraphCapacityPolicy",
    "GraphEvidenceUse",
    "GraphInputRole",
    "GraphInputVersionClosure",
    "GraphIntegrityCounts",
    "GraphIntegrityFinding",
    "GraphIntegrityReport",
    "GraphIntegrityStage",
    "GraphIntegrityStatus",
    "GraphLayoutHint",
    "GraphLogicalReferencePart",
    "GraphNodeVersionBinding",
    "GraphPolicySet",
    "GraphProgressiveChunk",
    "GraphProgressiveInput",
    "GraphRelationTraceBinding",
    "GraphRejectionReason",
    "GraphSourceSnapshotReference",
    "GraphStructuralEdgeRequest",
    "GraphTaxonomy",
]
