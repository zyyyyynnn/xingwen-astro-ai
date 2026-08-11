/**
 * Data-access error types.
 *
 * These errors are thrown by fixture and HTTP repository adapters
 * when data fails validation or cannot be found. They carry enough context for
 * the UI to render actionable failure states.
 */

/** A fixture payload failed contract schema validation. */
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

/** A pure, normalized network-level failure. */
export class NetworkError extends Error {
  override readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
  }
}

/** A pure, normalized session-expired failure. */
export class SessionExpiredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SessionExpiredError";
  }
}

/** A pure, normalized forbidden-action failure. */
export class ForbiddenError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "ForbiddenError";
    this.code = code;
  }
}

/** A pure, normalized not-found failure. */
export class NotFoundError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "NotFoundError";
    this.code = code;
  }
}

/** A pure, normalized state, version or idempotency conflict. */
export class ConflictError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "ConflictError";
    this.code = code;
  }
}

export interface ValidationFieldError {
  readonly field: string;
  readonly code: string;
  readonly message: string;
}

/** A pure, normalized business or schema validation failure. */
export class ValidationError extends Error {
  readonly code: string;
  readonly fieldErrors: readonly ValidationFieldError[];

  constructor(
    message: string,
    code: string,
    fieldErrors: readonly ValidationFieldError[],
  ) {
    super(message);
    this.name = "ValidationError";
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

/** A pure, normalized rate-limit or quota failure. */
export class RateLimitedError extends Error {
  readonly retryAfterMs: number | null;

  constructor(message: string, retryAfterMs: number | null) {
    super(message);
    this.name = "RateLimitedError";
    this.retryAfterMs = retryAfterMs;
  }
}

/** A pure, normalized upstream service failure. */
export class UpstreamError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "UpstreamError";
    this.code = code;
    this.status = status;
  }
}

/** A pure, normalized unexpected upstream/transport failure. */
export class UnexpectedHttpError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "UnexpectedHttpError";
    this.status = status;
    this.code = code;
  }
}
