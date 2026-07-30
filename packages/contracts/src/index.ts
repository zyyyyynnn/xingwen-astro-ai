/**
 * @xingwen/contracts — the frontend consumption boundary for the B-15 frozen
 * `/api` core contract.
 *
 * Pydantic remains the sole production schema authoring source. This package
 * vendors the generated JSON Schemas and exposes:
 *
 * - TypeScript DTO types generated from the OpenAPI components (never
 *   hand-written — see `scripts/sync_contracts.mjs`).
 * - Runtime validation via `ajv` against the real B-15 JSON Schemas.
 *
 * The fixture adapter (`@xingwen/data-access`) uses these validators to assert
 * contract conformance before mapping payloads into the domain model.
 */

export { isDto, parseDto, validateDto } from "./validation";
export type {
  ContractValidationError,
  ContractValidationResult,
  CoreModelName,
} from "./validation";
export {
  CONTRACT_AUTHORING_SOURCE,
  CONTRACT_SCHEMA_VERSION,
  CORE_MODEL_NAMES,
} from "./validation";

export type {
  ArtifactVersionDto,
  ArtifactVersionDetailDto,
  EvidenceReadDto,
  ResearchArtifactDto,
  ResearchArtifactDetailDto,
  ResearchContractDto,
  ResearchContractDraftDto,
  ResearchProjectDto,
  ResearchRunDto,
  RunEventDto,
  SourceSnapshotDetailDto,
} from "./validation";

// Re-export all generated transport types for adapter consumption.
export type * from "./generated/core/dto";
