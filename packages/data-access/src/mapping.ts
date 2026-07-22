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
  EvidenceLocator,
  EvidenceTargetType,
  EvidenceType,
  ExecutionMode,
  NonEmptyString,
  ProducerReference,
  ProvenanceState,
  SemanticVersion,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchContractInput,
  ResearchProject,
  ResearchRun,
  RunEvent,
  RunStatus,
  ShareSnapshot,
  ShareSnapshotCreated,
  CreateShareSnapshotRequest,
  PublicShareSnapshot,
  SourceMode,
  UtcIsoTimestamp,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import type {
  ArtifactVersion as ArtifactVersionDto,
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  DataRequirements as DataRequirementsDto,
  EvidenceRead as EvidenceReadDto,
  PaperSearchScope as PaperSearchScopeDto,
  ProducerReference as ProducerReferenceDto,
  ResearchArtifact as ResearchArtifactDto,
  ResearchArtifactDetail as ResearchArtifactDetailDto,
  ResearchContract as ResearchContractDto,
  ResearchContractDraft as ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
  ResearchProject as ResearchProjectDto,
  ResearchRun as ResearchRunDto,
  RunEvent as RunEventDto,
  WorkspaceSnapshot as WorkspaceSnapshotDto,
  WorkspaceSnapshotInput as WorkspaceSnapshotInputDto,
  ShareSnapshot as ShareSnapshotDto,
  ShareSnapshotCreated as ShareSnapshotCreatedDto,
  CreateShareSnapshotRequest as CreateShareSnapshotRequestDto,
  PublicShareSnapshot as PublicShareSnapshotDto,
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
 * Map the richer `ResearchArtifactDetail` read projection down to the domain
 * `ResearchArtifact`. The extra `versions` summaries are validated by the
 * contract but not part of the base identity the workspace consumes.
 */
export function mapResearchArtifactDetail(
  dto: ResearchArtifactDetailDto,
): ResearchArtifact {
  return mapResearchArtifact(dto);
}

/**
 * Map the unified `ArtifactVersionDetail` read projection to the domain
 * `ArtifactVersion`. Detail types `content` as a loose object, so it is
 * narrowed to the discriminated union after schema validation.
 */
export function mapArtifactVersionDetail(
  dto: ArtifactVersionDetailDto,
): ArtifactVersion {
  return {
    id: mapId(dto.id),
    artifactId: mapId(dto.artifact_id),
    projectId: mapId(dto.project_id),
    createdByRunId: mapId(dto.created_by_run_id),
    versionNumber: dto.version_number,
    schemaVersion: dto.schema_version,
    content: mapArtifactContent(
      dto.content as unknown as ArtifactVersionDto["content"],
    ),
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

export function mapWorkspaceSnapshot(
  dto: WorkspaceSnapshotDto,
): WorkspaceSnapshot {
  return {
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    revision: dto.revision,
    layoutPreset: dto.layout_preset,
    activeRunId: dto.active_run_id ? mapId(dto.active_run_id) : null,
    panelSlots: (dto.panel_slots ?? []).map((s) => ({
      slotId: s.slot_id,
      panelType: s.panel_type,
      artifactVersionId: s.artifact_version_id
        ? mapId(s.artifact_version_id)
        : null,
      evidenceId: s.evidence_id ? mapId(s.evidence_id) : null,
    })),
    pinnedEvidenceIds: (dto.pinned_evidence_ids ?? []).map(mapId),
    atlasState: dto.atlas_state
      ? {
          focusMode: dto.atlas_state.focus_mode ?? null,
          selectedObjectRef: dto.atlas_state.selected_object_ref
            ? {
                artifactVersionId: dto.atlas_state.selected_object_ref
                  .artifact_version_id
                  ? mapId(
                      dto.atlas_state.selected_object_ref.artifact_version_id,
                    )
                  : null,
                objectId: mapId(dto.atlas_state.selected_object_ref.object_id),
                objectType: dto.atlas_state.selected_object_ref.object_type,
              }
            : null,
        }
      : null,
    observatoryState: dto.observatory_state
      ? {
          activeArtifactVersionId: dto.observatory_state
            .active_artifact_version_id
            ? mapId(dto.observatory_state.active_artifact_version_id)
            : null,
          activeEvidenceId: dto.observatory_state.active_evidence_id
            ? mapId(dto.observatory_state.active_evidence_id)
            : null,
        }
      : null,
    selectedObjectRef: dto.selected_object_ref
      ? {
          artifactVersionId: dto.selected_object_ref.artifact_version_id
            ? mapId(dto.selected_object_ref.artifact_version_id)
            : null,
          objectId: mapId(dto.selected_object_ref.object_id),
          objectType: dto.selected_object_ref.object_type,
        }
      : null,
    updatedAt: dto.updated_at as UtcIsoTimestamp,
  };
}

export function mapWorkspaceSnapshotInputToDto(
  domain: WorkspaceSnapshotInput,
): WorkspaceSnapshotInputDto {
  return {
    layout_preset: domain.layoutPreset,
    active_run_id: domain.activeRunId,
    panel_slots: domain.panelSlots.map((s) => ({
      slot_id: s.slotId,
      panel_type: s.panelType,
      artifact_version_id: s.artifactVersionId,
      evidence_id: s.evidenceId,
    })) as WorkspaceSnapshotInputDto["panel_slots"],
    pinned_evidence_ids: domain.pinnedEvidenceIds.map(String),
    atlas_state: domain.atlasState
      ? {
          focus_mode: domain.atlasState.focusMode,
          selected_object_ref: domain.atlasState.selectedObjectRef
            ? {
                artifact_version_id:
                  domain.atlasState.selectedObjectRef.artifactVersionId,
                object_id: domain.atlasState.selectedObjectRef.objectId,
                object_type: domain.atlasState.selectedObjectRef.objectType,
              }
            : null,
        }
      : undefined,
    observatory_state: domain.observatoryState
      ? {
          active_artifact_version_id:
            domain.observatoryState.activeArtifactVersionId,
          active_evidence_id: domain.observatoryState.activeEvidenceId,
        }
      : undefined,
    selected_object_ref: domain.selectedObjectRef
      ? {
          artifact_version_id: domain.selectedObjectRef.artifactVersionId,
          object_id: domain.selectedObjectRef.objectId,
          object_type: domain.selectedObjectRef.objectType,
        }
      : null,
  };
}

export function mapShareSnapshot(dto: ShareSnapshotDto): ShareSnapshot {
  return {
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    title: dto.title as NonEmptyString,
    status: dto.status,
    redactionPolicy: dto.redaction_policy,
    artifactVersionIds: dto.artifact_version_ids.map(mapId),
    evidenceIds: dto.evidence_ids.map(mapId),
    createdAt: dto.created_at as UtcIsoTimestamp,
    expiresAt: dto.expires_at as UtcIsoTimestamp,
    revokedAt: dto.revoked_at ? (dto.revoked_at as UtcIsoTimestamp) : null,
  };
}

export function mapShareSnapshotCreated(
  dto: ShareSnapshotCreatedDto,
): ShareSnapshotCreated {
  return {
    ...mapShareSnapshot(dto),
    shareToken: dto.share_token,
    shareUrl: dto.share_url,
  };
}

export function mapCreateShareSnapshotRequestToDto(
  domain: CreateShareSnapshotRequest,
): CreateShareSnapshotRequestDto {
  return {
    title: domain.title,
    artifact_version_ids: domain.artifactVersionIds.map(String) as [
      string,
      ...string[],
    ],
    evidence_ids: domain.evidenceIds.map(String),
    expires_at: domain.expiresAt,
    redaction_policy: domain.redactionPolicy,
  };
}

export function mapPublicShareSnapshot(
  dto: PublicShareSnapshotDto,
): PublicShareSnapshot {
  return {
    id: mapId(dto.id),
    title: dto.title as NonEmptyString,
    redactionPolicy: dto.redaction_policy,
    createdAt: dto.created_at as UtcIsoTimestamp,
    expiresAt: dto.expires_at as UtcIsoTimestamp,
    artifactVersions: dto.artifact_versions.map((v) => ({
      id: mapId(v.id),
      artifactId: mapId(v.artifact_id),
      kind: v.kind,
      title: v.title as NonEmptyString,
      versionNumber: v.version_number,
      schemaVersion: v.schema_version as SemanticVersion,
      contentHash: v.content_hash as ContentHash,
      sourceMode: v.source_mode,
      createdAt: v.created_at as UtcIsoTimestamp,
    })),
    evidence: dto.evidence.map((e) => ({
      id: mapId(e.id),
      artifactVersionId: mapId(e.artifact_version_id),
      sourceSnapshotId: mapId(e.source_snapshot_id),
    })),
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
 * Fixture evidence is already provided in domain form (camelCase), so no
 * transport mapping is needed for the fixture adapter.
 */
export function mapEvidence(entity: Evidence): Evidence {
  return entity;
}

function readString(raw: Record<string, unknown>, key: string): string {
  const value = raw[key];
  return typeof value === "string" ? value : "";
}

function readNumberOrNull(
  raw: Record<string, unknown>,
  key: string,
): number | null {
  const value = raw[key];
  return typeof value === "number" ? value : null;
}

/** Narrow the opaque wire locator dict to the domain discriminated union. */
function mapEvidenceLocator(raw: unknown): EvidenceLocator | null {
  if (raw === null || typeof raw !== "object") return null;
  const record = raw as Record<string, unknown>;
  switch (record.kind) {
    case "database_cell":
      return {
        kind: "database_cell",
        queryHash: readString(record, "query_hash"),
        rowKey: readString(record, "row_key"),
        field: mapId(readString(record, "field")),
      };
    case "paper_text":
      return {
        kind: "paper_text",
        section: readString(record, "section"),
        page: readNumberOrNull(record, "page"),
        paragraph: readNumberOrNull(record, "paragraph"),
        range: typeof record.range === "string" ? record.range : null,
      };
    case "model_extraction":
      return {
        kind: "model_extraction",
        inputEvidenceId: mapId(readString(record, "input_evidence_id")),
        promptName: readString(record, "prompt_name"),
        modelVersion: readString(record, "model_version"),
      };
    case "reasoning_trace":
      return {
        kind: "reasoning_trace",
        relationId: mapId(readString(record, "relation_id")),
        stepKey: mapId(readString(record, "step_key")),
      };
    default:
      return null;
  }
}

/**
 * Map the `EvidenceRead` transport projection to the domain `Evidence`. The
 * wire locator is an opaque object typed loosely by the contract, so it is
 * narrowed here; unknown locator kinds map to `null` rather than guessing.
 */
export function mapEvidenceRead(dto: EvidenceReadDto): Evidence {
  return {
    id: mapId(dto.id),
    artifactVersionId: mapId(dto.artifact_version_id),
    targetType: dto.target_type as EvidenceTargetType,
    targetId: mapId(dto.target_id),
    evidenceType: dto.evidence_type as EvidenceType,
    sourceSnapshotId: mapId(dto.source_snapshot_id),
    paperId: (dto.paper_id ?? null) as DomainEntityId | null,
    locator: mapEvidenceLocator(dto.locator),
    quoteOrValue:
      typeof dto.quote_or_value === "string" ? dto.quote_or_value : null,
    extractionMethod: dto.extraction_method,
    confidence: dto.confidence,
    createdAt: dto.created_at as UtcIsoTimestamp,
  };
}

export function mapDomainContractInputToDto(
  input: ResearchContractInput,
): ResearchContractInputDto {
  return {
    research_goal: input.researchGoal,
    target_objects: [...input.targetObjects] as unknown as [
      string,
      ...string[],
    ],
    data_requirements: {
      unit_policy: input.dataRequirements.unitPolicy,
    },
    requested_fields: [...input.requestedFields] as unknown as [
      string,
      ...string[],
    ],
    source_scope: {
      allowed_sources: [...input.sourceScope.allowedSources] as unknown as [
        string,
        ...string[],
      ],
    },
    paper_search_scope: {
      keywords: [...input.paperSearchScope.keywords],
      year_from: input.paperSearchScope.yearFrom,
      year_to: input.paperSearchScope.yearTo,
      source_ids: [...input.paperSearchScope.sourceIds],
      max_candidates: input.paperSearchScope.maxCandidates,
    },
    output_requirements: [...input.outputRequirements] as unknown as [
      ArtifactKind,
      ...ArtifactKind[],
    ],
    evidence_requirements: {
      require_locator: input.evidenceRequirements.requireLocator,
      require_source_snapshot: input.evidenceRequirements.requireSourceSnapshot,
      minimum_coverage: input.evidenceRequirements.minimumCoverage,
    },
    quality_constraints: {
      source_completeness_min: input.qualityConstraints.sourceCompletenessMin,
      unit_consistency_min: input.qualityConstraints.unitConsistencyMin,
    },
  };
}
