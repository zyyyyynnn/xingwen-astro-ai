"""Stable logical identities owned by the D-05 graph pipeline.

This module intentionally has no dependency on the graph artifact schema.  It
only turns authoritative logical references into opaque IDs.  Presentation
properties and ArtifactVersion bindings therefore cannot accidentally change
node or edge identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TypeVar

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import GraphEdgeType, GraphNodeType, LiteratureRelationType


class GraphIdentityError(ValueError):
    """A logical graph identity is incomplete or violates edge direction."""


_IdentityValue = TypeVar("_IdentityValue")


_GENERATED_NODE_TYPES = frozenset(
    {
        GraphNodeType.research_goal,
        GraphNodeType.dataset,
        GraphNodeType.field,
        GraphNodeType.paper,
        GraphNodeType.claim,
    }
)

_STRUCTURAL_EDGE_ENDPOINTS = {
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
}

_LITERATURE_RELATION_GRAPH_EDGE_TYPES = {
    LiteratureRelationType.supports: GraphEdgeType.supports,
    LiteratureRelationType.extends: GraphEdgeType.extends,
    LiteratureRelationType.derived_from: GraphEdgeType.derived_from,
    LiteratureRelationType.limits: GraphEdgeType.limits,
    LiteratureRelationType.contradicts: GraphEdgeType.contradicts,
    LiteratureRelationType.uses_same_dataset: GraphEdgeType.uses_same_dataset,
    LiteratureRelationType.compares_method: GraphEdgeType.compares_method,
}


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphIdentityError(f"{label} must be nonempty text")
    return value.strip()


def _digest_suffix(payload: object) -> str:
    return compute_canonical_payload_hash(payload).removeprefix("sha256:")[:24]


@dataclass(frozen=True, slots=True)
class GraphNodeIdentity:
    """Stable node identity: node type plus its authoritative logical reference."""

    node_type: GraphNodeType
    logical_reference: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if type(self.node_type) is not GraphNodeType:
            raise GraphIdentityError("node_type must be a typed GraphNodeType")
        if self.node_type not in _GENERATED_NODE_TYPES:
            raise GraphIdentityError(
                f"D-05 does not generate {self.node_type.value!r} nodes"
            )
        if not isinstance(self.logical_reference, tuple) or not self.logical_reference:
            raise GraphIdentityError("logical_reference must be a nonempty tuple")

        normalized: list[tuple[str, str]] = []
        for part in self.logical_reference:
            if (
                not isinstance(part, tuple)
                or len(part) != 2
                or not isinstance(part[0], str)
                or not isinstance(part[1], str)
            ):
                raise GraphIdentityError(
                    "logical_reference parts must be exact (name, value) tuples"
                )
            normalized.append(
                (
                    _require_text(part[0], "logical reference name"),
                    _require_text(part[1], "logical reference value"),
                )
            )
        ordered = tuple(sorted(normalized))
        names = tuple(name for name, _ in ordered)
        if len(names) != len(set(names)):
            raise GraphIdentityError("logical_reference names must be unique")
        object.__setattr__(self, "logical_reference", ordered)

    @property
    def node_id(self) -> str:
        payload = {
            "node_type": self.node_type.value,
            "logical_reference": [
                {"name": name, "value": value}
                for name, value in self.logical_reference
            ],
        }
        return f"node.{self.node_type.value}_{_digest_suffix(payload)}"


def research_goal_node_identity(research_goal_id: str) -> GraphNodeIdentity:
    """Create a stable ResearchGoal node identity from its logical ID."""

    return GraphNodeIdentity(
        node_type=GraphNodeType.research_goal,
        logical_reference=(("research_goal_id", research_goal_id),),
    )


def dataset_node_identity(research_artifact_id: str) -> GraphNodeIdentity:
    """Use ResearchArtifact.artifact_id as the Dataset logical identity."""

    return GraphNodeIdentity(
        node_type=GraphNodeType.dataset,
        logical_reference=(("artifact_id", research_artifact_id),),
    )


def field_node_identity(
    field_manifest_id: str,
    canonical_field_id: str,
) -> GraphNodeIdentity:
    """Use manifest plus canonical field ID as the Field logical identity."""

    return GraphNodeIdentity(
        node_type=GraphNodeType.field,
        logical_reference=(
            ("field_manifest_id", field_manifest_id),
            ("canonical_field_id", canonical_field_id),
        ),
    )


def paper_node_identity(canonical_paper_id: str) -> GraphNodeIdentity:
    """Create a stable Paper node identity from the canonical paper ID."""

    return GraphNodeIdentity(
        node_type=GraphNodeType.paper,
        logical_reference=(("canonical_paper_id", canonical_paper_id),),
    )


def claim_node_identity(claim_id: str) -> GraphNodeIdentity:
    """Create a stable Claim node identity from the claim logical ID."""

    return GraphNodeIdentity(
        node_type=GraphNodeType.claim,
        logical_reference=(("claim_id", claim_id),),
    )


@dataclass(frozen=True, slots=True)
class GraphNodeVersionBinding:
    """Bind a stable node to one input version without changing node identity."""

    node_id: str
    upstream_artifact_version_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _require_text(self.node_id, "node_id"))
        object.__setattr__(
            self,
            "upstream_artifact_version_id",
            _require_text(
                self.upstream_artifact_version_id,
                "upstream_artifact_version_id",
            ),
        )


@dataclass(frozen=True, slots=True)
class GraphEdgeIdentity:
    """Direction-sensitive graph edge identity with strict endpoint semantics."""

    edge_type: GraphEdgeType | LiteratureRelationType
    source: GraphNodeIdentity
    target: GraphNodeIdentity
    relation_logical_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.source) is not GraphNodeIdentity or type(
            self.target
        ) is not GraphNodeIdentity:
            raise GraphIdentityError("edge endpoints must be GraphNodeIdentity values")
        if self.source.node_id == self.target.node_id:
            raise GraphIdentityError("graph edges may not be self-referential")

        if type(self.edge_type) is GraphEdgeType:
            expected = _STRUCTURAL_EDGE_ENDPOINTS.get(self.edge_type)
            if expected is None:
                raise GraphIdentityError(
                    f"{self.edge_type.value!r} is not a D-05 structural edge"
                )
            if self.relation_logical_id is not None:
                raise GraphIdentityError(
                    "structural edges cannot carry relation_logical_id"
                )
        elif type(self.edge_type) is LiteratureRelationType:
            expected = (GraphNodeType.claim, GraphNodeType.claim)
            object.__setattr__(
                self,
                "relation_logical_id",
                _require_text(self.relation_logical_id, "relation_logical_id"),
            )
        else:
            raise GraphIdentityError(
                "edge_type must be a typed GraphEdgeType or LiteratureRelationType"
            )

        actual = (self.source.node_type, self.target.node_type)
        if actual != expected:
            raise GraphIdentityError(
                f"{self.edge_type.value} requires {expected[0].value} -> "
                f"{expected[1].value}, got {actual[0].value} -> {actual[1].value}"
            )

    @property
    def edge_id(self) -> str:
        is_relation = type(self.edge_type) is LiteratureRelationType
        payload = {
            "edge_class": "literature_relation" if is_relation else "structural",
            "edge_type": self.edge_type.value,
            "source_node_id": self.source.node_id,
            "target_node_id": self.target.node_id,
            "relation_logical_id": self.relation_logical_id,
        }
        return f"edge.{self.edge_type.value}_{_digest_suffix(payload)}"


def uses_dataset_edge_identity(
    research_goal: GraphNodeIdentity,
    dataset: GraphNodeIdentity,
) -> GraphEdgeIdentity:
    """Create the only allowed uses_dataset direction: goal -> dataset."""

    return GraphEdgeIdentity(
        edge_type=GraphEdgeType.uses_dataset,
        source=research_goal,
        target=dataset,
    )


def provides_field_edge_identity(
    dataset: GraphNodeIdentity,
    field: GraphNodeIdentity,
) -> GraphEdgeIdentity:
    """Create the only allowed provides_field direction: dataset -> field."""

    return GraphEdgeIdentity(
        edge_type=GraphEdgeType.provides_field,
        source=dataset,
        target=field,
    )


def supports_finding_edge_identity(
    paper: GraphNodeIdentity,
    claim: GraphNodeIdentity,
) -> GraphEdgeIdentity:
    """Create the D-05 paper -> claim supports_finding edge."""

    return GraphEdgeIdentity(
        edge_type=GraphEdgeType.supports_finding,
        source=paper,
        target=claim,
    )


def literature_relation_edge_identity(
    source_claim: GraphNodeIdentity,
    target_claim: GraphNodeIdentity,
    *,
    relation_type: LiteratureRelationType,
    relation_logical_id: str,
) -> GraphEdgeIdentity:
    """Create a strict source-claim -> target-claim LiteratureRelation edge."""

    return GraphEdgeIdentity(
        edge_type=relation_type,
        source=source_claim,
        target=target_claim,
        relation_logical_id=relation_logical_id,
    )


def graph_edge_type_for_literature_relation(
    relation_type: LiteratureRelationType,
) -> GraphEdgeType:
    """Map an upstream Relation type into the frozen v1 Graph taxonomy.

    Stable identity can be computed for every upstream Relation type, but a
    Graph edge is publishable only when the frozen GraphEdgeType has an exact
    value match.  D-05 admission turns this failure into ``taxonomy_violation``.
    """

    if type(relation_type) is not LiteratureRelationType:
        raise GraphIdentityError(
            "relation_type must be a typed LiteratureRelationType"
        )
    try:
        return _LITERATURE_RELATION_GRAPH_EDGE_TYPES[relation_type]
    except KeyError as exc:
        raise GraphIdentityError(
            f"{relation_type.value!r} is outside the D-05 v1 GraphEdgeType taxonomy"
        ) from exc


def graph_evidence_use_id(
    *,
    graph_edge_id: str,
    upstream_artifact_version_id: str,
    upstream_evidence_id: str,
) -> str:
    """Derive graph-owned Evidence-use ID from the complete upstream binding."""

    payload = {
        "graph_edge_id": _require_text(graph_edge_id, "graph_edge_id"),
        "upstream_artifact_version_id": _require_text(
            upstream_artifact_version_id,
            "upstream_artifact_version_id",
        ),
        "upstream_evidence_id": _require_text(
            upstream_evidence_id,
            "upstream_evidence_id",
        ),
    }
    return f"evidence.graph_use_{_digest_suffix(payload)}"


def _canonical_unique_order(
    values: Iterable[_IdentityValue],
    *,
    key: Callable[[_IdentityValue], str],
    label: str,
) -> tuple[_IdentityValue, ...]:
    materialized = tuple(values)
    ordered = tuple(sorted(materialized, key=key))
    identities = tuple(key(item) for item in ordered)
    if len(identities) != len(set(identities)):
        raise GraphIdentityError(f"{label} identities must be unique")
    return ordered


def canonical_node_order(
    nodes: Iterable[GraphNodeIdentity],
) -> tuple[GraphNodeIdentity, ...]:
    """Return deterministic node order independent of presentation order."""

    materialized = tuple(nodes)
    if any(type(node) is not GraphNodeIdentity for node in materialized):
        raise GraphIdentityError("canonical_node_order requires node identities")
    return _canonical_unique_order(
        materialized,
        key=lambda node: node.node_id,
        label="node",
    )


def canonical_edge_order(
    edges: Iterable[GraphEdgeIdentity],
) -> tuple[GraphEdgeIdentity, ...]:
    """Return deterministic edge order independent of presentation order."""

    materialized = tuple(edges)
    if any(type(edge) is not GraphEdgeIdentity for edge in materialized):
        raise GraphIdentityError("canonical_edge_order requires edge identities")
    return _canonical_unique_order(
        materialized,
        key=lambda edge: edge.edge_id,
        label="edge",
    )


def canonical_evidence_use_order(evidence_use_ids: Iterable[str]) -> tuple[str, ...]:
    """Return deterministic graph-owned Evidence-use ID order."""

    normalized = tuple(
        _require_text(value, "evidence_use_id") for value in evidence_use_ids
    )
    ordered = tuple(sorted(normalized))
    if len(ordered) != len(set(ordered)):
        raise GraphIdentityError("Evidence-use identities must be unique")
    return ordered


__all__ = [
    "GraphEdgeIdentity",
    "GraphIdentityError",
    "GraphNodeIdentity",
    "GraphNodeVersionBinding",
    "canonical_edge_order",
    "canonical_evidence_use_order",
    "canonical_node_order",
    "claim_node_identity",
    "dataset_node_identity",
    "field_node_identity",
    "graph_edge_type_for_literature_relation",
    "graph_evidence_use_id",
    "literature_relation_edge_identity",
    "paper_node_identity",
    "provides_field_edge_identity",
    "research_goal_node_identity",
    "supports_finding_edge_identity",
    "uses_dataset_edge_identity",
]
