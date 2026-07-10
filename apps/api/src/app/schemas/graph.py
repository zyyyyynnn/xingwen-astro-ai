"""Graph schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import GraphEdgeType, GraphNodeType


class GraphNode(BaseModel):
    id: str
    type: GraphNodeType | str
    label: str
    ref_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: GraphEdgeType | str
    relation_id: str | None = None
    reasoning_trace_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
