/**
 * @xingwen/contracts — the frontend consumption boundary for the B-15 frozen
 * `/api/v2` core contract.
 *
 * Pydantic remains the sole production schema authoring source. This package
 * vendors the generated JSON Schemas and exposes:
 *
 * - TypeScript DTO types generated from the OpenAPI components (never
 *   hand-written — see `scripts/sync_v2_contracts.mjs`).
 * - Runtime validation via `ajv` against the real B-15 JSON Schemas.
 *
 * The fixture adapter (`@xingwen/data-access`) uses these validators to assert
 * contract conformance before mapping payloads into the domain model.
 */

export { isV2Dto, parseV2Dto, validateV2Dto } from "./validation";
export type {
  ContractValidationError,
  ContractValidationResult,
  V2CoreModelName,
} from "./validation";
export {
  V2_CONTRACT_AUTHORING_SOURCE,
  V2_CONTRACT_SCHEMA_VERSION,
  V2_CORE_MODEL_NAMES,
} from "./validation";

export type {
  ArtifactVersionDto,
  ResearchArtifactDto,
  ResearchContractDto,
  ResearchContractDraftDto,
  ResearchProjectDto,
  ResearchRunDto,
  RunEventDto,
} from "./validation";

// Re-export all generated transport types for adapter consumption.
export type * from "./generated/v2-core/dto";
