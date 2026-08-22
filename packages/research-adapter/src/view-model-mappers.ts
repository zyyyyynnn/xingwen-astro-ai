import {
  isTerminalRunStatus,
  type ArtifactVersionMetadata,
  type DataArtifactReview,
  type Evidence,
  type EvidenceLocator,
  type GraphArtifactReview,
  type LiteratureArtifactReview,
  type LiteratureClaimReferenceReview,
  type LiteratureReasoningTraceReview,
  type LiteratureRelationReview,
  type PaperAcquisitionReview,
  type ResearchArtifact,
  type ResearchContract,
  type ResearchContractDraft,
  type ResearchContractInput,
  type ResearchProject,
  type ResearchRun,
  type RunCheckpoint,
  type ResearchThreadEntry,
  type ResearchTurn,
  type RunStepSnapshot,
} from "@xingwen/domain";

import type {
  ArtifactVersionMetadataViewModel,
  ContractInputViewModel,
  DataArtifactReviewViewModel,
  DatabaseCellLocatorViewModel,
  EvidenceLocatorViewModel,
  EvidenceViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  ModelExtractionLocatorViewModel,
  PaperAcquisitionReviewViewModel,
  PaperTextLocatorViewModel,
  ProducerReferenceViewModel,
  ProjectViewModel,
  ReasoningTraceLocatorViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  RunCheckpointViewModel,
  ResearchThreadEntryViewModel,
  ResearchTurnViewModel,
  RunStepViewModel,
} from "./view-model";

function toContractInputViewModel(
  input: ResearchContractInput,
): ContractInputViewModel {
  return {
    researchGoal: input.researchGoal,
    targetObjects: [...input.targetObjects],
    dataRequirements: {
      unitPolicy: input.dataRequirements.unitPolicy,
    },
    requestedFields: [...input.requestedFields],
    sourceScope: {
      allowedSources: [...input.sourceScope.allowedSources],
    },
    paperSearchScope: {
      keywords: [...input.paperSearchScope.keywords],
      yearFrom: input.paperSearchScope.yearFrom,
      yearTo: input.paperSearchScope.yearTo,
      sourceIds: [...input.paperSearchScope.sourceIds],
      maxCandidates: input.paperSearchScope.maxCandidates,
    },
    scientificTasks: input.scientificTasks.map((task) => ({
      taskId: task.taskId,
      skillId: task.skillId,
      parameters: { ...task.parameters },
      inputRefs: [...task.inputRefs],
    })),
    outputRequirements: [...input.outputRequirements],
    evidenceRequirements: {
      requireLocator: input.evidenceRequirements.requireLocator,
      requireSourceSnapshot: input.evidenceRequirements.requireSourceSnapshot,
      minimumCoverage: input.evidenceRequirements.minimumCoverage,
    },
    qualityConstraints: {
      sourceCompletenessMin: input.qualityConstraints.sourceCompletenessMin,
      unitConsistencyMin: input.qualityConstraints.unitConsistencyMin,
    },
  };
}

export function toProjectViewModel(project: ResearchProject): ProjectViewModel {
  return {
    id: project.id,
    name: project.name,
    description: project.description,
    caseKey: project.caseKey,
    activeDraftId: project.activeDraftId,
    activeContractId: project.activeContractId,
    latestRunId: project.latestRunId,
    latestRunStatus: project.latestRunStatus ?? null,
    latestRunFailureSummary: project.latestRunFailureSummary ?? null,
    threadSummary: project.threadSummary,
    revision: project.revision,
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
  };
}

export function toResearchThreadEntryViewModel(
  entry: ResearchThreadEntry,
): ResearchThreadEntryViewModel {
  return {
    id: entry.id,
    projectId: entry.projectId,
    sequence: entry.sequence,
    kind: entry.kind,
    actor: entry.actor,
    publicContent: entry.publicContent,
    structuredPayload:
      entry.kind === "clarification_question"
        ? {
            ...entry.structuredPayload,
            warnings: [...entry.structuredPayload.warnings],
            missingInformation: [...entry.structuredPayload.missingInformation],
            options: [...entry.structuredPayload.options],
          }
        : entry.kind === "assistant_reasoning" ||
            entry.kind === "assistant_message"
          ? {
              ...entry.structuredPayload,
              warnings: [...entry.structuredPayload.warnings],
              missingInformation: [
                ...entry.structuredPayload.missingInformation,
              ],
            }
          : { ...entry.structuredPayload },
    modelExecutionId: entry.modelExecutionId,
    createdAt: entry.createdAt,
  } as ResearchThreadEntryViewModel;
}

