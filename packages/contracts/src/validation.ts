/**
 * Runtime validation against the B-15 frozen `/api/v2` JSON Schemas.
 *
 * Each core entity and B-18 read schema is compiled once into an ajv
 * validator. The public API exposes type-safe `parse*` / `validate*` helpers
 * so the fixture adapter (and, later, the HTTP adapter) can assert contract
 * conformance before mapping payloads into the domain model.
 */

import Ajv from "ajv";
import addFormats from "ajv-formats";

import artifactVersionSchema from "./generated/v2-core/json/ArtifactVersion.schema.json";
import artifactVersionDetailSchema from "./generated/v2-core/json/ArtifactVersionDetail.schema.json";
import evidenceReadSchema from "./generated/v2-core/json/EvidenceRead.schema.json";
import manifest from "./generated/v2-core/manifest.json";
import researchArtifactSchema from "./generated/v2-core/json/ResearchArtifact.schema.json";
import researchArtifactDetailSchema from "./generated/v2-core/json/ResearchArtifactDetail.schema.json";
import researchContractDraftSchema from "./generated/v2-core/json/ResearchContractDraft.schema.json";
import researchContractSchema from "./generated/v2-core/json/ResearchContract.schema.json";
import researchProjectSchema from "./generated/v2-core/json/ResearchProject.schema.json";
import researchRunSchema from "./generated/v2-core/json/ResearchRun.schema.json";
import runEventSchema from "./generated/v2-core/json/RunEvent.schema.json";
import sourceSnapshotDetailSchema from "./generated/v2-core/json/SourceSnapshotDetail.schema.json";

/** Schema version from the B-15 generation manifest. */
export const V2_CONTRACT_SCHEMA_VERSION: number = manifest.schema_version;

/** Authoring source provenance for auditability. */
export const V2_CONTRACT_AUTHORING_SOURCE: string = manifest.authoring_source;

/** Core entity and generic provenance read models with standalone schemas. */
export const V2_CORE_MODEL_NAMES = [
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
] as const;
export type V2CoreModelName = (typeof V2_CORE_MODEL_NAMES)[number];

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

type SchemaMap = Record<V2CoreModelName, Record<string, unknown>>;

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
};

/** A compiled ajv validator function with its errors property. */
interface CompiledValidator {
  (data: unknown): boolean;
  readonly errors: unknown[] | null;
}

const validators = new Map<V2CoreModelName, CompiledValidator>();
for (const [name, schema] of Object.entries(schemas) as [
  V2CoreModelName,
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
 * Validate a value against a core v2 contract schema without throwing.
 */
export function validateV2Dto<T>(
  model: V2CoreModelName,
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
          message: `unknown v2 contract model: ${model}`,
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
export function parseV2Dto<T>(model: V2CoreModelName, value: unknown): T {
  const result = validateV2Dto<T>(model, value);
  if (!result.ok) {
    const lines = result.errors.map(
      (e) => `  at ${e.path}: ${e.message} (${e.keyword})`,
    );
    throw new Error(
      `v2 contract validation failed for ${model}:\n${lines.join("\n")}`,
    );
  }
  return result.data as T;
}

/** Type guard for a core v2 contract model. */
export function isV2Dto(model: V2CoreModelName, value: unknown): boolean {
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
} from "./generated/v2-core/dto";
