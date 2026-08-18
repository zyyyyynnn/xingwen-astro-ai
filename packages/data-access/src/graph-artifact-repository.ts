/** Read adapter for the governed Evidence Graph projection. */

import type {
  GraphArtifactRead,
  GraphEdgeRead,
  GraphNodeRead,
} from "@xingwen/contracts";
import type {
  ContentHash,
  DomainEntityId,
  GraphArtifactReview,
  GraphDataAggregationReview,
  GraphEdgeReview,
  GraphIntegrityReview,
  GraphNodeReview,
  GraphRelationTraceBindingReview,
  GraphVersionReferenceReview,
  SourceMode,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { ValidationError, NotFoundError } from "./errors";
import { HttpClient, seg } from "./http-client";
import { mapLiteratureRelationRead } from "./literature-artifact-repository";
import type { GraphArtifactRepository } from "./ports";

function id(value: string): DomainEntityId {
  return asEntityId(value);
}

function invalid(detail: string): ValidationError {
  return new ValidationError(detail, "SCHEMA_VALIDATION_FAILED", []);
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : null;
}

function requiredGraph(value: unknown): GraphArtifactRead {
  const root = record(value);
  const version = root ? record(root.version) : null;
  const integrity = root ? record(root.integrity_report) : null;
  const inputVersions = root ? record(root.input_versions) : null;
  if (
    !root ||
    !version ||
    !integrity ||
    !inputVersions ||
    typeof root.graph_id !== "string" ||
    typeof root.project_id !== "string" ||
    typeof root.node_count !== "number" ||
    typeof root.edge_count !== "number" ||
    typeof root.evidence_use_count !== "number" ||
    typeof version.artifact_id !== "string" ||
    typeof version.artifact_version_id !== "string" ||
    typeof version.project_id !== "string" ||
    typeof version.schema_version !== "string" ||
    typeof version.version_number !== "number" ||
    typeof version.content_hash !== "string" ||
    typeof version.input_hash !== "string" ||
    typeof version.created_at !== "string" ||
    typeof version.source_mode !== "string" ||
    typeof integrity.status !== "string" ||
    !Array.isArray(integrity.findings) ||
    !Array.isArray(inputVersions.versions)
  ) {
    throw invalid("Graph read failed its required metadata shape");
  }
  return value as GraphArtifactRead;
}

function requiredNode(value: unknown): GraphNodeRead {
  const root = record(value);
  const node = root ? record(root.node) : null;
  const version = root ? record(root.version) : null;
  if (
    !root ||
    !node ||
    !version ||
    typeof node.node_id !== "string" ||
    typeof node.node_type !== "string" ||
    typeof node.label !== "string" ||
    !Array.isArray(node.logical_reference) ||
    !Array.isArray(node.version_bindings)
  ) {
    throw invalid("Graph node read failed its required shape");
  }
  return value as GraphNodeRead;
}

function requiredEdge(value: unknown): GraphEdgeRead {
  const root = record(value);
  const edge = root ? record(root.edge) : null;
  const version = root ? record(root.version) : null;
  if (
    !root ||
    !edge ||
    !version ||
    typeof edge.edge_id !== "string" ||
    typeof edge.edge_type !== "string" ||
    typeof edge.source_node_id !== "string" ||
    typeof edge.target_node_id !== "string" ||
    !Array.isArray(edge.evidence_use_ids)
  ) {
    throw invalid("Graph edge read failed its required shape");
  }
  return value as GraphEdgeRead;
}

function mapVersionReference(
  value: GraphArtifactRead["input_versions"]["versions"][number],
): GraphVersionReferenceReview {
  return {
    artifactId: id(value.artifact_id),
    artifactVersionId: id(value.artifact_version_id),
    projectId: id(value.project_id),
    kind: value.kind,
    role: value.role,
    versionNumber: value.version_number,
    schemaVersion: value.schema_version,
    sourceMode: value.source_mode as SourceMode,
    contentHash: value.content_hash as ContentHash,
  };
}

function mapIntegrity(
  report: GraphArtifactRead["integrity_report"],
): GraphIntegrityReview {
  return {
    status: report.status,
    counts: {
      edgeCount: report.counts.edge_count,
      evidenceUseCount: report.counts.evidence_use_count,
      inputVersionCount: report.counts.input_version_count,
      nodeCount: report.counts.node_count,
      relationEdgeCount: report.counts.relation_edge_count,
      sourceSnapshotCount: report.counts.source_snapshot_count,
    },
    findings: report.findings.map((finding) => ({
      stage: finding.stage,
      reason: finding.reason,
      priority: finding.priority,
      path: finding.path,
      message: finding.message,
    })),
  };
}

function mapNode(read: GraphNodeRead): GraphNodeReview {
  return {
    nodeId: id(read.node.node_id),
    nodeType: read.node.node_type,
    label: read.node.label,
    logicalReference: read.node.logical_reference.map((part) => ({
      name: part.name,
      value: part.value,
    })),
    versionBindings: read.node.version_bindings.map((binding) => ({
      artifactVersionId: id(binding.artifact_version_id),
      domainObjectId: id(binding.domain_object_id),
    })),
  };
}

function mapAggregation(
  aggregation: NonNullable<GraphEdgeRead["edge"]["data_aggregation"]>,
): GraphDataAggregationReview {
  return {
    conflictCount: aggregation.conflict_count,
    declaredNullOutcomeCount: aggregation.declared_null_outcome_count,
    mappedOutcomeCount: aggregation.mapped_outcome_count,
    projectedRowCount: aggregation.projected_row_count,
    retainedCandidateCount: aggregation.retained_candidate_count,
    selectedCandidateCount: aggregation.selected_candidate_count,
    unresolvedOutcomeCount: aggregation.unresolved_outcome_count,
    unselectedCandidateCount: aggregation.unselected_candidate_count,
    upstreamEvidenceCount: aggregation.upstream_evidence_count,
  };
}

function mapRelationTrace(
  binding: NonNullable<GraphEdgeRead["edge"]["relation_trace"]>,
): GraphRelationTraceBindingReview {
  return {
    relationId: id(binding.relation_id),
    relationArtifactVersionId: id(binding.relation_artifact_version_id),
    reasoningTraceId: id(binding.reasoning_trace_id),
    relationType: binding.relation_type,
    relationStatus: binding.relation_status ?? null,
    sourceClaimId: id(binding.source_claim_id),
    targetClaimId: id(binding.target_claim_id),
    premiseClaimIds: binding.premise_claim_ids
      .filter((item): item is string => typeof item === "string")
      .map(id),
    traceEvidenceIds: binding.trace_evidence_ids.map(id),
  };
}

function mapEdge(read: GraphEdgeRead): GraphEdgeReview {
  return {
    edgeId: id(read.edge.edge_id),
    edgeType: read.edge.edge_type,
    sourceNodeId: id(read.edge.source_node_id),
    targetNodeId: id(read.edge.target_node_id),
    evidenceUseIds: read.edge.evidence_use_ids.map(id),
    dataAggregation: read.edge.data_aggregation
      ? mapAggregation(read.edge.data_aggregation)
      : null,
    relationTrace: read.edge.relation_trace
      ? mapRelationTrace(read.edge.relation_trace)
      : null,
    relation: read.relation ? mapLiteratureRelationRead(read.relation) : null,
  };
}

function mapGraph(
  read: GraphArtifactRead,
  nodes: readonly GraphNodeRead[],
  edges: readonly GraphEdgeRead[],
): GraphArtifactReview {
  return {
    kind: "graph",
    graphId: id(read.graph_id),
    artifactId: id(read.version.artifact_id),
    artifactVersionId: id(read.version.artifact_version_id),
    projectId: id(read.project_id),
    versionNumber: read.version.version_number,
    schemaVersion: read.version.schema_version,
    sourceMode: read.version.source_mode as SourceMode,
    contentHash: read.version.content_hash as ContentHash,
    inputHash: read.version.input_hash as ContentHash,
    createdAt: read.version.created_at as UtcIsoTimestamp,
    nodeCount: read.node_count,
    edgeCount: read.edge_count,
    evidenceUseCount: read.evidence_use_count,
    inputVersions: read.input_versions.versions.map(mapVersionReference),
    integrity: mapIntegrity(read.integrity_report),
    layoutStrategy: read.layout_hint.strategy ?? "none",
    scopeSummary: [
      ...(read.scope.research_goal_id ? [read.scope.research_goal_id] : []),
      ...(read.scope.literature_paper_ids ?? []),
      ...(read.scope.literature_claim_ids ?? []),
    ],
    taxonomyNodeTypes: read.taxonomy.node_types.map(String),
    taxonomyEdgeTypes: read.taxonomy.edge_types.map(String),
    progressive: {
      chunkCount: read.progressive.chunk_count,
      complete: read.progressive.complete,
    },
    nodes: nodes.map(mapNode),
    edges: edges.map(mapEdge),
  };
}

export function createGraphArtifactRepository(
  http: HttpClient,
): GraphArtifactRepository {
  return {
    async getReview(artifactVersionId) {
      const base = `/api/artifact-versions/${seg(artifactVersionId)}/graph`;
      const read = requiredGraph(await http.getRequired<unknown>(base));
      const nodeRows = (await http.list<unknown>(`${base}/nodes`)).map(
        requiredNode,
      );
      const edgeRows = (await http.list<unknown>(`${base}/edges`)).map(
        requiredEdge,
      );
      if (read.version.artifact_version_id !== artifactVersionId) {
        throw invalid(
          "Graph response is pinned to a different ArtifactVersion",
        );
      }
      return mapGraph(read, nodeRows, edgeRows);
    },
  };
}

export function createFixtureGraphArtifactRepository(
  reads: readonly GraphArtifactRead[],
  nodes: readonly GraphNodeRead[],
  edges: readonly GraphEdgeRead[],
): GraphArtifactRepository {
  return {
    getReview: async (artifactVersionId) => {
      const read = reads.find(
        (item) => item.version.artifact_version_id === artifactVersionId,
      );
      if (!read) {
        throw new NotFoundError(
          `Graph Artifact ${artifactVersionId} not found`,
          "ARTIFACT_VERSION_NOT_FOUND",
        );
      }
      return mapGraph(
        read,
        nodes.filter(
          (item) => item.version.artifact_version_id === artifactVersionId,
        ),
        edges.filter(
          (item) => item.version.artifact_version_id === artifactVersionId,
        ),
      );
    },
  };
}
