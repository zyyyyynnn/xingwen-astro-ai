/**
 * Transport DTO → domain entity mappers.
 *
 * These functions convert snake_case `/api` DTOs (validated by
 * `@xingwen/contracts`) into the camelCase domain model. They are the only
 * place where DTO shapes are referenced; downstream code never sees DTOs.
 */

import type {
  ArtifactKind,
  ArtifactVersion,
  ArtifactVersionMetadata,
  ArtifactVersionSummary,
  CaseKey,
  ContentHash,
  DomainEntityId,
  Evidence,
  EvidenceLocator,
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
  ResearchPlanningCatalog,
  ResearchRun,
  RunCheckpoint,
  ResearchThreadEntry,
  ResearchThreadAssistantPayload,
  ResearchThreadPublicOutcome,
  ResearchTurn,
  RunStepSnapshot,
  RunEvent,
  RunStatus,
  ScientificSkillId,
  ScientificTask,
  ShareSnapshot,
  ShareSnapshotCreated,
  CreateShareSnapshotRequest,
  PublicShareSnapshot,
  SourceMode,
  UtcIsoTimestamp,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";
import {
  asEntityId,
  isEvidenceTargetType,
  isEvidenceType,
  isScientificSkillId,
  parseEntityId,
} from "@xingwen/domain";

import type {
  ArtifactVersion as ArtifactVersionDto,
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  ArtifactVersionSummary as ArtifactVersionSummaryDto,
  DataRequirements as DataRequirementsDto,
  EvidenceDetail as EvidenceDetailDto,
  EvidenceRead as EvidenceReadDto,
  PaperSearchScope as PaperSearchScopeDto,
  ProducerReference as ProducerReferenceDto,
  ResearchArtifact as ResearchArtifactDto,
  ResearchArtifactDetail as ResearchArtifactDetailDto,
  ResearchContract as ResearchContractDto,
  ResearchContractDraft as ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
  ResearchProject as ResearchProjectDto,
  ResearchPlanningCatalog as ResearchPlanningCatalogDto,
  ResearchRun as ResearchRunDto,
  RunCheckpoint as RunCheckpointDto,
  ResearchThreadEntry as ResearchThreadEntryDto,
  ResearchTurnResult as ResearchTurnResultDto,
  RunStepRead as RunStepReadDto,
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

function mapScientificTask(
  dto: NonNullable<ResearchContractInputDto["scientific_tasks"]>[number],
): ScientificTask {
  if (!isScientificSkillId(dto.skill_id)) {
    throw new TypeError(
      `Scientific task ${dto.task_id} references an unknown skill_id: ${dto.skill_id}`,
    );
  }
  return {
    taskId: mapId(dto.task_id),
    skillId: dto.skill_id,
    parameters: { ...(dto.parameters ?? {}) },
    inputRefs: mapIds(dto.input_refs),
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
    scientificTasks: (dto.scientific_tasks ?? []).map(mapScientificTask),
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
    modelName: dto.requested_model ?? null,
    promptName: dto.prompt_name ?? null,
    promptVersion: dto.prompt_version ?? null,
    parametersHash: (dto.parameters_hash ?? null) as ContentHash | null,
  };
}

export function mapResearchProject(dto: ResearchProjectDto): ResearchProject {
  return {
    id: mapId(dto.id),
    sessionId: mapId(dto.session_id),
    name: dto.name,
    description: dto.description ?? "",
    caseKey: dto.case_key as CaseKey,
    activeDraftId: (dto.active_draft_id ?? null) as DomainEntityId | null,
    activeContractId: (dto.active_contract_id ?? null) as DomainEntityId | null,
    latestRunId: (dto.latest_run_id ?? null) as DomainEntityId | null,
    latestRunStatus: dto.latest_run_status ?? null,
    latestRunFailureSummary: dto.latest_run_failure_summary ?? null,
    threadSummary: {
      hasThreadEntries: dto.thread_summary.has_thread_entries,
      latestThreadActor: dto.thread_summary.latest_thread_actor,
      hasUnansweredClarification:
        dto.thread_summary.has_unanswered_clarification,
    },
    createdAt: dto.created_at as UtcIsoTimestamp,
    updatedAt: dto.updated_at as UtcIsoTimestamp,
    revision: dto.revision,
  };
}

export function mapResearchPlanningCatalog(
  dto: ResearchPlanningCatalogDto,
): ResearchPlanningCatalog {
  const mapOptions = <Value extends string>(
    options: ResearchPlanningCatalogDto["target_objects"],
  ) =>
    options.map((option) => ({
      value: option.value as Value,
      label: option.label,
      description: option.description ?? "",
      group: option.group ?? null,
    }));
  return {
    projectId: mapId(dto.project_id),
    caseKey: dto.case_key as CaseKey,
    targetObjects: mapOptions<DomainEntityId>(dto.target_objects),
    requestedFields: mapOptions<DomainEntityId>(dto.requested_fields),
    allowedSources: mapOptions<DomainEntityId>(dto.allowed_sources),
    scientificSkills: mapOptions<ScientificSkillId>(dto.scientific_skills),
    outputRequirements: mapOptions<ArtifactKind>(dto.output_requirements),
  };
}

export function mapResearchThreadEntry(
  dto: ResearchThreadEntryDto,
): ResearchThreadEntry {
  const base = {
    id: mapId(dto.id),
    projectId: mapId(dto.project_id),
    sequence: dto.sequence,
    publicContent: dto.public_content,
    modelExecutionId: (dto.model_execution_id ?? null) as DomainEntityId | null,
    createdAt: dto.created_at as UtcIsoTimestamp,
  };
  const payload = dto.structured_payload ?? {};
  if (dto.kind === "user_message" || dto.kind === "clarification_answer") {
    if (dto.actor !== "user") {
      throw new TypeError("Research Thread user entry has an invalid actor");
    }
    return {
      ...base,
      kind: dto.kind,
      actor: "user",
      structuredPayload: {
        answerToQuestionId: optionalPayloadId(
          payload.answer_to_question_id,
          "answer_to_question_id",
        ),
      },
    };
  }
  const assistantPayload = mapAssistantPayload(payload);
  if (dto.actor !== "assistant") {
    throw new TypeError("Research Thread assistant entry has an invalid actor");
  }
  if (dto.kind === "clarification_question") {
    return {
      ...base,
      kind: dto.kind,
      actor: "assistant",
      structuredPayload: {
        ...assistantPayload,
        questionId: requiredPayloadId(payload.question_id, "question_id"),
        options: stringArray(payload.options),
      },
    };
  }
  if (dto.kind === "assistant_reasoning" || dto.kind === "assistant_message") {
    return {
      ...base,
      kind: dto.kind,
      actor: "assistant",
      structuredPayload: assistantPayload,
    };
  }
  throw new TypeError(`Unsupported Research Thread entry kind: ${dto.kind}`);
}

const THREAD_OUTCOMES = new Set<ResearchThreadPublicOutcome>([
  "clarification_required",
  "draft_ready",
  "partial",
  "unsupported",
  "refused",
  "unavailable",
]);

function mapAssistantPayload(
  payload: NonNullable<ResearchThreadEntryDto["structured_payload"]>,
): ResearchThreadAssistantPayload {
  const outcome = payload.outcome;
  if (
    typeof outcome !== "string" ||
    !THREAD_OUTCOMES.has(outcome as ResearchThreadPublicOutcome)
  ) {
    throw new TypeError(
      "Research Thread assistant payload has an invalid outcome",
    );
  }
  return {
    outcome: outcome as ResearchThreadPublicOutcome,
    warnings: stringArray(payload.warnings),
    draftId: optionalPayloadId(payload.draft_id, "draft_id"),
    missingInformation: stringArray(payload.missing_information),
    reason: optionalPayloadString(payload.reason, "reason"),
    errorCode: optionalPayloadString(payload.error_code, "error_code"),
  };
}

function optionalPayloadId(
  value: unknown,
  field: string,
): DomainEntityId | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") {
    throw new TypeError(
      `Research Thread payload ${field} must be an identifier`,
    );
  }
  const parsed = parseEntityId(value);
  if (parsed === null) {
    throw new TypeError(`Research Thread payload ${field} is invalid`);
  }
  return parsed;
}

