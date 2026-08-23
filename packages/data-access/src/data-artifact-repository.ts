/**
 * Typed Data Artifact reads. The HTTP adapter consumes the generated
 * Dataset/FieldDictionary/SourceCollection DTOs and maps them to the domain
 * review projections. The fixture adapter consumes the same version-pinned
 * rich read payloads as the HTTP adapter.
 */

import type {
  DatasetArtifactCandidate,
  DatasetArtifactRead as DatasetArtifactReadDto,
  DatasetRow,
  FieldDefinition,
  FieldDictionaryArtifactCandidate,
  FieldDictionaryArtifactRead as FieldDictionaryArtifactReadDto,
  SourceCollectionArtifactCandidate,
  SourceCollectionArtifactRead as SourceCollectionArtifactReadDto,
  DocumentSourceCollectionMember,
  SourceTableSourceCollectionMember,
  StructuredSourceCollectionMember,
} from "@xingwen/contracts";
import {
  asEntityId,
  type ContentHash,
  type DataArtifactFieldDefinition,
  type DataArtifactReviewBase,
  type DatasetArtifactReview,
  type DatasetCellReview,
  type DatasetRowReview,
  type FieldDictionaryArtifactReview,
  type SourceCollectionArtifactReview,
  type SourceCollectionMemberReview,
  type DataArtifactReview,
  type DomainEntityId,
  type SourceMode,
} from "@xingwen/domain";

import { NotFoundError, ValidationError } from "./errors";
import { HttpClient, seg } from "./http-client";
import type { DataArtifactRepository } from "./ports";

type DataArtifactReadDto =
  | DatasetArtifactReadDto
  | FieldDictionaryArtifactReadDto
  | SourceCollectionArtifactReadDto;

function id(value: string): DomainEntityId {
  return asEntityId(value);
}

function mapField(dto: FieldDefinition): DataArtifactFieldDefinition {
  return {
    fieldId: id(dto.field_id),
    labelEn: dto.label_en,
    meaningZh: dto.meaning_zh,
    description: dto.description,
    dataType: String(dto.data_type),
    canonicalUnit: dto.canonical_unit,
    objectType: String(dto.object_type),
    required: dto.required,
    nullable: dto.nullable,
    crossmatchKey: dto.crossmatch_key,
    objectIdentityKey: dto.object_identity_key,
    sourceAliases: dto.source_aliases.map((alias) => ({
      sourceId: id(alias.source_id),
      sourceTable: alias.source_table,
      rawField: alias.raw_field,
      sourceUnit: alias.source_unit,
      priority: alias.priority,
    })),
    documentAliases: dto.document_aliases.map((alias) => ({
      alias: alias.alias,
      priority: alias.priority,
    })),
    sourcePriority: dto.source_priority.map(id),
  };
}

function mapSourceSnapshot(snapshot: {
  id: string;
  source_id: string;
  source_type: string;
  retrieved_at: string;
  query_hash: string;
  content_hash: string;
  source_version_or_etag?: string | null;
  license_note: string;
}) {
  return {
    id: id(snapshot.id),
    sourceId: id(snapshot.source_id),
    sourceType: snapshot.source_type,
    retrievedAt: snapshot.retrieved_at,
    queryHash: snapshot.query_hash as ContentHash,
    contentHash: snapshot.content_hash as ContentHash,
    sourceVersionOrEtag: snapshot.source_version_or_etag ?? null,
    licenseNote: snapshot.license_note,
  };
}

function mapBase(dto: DataArtifactReadDto): DataArtifactReviewBase {
  return {
    artifactVersionId: id(dto.artifact_version_id),
    artifactId: id(dto.artifact_id),
    projectId: id(dto.project_id),
    schemaVersion: dto.schema_version,
    sourceMode: dto.source_mode as SourceMode,
    contentHash: dto.content_hash as ContentHash,
    inputHash: dto.input_hash as ContentHash,
    createdAt: dto.created_at,
    sourceSnapshots: dto.source_snapshots.map(mapSourceSnapshot),
    evidenceIds: dto.evidence.map((item) => id(item.id)),
    quality: {
      status:
        dto.quality_projection?.overall_status === "pass" ? "pass" : "unknown",
      resultId: dto.quality_projection?.quality_result_id
        ? id(dto.quality_projection.quality_result_id)
        : null,
    },
  };
}

