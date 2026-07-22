/**
 * Research contract input — the shared scientific payload carried by an
 * editable draft and an immutable confirmed contract.
 *
 * Field names follow the frontend domain convention (camelCase) and are mapped
 * from the snake_case transport DTO by repository adapters. The shape mirrors
 * `ResearchContractInput` in the Pydantic `/api/v2` authoring source.
 */

import type { ArtifactKind, ContractDraftStatus, UnitPolicy } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type {
  ContentHash,
  NonEmptyString,
  ResearchGoal,
  UtcIsoTimestamp,
} from "./value-types";

export interface DataRequirements {
  readonly unitPolicy: UnitPolicy;
}

export interface SourceScope {
  readonly allowedSources: readonly DomainEntityId[];
}

export interface PaperSearchScope {
  readonly keywords: readonly string[];
  readonly yearFrom: number | null;
  readonly yearTo: number | null;
  readonly sourceIds: readonly DomainEntityId[];
  readonly maxCandidates: number;
}

export interface EvidenceRequirements {
  readonly requireLocator: boolean;
  readonly requireSourceSnapshot: boolean;
  readonly minimumCoverage: number;
}

export interface QualityConstraints {
  readonly sourceCompletenessMin: number;
  readonly unitConsistencyMin: number;
}

export interface ResearchContractInput {
  readonly researchGoal: ResearchGoal;
  readonly targetObjects: readonly DomainEntityId[];
  readonly dataRequirements: DataRequirements;
  readonly requestedFields: readonly DomainEntityId[];
  readonly sourceScope: SourceScope;
  readonly paperSearchScope: PaperSearchScope;
  readonly outputRequirements: readonly ArtifactKind[];
  readonly evidenceRequirements: EvidenceRequirements;
  readonly qualityConstraints: QualityConstraints;
}

/**
 * Validate the cross-field invariants of a contract input.
 *
 * Returns a list of human-readable violation messages; an empty list means the
 * input is valid. These mirror the `model_validator` rules in the Pydantic
 * source so the frontend can reject clearly malformed drafts before round-trip.
 */
export function validateContractInputInvariants(
  input: ResearchContractInput,
): readonly string[] {
  const violations: string[] = [];

  if (input.targetObjects.length !== new Set(input.targetObjects).size) {
    violations.push("target_objects must not contain duplicates");
  }
  if (input.requestedFields.length !== new Set(input.requestedFields).size) {
    violations.push("requested_fields must not contain duplicates");
  }
  if (
    input.outputRequirements.length !== new Set(input.outputRequirements).size
  ) {
    violations.push("output_requirements must not contain duplicates");
  }
  if (
    input.sourceScope.allowedSources.length !==
    new Set(input.sourceScope.allowedSources).size
  ) {
    violations.push("allowed_sources must not contain duplicates");
  }

  const { yearFrom, yearTo } = input.paperSearchScope;
  if (yearFrom !== null && yearTo !== null && yearFrom > yearTo) {
    violations.push("year_from must not exceed year_to");
  }

  return violations;
}

/**
 * Editable draft of a research contract. Carries the contract input payload
 * plus draft lifecycle metadata. Mirrors `ResearchContractDraft` in the
 * Pydantic `/api/v2` authoring source.
 */
export interface ResearchContractDraft {
  readonly id: DomainEntityId;
  readonly sessionId: DomainEntityId;
  readonly version: number;
  readonly intent: NonEmptyString;
  readonly status: ContractDraftStatus;
  readonly contract: ResearchContractInput;
  readonly warnings: readonly string[];
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
  readonly expiresAt: UtcIsoTimestamp;
}

/**
 * Immutable confirmed research contract. Extends the contract input with
 * identity, provenance and content hash. Mirrors `ResearchContract` in the
 * Pydantic `/api/v2` authoring source.
 */
export interface ResearchContract extends ResearchContractInput {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly version: number;
  readonly createdFromDraftId: DomainEntityId;
  readonly createdAt: UtcIsoTimestamp;
  readonly contentHash: ContentHash;
}