export function toResearchTurnViewModel(
  turn: ResearchTurn,
): ResearchTurnViewModel {
  return {
    outcome: turn.outcome,
    entries: turn.entries.map(toResearchThreadEntryViewModel),
    activeDraftId: turn.activeDraftId,
    modelExecutionId: turn.modelExecutionId,
  };
}

export function toRunStepViewModel(step: RunStepSnapshot): RunStepViewModel {
  return {
    id: step.id,
    runId: step.runId,
    position: step.position,
    key: step.key,
    label: step.label,
    phase: step.phase,
    taskId: step.taskId,
    skillId: step.skillId,
    dependsOnStepKeys: step.dependsOnStepKeys,
    status: step.status,
    progress: step.progress,
    publicMessage: step.publicMessage,
    startedAt: step.startedAt,
    finishedAt: step.finishedAt,
    failureCode: step.failureCode,
  };
}

export function toContractDraftViewModel(
  draft: ResearchContractDraft,
): ResearchContractDraftViewModel {
  return {
    id: draft.id,
    version: draft.version,
    intent: draft.intent,
    status: draft.status,
    contract: toContractInputViewModel(draft.contract),
    warnings: [...draft.warnings],
    createdAt: draft.createdAt,
    updatedAt: draft.updatedAt,
    expiresAt: draft.expiresAt,
  };
}

export function toContractViewModel(
  contract: ResearchContract,
): ResearchContractViewModel {
  return {
    ...toContractInputViewModel(contract),
    id: contract.id,
    projectId: contract.projectId,
    version: contract.version,
    createdAt: contract.createdAt,
    createdFromDraftId: contract.createdFromDraftId,
    provenance: {
      contentHash: contract.contentHash,
    },
  };
}

export function toRunViewModel(run: ResearchRun): ResearchRunViewModel {
  return {
    id: run.id,
    projectId: run.projectId,
    contractId: run.contractId,
    executionMode: run.executionMode,
    status: run.status,
    progress: run.progress,
    revision: run.revision,
    latestEventSequence: run.latestEventSequence,
    parentRunId: run.parentRunId,
    derivationKind: run.derivationKind,
    retryFromStep: run.retryFromStep,
    cachePolicy: run.cachePolicy,
    startedAt: run.startedAt,
    finishedAt: run.finishedAt,
    createdAt: run.createdAt,
    updatedAt: run.updatedAt,
    failure:
      run.failureCode === null && run.failureSummary === null
        ? null
        : {
            code: run.failureCode,
            summary: run.failureSummary,
          },
    isTerminal: isTerminalRunStatus(run.status),
    isFailed: run.status === "failed",
    isCancelled: run.status === "cancelled",
  };
}

export function toArtifactViewModel(
  artifact: ResearchArtifact,
): ResearchArtifactViewModel {
  return {
    id: artifact.id,
    projectId: artifact.projectId,
    kind: artifact.kind,
    title: artifact.title,
    logicalKey: artifact.logicalKey,
    latestVersionId: artifact.latestVersionId,
    createdAt: artifact.createdAt,
  };
}

function toProducerViewModel(
  producer: ArtifactVersionMetadata["producer"],
): ProducerReferenceViewModel {
  return {
    type: producer.type,
    name: producer.name,
    version: producer.version,
    modelName: producer.modelName,
    promptName: producer.promptName,
    promptVersion: producer.promptVersion,
    parametersHash: producer.parametersHash,
  };
}