function mapCell(field: DatasetRow["fields"][number]): DatasetCellReview {
  if ("canonical_value" in field) {
    return {
      canonicalFieldId: id(field.canonical_field_id),
      status: "mapped",
      value: field.canonical_value,
      unit: field.canonical_unit,
      reason: null,
      conflictIds: field.conflict_ids.map(id),
      evidenceIds: field.transformation_evidence_ids.map(id),
    };
  }
  if ("conflict_ids" in field) {
    return {
      canonicalFieldId: id(field.canonical_field_id),
      status: "unresolved",
      value: null,
      unit: null,
      reason: field.reason,
      conflictIds: field.conflict_ids.map(id),
      evidenceIds: field.transformation_evidence_ids.map(id),
    };
  }
  return {
    canonicalFieldId: id(field.canonical_field_id),
    status: "declared_null",
    value: null,
    unit: null,
    reason: field.reason,
    conflictIds: [],
    evidenceIds: field.transformation_evidence_ids.map(id),
  };
}

function mapRow(dto: DatasetRow): DatasetRowReview {
  const authority = dto.row_authority;
  const identity =
    "logical_key" in authority
      ? authority.canonical_row_identity.member_entities
          .flatMap((entity) => entity.identity_values)
          .map((value) => `${value.field_id}=${value.normalized_value}`)
          .join(" · ")
      : authority.canonical_row_identity.canonical_identity;
  return {
    rowId: dto.row_id,
    entityLevel:
      "entity_level" in authority
        ? String(authority.entity_level)
        : String(
            authority.canonical_row_identity.entity_level ?? "source_table",
          ),
    alignmentStatus:
      "alignment_status" in authority
        ? String(authority.alignment_status)
        : "not_applicable",
    identity,
    cells: dto.fields.map(mapCell),
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
  };
}

function mapDataset(dto: DatasetArtifactReadDto): DatasetArtifactReview {
  const candidate: DatasetArtifactCandidate = dto.dataset;
  return {
    ...mapBase(dto),
    kind: "dataset",
    candidateId: id(candidate.candidate_id),
    requestedFields: candidate.requested_fields.map(id),
    columns: candidate.columns.map((column) => mapField(column.field)),
    rows: candidate.rows.map(mapRow),
    rowCount: candidate.row_count,
    fieldCount: candidate.field_count,
    conflictCount: candidate.conflicts.length,
  };
}

function mapFieldDictionary(
  dto: FieldDictionaryArtifactReadDto,
): FieldDictionaryArtifactReview {
  const candidate: FieldDictionaryArtifactCandidate = dto.field_dictionary;
  return {
    ...mapBase(dto),
    kind: "field_dictionary",
    candidateId: id(candidate.candidate_id),
    requestedFields: candidate.requested_fields.map(id),
    fieldDefinitions: candidate.field_definitions.map(mapField),
  };
}

function mapSourceMember(
  member:
    | StructuredSourceCollectionMember
    | SourceTableSourceCollectionMember
    | DocumentSourceCollectionMember,
): SourceCollectionMemberReview {
  if (member.member_kind === "source_table") {
    return {
      memberKind: "source_table",
      sourceId: id(member.source_id),
      sourceSnapshotId: id(member.source_snapshot_id),
      sourceSnapshotContentHash:
        member.source_snapshot_content_hash as ContentHash,
      side: null,
      dataLevel: null,
      sourceMode: null,
      rawRecordCount: member.raw_record_count,
      completionStatus: null,
      licenseNote: member.license_note,
    };
  }
  if ("research_input_id" in member) {
    return {
      memberKind: "document",
      sourceId: member.source_id ? id(member.source_id) : null,
      sourceSnapshotId: id(member.source_snapshot_id),
      sourceSnapshotContentHash:
        member.source_snapshot_content_hash as ContentHash,
      side: null,
      dataLevel: null,
      sourceMode: null,
      rawRecordCount: null,
      completionStatus: null,
      licenseNote: member.source_snapshot.license_note,
      researchInputId: id(member.research_input_id),
      documentParseIds: member.document_parse_ids.map((value) => id(value)),
    };
  }
  if (!("side" in member)) {
    throw new Error("unsupported SourceCollection member shape");
  }
  return {
    memberKind: "structured",
    sourceId: member.source_id ? id(member.source_id) : null,
    sourceSnapshotId: id(member.source_snapshot_id),
    sourceSnapshotContentHash:
      member.source_snapshot_content_hash as ContentHash,
    side: String(member.side),
    dataLevel: String(member.data_level),
    sourceMode: member.source_mode as SourceMode,
    rawRecordCount: member.raw_record_count,
    completionStatus: String(member.completion.status),
    licenseNote: member.license_note,
  };
}

