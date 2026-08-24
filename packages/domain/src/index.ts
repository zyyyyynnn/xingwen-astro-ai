/**
 * @xingwen/domain — the framework-free frontend domain model.
 *
 * This package contains pure TypeScript types and invariant helpers only. It
 * must not depend on React, Astro, Vite, HTTP, DOM or any browser/global API.
 * Purity is enforced by `scripts/check-frontend-architecture.mjs`.
 *
 * Entity shapes mirror the Pydantic `/api` authoring source
 * (`apps/api/src/app/schemas/core.py`) using frontend camelCase convention.
 * Transport DTO mapping lives in `@xingwen/data-access`.
 */

export type {
  CaseKey,
  ContentHash,
  NonEmptyString,
  ResearchGoal,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";
export { CASE_KEY, CONTRACT_VERSION } from "./value-types";

export type { DomainEntityId } from "./identifiers";
export { asEntityId, parseEntityId } from "./identifiers";

export {
  ARTIFACT_KINDS,
  CACHE_POLICIES,
  CONTRACT_DRAFT_STATUSES,
  DERIVATION_KINDS,
  DOCUMENT_SOURCE_POLICIES,
  EXECUTION_MODES,
  EXPORT_FORMATS,
  RUN_STATUSES,
  SCIENTIFIC_SKILL_IDS,
  SESSION_STATUSES,
  SOURCE_MODES,
  UNIT_POLICIES,
} from "./enums";
export type {
  ArtifactKind,
  CachePolicy,
  ContractDraftStatus,
  DerivationKind,
  DocumentSourcePolicy,
  ExecutionMode,
  ExportFormat,
  RunStatus,
  ScientificSkillId,
  SessionStatus,
  SourceMode,
  UnitPolicy,
} from "./enums";
export {
  isArtifactKind,
  isExecutionMode,
  isRunStatus,
  isScientificSkillId,
  isSourceMode,
  isTerminalRunStatus,
} from "./enums";

export type {
  DataRequirements,
  EvidenceRequirements,
  JsonValue,
  PaperSearchScope,
  QualityConstraints,
  ResearchContract,
  ResearchContractDraft,
  ResearchContractInput,
  ScientificTask,
  SourceScope,
} from "./research-contract";
export { validateContractInputInvariants } from "./research-contract";

export type { ResearchProject, ResearchThreadSummary } from "./project";

export type {
  ResearchCatalogOption,
  ResearchPlanningCatalog,
} from "./research-catalog";

export type {
  ResearchThreadActor,
  ResearchThreadEntry,
  ResearchThreadEntryKind,
  ResearchThreadAssistantPayload,
  ResearchThreadPublicOutcome,
  ResearchThreadQuestionPayload,
  ResearchThreadUserPayload,
  ResearchTurn,
  ResearchTurnOutcome,
} from "./research-thread";

export type {
  ModelExecutionRecord,
  ModelExecutionStatus,
} from "./model-execution";

export type {
  RunEvent,
  ResearchRun,
  RunCheckpoint,
  ChoiceCheckpointDecisionRequest,
  RepairAction,
  RepairCheckpointContext,
  RepairCheckpointDecisionRequest,
  RepairDecisionInput,
  RepairCandidateSummary,
  RepairDefect,
  RepairEvidenceFact,
  RepairOutcome,
  RepairRuleSetReference,
  RunCheckpointDecisionRequest,
} from "./run";
export { validateRunInvariants } from "./run";
export type { RunStepSnapshot, RunStepStatus } from "./run-step";

export type {
  ArtifactVersion,
  ArtifactVersionContent,
  ArtifactVersionMetadata,
  ArtifactVersionSummary,
  ProducerReference,
  ProducerType,
  ResearchArtifact,
} from "./artifact";

export type {
  DatabaseCellLocator,
  Evidence,
  EvidenceLocator,
  EvidenceTargetType,
  EvidenceType,
  LocatorKind,
  ModelExtractionLocator,
  PaperTextLocator,
  ReasoningTraceLocator,
} from "./evidence";
export {
  EVIDENCE_TARGET_TYPES,
  EVIDENCE_TYPES,
  isEvidenceTargetType,
  isEvidenceType,
  LOCATOR_KINDS,
} from "./evidence";

export type { EvidenceCompleteness, ProvenanceState } from "./provenance";
export { evidenceCompletenessRatio } from "./provenance";

export type {
  CachedSnapshotOrigin,
  PaperAcquisitionMetrics,
  PaperAcquisitionReview,
  PaperAcquisitionRules,
  PaperAcquisitionRunReview,
  PaperBenchmarkReview,
  PaperCacheAudit,
  PaperCandidateConflictReview,
  PaperCandidateReview,
  PaperCandidateSelection,
  PaperDataLevel,
  PaperDuplicateReview,
  PaperQueryPaginationReview,
  PaperRawRecordReview,
  PaperSearchReview,
  PaperSourceExecutionReview,
  PaperSourceFailureClass,
  PaperSourcePageReview,
  PaperSourceParametersReview,
  ProducerExecutionSummary,
  ReviewMetadataEntry,
  SourceSnapshotSummary,
} from "./paper-acquisition";
export { safeExternalUrl } from "./paper-acquisition";
export type {
  AnalysisReportReviewContent,
  ChartAxisReview,
  ChartPointReview,
  ChartSeriesReview,
  ChartVisualizationReview,
  FitsImageVisualizationReview,
  LightCurveArtifactReviewContent,
  LightCurvePointReview,
  ModelArtifactReviewContent,
  ModelBinaryReview,
  ModelDiagnosticVisualizationReview,
  ModelEvaluationReviewContent,
  ModelSplitReview,
  ModelTrainingInputReview,
  PeriodogramPeakReview,
  ScientificArtifactReview,
  ScientificArtifactReviewContent,
  ScientificFindingReview,
  ScientificMetricReview,
  ScientificResultBlockReview,
  ScientificSkillExecutionReview,
  ScientificSkillStatus,
  ScientificSupportStatus,
  ScientificVisualizationSpecReview,
  SpectrumArtifactReviewContent,
  SpectrumLineReview,
  SpectrumPointReview,
  VisualizationReviewContent,
  WwtAnnotationReview,
  WwtCartesianTableCoordinatesReview,
  WwtConstellationOverlaysReview,
  WwtCoordinateGridReview,
  WwtCoordinateReview,
  WwtCoordinateViewReview,
  WwtFitsLayerReview,
  WwtForegroundReview,
  WwtObserverReview,
  WwtReadbackRequest,
  WwtSceneStepReview,
  WwtSceneVisualizationReview,
  WwtSolarSystemOptionsReview,
  WwtSphericalTableCoordinatesReview,
  WwtTableCoordinatesReview,
  WwtTableLayerReview,
  WwtTableTimeSeriesReview,
  WwtTimeControlReview,
  WwtTrackedObjectViewReview,
  WwtViewReview,
} from "./scientific-artifact";

export type {
  PaperSummaryEvidenceLocator,
  PaperSummaryEvidenceReview,
  PaperSummaryCacheAuditReview,
  PaperSummaryInputVersionsReview,
  PaperSummaryMetadataLocator,
  PaperSummaryDocumentSourceReview,
  PaperSummaryProducerReview,
  PaperSummaryPaperReview,
  PaperSummaryReview,
  PaperSummarySnapshotVersionReview,
  PaperSummarySourceConflictReview,
  PaperSummaryStatementReview,
  PaperSummarySupportStatus,
  PaperSummaryTextLocator,
} from "./paper-summary";
export { PAPER_SUMMARY_SUPPORT_STATUSES } from "./paper-summary";

export type {
  ShareSnapshot,
  ShareSnapshotCreated,
  CreateShareSnapshotRequest,
  PublicShareSnapshot,
  PublicArtifactVersion,
  PublicEvidence,
} from "./share-snapshot";

export type {
  ArtifactExport,
  ArtifactExportDownload,
  ArtifactExportFormat,
} from "./artifact-export";

export type {
  DataArtifactCellStatus,
  DataArtifactFieldDefinition,
  DataArtifactFieldSourceAlias,
  DataArtifactKind,
  DataArtifactQualityProjection,
  DataArtifactReview,
  DataArtifactReviewBase,
  DataArtifactSourceSnapshot,
  DatasetArtifactReview,
  DatasetCellReview,
  DatasetRowReview,
  FieldDictionaryArtifactReview,
  SourceCollectionArtifactReview,
  SourceCollectionMemberReview,
} from "./data-artifact";

export type {
  LiteratureArtifactReview,
  LiteratureArtifactVersionReview,
  LiteratureClaimReferenceReview,
  LiteratureClaimReview,
  LiteratureClaimsArtifactReview,
  LiteratureReasoningTraceReview,
  LiteratureReasoningTraceStepReview,
  LiteratureRelationComparabilityReview,
  LiteratureRelationConfidenceReview,
  LiteratureRelationDirectionReview,
  LiteratureRelationReview,
  LiteratureRelationsArtifactReview,
} from "./literature-artifact";

export type {
  GraphArtifactReview,
  GraphDataAggregationReview,
  GraphEdgeReview,
  GraphIntegrityReview,
  GraphNodeReview,
  GraphRelationTraceBindingReview,
  GraphVersionReferenceReview,
} from "./graph-artifact";

export type {
  WorkspaceObjectRef,
  AtlasWorkspaceState,
  ObservatoryWorkspaceState,
  WorkspacePanelSlot,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "./workspace-snapshot";

export type {
  FeedbackCategory,
  FeedbackTargetType,
  RevisionConflict,
  RevisionPlan,
  RevisionVersionDecision,
  UserFeedback,
} from "./revision";

export type {
  ConfigureModelProviderInput,
  ModelProviderConfigurationSource,
  ModelProviderConfigurationStatus,
  ModelProviderPreset,
} from "./model-provider";