export function toArtifactVersionMetadataViewModel(
  version: ArtifactVersionMetadata,
): ArtifactVersionMetadataViewModel {
  return {
    id: version.id,
    artifactId: version.artifactId,
    projectId: version.projectId,
    createdByRunId: version.createdByRunId,
    versionNumber: version.versionNumber,
    schemaVersion: version.schemaVersion,
    sourceMode: version.sourceMode,
    createdAt: version.createdAt,
    provenance: {
      contentHash: version.contentHash,
      inputHash: version.inputHash,
      producer: toProducerViewModel(version.producer),
      sourceSnapshotIds: [...version.sourceSnapshotIds],
      evidenceIds: [...version.evidenceIds],
      supersedesVersionId: version.supersedesVersionId,
    },
  };
}

export const toArtifactVersionViewModel = toArtifactVersionMetadataViewModel;

export function toRunCheckpointViewModel(
  checkpoint: RunCheckpoint,
): RunCheckpointViewModel {
  return {
    id: checkpoint.id,
    runId: checkpoint.runId,
    runRevision: checkpoint.runRevision,
    stepKey: checkpoint.stepKey,
    question: checkpoint.question,
    options: [...checkpoint.options],
    kind: checkpoint.kind,
    repairContext: checkpoint.repairContext,
    createdAt: checkpoint.createdAt,
    selectedOption: checkpoint.selectedOption,
    freeText: checkpoint.freeText,
    repairDecisions: checkpoint.repairDecisions,
    repairOutcome: checkpoint.repairOutcome,
    decidedAt: checkpoint.decidedAt,
    isAnswered:
      checkpoint.selectedOption !== null ||
      checkpoint.repairDecisions.length > 0 ||
      checkpoint.decidedAt !== null,
  };
}

function assertNever(value: never): never {
  throw new Error(`Unsupported Evidence locator kind: ${String(value)}`);
}

function toEvidenceLocatorViewModel(
  locator: EvidenceLocator,
): EvidenceLocatorViewModel {
  switch (locator.kind) {
    case "database_cell": {
      const result: DatabaseCellLocatorViewModel = {
        kind: locator.kind,
        queryHash: locator.queryHash,
        rowKey: locator.rowKey,
        field: locator.field,
      };
      return result;
    }
    case "paper_text": {
      const result: PaperTextLocatorViewModel = {
        kind: locator.kind,
        section: locator.section,
        page: locator.page,
        paragraph: locator.paragraph,
        range: locator.range,
      };
      return result;
    }
    case "model_extraction": {
      const result: ModelExtractionLocatorViewModel = {
        kind: locator.kind,
        inputEvidenceId: locator.inputEvidenceId,
        promptName: locator.promptName,
        modelVersion: locator.modelVersion,
      };
      return result;
    }
    case "reasoning_trace": {
      const result: ReasoningTraceLocatorViewModel = {
        kind: locator.kind,
        relationId: locator.relationId,
        stepKey: locator.stepKey,
      };
      return result;
    }
    default:
      return assertNever(locator);
  }
}

export function toEvidenceViewModel(evidence: Evidence): EvidenceViewModel {
  return {
    id: evidence.id,
    artifactVersionId: evidence.artifactVersionId,
    targetType: evidence.targetType,
    targetId: evidence.targetId,
    evidenceType: evidence.evidenceType,
    sourceSnapshotId: evidence.sourceSnapshotId,
    paperId: evidence.paperId,
    locator:
      evidence.locator === null
        ? null
        : toEvidenceLocatorViewModel(evidence.locator),
    quoteOrValue: evidence.quoteOrValue,
    extractionMethod: evidence.extractionMethod,
    confidence: evidence.confidence,
    createdAt: evidence.createdAt,
    source: evidence.source
      ? {
          sourceId: evidence.source.sourceId,
          sourceType: evidence.source.sourceType,
          retrievedAt: evidence.source.retrievedAt,
          licenseNote: evidence.source.licenseNote,
          sourceVersionOrEtag: evidence.source.sourceVersionOrEtag,
          requestMetadata: evidence.source.requestMetadata,
        }
      : null,
  };
}