function requiredPayloadId(value: unknown, field: string): DomainEntityId {
  const parsed = optionalPayloadId(value, field);
  if (parsed === null) {
    throw new TypeError(`Research Thread payload ${field} is required`);
  }
  return parsed;
}

function optionalPayloadString(value: unknown, field: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") {
    throw new TypeError(`Research Thread payload ${field} must be text`);
  }
  return value;
}

function stringArray(value: unknown): readonly string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new TypeError("Research Thread payload list must contain text only");
  }
  return [...value];
}

export function mapResearchTurn(dto: ResearchTurnResultDto): ResearchTurn {
  return {
    outcome: dto.outcome as ResearchTurn["outcome"],
    entries: dto.entries.map(mapResearchThreadEntry),
    activeDraftId: (dto.active_draft_id ?? null) as DomainEntityId | null,
    modelExecutionId: mapId(dto.model_execution_id),
  };
}

export function mapRunStep(dto: RunStepReadDto): RunStepSnapshot {
  return {
    id: mapId(dto.id),
    runId: mapId(dto.run_id),
    position: dto.position,
    key: mapId(dto.key),
    label: dto.label,
    status: dto.status as RunStepSnapshot["status"],
    progress: dto.progress,
    publicMessage: dto.public_message,
    startedAt: (dto.started_at ?? null) as UtcIsoTimestamp | null,
    finishedAt: (dto.finished_at ?? null) as UtcIsoTimestamp | null,
    failureCode: dto.failure_code ?? null,
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
    revision: dto.revision ?? 1,
    parentRunId: (dto.parent_run_id ?? null) as DomainEntityId | null,
    derivationKind: dto.derivation_kind,
    retryFromStep: (dto.retry_from_step ?? null) as DomainEntityId | null,
    cachePolicy: dto.cache_policy,
    revisionPlanId: (dto.revision_plan_id ?? null) as DomainEntityId | null,
    feedbackIds: dto.feedback_ids ? dto.feedback_ids.map(mapId) : undefined,
    recomputeSteps: dto.recompute_steps
      ? dto.recompute_steps.map(mapId)
      : undefined,
    reusedArtifactVersionIds: dto.reused_artifact_version_ids
      ? dto.reused_artifact_version_ids.map(mapId)
      : undefined,
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
    activityId: dto.activity_id,
    activityKind: dto.activity_kind,
    activityPhase: dto.activity_phase,
    activityName: dto.activity_name,
    stepKey: (dto.step_key ?? null) as DomainEntityId | null,
    progress: dto.progress ?? null,
    content: dto.content,
    details: dto.details ?? {},
    artifactVersionIds: mapIds(dto.artifact_version_ids),
    occurredAt: dto.occurred_at as UtcIsoTimestamp,
  };
}