function mapSourceCollection(
  dto: SourceCollectionArtifactReadDto,
): SourceCollectionArtifactReview {
  const candidate: SourceCollectionArtifactCandidate = dto.source_collection;
  const alignmentRecordKeys =
    "alignment_record_keys" in candidate.authority
      ? (candidate.authority.alignment_record_keys ?? [])
      : [];
  const conflictRecordKeys =
    "conflict_record_keys" in candidate.authority
      ? (candidate.authority.conflict_record_keys ?? [])
      : [];
  const inconclusiveRecordKeys =
    "inconclusive_record_keys" in candidate.authority
      ? (candidate.authority.inconclusive_record_keys ?? [])
      : [];
  const reviewRequiredRecordKeys =
    "review_required_record_keys" in candidate.authority
      ? (candidate.authority.review_required_record_keys ?? [])
      : [];
  return {
    ...mapBase(dto),
    kind: "source_collection",
    candidateId: id(candidate.candidate_id),
    members: candidate.members.map(mapSourceMember),
    alignedRecordCount: alignmentRecordKeys.length,
    conflictRecordCount: conflictRecordKeys.length,
    inconclusiveRecordCount: inconclusiveRecordKeys.length,
    reviewRequiredRecordCount: reviewRequiredRecordKeys.length,
  };
}

function validateDataArtifactRead(
  payload: unknown,
  kind: DataArtifactReview["kind"],
): DataArtifactReadDto {
  if (payload === null || typeof payload !== "object") {
    throw new ValidationError(
      `Data Artifact ${kind} read is not an object`,
      "SCHEMA_VALIDATION_FAILED",
      [],
    );
  }
  const value = payload as Record<string, unknown>;
  const candidate = value[kind];
  if (
    typeof value.artifact_version_id !== "string" ||
    typeof value.project_id !== "string" ||
    typeof value.schema_version !== "string" ||
    !Array.isArray(value.source_snapshots) ||
    !Array.isArray(value.evidence) ||
    candidate === null ||
    typeof candidate !== "object"
  ) {
    throw new ValidationError(
      `Data Artifact ${kind} read failed its required shape`,
      "SCHEMA_VALIDATION_FAILED",
      [],
    );
  }
  return value as unknown as DataArtifactReadDto;
}

function mapTypedRead(
  payload: unknown,
  kind: DataArtifactReview["kind"],
): DataArtifactReview {
  const dto = validateDataArtifactRead(payload, kind);
  if (kind === "dataset") return mapDataset(dto as DatasetArtifactReadDto);
  if (kind === "field_dictionary") {
    return mapFieldDictionary(dto as FieldDictionaryArtifactReadDto);
  }
  return mapSourceCollection(dto as SourceCollectionArtifactReadDto);
}

export function createDataArtifactRepository(
  http: HttpClient,
): DataArtifactRepository {
  return {
    async getDataset(artifactVersionId) {
      return mapTypedRead(
        await http.getRequired<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/dataset`,
        ),
        "dataset",
      ) as DatasetArtifactReview;
    },
    async getFieldDictionary(artifactVersionId) {
      return mapTypedRead(
        await http.getRequired<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/field-dictionary`,
        ),
        "field_dictionary",
      ) as FieldDictionaryArtifactReview;
    },
    async getSourceCollection(artifactVersionId) {
      return mapTypedRead(
        await http.getRequired<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/source-collection`,
        ),
        "source_collection",
      ) as SourceCollectionArtifactReview;
    },
  };
}

export function createFixtureDataArtifactRepository(
  reads: readonly DataArtifactReadDto[],
): DataArtifactRepository {
  const read = async (
    artifactVersionId: DomainEntityId,
    kind: DataArtifactReview["kind"],
  ): Promise<DataArtifactReview> => {
    const payload = reads.find(
      (item) => item.artifact_version_id === artifactVersionId,
    );
    if (!payload) {
      throw new NotFoundError(
        `Data Artifact ${artifactVersionId} not found`,
        "ARTIFACT_VERSION_NOT_FOUND",
      );
    }
    return mapTypedRead(payload, kind);
  };
  return {
    getDataset: (artifactVersionId) =>
      read(artifactVersionId, "dataset") as Promise<DatasetArtifactReview>,
    getFieldDictionary: (artifactVersionId) =>
      read(
        artifactVersionId,
        "field_dictionary",
      ) as Promise<FieldDictionaryArtifactReview>,
    getSourceCollection: (artifactVersionId) =>
      read(
        artifactVersionId,
        "source_collection",
      ) as Promise<SourceCollectionArtifactReview>,
  };
}
