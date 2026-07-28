/**
 * Paper acquisition review domain model (A-05).
 *
 * A UI-facing projection of the B-06 `PaperCollectionRead` /
 * `PaperCollectionCandidateRead` transport contract. It is deliberately NOT a
 * field-by-field DTO mirror: identifiers are branded, optionality is resolved
 * into explicit `null`, state is expressed as discriminated unions, and
 * reproduction-critical provenance (hashes, versions, snapshots) is kept while
 * private transport details (auth headers, cookies, raw source parameters and
 * raw responses) are never carried into the domain.
 *
 * Ranking is authored by the backend pipeline: `stableRank` labels the
 * server-provided candidate order and is never recomputed client-side.
 */

import type { SourceMode } from "./enums";
import type { Evidence } from "./evidence";
import type { DomainEntityId } from "./identifiers";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

/** Scientific data level of a source execution, distinct from `SourceMode`. */
export type PaperDataLevel =
  | "live_result"
  | "real_run_cache"
  | "fixture"
  | "recorded_response"
  | "benchmark"
  | "manual_review";

/** Upstream failure classification reported by the acquisition pipeline. */
export type PaperSourceFailureClass =
  | "timeout"
  | "rate_limited"
  | "transport"
  | "upstream_server"
  | "upstream_client"
  | "invalid_response"
  | "policy_violation";

/** Normalized search parameters the acquisition actually executed. */
export interface PaperSearchReview {
  readonly originalQuery: string;
  readonly normalizedQuery: string;
  readonly keywords: readonly string[];
  readonly yearFrom: number;
  readonly yearTo: number;
  readonly sourceIds: readonly DomainEntityId[];
  readonly sortStrategy: string;
  readonly candidateLimit: number;
  readonly queryHash: ContentHash;
}

/** Pipeline-local acquisition execution summary (never a ResearchRun). */
export interface PaperAcquisitionRunReview {
  readonly acquisitionId: DomainEntityId;
  readonly status: "completed" | "partial" | "failed";
  readonly startedAt: UtcIsoTimestamp;
  readonly finishedAt: UtcIsoTimestamp;
  readonly candidateCount: number;
  readonly selectedCount: number;
  readonly duplicateGroupCount: number;
  readonly sourceFailureCount: number;
}

/** Frozen benchmark identity when the collection derives from X-00 seeds. */
export interface PaperBenchmarkReview {
  readonly benchmarkId: DomainEntityId;
  readonly benchmarkVersion: string;
  readonly scenarioId: DomainEntityId;
  readonly schemaVersion: string;
  readonly contentHash: ContentHash;
}

/** Contract-reported acquisition metrics; the UI never re-derives them. */
export interface PaperAcquisitionMetrics {
  readonly candidateCount: number;
  readonly selectedCount: number;
  readonly duplicateCandidateCount: number;
  readonly duplicateRate: number;
  readonly expectedCandidateCount: number;
  readonly recalledExpectedCandidateCount: number;
  readonly candidateRecall: number | null;
  readonly sourceExecutionCount: number;
  readonly sourceFailureCount: number;
  readonly sourceEmptyResultCount: number;
}

/** Versioned rule identifiers proving which algorithms produced the result. */
export interface PaperAcquisitionRules {
  readonly dedupeRule: string;
  readonly rankingRule: string;
  readonly adapterName: string;
  readonly adapterVersion: string;
  readonly queryNormalizationVersion: string;
  readonly canonicalizationVersion: string;
  readonly dedupeVersion: string;
  readonly rankingVersion: string;
  readonly selectionVersion: string;
  readonly selectionLimit: number;
  readonly retryPolicyVersion: string;
  readonly sourcePolicyVersion: string;
}

/** One page fetched from a source, kept for rate-limit and audit review. */
export interface PaperSourcePageReview {
  readonly pageNumber: number;
  readonly statusCode: number;
  readonly retrievedAt: UtcIsoTimestamp;
  readonly returnedRows: number;
  readonly attemptCount: number;
  readonly rateLimitMetadata: Readonly<Record<string, string | number | null>>;
}