export function mapRunCheckpoint(dto: RunCheckpointDto): RunCheckpoint {
  return {
    id: mapId(dto.id),
    runId: mapId(dto.run_id),
    stepKey: mapId(dto.step_key),
    question: dto.question,
    options: [...dto.options],
    createdAt: dto.created_at as UtcIsoTimestamp,
    selectedOption: dto.selected_option ?? null,
    freeText: dto.free_text ?? null,
    decidedAt: (dto.decided_at ?? null) as UtcIsoTimestamp | null,
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
    // Keep persisted JSON in its canonical API shape. Kind-specific mapping
    // belongs to the owning repository/read contract, not this generic mapper.
    content: { ...dto.content },
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

export function mapArtifactVersionSummary(
  dto: ArtifactVersionSummaryDto,
): ArtifactVersionSummary {
  return {
    id: mapId(dto.id),
    artifactId: mapId(dto.artifact_id),
    versionNumber: dto.version_number,
    schemaVersion: dto.schema_version,
    contentHash: dto.content_hash as ContentHash,
    sourceMode: dto.source_mode as SourceMode,
    supersedesVersionId: (dto.supersedes_version_id ??
      null) as DomainEntityId | null,
    createdAt: dto.created_at as UtcIsoTimestamp,
  };
}

/**
 * Map the `ArtifactVersionDetail` read projection to the narrowed
 * `ArtifactVersionMetadata` domain shape.
 *
 * The generic workspace read deliberately drops the scientific `content`
 * payload: rich kind-specific content must be read through its dedicated
 * repository and contract.
 */
export function mapArtifactVersionMetadata(
  dto: ArtifactVersionDto | ArtifactVersionDetailDto,
): ArtifactVersionMetadata {
  return {
    id: mapId(dto.id),
    artifactId: mapId(dto.artifact_id),
    projectId: mapId(dto.project_id),
    createdByRunId: mapId(dto.created_by_run_id),
    versionNumber: dto.version_number,
    schemaVersion: dto.schema_version,
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
 * transport mapping is needed for the fixture adapter. The `source`
 * projection is normalized to an explicit `null` so the store shape matches
 * the HTTP `mapEvidenceRead` / `mapEvidenceDetail` projections.
 */
export function mapEvidence(entity: Evidence): Evidence {
  return { ...entity, source: entity.source ?? null };
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
 * Shared Evidence projection core. `EvidenceRead` (top-level, with a nested
 * source snapshot) and the embedded `EvidenceDetail` share every domain
 * field; the nested snapshot projection is intentionally not carried into
 * the domain `Evidence`, so pinning/Share always reuses the same ids.
 *
 * Target/evidence types are validated against the closed domain enums
 * instead of being asserted, so contract drift fails loudly here.
 */
function mapEvidenceCore(
  dto: EvidenceDetailDto,
  source: Evidence["source"],
): Evidence {
  if (!isEvidenceTargetType(dto.target_type)) {
    throw new Error(
      `Evidence ${dto.id} carries an unknown target_type: ${dto.target_type}`,
    );
  }
  if (!isEvidenceType(dto.evidence_type)) {
    throw new Error(
      `Evidence ${dto.id} carries an unknown evidence_type: ${dto.evidence_type}`,
    );
  }
  return {
    id: mapId(dto.id),
    artifactVersionId: mapId(dto.artifact_version_id),
    targetType: dto.target_type,
    targetId: mapId(dto.target_id),
    evidenceType: dto.evidence_type,
    sourceSnapshotId: mapId(dto.source_snapshot_id),
    paperId: (dto.paper_id ?? null) as DomainEntityId | null,
    locator: mapEvidenceLocator(dto.locator),
    quoteOrValue:
      typeof dto.quote_or_value === "string" ? dto.quote_or_value : null,
    extractionMethod: dto.extraction_method,
    confidence: dto.confidence,
    createdAt: dto.created_at as UtcIsoTimestamp,
    source,
  };
}

/** Map the `EvidenceRead` transport projection to the domain `Evidence`. */
export function mapEvidenceRead(dto: EvidenceReadDto): Evidence {
  return mapEvidenceCore(dto, {
    id: mapId(dto.source_snapshot.id),
    sourceId: dto.source_snapshot.source_id,
    sourceType: dto.source_snapshot.source_type,
    retrievedAt: dto.source_snapshot.retrieved_at as UtcIsoTimestamp,
    licenseNote: dto.source_snapshot.license_note,
    sourceVersionOrEtag: dto.source_snapshot.source_version_or_etag ?? null,
    requestMetadata: { ...dto.source_snapshot.request_metadata },
  });
}

/** Embedded evidence omits the source projection; callers that need source detail use EvidenceRead. */
export function mapEvidenceDetail(dto: EvidenceDetailDto): Evidence {
  return mapEvidenceCore(dto, null);
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
    scientific_tasks: input.scientificTasks.map((task) => ({
      task_id: String(task.taskId),
      skill_id: task.skillId,
      parameters: { ...task.parameters },
      input_refs: [...task.inputRefs].map(String),
    })),
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
