import {
  isTerminalRunStatus,
  type ArtifactVersionMetadata,
  type Evidence,
  type EvidenceLocator,
  type ResearchArtifact,
  type ResearchContract,
  type ResearchContractDraft,
  type ResearchContractInput,
  type ResearchProject,
  type ResearchRun,
  type ResearchThreadEntry,
  type ResearchTurn,
  type RunStepSnapshot,
} from "@xingwen/domain";

import type {
  ArtifactVersionMetadataViewModel,
  ContractInputViewModel,
  DatabaseCellLocatorViewModel,
  EvidenceLocatorViewModel,
  EvidenceViewModel,
  ModelExtractionLocatorViewModel,
  PaperTextLocatorViewModel,
  ProducerReferenceViewModel,
  ProjectViewModel,
  ReasoningTraceLocatorViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
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
        : entry.kind === "assistant_analysis" ||
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

export function toArtifactVersionViewModel(
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
  };
}
