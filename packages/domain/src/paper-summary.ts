/**
 * Paper summary review domain model (A-06).
 *
 * A read-only projection of the B-07 `PaperSummaryRead` transport contract into
 * the frontend domain: structured summary statements (goal, method, dataset,
 * findings, limitations, future work), per-item evidence with locators and
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

/** Evidence locator for a short in-text quote inside a paper. */
export interface PaperSummaryTextLocator {
  readonly kind: "paper_text";
  readonly sourceUrl: string;
  readonly section: string;
  readonly paragraph: number | null;
  readonly textRange: string;
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
  readonly text: string;
  readonly status: PaperSummarySupportStatus;
  readonly evidenceIds: readonly DomainEntityId[];
  readonly validationCode: DomainEntityId;
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
  readonly paperCollectionVersionId: DomainEntityId;
  readonly paperCollectionSchemaVersion: SemanticVersion;
  readonly paperCollectionOutputHash: ContentHash;
  readonly sourceSnapshots: readonly PaperSummarySnapshotVersionReview[];
}

/** Model/prompt provenance without private chain-of-thought or raw output. */
export interface PaperSummaryProducerReview {
  readonly executionId: DomainEntityId;
  readonly runId: DomainEntityId | null;
  readonly producerName: string;
  readonly producerVersion: SemanticVersion;
  readonly modelName: string;
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

/**
 * The complete paper summary review for one immutable ArtifactVersion.
 *
 * `evidence` carries the generic B-18 Evidence records (for the Provenance
 * Observatory and Share), while `summaryEvidence` carries the summary-internal
 * evidence with quotes/locators/status shown inline against each statement.
 */
export interface PaperSummaryReview {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly summaryId: DomainEntityId;
  readonly paperId: DomainEntityId;
  readonly schemaVersion: SemanticVersion;
  readonly benchmark: PaperBenchmarkReview;
  readonly inputVersions: PaperSummaryInputVersionsReview;
  readonly researchGoal: PaperSummaryStatementReview | null;
  readonly method: PaperSummaryStatementReview | null;
  readonly dataset: PaperSummaryStatementReview | null;
  readonly findings: readonly PaperSummaryStatementReview[];
  readonly limitations: readonly PaperSummaryStatementReview[];
  readonly futureWork: readonly PaperSummaryStatementReview[];
  readonly summaryEvidence: readonly PaperSummaryEvidenceReview[];
  readonly sourceConflicts: readonly PaperSummarySourceConflictReview[];
  readonly producer: PaperSummaryProducerReview;
  /** Generic runtime execution record persisted alongside the version. */
  readonly producerExecution: ProducerExecutionSummary;
  readonly sourceSnapshots: readonly SourceSnapshotSummary[];
  readonly evidence: readonly Evidence[];
}
