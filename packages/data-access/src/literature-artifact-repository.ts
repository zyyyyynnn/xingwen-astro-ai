/**
 * Read adapters for the public LiteratureClaim, LiteratureRelation and
 * ReasoningTrace projections.
 *
 * These endpoints are generated in the Core contract, but their model names
 * are not yet registered in the frontend contract validator. The HTTP path
 * therefore performs a small required-shape check before mapping; malformed
 * payloads fail closed instead of becoming an empty or raw JSON view.
 */

import type {
  ArtifactVersionDetailDto,
  LiteratureClaimRead,
  LiteratureRelationRead,
  SourceSnapshotDetail as SourceSnapshotDetailDto,
} from "@xingwen/contracts";
import type {
  ContentHash,
  DomainEntityId,
  LiteratureArtifactVersionReview,
  LiteratureClaimReferenceReview,
  LiteratureClaimReview,
  LiteratureClaimsArtifactReview,
  LiteratureRelationReview,
  LiteratureRelationsArtifactReview,
  LiteratureReasoningTraceReview,
  LiteratureReasoningTraceStepReview,
  PublicArtifactPresentation,
  SourceMode,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { ValidationError, NotFoundError } from "./errors";
import { HttpClient, seg } from "./http-client";
import { mapPublicArtifactPresentation } from "./mapping";
import {
  mapSnapshotSummary,
  parseContract,
} from "./paper-acquisition-repository";
import type { LiteratureArtifactRepository } from "./ports";

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

function requiredRead(value: unknown, label: string): Record<string, unknown> {
  const root = record(value);
  const version = root ? record(root.version) : null;
  if (
    !root ||
    !version ||
    typeof version.artifact_id !== "string" ||
    typeof version.artifact_version_id !== "string" ||
    typeof version.project_id !== "string" ||
    typeof version.schema_version !== "string" ||
    typeof version.version_number !== "number" ||
    typeof version.content_hash !== "string" ||
    typeof version.input_hash !== "string" ||
    typeof version.output_hash !== "string" ||
    typeof version.created_at !== "string" ||
    typeof version.source_mode !== "string" ||
    !Array.isArray(root.evidence) ||
    !Array.isArray(root.source_snapshots)
  ) {
    throw invalid(`${label} read failed its required version/provenance shape`);
  }
  return root;
}

function evidenceIds(value: unknown): DomainEntityId[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => record(item)?.id)
    .filter((item): item is string => typeof item === "string")
    .map(id);
}

function snapshotList(value: unknown): ReturnType<typeof mapSnapshotSummary>[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) =>
    mapSnapshotSummary(item as SourceSnapshotDetailDto),
  );
}

type LiteratureArtifactVersionMetadata = Omit<
  LiteratureArtifactVersionReview,
  "presentation"
>;

function versionOf(
  value: LiteratureClaimRead["version"],
  sourceSnapshots: readonly ReturnType<typeof mapSnapshotSummary>[],
  evidence: readonly DomainEntityId[],
): LiteratureArtifactVersionMetadata {
  return {
    artifactVersionId: id(value.artifact_version_id),
    artifactId: id(value.artifact_id),
    projectId: id(value.project_id),
    versionNumber: value.version_number,
    schemaVersion: value.schema_version,
    sourceMode: value.source_mode as SourceMode,
    contentHash: value.content_hash as ContentHash,
    inputHash: value.input_hash as ContentHash,
    outputHash: value.output_hash as ContentHash,
    createdAt: value.created_at as UtcIsoTimestamp,
    sourceSnapshots,
    evidenceIds: [...evidence],
  };
}

function claimReference(
  read: LiteratureClaimRead | null,
): LiteratureClaimReferenceReview | null {
  if (!read) return null;
  const claim = read.claim;
  return {
    claimId: id(claim.claim_id),
    text: claim.text,
    normalizedText: claim.normalized_text,
    status: claim.status,
    claimType: claim.claim_type,
    polarity: claim.polarity,
    paperId: claim.paper_id ? id(claim.paper_id) : null,
  };
}

export function mapLiteratureClaimRead(
  read: LiteratureClaimRead,
): LiteratureClaimReview {
  const claim = read.claim;
  const persistedEvidenceIds = evidenceIds(read.evidence);
  return {
    ...claimReference(read)!,
    objects: [...claim.objects],
    scope: [...claim.scope],
    conditions: [...claim.conditions],
    qualifiers: [...claim.qualifiers],
    limitations: [...claim.limitations],
    metric: claim.metric ?? null,
    unit: claim.unit ?? null,
    uncertainty: claim.uncertainty ?? null,
    comparisonBasis: claim.comparison_basis ?? null,
    sourceStatementId: claim.source_statement_id
      ? id(claim.source_statement_id)
      : null,
    sourceSummaryId: claim.source_summary_id
      ? id(claim.source_summary_id)
      : null,
    sourcePaperSummaryArtifactVersionId:
      claim.source_paper_summary_artifact_version_id
        ? id(claim.source_paper_summary_artifact_version_id)
        : null,
    sourceSnapshotIds: claim.source_snapshot_ids.map(id),
    evidenceIds: persistedEvidenceIds,
    failureStage: claim.failure_stage ?? null,
    rejectionReason: claim.rejection_reason ?? null,
  };
}

