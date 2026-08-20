import type {
  ArtifactKind,
  CachePolicy,
  CaseKey,
  ContractDraftStatus,
  ContentHash,
  DataArtifactReview,
  DerivationKind,
  DomainEntityId,
  ExecutionMode,
  GraphArtifactReview,
  LiteratureArtifactReview,
  PaperAcquisitionReview,
  ResearchGoal,
  ResearchPlanningCatalog,
  ResearchThreadAssistantPayload,
  ResearchThreadQuestionPayload,
  ResearchThreadSummary,
  ResearchThreadUserPayload,
  RepairCheckpointContext,
  RepairDecisionInput,
  RepairOutcome,
  RunStatus,
  ScientificTask,
  SemanticVersion,
  SourceMode,
  UnitPolicy,
  UtcIsoTimestamp,
  EvidenceTargetType,
  EvidenceType,
} from "@xingwen/domain";

export interface ProjectViewModel {
  readonly id: DomainEntityId;
  readonly name: string;
  readonly description: string;
  readonly caseKey: CaseKey;
  readonly activeDraftId: DomainEntityId | null;
  readonly activeContractId: DomainEntityId | null;
  readonly latestRunId: DomainEntityId | null;
  readonly latestRunStatus: RunStatus | null;
  readonly latestRunFailureSummary: string | null;
  readonly threadSummary: ResearchThreadSummary;
  readonly revision: number;
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
}

export type ResearchPlanningCatalogViewModel = ResearchPlanningCatalog;