export function toDataArtifactViewModel(
  review: DataArtifactReview,
): DataArtifactReviewViewModel {
  const base = {
    artifactVersionId: review.artifactVersionId,
    artifactId: review.artifactId,
    projectId: review.projectId,
    schemaVersion: review.schemaVersion,
    sourceMode: review.sourceMode,
    contentHash: review.contentHash,
    inputHash: review.inputHash,
    createdAt: review.createdAt,
    sourceSnapshots: review.sourceSnapshots.map((snapshot) => ({
      ...snapshot,
    })),
    evidenceIds: [...review.evidenceIds],
    quality: { ...review.quality },
  };
  if (review.kind === "dataset") {
    return {
      ...base,
      kind: review.kind,
      candidateId: review.candidateId,
      requestedFields: [...review.requestedFields],
      columns: review.columns.map((column) => ({
        ...column,
        sourceAliases: column.sourceAliases.map((alias) => ({ ...alias })),
        sourcePriority: [...column.sourcePriority],
      })),
      rows: review.rows.map((row) => ({
        ...row,
        cells: row.cells.map((cell) => ({
          ...cell,
          conflictIds: [...cell.conflictIds],
          evidenceIds: [...cell.evidenceIds],
        })),
        sourceSnapshotIds: [...row.sourceSnapshotIds],
        evidenceIds: [...row.evidenceIds],
      })),
      rowCount: review.rowCount,
      fieldCount: review.fieldCount,
      conflictCount: review.conflictCount,
    };
  }
  if (review.kind === "field_dictionary") {
    return {
      ...base,
      kind: review.kind,
      candidateId: review.candidateId,
      requestedFields: [...review.requestedFields],
      fieldDefinitions: review.fieldDefinitions.map((field) => ({
        ...field,
        sourceAliases: field.sourceAliases.map((alias) => ({ ...alias })),
        sourcePriority: [...field.sourcePriority],
      })),
    };
  }
  return {
    ...base,
    kind: review.kind,
    candidateId: review.candidateId,
    members: review.members.map((member) => ({ ...member })),
    alignedRecordCount: review.alignedRecordCount,
    conflictRecordCount: review.conflictRecordCount,
    inconclusiveRecordCount: review.inconclusiveRecordCount,
    reviewRequiredRecordCount: review.reviewRequiredRecordCount,
  };
}

export function toPaperAcquisitionViewModel(
  review: PaperAcquisitionReview,
): PaperAcquisitionReviewViewModel {
  return {
    ...review,
    query: {
      ...review.query,
      originalKeywords: [...review.query.originalKeywords],
      normalizedKeywords: [...review.query.normalizedKeywords],
      sourceIds: [...review.query.sourceIds],
      sourceParameters: review.query.sourceParameters.map((source) => ({
        ...source,
        parameters: source.parameters.map((entry) => ({ ...entry })),
      })),
    },
    acquisition: { ...review.acquisition },
    benchmark: review.benchmark ? { ...review.benchmark } : null,
    metrics: { ...review.metrics },
    rules: { ...review.rules },
    sourceExecutions: review.sourceExecutions.map((execution) => ({
      ...execution,
      pagination: { ...execution.pagination },
      pages: execution.pages.map((page) => ({
        ...page,
        rateLimitMetadata: page.rateLimitMetadata.map((entry) => ({
          ...entry,
        })),
      })),
      cache: execution.cache ? { ...execution.cache } : null,
    })),
    sourceSnapshots: review.sourceSnapshots.map((snapshot) => ({
      ...snapshot,
      requestMetadata: snapshot.requestMetadata.map((entry) => ({ ...entry })),
    })),
    producerExecution: { ...review.producerExecution },
    candidates: review.candidates.map((candidate) => ({
      ...candidate,
      authors: [...candidate.authors],
      rawRecord: {
        ...candidate.rawRecord,
        authors: [...candidate.rawRecord.authors],
      },
      conflicts: candidate.conflicts.map((conflict) => ({ ...conflict })),
      selection: { ...candidate.selection },
      duplicateGroup: {
        ...candidate.duplicateGroup,
        candidateIds: [...candidate.duplicateGroup.candidateIds],
        matchBasis: [...candidate.duplicateGroup.matchBasis],
        conflicts: candidate.duplicateGroup.conflicts.map((conflict) => ({
          ...conflict,
        })),
      },
      sourceSnapshot: {
        ...candidate.sourceSnapshot,
        requestMetadata: candidate.sourceSnapshot.requestMetadata.map(
          (entry) => ({
            ...entry,
          }),
        ),
      },
    })),
  };
}

