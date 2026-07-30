/**
 * Runtime validation against the B-15 frozen `/api` JSON Schemas.
 *
 * Each core entity and B-18 read schema is compiled once into an ajv
 * validator. The public API exposes type-safe `parse*` / `validate*` helpers
 * so the fixture adapter (and, later, the HTTP adapter) can assert contract
 * conformance before mapping payloads into the domain model.
 */

import Ajv from "ajv";
import addFormats from "ajv-formats";

import artifactVersionSchema from "./generated/core/json/ArtifactVersion.schema.json";
import artifactVersionDetailSchema from "./generated/core/json/ArtifactVersionDetail.schema.json";
import evidenceReadSchema from "./generated/core/json/EvidenceRead.schema.json";
import manifest from "./generated/core/manifest.json";
import paperCollectionCandidateReadSchema from "./generated/core/json/PaperCollectionCandidateRead.schema.json";
import paperCollectionReadSchema from "./generated/core/json/PaperCollectionRead.schema.json";
import paperSummaryReadSchema from "./generated/core/json/PaperSummaryRead.schema.json";
import publicShareSnapshotSchema from "./generated/core/json/PublicShareSnapshot.schema.json";
import researchArtifactSchema from "./generated/core/json/ResearchArtifact.schema.json";
import researchArtifactDetailSchema from "./generated/core/json/ResearchArtifactDetail.schema.json";
import researchContractDraftSchema from "./generated/core/json/ResearchContractDraft.schema.json";
import researchContractSchema from "./generated/core/json/ResearchContract.schema.json";
import researchProjectSchema from "./generated/core/json/ResearchProject.schema.json";
import researchRunSchema from "./generated/core/json/ResearchRun.schema.json";
import runEventSchema from "./generated/core/json/RunEvent.schema.json";
import sessionCreatedSchema from "./generated/core/json/SessionCreated.schema.json";
import shareSnapshotSchema from "./generated/core/json/ShareSnapshot.schema.json";
import shareSnapshotCreatedSchema from "./generated/core/json/ShareSnapshotCreated.schema.json";
import sourceSnapshotDetailSchema from "./generated/core/json/SourceSnapshotDetail.schema.json";
import workspaceSnapshotSchema from "./generated/core/json/WorkspaceSnapshot.schema.json";

/** Schema version from the B-15 generation manifest. */
export const CONTRACT_SCHEMA_VERSION: number = manifest.schema_version;

/** Authoring source provenance for auditability. */
export const CONTRACT_AUTHORING_SOURCE: string = manifest.authoring_source;

/** Core entity and generic provenance read models with standalone schemas. */
export const CORE_MODEL_NAMES = [
  "ResearchProject",
  "ResearchContractDraft",
  "ResearchContract",
  "ResearchRun",
  "RunEvent",
  "ArtifactVersion",
  "ResearchArtifact",
  "ResearchArtifactDetail",
  "ArtifactVersionDetail",
  "EvidenceRead",
  "SourceSnapshotDetail",
  "PaperCollectionRead",
  "PaperCollectionCandidateRead",
  "PaperSummaryRead",
  "SessionCreated",
  "WorkspaceSnapshot",
  "ShareSnapshot",
  "ShareSnapshotCreated",
  "PublicShareSnapshot",
] as const;
export type CoreModelName = (typeof CORE_MODEL_NAMES)[number];

export interface ContractValidationError {
  readonly path: string;
  readonly message: string;
  readonly keyword: string;
}

export interface ContractValidationResult<T> {
  readonly ok: boolean;
  readonly data: T | null;
  readonly errors: readonly ContractValidationError[];
}

const ajv = new Ajv({
  strict: false,
  allErrors: true,
  validateFormats: true,
});
addFormats(ajv);

type SchemaMap = Record<CoreModelName, Record<string, unknown>>;