interface ResearchThreadEntryViewModelBase<Kind, Actor, Payload> {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly sequence: number;
  readonly kind: Kind;
  readonly actor: Actor;
  readonly publicContent: string;
  readonly structuredPayload: Payload;
  readonly modelExecutionId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

export type ResearchThreadEntryViewModel =
  | ResearchThreadEntryViewModelBase<
      "user_message",
      "user",
      ResearchThreadUserPayload
    >
  | ResearchThreadEntryViewModelBase<
      "clarification_answer",
      "user",
      ResearchThreadUserPayload
    >
  | ResearchThreadEntryViewModelBase<
      "assistant_reasoning",
      "assistant",
      ResearchThreadAssistantPayload
    >
  | ResearchThreadEntryViewModelBase<
      "assistant_message",
      "assistant",
      ResearchThreadAssistantPayload
    >
  | ResearchThreadEntryViewModelBase<
      "clarification_question",
      "assistant",
      ResearchThreadQuestionPayload
    >;

export interface ResearchTurnViewModel {
  readonly outcome:
    | "clarification_required"
    | "draft_ready"
    | "partial"
    | "unsupported"
    | "refused";
  readonly entries: readonly ResearchThreadEntryViewModel[];
  readonly activeDraftId: DomainEntityId | null;
  readonly modelExecutionId: DomainEntityId;
}

export interface RunStepViewModel {
  readonly id: DomainEntityId;
  readonly runId: DomainEntityId;
  readonly position: number;
  readonly key: DomainEntityId;
  readonly label: string;
  readonly status:
    | "pending"
    | "running"
    | "waiting"
    | "completed"
    | "failed"
    | "cancelled"
    | "skipped";
  readonly progress: number;
  readonly publicMessage: string;
  readonly startedAt: UtcIsoTimestamp | null;
  readonly finishedAt: UtcIsoTimestamp | null;
  readonly failureCode: string | null;
}

export interface ContractInputViewModel {
  readonly researchGoal: ResearchGoal;
  readonly targetObjects: readonly DomainEntityId[];
  readonly dataRequirements: {
    readonly unitPolicy: UnitPolicy;
  };
  readonly requestedFields: readonly DomainEntityId[];
  readonly sourceScope: {
    readonly allowedSources: readonly DomainEntityId[];
  };
  readonly paperSearchScope: {
    readonly keywords: readonly string[];
    readonly yearFrom: number | null;
    readonly yearTo: number | null;
    readonly sourceIds: readonly DomainEntityId[];
    readonly maxCandidates: number;
  };
  readonly scientificTasks: readonly ScientificTask[];
  readonly outputRequirements: readonly ArtifactKind[];
  readonly evidenceRequirements: {
    readonly requireLocator: boolean;
    readonly requireSourceSnapshot: boolean;
    readonly minimumCoverage: number;
  };
  readonly qualityConstraints: {
    readonly sourceCompletenessMin: number;
    readonly unitConsistencyMin: number;
  };
}

export interface ResearchContractDraftViewModel {
  readonly id: DomainEntityId;
  readonly version: number;
  readonly intent: string;
  readonly status: ContractDraftStatus;
  readonly contract: ContractInputViewModel;
  readonly warnings: readonly string[];
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
  readonly expiresAt: UtcIsoTimestamp;
}

export interface ResearchContractViewModel extends ContractInputViewModel {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly version: number;
  readonly createdAt: UtcIsoTimestamp;
  readonly createdFromDraftId: DomainEntityId;
  readonly provenance: {
    readonly contentHash: ContentHash;
  };
}

export interface ResearchRunViewModel {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly contractId: DomainEntityId;
  readonly executionMode: ExecutionMode;
  readonly status: RunStatus;
  readonly progress: number;
  readonly revision: number;
  readonly latestEventSequence: number;
  readonly parentRunId: DomainEntityId | null;
  readonly derivationKind: DerivationKind;
  readonly retryFromStep: DomainEntityId | null;
  readonly cachePolicy: CachePolicy;
  readonly startedAt: UtcIsoTimestamp | null;
  readonly finishedAt: UtcIsoTimestamp | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
  readonly failure: {
    readonly code: string | null;
    readonly summary: string | null;
  } | null;
  readonly isTerminal: boolean;
  readonly isFailed: boolean;
  readonly isCancelled: boolean;
}

export interface ResearchArtifactViewModel {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly kind: ArtifactKind;
  readonly title: string;
  readonly logicalKey: DomainEntityId;
  readonly latestVersionId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

export interface ProducerReferenceViewModel {
  readonly type: "pipeline" | "model" | "algorithm";
  readonly name: string;
  readonly version: string;
  readonly modelName: string | null;
  readonly promptName: string | null;
  readonly promptVersion: string | null;
  readonly parametersHash: ContentHash | null;
}

export interface ArtifactVersionProvenanceViewModel {
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly producer: ProducerReferenceViewModel;
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly supersedesVersionId: DomainEntityId | null;
}

export interface ArtifactVersionMetadataViewModel {
  readonly id: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly createdByRunId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: SemanticVersion;
  readonly sourceMode: SourceMode;
  readonly createdAt: UtcIsoTimestamp;
  readonly provenance: ArtifactVersionProvenanceViewModel;
}

export interface DatabaseCellLocatorViewModel {
  readonly kind: "database_cell";
  readonly queryHash: string;
  readonly rowKey: string;
  readonly field: DomainEntityId;
}

export interface PaperTextLocatorViewModel {
  readonly kind: "paper_text";
  readonly section: string;
  readonly page: number | null;
  readonly paragraph: number | null;
  readonly range: string | null;
}

export interface ModelExtractionLocatorViewModel {
  readonly kind: "model_extraction";
  readonly inputEvidenceId: DomainEntityId;
  readonly promptName: string;
  readonly modelVersion: string;
}

export interface ReasoningTraceLocatorViewModel {
  readonly kind: "reasoning_trace";
  readonly relationId: DomainEntityId;
  readonly stepKey: DomainEntityId;
}

export type EvidenceLocatorViewModel =
  | DatabaseCellLocatorViewModel
  | PaperTextLocatorViewModel
  | ModelExtractionLocatorViewModel
  | ReasoningTraceLocatorViewModel;

export interface EvidenceViewModel {
  readonly id: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly targetType: EvidenceTargetType;
  readonly targetId: DomainEntityId;
  readonly evidenceType: EvidenceType;
  readonly sourceSnapshotId: DomainEntityId | null;
  readonly paperId: DomainEntityId | null;
  readonly locator: EvidenceLocatorViewModel | null;
  readonly quoteOrValue: string | null;
  readonly extractionMethod: string;
  readonly confidence: number;
  readonly createdAt: UtcIsoTimestamp;
  readonly source: {
    readonly sourceId: string;
    readonly sourceType: string;
    readonly retrievedAt: UtcIsoTimestamp;
    readonly licenseNote: string;
    readonly sourceVersionOrEtag: string | null;
    readonly requestMetadata: Readonly<Record<string, unknown>>;
  } | null;
}

export interface RunCheckpointViewModel {
  readonly id: DomainEntityId;
  readonly runId: DomainEntityId;
  readonly runRevision: number;
  readonly stepKey: DomainEntityId;
  readonly question: string;
  readonly options: readonly string[];
  readonly kind: "choice" | "scientific_repair";
  readonly repairContext: RepairCheckpointContext | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly selectedOption: string | null;
  readonly freeText: string | null;
  readonly repairDecisions: readonly RepairDecisionInput[];
  readonly repairOutcome: RepairOutcome | null;
  readonly decidedAt: UtcIsoTimestamp | null;
  readonly isAnswered: boolean;
}

/** UI-safe projection of typed data artifact reads. */
export type DataArtifactReviewViewModel = DataArtifactReview;
export type PaperAcquisitionReviewViewModel = PaperAcquisitionReview;
export type LiteratureArtifactReviewViewModel = LiteratureArtifactReview;
export type LiteratureClaimsArtifactReviewViewModel = Extract<
  LiteratureArtifactReview,
  { readonly kind: "literature_claims" }
>;
export type LiteratureRelationsArtifactReviewViewModel = Extract<
  LiteratureArtifactReview,
  { readonly kind: "literature_relations" }
>;
export type ReasoningTracesArtifactReviewViewModel = Extract<
  LiteratureArtifactReview,
  { readonly kind: "reasoning_traces" }
>;
export type GraphArtifactReviewViewModel = GraphArtifactReview;
export type DatasetArtifactReviewViewModel = Extract<
  DataArtifactReview,
  { readonly kind: "dataset" }
>;
export type FieldDictionaryArtifactReviewViewModel = Extract<
  DataArtifactReview,
  { readonly kind: "field_dictionary" }
>;
export type SourceCollectionArtifactReviewViewModel = Extract<
  DataArtifactReview,
  { readonly kind: "source_collection" }
>;
export type DataArtifactFieldDefinitionViewModel =
  | DatasetArtifactReviewViewModel["columns"][number]
  | FieldDictionaryArtifactReviewViewModel["fieldDefinitions"][number];
export type DatasetCellReviewViewModel =
  DatasetArtifactReviewViewModel["rows"][number]["cells"][number];
