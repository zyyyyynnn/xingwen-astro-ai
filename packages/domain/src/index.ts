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
export { asEntityId } from "./identifiers";

export {
  ARTIFACT_KINDS,
  CACHE_POLICIES,
  CONTRACT_DRAFT_STATUSES,
  DERIVATION_KINDS,
  EXECUTION_MODES,
  EXPORT_FORMATS,
  RUN_STATUSES,
  SESSION_STATUSES,
  SOURCE_MODES,
  UNIT_POLICIES,
} from "./enums";
export type {
  ArtifactKind,
  CachePolicy,
  ContractDraftStatus,
  DerivationKind,
  ExecutionMode,
  ExportFormat,
  RunStatus,
  SessionStatus,
  SourceMode,
  UnitPolicy,
} from "./enums";
export {
  isArtifactKind,
  isExecutionMode,
  isRunStatus,
  isSourceMode,
  isTerminalRunStatus,
} from "./enums";

export type {
  DataRequirements,
  EvidenceRequirements,
  PaperSearchScope,
  QualityConstraints,
  ResearchContract,
  ResearchContractDraft,
  ResearchContractInput,
  SourceScope,
} from "./research-contract";
export { validateContractInputInvariants } from "./research-contract";

export type { ResearchProject } from "./project";

export type { RunEvent, ResearchRun } from "./run";
export { validateRunInvariants } from "./run";

export type {
  ArtifactContent,
  ArtifactVersion,
  ArtifactVersionMetadata,
  DatasetArtifactContent,
  DataCell,
  ExportArtifactContent,
  FieldDictionaryArtifactContent,
  GraphArtifactContent,
  LiteratureClaimsArtifactContent,
  LiteratureRelationsArtifactContent,
  PaperCollectionArtifactContent,
  PaperSummaryArtifactContent,
  ProducerReference,
  ProducerType,
  ReasoningTracesArtifactContent,
  ResearchArtifact,
  SourceCollectionArtifactContent,
} from "./artifact";
export { validateDatasetContentInvariants } from "./artifact";

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
  PaperSummaryEvidenceLocator,
  PaperSummaryEvidenceReview,
  PaperSummaryCacheAuditReview,
  PaperSummaryInputVersionsReview,
  PaperSummaryMetadataLocator,
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
  WorkspaceObjectRef,
  AtlasWorkspaceState,
  ObservatoryWorkspaceState,
  WorkspacePanelSlot,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "./workspace-snapshot";