/** Per-source execution outcome as reported by the contract. */
export interface PaperSourceExecutionReview {
  readonly sourceId: DomainEntityId;
  readonly sourceMode: SourceMode;
  readonly dataLevel: PaperDataLevel;
  readonly status: "completed" | "failed";
  readonly failureClass: PaperSourceFailureClass | null;
  readonly failureCode: string | null;
  readonly candidateCount: number;
  readonly retryCount: number;
  readonly startedAt: UtcIsoTimestamp;
  readonly finishedAt: UtcIsoTimestamp;
  readonly queryHash: ContentHash;
  readonly sourceSnapshotId: DomainEntityId | null;
  readonly pages: readonly PaperSourcePageReview[];
}

/** Producer execution summary; parameters stay behind their hash. */
export interface ProducerExecutionSummary {
  readonly id: DomainEntityId;
  readonly producerName: string;
  readonly producerVersion: string;
  readonly status:
    "running" | "completed" | "failed" | "rejected" | "cancelled";
  readonly startedAt: UtcIsoTimestamp;
  readonly finishedAt: UtcIsoTimestamp | null;
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash | null;
  readonly parametersHash: ContentHash;
  readonly latencyMs: number | null;
  readonly errorCode: string | null;
}

/** Reproduction-critical snapshot identity without raw request internals. */
export interface SourceSnapshotSummary {
  readonly id: DomainEntityId;
  readonly sourceId: DomainEntityId;
  readonly sourceType: string;
  readonly retrievedAt: UtcIsoTimestamp;
  readonly queryHash: ContentHash;
  readonly contentHash: ContentHash;
  readonly sourceVersionOrEtag: string | null;
  readonly licenseNote: string;
  readonly cacheVersion: string | null;
}

/** Field-level duplicate conflict or uncertain match between candidates. */
export interface PaperCandidateConflictReview {
  readonly classification: "conflict" | "uncertain_match";
  readonly field: "doi" | "arxiv_id" | "title" | "year" | "authors";
  readonly detail: string;
  readonly relatedCandidateId: DomainEntityId;
}

/** Duplicate group with its canonical winner and the match justification. */
export interface PaperDuplicateReview {
  readonly groupId: DomainEntityId;
  readonly canonicalPaperId: DomainEntityId;
  readonly candidateIds: readonly DomainEntityId[];
  readonly matchBasis: readonly string[];
  readonly conflicts: readonly PaperCandidateConflictReview[];
}

/** Selection outcome as a discriminated union — never a bare boolean pair. */
export type PaperCandidateSelection =
  | { readonly kind: "selected"; readonly reason: string | null }
  | { readonly kind: "excluded"; readonly reason: string | null };

/** One reviewable candidate in authoritative server ranking order. */
export interface PaperCandidateReview {
  readonly candidateId: DomainEntityId;
  readonly canonicalPaperId: DomainEntityId;
  readonly title: string;
  readonly authors: readonly string[];
  readonly year: number | null;
  readonly doi: string | null;
  readonly arxivId: string | null;
  readonly url: string | null;
  readonly relevanceScore: number;
  /** 1-based position in the server ranking order; never recomputed. */
  readonly stableRank: number;
  readonly selection: PaperCandidateSelection;
  readonly rankingRuleVersion: string;
  readonly selectionRuleVersion: string;
  readonly duplicateGroup: PaperDuplicateReview;
  readonly sourceSnapshot: SourceSnapshotSummary;
  readonly evidence: readonly Evidence[];
}

/** The complete reviewable acquisition pinned to one immutable version. */
export interface PaperAcquisitionReview {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly schemaVersion: string;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly query: PaperSearchReview;
  readonly acquisition: PaperAcquisitionRunReview;
  readonly benchmark: PaperBenchmarkReview;
  readonly metrics: PaperAcquisitionMetrics;
  readonly rules: PaperAcquisitionRules;
  readonly sourceExecutions: readonly PaperSourceExecutionReview[];
  readonly producerExecution: ProducerExecutionSummary;
  readonly candidates: readonly PaperCandidateReview[];
}

/**
 * Return the candidate's external URL only when it is a safe http(s) link;
 * anything else (javascript:, data:, malformed) must render as plain text.
 *
 * Pure string validation: this package must stay free of DOM/global APIs, so
 * the scheme is anchored explicitly instead of relying on the `URL` parser.
 */
const SAFE_EXTERNAL_URL = /^https?:\/\/\S+$/iu;

export function safeExternalUrl(url: string | null): string | null {
  if (url === null) return null;
  const trimmed = url.trim();
  return SAFE_EXTERNAL_URL.test(trimmed) ? trimmed : null;
}
