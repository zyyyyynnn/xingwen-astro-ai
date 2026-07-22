/**
 * Data-access error types.
 *
 * These errors are thrown by repository adapters (fixture and, later, HTTP)
 * when data fails validation or cannot be found. They carry enough context for
 * the UI to render actionable failure states.
 */

/** A fixture payload failed v2 contract schema validation. */
export class FixtureValidationError extends Error {
  readonly model: string;
  readonly errors: readonly string[];

  constructor(model: string, errors: readonly string[]) {
    const lines = errors.map((e) => `  - ${e}`);
    super(`Fixture validation failed for ${model}:\n${lines.join("\n")}`);
    this.name = "FixtureValidationError";
    this.model = model;
    this.errors = errors;
  }
}

/** A requested entity was not found in the repository. */
export class EntityNotFoundError extends Error {
  readonly entityKind: string;
  readonly entityId: string;

  constructor(entityKind: string, entityId: string) {
    super(`${entityKind} not found: ${entityId}`);
    this.name = "EntityNotFoundError";
    this.entityKind = entityKind;
    this.entityId = entityId;
  }
}

/**
 * Thrown when a fixture bundle violates the Demo Replay semantic constraints
 * (e.g. marking fixture data as `live` or `cached`).
 */
export class FixtureSemanticError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FixtureSemanticError";
  }
}

/**
 * Thrown when an HTTP adapter method cannot be implemented because the
 * corresponding operation does not exist in the generated OpenAPI contract.
 *
 * This is NOT a runtime failure — it means the backend has not yet exposed
 * the route. The caller should treat this as a permanent "not available"
 * until the OpenAPI is regenerated with the new operationId.
 */
export class CapabilityUnavailableError extends Error {
  readonly capability: string;
  readonly reason: string;

  constructor(capability: string, reason: string) {
    super(`Capability unavailable: ${capability} — ${reason}`);
    this.name = "CapabilityUnavailableError";
    this.capability = capability;
    this.reason = reason;
  }
}
