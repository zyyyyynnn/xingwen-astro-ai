/**
 * Paper summary review repository (Literature Summary Workspace) over the PaperSummary API read boundary.
 *
 * One deep port method — `getSummary(artifactVersionId)` — hides the entire
 * transport protocol:
 *
 * - `GET /api/artifact-versions/{id}/paper-summary` (required read)
 * - generated-contract validation of the payload
 * - a single DTO→domain assembly shared verbatim with the fixture adapter
 *
 * Support status is never inferred here: statements and evidence carry the
 * server-validated `supported`/`unsupported`/`unverifiable` status, and no
 * scientific validation is recomputed on the client.
 */

import type {
  EvidenceDetail as EvidenceDetailDto,
  PaperSummaryCacheAudit as PaperSummaryCacheAuditDto,
  PaperSummaryEvidence as PaperSummaryEvidenceDto,
  PaperSummaryEvidenceLocator as PaperSummaryEvidenceLocatorDto,
  PaperSummaryInputVersions as PaperSummaryInputVersionsDto,
  PaperSummaryProducerExecution as PaperSummaryProducerExecutionDto,
  PaperSummaryRead as PaperSummaryReadDto,
  PaperSummarySection as PaperSummarySectionDto,
  PaperSummarySourceConflict as PaperSummarySourceConflictDto,
  PaperSummaryStatement as PaperSummaryStatementDto,
} from "@xingwen/contracts";
import type {
  ContentHash,
  DomainEntityId,
  PaperSummaryEvidenceLocator,
  PaperSummaryEvidenceReview,
  PaperSummaryInputVersionsReview,
  PaperSummaryProducerReview,
  PaperSummaryReview,
  PaperSummarySectionReview,
  PaperSummarySourceConflictReview,
  PaperSummaryStatementReview,
  PaperSummaryCacheAuditReview,
  SourceMode,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { HttpClient, seg } from "./http-client";
import { ValidationError } from "./errors";
import { mapEvidenceDetail } from "./mapping";
import {
  mapProducerExecutionSummary,
  mapSnapshotSummary,
  parseContract,
} from "./paper-acquisition-repository";
import type { PaperSummaryRepository } from "./ports";

function mapId(value: string): DomainEntityId {
  return asEntityId(value);
}

function mapStatement(
  dto: PaperSummaryStatementDto,
): PaperSummaryStatementReview {
  return {
    statementId: mapId(dto.statement_id),
    itemKind: dto.item_kind,
    text: dto.text,
    status: dto.status,
    evidenceIds: dto.evidence_ids.map(mapId),
    validationCode: mapId(dto.validation_code),
  };
}

function mapSection(dto: PaperSummarySectionDto): PaperSummarySectionReview {
  return {
    sectionKind: dto.section_kind,
    overview: mapStatementOrNull(dto.overview),
    items: dto.items.map(mapStatement),
  };
}

function mapStatementOrNull(
  dto: PaperSummaryStatementDto | null,
): PaperSummaryStatementReview | null {
  return dto === null ? null : mapStatement(dto);
}

/** Narrow the wire locator to the domain discriminated union. */
function mapLocator(
  dto: PaperSummaryEvidenceLocatorDto,
): PaperSummaryEvidenceLocator {
  if (dto.kind === "paper_text") {
    if (
      !dto.text_range ||
      (!dto.source_url && (!dto.document_parse_id || !dto.document_locator))
    ) {
      throw new ValidationError(
        "paper text evidence locator is incomplete",
        "PAPER_SUMMARY_PROVENANCE_INVALID",
        [],
      );
    }
    return {
      kind: "paper_text",
      sourceUrl: dto.source_url ?? null,
      section: dto.section ?? "",
      paragraph: dto.paragraph ?? null,
      textRange: dto.text_range ?? "",
      documentParseId: dto.document_parse_id
        ? mapId(dto.document_parse_id)
        : null,
      documentParseOutputHash: (dto.document_parse_output_hash ??
        null) as ContentHash | null,
      documentLocator: dto.document_locator
        ? {
            pageIndex: dto.document_locator.page_index,
            blockId: dto.document_locator.block_id
              ? mapId(dto.document_locator.block_id)
              : null,
            readingOrder: dto.document_locator.reading_order ?? null,
            textSpan: dto.document_locator.text_span ?? null,
            tableId: dto.document_locator.table_id
              ? mapId(dto.document_locator.table_id)
              : null,
            cellId: dto.document_locator.cell_id
              ? mapId(dto.document_locator.cell_id)
              : null,
            bbox: dto.document_locator.bbox ?? null,
          }
        : null,
    };
  }
  if (!dto.source_url || !dto.metadata_field) {
    throw new ValidationError(
      "paper metadata evidence locator is incomplete",
      "PAPER_SUMMARY_PROVENANCE_INVALID",
      [],
    );
  }
  return {
    kind: "paper_metadata",
    sourceUrl: dto.source_url,
    metadataField: dto.metadata_field ?? "",
  };
}

function mapSummaryEvidence(
  dto: PaperSummaryEvidenceDto,
): PaperSummaryEvidenceReview {
  return {
    evidenceId: mapId(dto.evidence_id),
    paperId: mapId(dto.paper_id),
    candidateId: mapId(dto.candidate_id),
    sourceId: mapId(dto.source_id),
    sourceRecordId: dto.source_record_id,
    sourceSnapshotId: mapId(dto.source_snapshot_id),
    sourceSnapshotVersion: dto.source_snapshot_version,
    sourceSnapshotContentHash: dto.source_snapshot_content_hash as ContentHash,
    locator: mapLocator(dto.locator),
    quoteOrValue: dto.quote_or_value,
    status: dto.status,
    validationCode: mapId(dto.validation_code),
  };
}

function mapSourceConflict(
  dto: PaperSummarySourceConflictDto,
): PaperSummarySourceConflictReview {
  return {
    conflictId: mapId(dto.conflict_id),
    evidenceId: mapId(dto.evidence_id),
    sourceSnapshotId: mapId(dto.source_snapshot_id),
    claimedSourceVersion: dto.claimed_source_version,
    sourceSnapshotVersion: dto.source_snapshot_version,
    // The contract default: the snapshot version is always authoritative.
    resolution: dto.resolution ?? "source_snapshot_version_retained",
  };
}

function mapInputVersions(
  dto: PaperSummaryInputVersionsDto,
): PaperSummaryInputVersionsReview {
  return {
    collection: dto.collection
      ? {
          artifactVersionId: mapId(dto.collection.artifact_version_id),
          schemaVersion: dto.collection.schema_version,
          outputHash: dto.collection.output_hash as ContentHash,
        }
      : null,
    documentParses: (dto.document_parses ?? []).map((item) => ({
      documentParseId: mapId(item.document_parse_id),
      candidateParseId: mapId(item.candidate_parse_id),
      researchInputId: mapId(item.research_input_id),
      sourceSnapshotId: mapId(item.source_snapshot_id),
      inputContentHash: item.input_content_hash as ContentHash,
      canonicalOutputHash: item.canonical_output_hash as ContentHash,
      parserProfileId: mapId(item.parser_profile_id),
      parserProfileVersion: item.parser_profile_version,
      configHash: item.config_hash as ContentHash,
    })),
    sourceSnapshots: dto.source_snapshots.map((snapshot) => ({
      sourceSnapshotId: mapId(snapshot.source_snapshot_id),
      sourceId: mapId(snapshot.source_id),
      sourceVersion: snapshot.source_version,
      contentHash: snapshot.content_hash as ContentHash,
    })),
  };
}

function mapProducer(
  dto: PaperSummaryProducerExecutionDto,
): PaperSummaryProducerReview {
  return {
    executionId: mapId(dto.execution_id),
    runId: dto.run_id ? mapId(dto.run_id) : null,
    producerName: dto.producer_name,
    producerVersion: dto.producer_version,
    modelName: dto.model_name,
    modelRevision: dto.model_revision ?? null,
    provider: dto.provider ? mapId(dto.provider) : null,
    providerRequestId: dto.provider_request_id ?? null,
    usage: dto.usage
      ? {
          promptTokens: dto.usage.prompt_tokens,
          completionTokens: dto.usage.completion_tokens,
          totalTokens: dto.usage.total_tokens,
        }
      : null,
    promptName: mapId(dto.prompt_name),
    promptVersion: dto.prompt_version,
    promptHash: dto.prompt_hash as ContentHash,
    parametersVersion: dto.parameters_version,
    parametersHash: dto.parameters_hash as ContentHash,
    inputHash: dto.input_hash as ContentHash,
    modelResponseHash: dto.model_response_hash as ContentHash,
    outputHash: (dto.output_hash ?? null) as ContentHash | null,
    status: dto.status,
  };
}

function mapCacheAudit(
  dto: PaperSummaryCacheAuditDto,
): PaperSummaryCacheAuditReview {
  return {
    sourceId: mapId(dto.source_id),
    sourceSnapshotId: mapId(dto.source_snapshot_id),
    cacheVersion: dto.cache_version,
    cacheApplicability: dto.cache_applicability,
    liveFailureClass: dto.live_failure_class,
    liveFailureCode: dto.live_failure_code,
    originRunId: mapId(dto.origin_run_id),
    originArtifactVersionId: mapId(dto.origin_artifact_version_id),
  };
}

function summaryContractViolation(detail: string): ValidationError {
  return new ValidationError(detail, "PAPER_SUMMARY_PROVENANCE_INVALID", []);
}

/**
 * Assemble the complete domain review from a validated transport payload.
 *
 * Shared by the HTTP and fixture adapters so both return byte-identical
 * domain shapes. The summary-internal evidence keeps its locator/quote/status
 * for inline display, while `read.evidence` maps to the generic Artifact Read Boundary Evidence
 * records through the same `mapEvidenceDetail` used everywhere else.
 */
export function assemblePaperSummaryReview(
  read: PaperSummaryReadDto,
): PaperSummaryReview {
  const summary = read.summary;
  if (read.paper.paper_id !== summary.paper_id) {
    throw summaryContractViolation(
      "paper metadata does not identify the summarized paper",
    );
  }
  const cacheAudits = read.cache_audits ?? [];
  if (
    (read.source_mode === "cached" && cacheAudits.length === 0) ||
    (read.source_mode !== "cached" && cacheAudits.length > 0)
  ) {
    throw summaryContractViolation(
      "cache audit context must exist exactly for cached summaries",
    );
  }
  const sourceSnapshots = (read.source_snapshots ?? []).map(mapSnapshotSummary);
  const mappedCacheAudits = cacheAudits.map(mapCacheAudit);
  for (const audit of mappedCacheAudits) {
    const snapshot = sourceSnapshots.find(
      (item) => String(item.id) === String(audit.sourceSnapshotId),
    );
    if (
      snapshot === undefined ||
      String(snapshot.sourceId) !== String(audit.sourceId) ||
      snapshot.cacheVersion !== audit.cacheVersion ||
      snapshot.cachedOrigin === null ||
      String(snapshot.cachedOrigin.originRunId) !== String(audit.originRunId) ||
      String(snapshot.cachedOrigin.originArtifactVersionId) !==
        String(audit.originArtifactVersionId) ||
      [
        audit.cacheVersion,
        audit.cacheApplicability,
        audit.liveFailureClass,
        audit.liveFailureCode,
      ].some((value) => value.trim().length === 0)
    ) {
      throw summaryContractViolation(
        `cached source ${String(audit.sourceId)} has inconsistent provenance`,
      );
    }
  }
  return {
    artifactVersionId: mapId(read.artifact_version_id),
    artifactId: mapId(read.artifact_id),
    projectId: mapId(read.project_id),
    versionNumber: read.version_number,
    supersedesVersionId:
      read.supersedes_version_id === null
        ? null
        : mapId(read.supersedes_version_id),
    sourceMode: read.source_mode as SourceMode,
    contentHash: read.content_hash as ContentHash,
    inputHash: read.input_hash as ContentHash,
    createdAt: read.created_at as UtcIsoTimestamp,
    summaryId: mapId(summary.summary_id),
    paperId: mapId(summary.paper_id),
    paper: {
      paperId: mapId(read.paper.paper_id),
      title: read.paper.title,
      authors: read.paper.authors ?? [],
      year: read.paper.year ?? null,
    },
    schemaVersion: summary.schema_version,
    benchmark: summary.benchmark
      ? {
          benchmarkId: mapId(summary.benchmark.benchmark_id),
          benchmarkVersion: summary.benchmark.benchmark_version,
          scenarioId: mapId(summary.benchmark.scenario_id),
          schemaVersion: summary.benchmark.schema_version,
          contentHash: summary.benchmark.content_hash as ContentHash,
        }
      : null,
    inputVersions: mapInputVersions(summary.input_versions),
    background: mapSection(summary.background),
    methodology: mapSection(summary.methodology),
    dataset: mapSection(summary.dataset),
    experiments: mapSection(summary.experiments),
    discussion: mapSection(summary.discussion),
    limitations: mapSection(summary.limitations),
    researchQuestions: mapSection(summary.research_questions),
    summaryEvidence: summary.evidence.map(mapSummaryEvidence),
    sourceConflicts: summary.source_conflicts.map(mapSourceConflict),
    producer: mapProducer(summary.producer),
    cacheAudits: mappedCacheAudits,
    producerExecution: mapProducerExecutionSummary(read.producer_execution),
    sourceSnapshots,
    evidence: read.evidence.map((item: EvidenceDetailDto) =>
      mapEvidenceDetail(item),
    ),
  };
}

export function createPaperSummaryRepository(
  http: HttpClient,
): PaperSummaryRepository {
  return {
    async getSummary(artifactVersionId) {
      const payload = await http.getRequired<unknown>(
        `/api/artifact-versions/${seg(artifactVersionId)}/paper-summary`,
      );
      const read = parseContract<PaperSummaryReadDto>(
        "PaperSummaryRead",
        payload,
      );
      return assemblePaperSummaryReview(read);
    },
  };
}
