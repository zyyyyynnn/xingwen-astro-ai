/**
 * Paper summary review domain model (Literature Summary Workspace).
 *
 * A read-only projection of the PaperSummary API `PaperSummaryRead` transport contract into
 * the frontend domain: seven structured research sections, per-item evidence with locators and
 * support status, source-version conflicts, the model/prompt provenance and the
 * persisted SourceSnapshots. It carries no DOM, React or transport dependency.
 *
 * Support status is never inferred: a statement with no evidence is
 * `unsupported`, and a statement whose evidence cannot be verified is
 * `unverifiable`. The reading UI must surface these plainly and never present a
 * model-generated statement as an unconditional fact.
 */

import type { Evidence } from "./evidence";
import type { SourceMode } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type {
  PaperBenchmarkReview,
  PaperSourceFailureClass,
  ProducerExecutionSummary,
  SourceSnapshotSummary,
} from "./paper-acquisition";
import type {
  ContentHash,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";

/** Whether a summary statement or evidence item is backed by verifiable evidence. */
export const PAPER_SUMMARY_SUPPORT_STATUSES = [
  "supported",
  "unsupported",
  "unverifiable",
] as const;
export type PaperSummarySupportStatus =
  (typeof PAPER_SUMMARY_SUPPORT_STATUSES)[number];

export const PAPER_SUMMARY_SECTION_KINDS = [
  "background",
  "methodology",
  "dataset",
  "experiments",
  "discussion",
  "limitations",
  "research_questions",
] as const;
export type PaperSummarySectionKind =
  (typeof PAPER_SUMMARY_SECTION_KINDS)[number];

export const PAPER_SUMMARY_ITEM_KINDS = [
  "narrative",
  "objective",
  "workflow_step",
  "formula",
  "dataset",
  "experiment",
  "result",
  "contribution",
  "implication",
  "limitation",
  "research_question",
] as const;
export type PaperSummaryItemKind = (typeof PAPER_SUMMARY_ITEM_KINDS)[number];

/** Evidence locator for a short in-text quote inside a paper. */
export interface PaperSummaryTextLocator {
  readonly kind: "paper_text";
  readonly sourceUrl: string | null;
  readonly section: string;
  readonly paragraph: number | null;
  readonly textRange: string;
  readonly documentParseId: DomainEntityId | null;
  readonly documentParseOutputHash: ContentHash | null;
  readonly documentLocator: PaperSummaryDocumentLocator | null;
}

export interface PaperSummaryDocumentLocator {
  readonly pageIndex: number;
  readonly blockId: DomainEntityId | null;
  readonly readingOrder: number | null;
  readonly textSpan: { readonly start: number; readonly end: number } | null;
  readonly tableId: DomainEntityId | null;
  readonly cellId: DomainEntityId | null;
  readonly bbox: {
    readonly x1: number;
    readonly y1: number;
    readonly x2: number;
    readonly y2: number;
  } | null;
}

/** Evidence locator for a bibliographic metadata field value. */
export interface PaperSummaryMetadataLocator {
  readonly kind: "paper_metadata";
  readonly sourceUrl: string;
  readonly metadataField: string;
}

export type PaperSummaryEvidenceLocator =
  PaperSummaryTextLocator | PaperSummaryMetadataLocator;

/** One structured summary statement bound to its supporting evidence ids. */
export interface PaperSummaryStatementReview {
  readonly statementId: DomainEntityId;
  readonly itemKind: PaperSummaryItemKind;
  readonly text: string;
  readonly status: PaperSummarySupportStatus;
  readonly evidenceIds: readonly DomainEntityId[];
  readonly validationCode: DomainEntityId;
}

/** One of the seven evidence-backed sections in the current summary contract. */
export interface PaperSummarySectionReview {
  readonly sectionKind: PaperSummarySectionKind;
  readonly overview: PaperSummaryStatementReview | null;
  readonly items: readonly PaperSummaryStatementReview[];
}

/** One admitted summary evidence record with its locator and support status. */
export interface PaperSummaryEvidenceReview {
  readonly evidenceId: DomainEntityId;
  readonly paperId: DomainEntityId;
  readonly candidateId: DomainEntityId;
  readonly sourceId: DomainEntityId;
  readonly sourceRecordId: string;
  readonly sourceSnapshotId: DomainEntityId;
  readonly sourceSnapshotVersion: string;
  readonly sourceSnapshotContentHash: ContentHash;
  readonly locator: PaperSummaryEvidenceLocator;
  readonly quoteOrValue: string;
  readonly status: PaperSummarySupportStatus;
  readonly validationCode: DomainEntityId;
}

/** A retained source-version conflict; the snapshot version is authoritative. */
export interface PaperSummarySourceConflictReview {
  readonly conflictId: DomainEntityId;
  readonly evidenceId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly claimedSourceVersion: string;
  readonly sourceSnapshotVersion: string;
  readonly resolution: string;
}

/** The versioned inputs that produced the summary (for reproduction display). */
export interface PaperSummarySnapshotVersionReview {
  readonly sourceSnapshotId: DomainEntityId;
  readonly sourceId: DomainEntityId;
  readonly sourceVersion: string;
  readonly contentHash: ContentHash;
}

export interface PaperSummaryInputVersionsReview {
  readonly collection: {
    readonly artifactVersionId: DomainEntityId;
    readonly schemaVersion: SemanticVersion;
    readonly outputHash: ContentHash;
  } | null;
  readonly documentParses: readonly {
    readonly documentParseId: DomainEntityId;
    readonly candidateParseId: DomainEntityId;
    readonly researchInputId: DomainEntityId;
    readonly sourceSnapshotId: DomainEntityId;
    readonly inputContentHash: ContentHash;
    readonly canonicalOutputHash: ContentHash;
    readonly parserProfileId: DomainEntityId;
    readonly parserProfileVersion: SemanticVersion;
    readonly configHash: ContentHash;
  }[];
  readonly sourceSnapshots: readonly PaperSummarySnapshotVersionReview[];
}

/** Model/prompt provenance without private chain-of-thought or raw output. */
export interface PaperSummaryProducerReview {
  readonly executionId: DomainEntityId;
  readonly runId: DomainEntityId | null;
  readonly producerName: string;
  readonly producerVersion: SemanticVersion;
  readonly modelName: string;
  readonly modelRevision: string | null;
  readonly provider: DomainEntityId | null;
  readonly providerRequestId: string | null;
  readonly usage: {
    readonly promptTokens: number;
    readonly completionTokens: number;
    readonly totalTokens: number;
  } | null;
  readonly promptName: DomainEntityId;
  readonly promptVersion: string;
  readonly promptHash: ContentHash;
  readonly parametersVersion: SemanticVersion;
  readonly parametersHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly modelResponseHash: ContentHash;
  readonly outputHash: ContentHash | null;
  readonly status: string;
}

/** Bibliographic identity derived from the immutable input PaperCollection. */
export interface PaperSummaryPaperReview {
  readonly paperId: DomainEntityId;
  readonly title: string;
  readonly authors: readonly string[];
  readonly year: number | null;
}

/** Complete audit context for one cached source used by the summary input. */
export interface PaperSummaryCacheAuditReview {
  readonly sourceId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly cacheVersion: string;
  readonly cacheApplicability: string;
  readonly liveFailureClass: PaperSourceFailureClass;
  readonly liveFailureCode: string;
  readonly originRunId: DomainEntityId;
  readonly originArtifactVersionId: DomainEntityId;
}

/**
 * The complete paper summary review for one immutable ArtifactVersion.
 *
 * `evidence` carries the generic Artifact Read Boundary Evidence records (for the Provenance
 * Observatory and Share), while `summaryEvidence` carries the summary-internal
 * evidence with quotes/locators/status shown inline against each statement.
 */
export interface PaperSummaryReview {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly versionNumber: number;
  readonly supersedesVersionId: DomainEntityId | null;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly summaryId: DomainEntityId;
  readonly paperId: DomainEntityId;
  readonly paper: PaperSummaryPaperReview;
  readonly schemaVersion: SemanticVersion;
  readonly benchmark: PaperBenchmarkReview | null;
  readonly inputVersions: PaperSummaryInputVersionsReview;
  readonly background: PaperSummarySectionReview;
  readonly methodology: PaperSummarySectionReview;
  readonly dataset: PaperSummarySectionReview;
  readonly experiments: PaperSummarySectionReview;
  readonly discussion: PaperSummarySectionReview;
  readonly limitations: PaperSummarySectionReview;
  readonly researchQuestions: PaperSummarySectionReview;
  readonly summaryEvidence: readonly PaperSummaryEvidenceReview[];
  readonly sourceConflicts: readonly PaperSummarySourceConflictReview[];
  readonly producer: PaperSummaryProducerReview;
  readonly cacheAudits: readonly PaperSummaryCacheAuditReview[];
  /** Generic runtime execution record persisted alongside the version. */
  readonly producerExecution: ProducerExecutionSummary;
  readonly sourceSnapshots: readonly SourceSnapshotSummary[];
  readonly evidence: readonly Evidence[];
}