function toClaimReferenceViewModel(
  reference: LiteratureClaimReferenceReview | null,
) {
  return reference
    ? {
        ...reference,
      }
    : null;
}

function toTraceViewModel(trace: LiteratureReasoningTraceReview | null) {
  return trace
    ? {
        ...trace,
        premiseClaimIds: [...trace.premiseClaimIds],
        conditions: [...trace.conditions],
        conflicts: [...trace.conflicts],
        limitations: [...trace.limitations],
        steps: trace.steps.map((step) => ({
          ...step,
          claimIds: [...step.claimIds],
          evidenceIds: [...step.evidenceIds],
        })),
        evidenceIds: [...trace.evidenceIds],
      }
    : null;
}

function toRelationViewModel(relation: LiteratureRelationReview) {
  return {
    ...relation,
    direction: { ...relation.direction },
    comparability: { ...relation.comparability },
    conditions: [...relation.conditions],
    conditionConflicts: [...relation.conditionConflicts],
    conditionUncertainties: [...relation.conditionUncertainties],
    confidence: relation.confidence ? { ...relation.confidence } : null,
    evidenceIds: [...relation.evidenceIds],
    sourceSnapshotIds: [...relation.sourceSnapshotIds],
    sourceClaim: toClaimReferenceViewModel(relation.sourceClaim),
    targetClaim: toClaimReferenceViewModel(relation.targetClaim),
    reasoningTrace: toTraceViewModel(relation.reasoningTrace),
  };
}

export function toLiteratureArtifactViewModel(
  review: LiteratureArtifactReview,
): LiteratureArtifactReviewViewModel {
  const base = {
    artifactVersionId: review.artifactVersionId,
    artifactId: review.artifactId,
    projectId: review.projectId,
    versionNumber: review.versionNumber,
    schemaVersion: review.schemaVersion,
    sourceMode: review.sourceMode,
    contentHash: review.contentHash,
    inputHash: review.inputHash,
    outputHash: review.outputHash,
    createdAt: review.createdAt,
    sourceSnapshots: review.sourceSnapshots.map((snapshot) => ({
      ...snapshot,
    })),
    evidenceIds: [...review.evidenceIds],
  };
  if (review.kind === "literature_claims") {
    return {
      ...base,
      kind: review.kind,
      claims: review.claims.map((claim) => ({
        ...claim,
        objects: [...claim.objects],
        scope: [...claim.scope],
        conditions: [...claim.conditions],
        qualifiers: [...claim.qualifiers],
        limitations: [...claim.limitations],
        sourceSnapshotIds: [...claim.sourceSnapshotIds],
        evidenceIds: [...claim.evidenceIds],
      })),
    };
  }
  return {
    ...base,
    kind: review.kind,
    relations: review.relations.map(toRelationViewModel),
  };
}

export function toGraphArtifactViewModel(
  review: GraphArtifactReview,
): GraphArtifactReviewViewModel {
  return {
    ...review,
    inputVersions: review.inputVersions.map((version) => ({ ...version })),
    integrity: {
      ...review.integrity,
      counts: { ...review.integrity.counts },
      findings: review.integrity.findings.map((finding) => ({ ...finding })),
    },
    scopeSummary: [...review.scopeSummary],
    taxonomyNodeTypes: [...review.taxonomyNodeTypes],
    taxonomyEdgeTypes: [...review.taxonomyEdgeTypes],
    progressive: { ...review.progressive },
    nodes: review.nodes.map((node) => ({
      ...node,
      logicalReference: node.logicalReference.map((part) => ({ ...part })),
      versionBindings: node.versionBindings.map((binding) => ({ ...binding })),
    })),
    edges: review.edges.map((edge) => ({
      ...edge,
      evidenceUseIds: [...edge.evidenceUseIds],
      dataAggregation: edge.dataAggregation
        ? { ...edge.dataAggregation }
        : null,
      relationTrace: edge.relationTrace
        ? {
            ...edge.relationTrace,
            premiseClaimIds: [...edge.relationTrace.premiseClaimIds],
            traceEvidenceIds: [...edge.relationTrace.traceEvidenceIds],
          }
        : null,
      relation: edge.relation ? toRelationViewModel(edge.relation) : null,
    })),
  };
}
