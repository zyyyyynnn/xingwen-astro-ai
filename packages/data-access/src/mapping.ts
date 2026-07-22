/**
 * Transport DTO → domain entity mappers.
 *
 * These functions convert snake_case `/api/v2` DTOs (validated by
 * `@xingwen/contracts`) into the camelCase domain model. They are the only
 * place where DTO shapes are referenced; downstream code never sees DTOs.
 */

import type {
  ArtifactKind,
  ArtifactVersion,
  CaseKey,
  ContentHash,
  DataCell,
  DomainEntityId,
  Evidence,
  ExecutionMode,
  ProducerReference,
  ProvenanceState,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchContractInput,
  ResearchProject,
  ResearchRun,
  RunEvent,
  RunStatus,
  SourceMode,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import type {
  ArtifactVersion as ArtifactVersionDto,
  DataRequirements as DataRequirementsDto,
  PaperSearchScope as PaperSearchScopeDto,
  ProducerReference as ProducerReferenceDto,
  ResearchArtifact as ResearchArtifactDto,
  ResearchContract as ResearchContractDto,
  ResearchContractDraft as ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
  ResearchProject as ResearchProjectDto,
  ResearchRun as ResearchRunDto,
  RunEvent as RunEventDto,
} from "@xingwen/contracts";

function mapId(value: string): DomainEntityId {
  return asEntityId(value);
}

function mapIds(
  values: readonly string[] | undefined,
): readonly DomainEntityId[] {
  return (values ?? []).map(mapId);
}

function mapDataRequirements(
  dto: DataRequirementsDto,
): ResearchContractInput["dataRequirements"] {
  return {
    unitPolicy: dto.unit_policy ?? "canonical",
  };
}

function mapPaperSearchScope(
  dto: PaperSearchScopeDto,
): ResearchContractInput["paperSearchScope"] {
  return {
    keywords: [...(dto.keywords ?? [])],
    yearFrom: dto.year_from ?? null,
    yearTo: dto.year_to ?? null,
    sourceIds: mapIds(dto.source_ids),
    maxCandidates: dto.max_candidates ?? 20,
  };
}

function mapContractInput(
  dto: ResearchContractInputDto,
): ResearchContractInput {
  return {
    researchGoal: dto.research_goal,
    targetObjects: mapIds(dto.target_objects),
    dataRequirements: mapDataRequirements(dto.data_requirements),
    requestedFields: mapIds(dto.requested_fields),
    sourceScope: {
      allowedSources: mapIds(dto.source_scope.allowed_sources),
    },
    paperSearchScope: mapPaperSearchScope(dto.paper_search_scope),
    outputRequirements: [
      ...(dto.output_requirements ?? []),
    ] as readonly ArtifactKind[],
    evidenceRequirements: {
      requireLocator: dto.evidence_requirements?.require_locator ?? true,
      requireSourceSnapshot:
        dto.evidence_requirements?.require_source_snapshot ?? true,
      minimumCoverage: dto.evidence_requirements?.minimum_coverage ?? 1,
    },
    qualityConstraints: {
      sourceCompletenessMin:
        dto.quality_constraints?.source_completeness_min ?? 1,
      unitConsistencyMin: dto.quality_constraints?.unit_consistency_min ?? 1,
    },
  };
}

function mapProducer(dto: ProducerReferenceDto): ProducerReference {
  return {
    type: dto.type,
    name: dto.name,
    version: dto.version,
    modelName: dto.model_name ?? null,
    promptName: dto.prompt_name ?? null,
    promptVersion: dto.prompt_version ?? null,
    parametersHash: (dto.parameters_hash ?? null) as ContentHash | null,
  };
}

function mapArtifactContent(
  dto: ArtifactVersionDto["content"],
): ArtifactVersion["content"] {
  switch (dto.kind) {
    case "dataset":
      return {
        kind: "dataset",
        fieldIds: mapIds(dto.field_ids),
        rows: dto.rows.map((row) => ({ ...row }) as Record<string, DataCell>),
      };
    case "field_dictionary":
      return {
        kind: "field_dictionary",
        fieldIds: mapIds(dto.field_ids),
      };
    case "source_collection":
      return {
        kind: "source_collection",
        sourceSnapshotIds: mapIds(dto.source_snapshot_ids),
      };
    case "paper_collection":
      return {
        kind: "paper_collection",
        paperIds: mapIds(dto.paper_ids),
      };
    case "paper_summary":
      return {
        kind: "paper_summary",
        paperId: mapId(dto.paper_id),
        summaryId: mapId(dto.summary_id),
      };
    case "literature_claims":
      return {
        kind: "literature_claims",
        claimIds: mapIds(dto.claim_ids),
      };
    case "literature_relations":
      return {
        kind: "literature_relations",
        relationIds: mapIds(dto.relation_ids),
      };
    case "reasoning_traces":
      return {
        kind: "reasoning_traces",
        reasoningTraceIds: mapIds(dto.reasoning_trace_ids),
      };
    case "graph":
      return {
        kind: "graph",
        nodeIds: mapIds(dto.node_ids),
        edgeIds: mapIds(dto.edge_ids),
      };
    case "export":
      return {
        kind: "export",
        format: dto.format,
        artifactVersionIds: mapIds(dto.artifact_version_ids),
      };
  }
}

export function mapResearchProject(dto: ResearchProjectDto): ResearchProject {
  return {
    id: mapId(dto.id),
    sessionId: mapId(dto.session_id),
    name: dto.name,
    description: dto.description ?? "",
    caseKey: dto.case_key as CaseKey,
    activeContractId: (dto.active_contract_id ?? null) as DomainEntityId | null,
    latestRunId: (dto.latest_run_id ?? null) as DomainEntityId | null,
    createdAt: dto.created_at as UtcIsoTimestamp,
    updatedAt: dto.updated_at as UtcIsoTimestamp,
    revision: dto.revision,
  };
}

export function mapResearchContractDraft(
  dto: ResearchContractDraftDto,
): ResearchContractDraft {
  return {
    id: mapId(dto.id),
    sessionId: mapId(dto.session_id),
    version: dto.version,
    intent: dto.intent,
    status: (dto.status ?? "draft") as ResearchContractDraft["status"],
    contract: mapContractInput(dto.contract),
    warnings: [...(dto.warnings ?? [])],
    createdAt: dto.created_at as UtcIsoTimestamp,
    updatedAt: dto.updated_at as UtcIsoTimestamp,
    expiresAt: dto.expires_at as UtcIsoTimestamp,
  };
}

export function mapResearchContract(
  dto: ResearchContractDto,
): ResearchContract {
  return {
    ...mapContractInput(dto),
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    version: dto.version,
    createdFromDraftId: mapId(dto.created_from_draft_id),
    createdAt: dto.created_at as UtcIsoTimestamp,
    contentHash: dto.content_hash as ContentHash,
  };
}

export function mapResearchRun(dto: ResearchRunDto): ResearchRun {
  return {
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    contractId: mapId(dto.contract_id),
    executionMode: dto.execution_mode as ExecutionMode,
    status: dto.status as RunStatus,
    progress: dto.progress,
    parentRunId: (dto.parent_run_id ?? null) as DomainEntityId | null,
    derivationKind: dto.derivation_kind,
    retryFromStep: (dto.retry_from_step ?? null) as DomainEntityId | null,
    cachePolicy: dto.cache_policy,
    startedAt: (dto.started_at ?? null) as UtcIsoTimestamp | null,
    finishedAt: (dto.finished_at ?? null) as UtcIsoTimestamp | null,
    createdAt: dto.created_at as UtcIsoTimestamp,
    updatedAt: dto.updated_at as UtcIsoTimestamp,
    latestEventSequence: dto.latest_event_sequence ?? 0,
    failureCode: dto.failure_code ?? null,
    failureSummary: dto.failure_summary ?? null,
  };
}

export function mapRunEvent(dto: RunEventDto): RunEvent {
  return {
    runId: mapId(dto.run_id),
    sequence: dto.sequence,
    eventType: mapId(dto.event_type),
    stepKey: (dto.step_key ?? null) as DomainEntityId | null,
    progress: dto.progress ?? null,
    publicMessage: dto.public_message,
    artifactVersionIds: mapIds(dto.artifact_version_ids),
    occurredAt: dto.occurred_at as UtcIsoTimestamp,
  };
}

export function mapArtifactVersion(dto: ArtifactVersionDto): ArtifactVersion {
  return {
    id: mapId(dto.id),
    artifactId: mapId(dto.artifact_id),
    projectId: mapId(dto.project_id),
    createdByRunId: mapId(dto.created_by_run_id),
    versionNumber: dto.version_number,
    schemaVersion: dto.schema_version,
    content: mapArtifactContent(dto.content),
    contentHash: dto.content_hash as ContentHash,
    inputHash: dto.input_hash as ContentHash,
    sourceMode: dto.source_mode as SourceMode,
    producer: mapProducer(dto.producer),
    sourceSnapshotIds: mapIds(dto.source_snapshot_ids),
    evidenceIds: mapIds(dto.evidence_ids),
    supersedesVersionId: (dto.supersedes_version_id ??
      null) as DomainEntityId | null,
    createdAt: dto.created_at as UtcIsoTimestamp,
  };
}

export function mapResearchArtifact(
  dto: ResearchArtifactDto,
): ResearchArtifact {
  return {
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    kind: dto.kind,
    title: dto.title,
    logicalKey: mapId(dto.logical_key),
    createdAt: dto.created_at as UtcIsoTimestamp,
    latestVersionId: (dto.latest_version_id ?? null) as DomainEntityId | null,
  };
}

/**
 * Build a `ProvenanceState` for a fixture bundle.
 *
 * Fixture provenance always reports `demo_replay` execution mode and `fixture`
 * source mode. Evidence completeness is derived from the bundle's declared
 * counts.
 */
export function buildFixtureProvenance(
  schemaVersion: string,
  retrievedAt: UtcIsoTimestamp,
  evidenceCovered: number,
  evidenceTotal: number,
  note: string,
): ProvenanceState {
  return {
    executionMode: "demo_replay",
    sourceMode: "fixture",
    schemaVersion,
    retrievedAt,
    evidenceCompleteness: {
      covered: evidenceCovered,
      total: evidenceTotal,
    },
    note,
  };
}

/**
 * Evidence is a frontend domain entity without a v2 transport schema.
 * Fixture evidence is provided directly in domain form (camelCase), so no
 * mapping is needed — this identity function exists for API symmetry.
 */
export function mapEvidence(entity: Evidence): Evidence {
  return entity;
}