const schemas: SchemaMap = {
  ResearchProject: researchProjectSchema,
  ResearchContractDraft: researchContractDraftSchema,
  ResearchContract: researchContractSchema,
  ResearchRun: researchRunSchema,
  RunEvent: runEventSchema,
  ArtifactVersion: artifactVersionSchema,
  ResearchArtifact: researchArtifactSchema,
  ResearchArtifactDetail: researchArtifactDetailSchema,
  ArtifactVersionDetail: artifactVersionDetailSchema,
  EvidenceRead: evidenceReadSchema,
  SourceSnapshotDetail: sourceSnapshotDetailSchema,
  PaperCollectionRead: paperCollectionReadSchema,
  PaperCollectionCandidateRead: paperCollectionCandidateReadSchema,
  PaperSummaryRead: paperSummaryReadSchema,
  SessionCreated: sessionCreatedSchema,
  WorkspaceSnapshot: workspaceSnapshotSchema,
  ShareSnapshot: shareSnapshotSchema,
  ShareSnapshotCreated: shareSnapshotCreatedSchema,
  PublicShareSnapshot: publicShareSnapshotSchema,
};

/** A compiled ajv validator function with its errors property. */
interface CompiledValidator {
  (data: unknown): boolean;
  readonly errors: unknown[] | null;
}

const validators = new Map<CoreModelName, CompiledValidator>();
for (const [name, schema] of Object.entries(schemas) as [
  CoreModelName,
  Record<string, unknown>,
][]) {
  validators.set(name, ajv.compile(schema) as unknown as CompiledValidator);
}

function formatErrors(
  validator: CompiledValidator,
): readonly ContractValidationError[] {
  const errors = (validator.errors ?? []) as Array<{
    instancePath: string;
    message?: string;
    keyword: string;
  }>;
  return errors.map((error) => ({
    path: error.instancePath || "/",
    message: error.message ?? "validation failed",
    keyword: error.keyword,
  }));
}

/**
 * Validate a value against a core contract schema without throwing.
 */
export function validateDto<T>(
  model: CoreModelName,
  value: unknown,
): ContractValidationResult<T> {
  const validator = validators.get(model);
  if (!validator) {
    return {
      ok: false,
      data: null,
      errors: [
        {
          path: "/",
          message: `unknown contract model: ${model}`,
          keyword: "schema",
        },
      ],
    };
  }

  const valid = validator(value);
  if (valid) {
    return { ok: true, data: value as T, errors: [] };
  }
  return { ok: false, data: null, errors: formatErrors(validator) };
}

/**
 * Parse and validate a value, throwing on contract violation.
 *
 * @throws {Error} when the value does not conform to the schema, with a
 *   human-readable multi-line message listing every violation.
 */
export function parseDto<T>(model: CoreModelName, value: unknown): T {
  const result = validateDto<T>(model, value);
  if (!result.ok) {
    const lines = result.errors.map(
      (e) => `  at ${e.path}: ${e.message} (${e.keyword})`,
    );
    throw new Error(
      `contract validation failed for ${model}:\n${lines.join("\n")}`,
    );
  }
  return result.data as T;
}

/** Type guard for a core contract model. */
export function isDto(model: CoreModelName, value: unknown): boolean {
  const validator = validators.get(model);
  return validator ? validator(value) : false;
}

// Re-export DTO types for adapter consumption.
export type {
  ArtifactVersion as ArtifactVersionDto,
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  EvidenceRead as EvidenceReadDto,
  ResearchArtifact as ResearchArtifactDto,
  ResearchArtifactDetail as ResearchArtifactDetailDto,
  ResearchContract as ResearchContractDto,
  ResearchContractDraft as ResearchContractDraftDto,
  ResearchProject as ResearchProjectDto,
  ResearchRun as ResearchRunDto,
  RunEvent as RunEventDto,
  SourceSnapshotDetail as SourceSnapshotDetailDto,
} from "./generated/core/dto";
