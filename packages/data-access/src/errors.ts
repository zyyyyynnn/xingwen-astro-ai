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
