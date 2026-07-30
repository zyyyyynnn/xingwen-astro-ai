/**
 * Paper summary review repository (A-06) over the B-07 read boundary.
 *
 * One deep port method — `getSummary(artifactVersionId)` — hides the entire
 * transport protocol:
 *
 * - `GET /api/v2/artifact-versions/{id}/paper-summary` (required read)
 * - generated-contract validation of the payload
 * - a single DTO→domain assembly shared verbatim with the fixture adapter
 *
 * Support status is never inferred here: statements and evidence carry the
 * server-validated `supported`/`unsupported`/`unverifiable` status, and no
 * scientific validation is recomputed on the client.
 */

import type {
  EvidenceDetail as EvidenceDetailDto,
  PaperSummaryEvidence as PaperSummaryEvidenceDto,
  PaperSummaryEvidenceLocator as PaperSummaryEvidenceLocatorDto,
  PaperSummaryInputVersions as PaperSummaryInputVersionsDto,
  PaperSummaryProducerExecution as PaperSummaryProducerExecutionDto,
  PaperSummaryRead as PaperSummaryReadDto,
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
  PaperSummarySourceConflictReview,
  PaperSummaryStatementReview,
  SourceMode,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { HttpClient, seg } from "./http-client";
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
    text: dto.text,
    status: dto.status,
    evidenceIds: dto.evidence_ids.map(mapId),
    validationCode: mapId(dto.validation_code),
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
    return {
      kind: "paper_text",
      sourceUrl: dto.source_url,
      section: dto.section ?? "",
      paragraph: dto.paragraph ?? null,
      textRange: dto.text_range ?? "",
    };
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
    paperCollectionVersionId: mapId(dto.paper_collection_version_id),
    paperCollectionSchemaVersion: dto.paper_collection_schema_version,
    paperCollectionOutputHash: dto.paper_collection_output_hash as ContentHash,
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

/**
 * Assemble the complete domain review from a validated transport payload.
 *
 * Shared by the HTTP and fixture adapters so both return byte-identical
 * domain shapes. The summary-internal evidence keeps its locator/quote/status
 * for inline display, while `read.evidence` maps to the generic B-18 Evidence
 * records through the same `mapEvidenceDetail` used everywhere else.
 */
export function assemblePaperSummaryReview(
  read: PaperSummaryReadDto,
): PaperSummaryReview {
  const summary = read.summary;
  return {
    artifactVersionId: mapId(read.artifact_version_id),
    artifactId: mapId(read.artifact_id),
    projectId: mapId(read.project_id),
    sourceMode: read.source_mode as SourceMode,
    contentHash: read.content_hash as ContentHash,
    inputHash: read.input_hash as ContentHash,
    createdAt: read.created_at as UtcIsoTimestamp,
    summaryId: mapId(summary.summary_id),
    paperId: mapId(summary.paper_id),
    schemaVersion: summary.schema_version,
    benchmark: {
      benchmarkId: mapId(summary.benchmark.benchmark_id),
      benchmarkVersion: summary.benchmark.benchmark_version,
      scenarioId: mapId(summary.benchmark.scenario_id),
      schemaVersion: summary.benchmark.schema_version,
      contentHash: summary.benchmark.content_hash as ContentHash,
    },
    inputVersions: mapInputVersions(summary.input_versions),
    researchGoal: mapStatementOrNull(summary.research_goal),
    method: mapStatementOrNull(summary.method),
    dataset: mapStatementOrNull(summary.dataset),
    findings: summary.findings.map(mapStatement),
    limitations: summary.limitations.map(mapStatement),
    futureWork: summary.future_work.map(mapStatement),
    summaryEvidence: summary.evidence.map(mapSummaryEvidence),
    sourceConflicts: summary.source_conflicts.map(mapSourceConflict),
    producer: mapProducer(summary.producer),
    producerExecution: mapProducerExecutionSummary(read.producer_execution),
    sourceSnapshots: (read.source_snapshots ?? []).map(mapSnapshotSummary),
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
