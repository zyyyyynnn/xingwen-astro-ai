/**
 * Paper acquisition review repository (A-05) over the B-06 read boundary.
 *
 * One deep port method — `getReview(artifactVersionId)` — hides the entire
 * transport protocol:
 *
 * - `GET /api/v2/artifact-versions/{id}/paper-collection` (required read)
 * - cursor-paged `GET .../paper-candidates` until exhausted
 * - generated-contract validation of every payload
 * - integrity guards: non-advancing/looping cursors, duplicate candidates,
 *   count mismatches and ranking drift against the collection order
 * - a single DTO→domain assembly shared verbatim with the fixture adapter
 *
 * The server ranking order is authoritative: `stableRank` labels the received
 * order and no scientific ranking, dedupe or selection is recomputed here.
 */

import type {
  EvidenceDetail as EvidenceDetailDto,
  PaperCollection as PaperCollectionDto,
  PaperCollectionCandidateRead as PaperCollectionCandidateReadDto,
  PaperCollectionRead as PaperCollectionReadDto,
  PaperDuplicateGroup as PaperDuplicateGroupDto,
  PaperSourceExecution as PaperSourceExecutionDto,
  ProducerExecutionDetail as ProducerExecutionDetailDto,
  SourceSnapshotDetail as SourceSnapshotDetailDto,
} from "@xingwen/contracts";
import { parseV2Dto } from "@xingwen/contracts";
import type {
  ContentHash,
  DomainEntityId,
  PaperAcquisitionReview,
  PaperCandidateReview,
  PaperCandidateSelection,
  PaperDuplicateReview,
  PaperSearchReview,
  PaperSourceExecutionReview,
  ProducerExecutionSummary,
  SourceMode,
  SourceSnapshotSummary,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { HttpClient, seg } from "./http-client";
import { ValidationError } from "./http-errors";
import { mapEvidenceDetail } from "./mapping";
import type { PaperAcquisitionRepository } from "./ports";

/** Internal page size; deliberately not exposed through the port. */
const CANDIDATE_PAGE_SIZE = 50;

function contractViolation(detail: string): ValidationError {
  return new ValidationError(detail, "PAPER_REVIEW_CONTRACT_VIOLATION", []);
}

function mapId(value: string): DomainEntityId {
  return asEntityId(value);
}

function mapSnapshotSummary(
  dto: SourceSnapshotDetailDto,
): SourceSnapshotSummary {
  return {
    id: mapId(dto.id),
    sourceId: mapId(dto.source_id),
    sourceType: dto.source_type,
    retrievedAt: dto.retrieved_at as UtcIsoTimestamp,
    queryHash: dto.query_hash as ContentHash,
    contentHash: dto.content_hash as ContentHash,
    sourceVersionOrEtag: dto.source_version_or_etag ?? null,
    licenseNote: dto.license_note,
    cacheVersion: dto.cache_version ?? null,
  };
}

function mapProducerExecutionSummary(
  dto: ProducerExecutionDetailDto,
): ProducerExecutionSummary {
  return {
    id: mapId(dto.id),
    producerName: dto.producer.name,
    producerVersion: dto.producer.version,
    status: dto.status,
    startedAt: dto.started_at as UtcIsoTimestamp,
    finishedAt: (dto.finished_at ?? null) as UtcIsoTimestamp | null,
    inputHash: dto.input_hash as ContentHash,
    outputHash: (dto.output_hash ?? null) as ContentHash | null,
    parametersHash: dto.parameters_hash as ContentHash,
    latencyMs: dto.latency_ms ?? null,
    errorCode: dto.error_code ?? null,
  };
}

function mapDuplicateGroup(dto: PaperDuplicateGroupDto): PaperDuplicateReview {
  return {
    groupId: mapId(dto.duplicate_group_id),
    canonicalPaperId: mapId(dto.canonical_paper_id),
    candidateIds: dto.candidate_ids.map(mapId),
    matchBasis: [...dto.match_basis],
    conflicts: (dto.conflicts ?? []).map((conflict) => ({
      classification: conflict.classification,
      field: conflict.field,
      detail: conflict.detail,
      relatedCandidateId: mapId(conflict.related_candidate_id),
    })),
  };
}

function mapSourceExecution(
  dto: PaperSourceExecutionDto,
): PaperSourceExecutionReview {
  return {
    sourceId: mapId(dto.source_id),
    sourceMode: dto.source_mode as SourceMode,
    dataLevel: dto.data_level,
    status: dto.status,
    failureClass: dto.failure_class ?? null,
    failureCode: dto.failure_code ?? null,
    candidateCount: dto.candidate_count,
    retryCount: dto.retry_count,
    startedAt: dto.started_at as UtcIsoTimestamp,
    finishedAt: dto.finished_at as UtcIsoTimestamp,
    queryHash: dto.query_hash as ContentHash,
    sourceSnapshotId: dto.source_snapshot_id
      ? mapId(dto.source_snapshot_id)
      : null,
    pages: (dto.pages ?? []).map((page) => ({
      pageNumber: page.page_number,
      statusCode: page.status_code,
      retrievedAt: page.retrieved_at as UtcIsoTimestamp,
      returnedRows: page.returned_rows,
      attemptCount: page.attempt_count,
      rateLimitMetadata: { ...(page.rate_limit_metadata ?? {}) },
    })),
  };
}

function mapQuery(collection: PaperCollectionDto): PaperSearchReview {
  const query = collection.query;
  return {
    originalQuery: query.original_query_string,
    normalizedQuery: query.normalized_query_string,
    keywords: [...query.normalized_keywords],
    yearFrom: query.year_from,
    yearTo: query.year_to,
    sourceIds: query.source_ids.map(mapId),
    sortStrategy: query.sort_strategy,
    candidateLimit: query.pagination.candidate_limit,
    queryHash: query.query_hash as ContentHash,
  };
}

function mapSelection(
  selected: boolean,
  selectionReason: string | null | undefined,
  exclusionReason: string | null | undefined,
): PaperCandidateSelection {
  return selected
    ? { kind: "selected", reason: selectionReason ?? null }
    : { kind: "excluded", reason: exclusionReason ?? null };
}

function mapCandidate(
  read: PaperCollectionCandidateReadDto,
  stableRank: number,
): PaperCandidateReview {
  const candidate = read.candidate;
  return {
    candidateId: mapId(candidate.candidate_id),
    canonicalPaperId: mapId(candidate.canonical_paper_id),
    title: candidate.title,
    authors: [...(candidate.authors ?? [])],
    year: candidate.year ?? null,
    doi: candidate.doi ?? null,
    arxivId: candidate.arxiv_id ?? null,
    url: candidate.url ?? null,
    relevanceScore: candidate.relevance_score,
    stableRank,
    selection: mapSelection(
      candidate.selected,
      candidate.selection_reason,
      candidate.exclusion_reason,
    ),
    rankingRuleVersion: candidate.ranking_rule_version,
    selectionRuleVersion: candidate.selection_rule_version,
    duplicateGroup: mapDuplicateGroup(read.duplicate_group),
    sourceSnapshot: mapSnapshotSummary(read.source_snapshot),
    evidence: read.evidence.map((item: EvidenceDetailDto) =>
      mapEvidenceDetail(item),
    ),
  };
}

/**
 * Assemble the complete domain review from validated transport payloads.
 *
 * Shared by the HTTP and fixture adapters so both return byte-identical
 * domain shapes. Enforces cross-payload integrity: the paged candidate reads
 * must match the collection's own candidate list in count and order (the
 * authoritative server ranking), with no duplicate candidate ids.
 */
export function assemblePaperAcquisitionReview(
  read: PaperCollectionReadDto,
  candidateReads: readonly PaperCollectionCandidateReadDto[],
): PaperAcquisitionReview {
  const collection = read.collection;
  const declared = collection.candidates ?? [];

  if (candidateReads.length !== declared.length) {
    throw contractViolation(
      `candidate pages returned ${String(candidateReads.length)} candidates ` +
        `but the collection declares ${String(declared.length)}`,
    );
  }
  const seen = new Set<string>();
  candidateReads.forEach((item, index) => {
    const id = item.candidate.candidate_id;
    if (seen.has(id)) {
      throw contractViolation(`duplicate candidate id across pages: ${id}`);
    }
    seen.add(id);
    const declaredId = declared[index]?.candidate_id;
    if (declaredId !== id) {
      throw contractViolation(
        `candidate order drifted from the collection ranking at position ` +
          `${String(index + 1)}: expected ${declaredId ?? "<none>"}, got ${id}`,
      );
    }
  });

  return {
    artifactVersionId: mapId(read.artifact_version_id),
    artifactId: mapId(read.artifact_id),
    projectId: mapId(read.project_id),
    schemaVersion: collection.schema_version ?? "1.0.0",
    sourceMode: read.source_mode as SourceMode,
    contentHash: read.content_hash as ContentHash,
    inputHash: read.input_hash as ContentHash,
    createdAt: read.created_at as UtcIsoTimestamp,
    query: mapQuery(collection),
    acquisition: {
      acquisitionId: mapId(collection.acquisition_run.acquisition_id),
      status: collection.acquisition_run.status,
      startedAt: collection.acquisition_run.started_at as UtcIsoTimestamp,
      finishedAt: collection.acquisition_run.finished_at as UtcIsoTimestamp,
      candidateCount: collection.acquisition_run.candidate_count,
      selectedCount: collection.acquisition_run.selected_count,
      duplicateGroupCount: collection.acquisition_run.duplicate_group_count,
      sourceFailureCount: collection.acquisition_run.source_failure_count,
    },
    benchmark: {
      benchmarkId: mapId(collection.benchmark.benchmark_id),
      benchmarkVersion: collection.benchmark.benchmark_version,
      scenarioId: mapId(collection.benchmark.scenario_id),
      schemaVersion: collection.benchmark.schema_version,
      contentHash: collection.benchmark.content_hash as ContentHash,
    },
    metrics: {
      candidateCount: collection.metrics.candidate_count,
      selectedCount: collection.metrics.selected_count,
      duplicateCandidateCount: collection.metrics.duplicate_candidate_count,
      duplicateRate: collection.metrics.duplicate_rate,
      expectedCandidateCount: collection.metrics.expected_candidate_count,
      recalledExpectedCandidateCount:
        collection.metrics.recalled_expected_candidate_count,
      candidateRecall: collection.metrics.candidate_recall ?? null,
      sourceExecutionCount: collection.metrics.source_execution_count,
      sourceFailureCount: collection.metrics.source_failure_count,
      sourceEmptyResultCount: collection.metrics.source_empty_result_count,
    },
    rules: {
      dedupeRule: collection.dedupe_rule,
      rankingRule: collection.ranking_rule,
      adapterName: collection.rules.adapter_name,
      adapterVersion: collection.rules.adapter_version,
      queryNormalizationVersion: collection.rules.query_normalization_version,
      canonicalizationVersion: collection.rules.canonicalization_version,
      dedupeVersion: collection.rules.dedupe_version,
      rankingVersion: collection.rules.ranking_version,
      selectionVersion: collection.rules.selection_version,
      selectionLimit: collection.rules.selection_limit,
      retryPolicyVersion: collection.rules.retry_policy_version,
      sourcePolicyVersion: collection.rules.source_policy_version,
    },
    sourceExecutions: collection.source_executions.map(mapSourceExecution),
    producerExecution: mapProducerExecutionSummary(read.producer_execution),
    candidates: candidateReads.map((item, index) =>
      mapCandidate(item, index + 1),
    ),
  };
}

/** Parse helper that reports contract failures as `ValidationError`. */
function parseContract<T>(
  model: Parameters<typeof parseV2Dto>[0],
  value: unknown,
): T {
  try {
    return parseV2Dto<T>(model, value);
  } catch (error) {
    throw new ValidationError(
      error instanceof Error ? error.message : "contract validation failed",
      "SCHEMA_VALIDATION_FAILED",
      [],
    );
  }
}

export function createPaperAcquisitionRepository(
  http: HttpClient,
): PaperAcquisitionRepository {
  return {
    async getReview(artifactVersionId) {
      const base = `/api/v2/artifact-versions/${seg(artifactVersionId)}`;
      const collectionPayload = await http.getRequired<unknown>(
        `${base}/paper-collection`,
      );
      const read = parseContract<PaperCollectionReadDto>(
        "PaperCollectionRead",
        collectionPayload,
      );

      const candidateReads: PaperCollectionCandidateReadDto[] = [];
      const seenCursors = new Set<string>();
      let cursor: string | null = null;
      do {
        const params = new URLSearchParams({
          limit: String(CANDIDATE_PAGE_SIZE),
        });
        if (cursor !== null) params.set("cursor", cursor);
        const envelope = await http.getPage<unknown>(
          `${base}/paper-candidates?${params.toString()}`,
        );
        for (const payload of envelope.data) {
          candidateReads.push(
            parseContract<PaperCollectionCandidateReadDto>(
              "PaperCollectionCandidateRead",
              payload,
            ),
          );
        }
        const next: string | null = envelope.page?.has_more
          ? (envelope.page?.next_cursor ?? null)
          : null;
        if (next !== null) {
          if (envelope.data.length === 0) {
            throw contractViolation(
              "candidate page reported has_more without returning items",
            );
          }
          if (next === cursor || seenCursors.has(next)) {
            throw contractViolation(
              "candidate pagination cursor did not advance",
            );
          }
          seenCursors.add(next);
        }
        cursor = next;
      } while (cursor !== null);

      return assemblePaperAcquisitionReview(read, candidateReads);
    },
  };
}