function mapTraceCandidate(
  trace: NonNullable<LiteratureRelationRead["reasoning_trace"]>,
  persistedEvidenceIds: readonly DomainEntityId[],
): LiteratureReasoningTraceReview {
  return {
    traceId: id(trace.trace_id),
    relationId: trace.relation_id ? id(trace.relation_id) : null,
    relationStatus: trace.relation_status,
    conclusion: trace.conclusion,
    premiseClaimIds: trace.premise_claim_ids
      .filter((item): item is string => typeof item === "string")
      .map(id),
    conditions: [...trace.conditions],
    conflicts: [...trace.conflicts],
    limitations: [...trace.limitations],
    steps: trace.steps.map((step): LiteratureReasoningTraceStepReview => ({
      order: step.order,
      operation: step.operation,
      statement: step.statement,
      claimIds: step.claim_ids.map(id),
      evidenceIds: step.evidence_ids
        .filter((evidenceId) => persistedEvidenceIds.includes(id(evidenceId)))
        .map(id),
    })),
    evidenceIds: [...persistedEvidenceIds],
    protocolVersion: trace.trace_protocol_version,
  };
}

function mapRelation(read: LiteratureRelationRead): LiteratureRelationReview {
  const relation = read.relation;
  const confidence = relation.confidence;
  const persistedEvidenceIds = evidenceIds(read.evidence);
  return {
    relationId: id(relation.relation_id),
    pairId: relation.pair_id,
    relationType: relation.relation_type,
    status: relation.status,
    sourceClaimId: relation.source_claim_id
      ? id(relation.source_claim_id)
      : null,
    targetClaimId: relation.target_claim_id
      ? id(relation.target_claim_id)
      : null,
    reasoningTraceId: relation.reasoning_trace_id
      ? id(relation.reasoning_trace_id)
      : null,
    graphEligible: read.graph_eligible,
    direction: {
      basis: relation.direction.basis,
      sourceClaimId: relation.direction.source_claim_id
        ? id(relation.direction.source_claim_id)
        : null,
      targetClaimId: relation.direction.target_claim_id
        ? id(relation.direction.target_claim_id)
        : null,
    },
    comparability: {
      metricBasis: relation.comparability.metric_basis,
      metricStatus: relation.comparability.metric_status,
      objectBasis: relation.comparability.object_basis,
      objectStatus: relation.comparability.object_status,
      unitBasis: relation.comparability.unit_basis,
      unitStatus: relation.comparability.unit_status,
    },
    conditions: [...relation.conditions],
    conditionConflicts: [...relation.condition_conflicts],
    conditionUncertainties: [...relation.condition_uncertainties],
    confidence: confidence
      ? {
          score: confidence.score ?? null,
          status: confidence.status,
          decision: confidence.decision,
          acceptanceThreshold: confidence.acceptance_threshold,
        }
      : null,
    evidenceIds: persistedEvidenceIds,
    sourceSnapshotIds: relation.source_snapshot_ids.map(id),
    sourceClaim: claimReference(read.source_claim),
    targetClaim: claimReference(read.target_claim),
    reasoningTrace: read.reasoning_trace
      ? mapTraceCandidate(read.reasoning_trace, persistedEvidenceIds)
      : null,
    failureStage: relation.failure_stage ?? null,
    rejectionReason: relation.rejection_reason ?? null,
  };
}

export function mapLiteratureRelationRead(
  read: LiteratureRelationRead,
): LiteratureRelationReview {
  return mapRelation(read);
}

function claimRead(value: unknown): LiteratureClaimRead {
  const root = requiredRead(value, "LiteratureClaim");
  if (!record(root.claim) || !record(root.paper_summary)) {
    throw invalid("LiteratureClaim read lacks claim or paper summary");
  }
  return value as LiteratureClaimRead;
}

function relationRead(value: unknown): LiteratureRelationRead {
  const root = requiredRead(value, "LiteratureRelation");
  if (!record(root.relation)) {
    throw invalid("LiteratureRelation read lacks relation payload");
  }
  return value as LiteratureRelationRead;
}

function sameVersion(
  versions: readonly LiteratureArtifactVersionMetadata[],
): LiteratureArtifactVersionMetadata {
  const first = versions[0];
  if (!first) throw invalid("Literature artifact returned no version context");
  for (const version of versions.slice(1)) {
    if (
      version.artifactVersionId !== first.artifactVersionId ||
      version.artifactId !== first.artifactId ||
      version.projectId !== first.projectId
    ) {
      throw invalid("Literature artifact page returned mixed version context");
    }
  }
  return first;
}

function assembleClaims(
  reads: readonly LiteratureClaimRead[],
  presentation: PublicArtifactPresentation,
): LiteratureClaimsArtifactReview {
  const versions = reads.map((read) =>
    versionOf(
      read.version,
      snapshotList(read.source_snapshots),
      evidenceIds(read.evidence),
    ),
  );
  const version = sameVersion(versions);
  return {
    ...version,
    kind: "literature_claims",
    presentation,
    claims: reads.map(mapLiteratureClaimRead),
  };
}

function assembleRelations(
  reads: readonly LiteratureRelationRead[],
  presentation: PublicArtifactPresentation,
): LiteratureRelationsArtifactReview {
  const versions = reads.map((read) =>
    versionOf(
      read.version,
      snapshotList(read.source_snapshots),
      evidenceIds(read.evidence),
    ),
  );
  const version = sameVersion(versions);
  return {
    ...version,
    kind: "literature_relations",
    presentation,
    relations: reads.map(mapRelation),
  };
}

async function emptyVersion(
  http: HttpClient,
  artifactVersionId: DomainEntityId,
): Promise<
  LiteratureArtifactVersionReview & {
    readonly presentation: PublicArtifactPresentation;
  }
> {
  const detail = parseContract<ArtifactVersionDetailDto>(
    "ArtifactVersionDetail",
    await http.getRequired<unknown>(
      `/api/artifact-versions/${seg(artifactVersionId)}`,
    ),
  );
  if (detail.id !== artifactVersionId) {
    throw invalid(
      "Literature collection is pinned to a different ArtifactVersion",
    );
  }
  return {
    artifactVersionId: id(detail.id),
    artifactId: id(detail.artifact_id),
    projectId: id(detail.project_id),
    versionNumber: detail.version_number,
    schemaVersion: detail.schema_version,
    sourceMode: detail.source_mode as SourceMode,
    contentHash: detail.content_hash as ContentHash,
    inputHash: detail.input_hash as ContentHash,
    outputHash: null,
    createdAt: detail.created_at as UtcIsoTimestamp,
    sourceSnapshots: detail.source_snapshots.map(mapSnapshotSummary),
    evidenceIds: (
      detail.evidence_ids ?? detail.evidence.map((item) => item.id)
    ).map(id),
    presentation: mapPublicArtifactPresentation(detail.presentation),
  };
}

export function createLiteratureArtifactRepository(
  http: HttpClient,
): LiteratureArtifactRepository {
  return {
    async getClaims(artifactVersionId) {
      const [payloads, version] = await Promise.all([
        http.list<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/literature-claims`,
        ),
        emptyVersion(http, artifactVersionId),
      ]);
      const rows = payloads.map(claimRead);
      if (rows.length === 0) {
        return {
          ...version,
          kind: "literature_claims" as const,
          claims: [],
        };
      }
      return assembleClaims(rows, version.presentation);
    },
    async getRelations(artifactVersionId) {
      const [payloads, version] = await Promise.all([
        http.list<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/literature-relations`,
        ),
        emptyVersion(http, artifactVersionId),
      ]);
      const rows = payloads.map(relationRead);
      if (rows.length === 0) {
        return {
          ...version,
          kind: "literature_relations" as const,
          relations: [],
        };
      }
      return assembleRelations(rows, version.presentation);
    },
  };
}

function fixtureRepository(
  claims: readonly LiteratureClaimRead[],
  relations: readonly LiteratureRelationRead[],
  presentations: Readonly<Record<string, PublicArtifactPresentation>>,
): LiteratureArtifactRepository {
  const presentation = (
    artifactVersionId: DomainEntityId,
  ): PublicArtifactPresentation => {
    const value = presentations[String(artifactVersionId)];
    if (!value) {
      throw new NotFoundError(
        `Artifact presentation ${artifactVersionId} not found`,
        "ARTIFACT_VERSION_NOT_FOUND",
      );
    }
    return value;
  };
  const requireRows = <
    Read extends { readonly version: { readonly artifact_version_id: string } },
  >(
    reads: readonly Read[],
    artifactVersionId: DomainEntityId,
    label: string,
  ): readonly Read[] => {
    const rows = reads.filter(
      (item) => item.version.artifact_version_id === artifactVersionId,
    );
    if (rows.length === 0) {
      throw new NotFoundError(
        `${label} ${artifactVersionId} not found`,
        "ARTIFACT_VERSION_NOT_FOUND",
      );
    }
    return rows;
  };

  return {
    getClaims: async (artifactVersionId) => {
      return assembleClaims(
        requireRows(claims, artifactVersionId, "Literature claims"),
        presentation(artifactVersionId),
      );
    },
    getRelations: async (artifactVersionId) => {
      return assembleRelations(
        requireRows(relations, artifactVersionId, "Literature relations"),
        presentation(artifactVersionId),
      );
    },
  };
}

export function createFixtureLiteratureArtifactRepository(
  claims: readonly LiteratureClaimRead[],
  relations: readonly LiteratureRelationRead[],
  presentations: Readonly<Record<string, PublicArtifactPresentation>>,
): LiteratureArtifactRepository {
  return fixtureRepository(claims, relations, presentations);
}
