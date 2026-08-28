/**
 * HTTP error mapping — RFC 9457 Problem Details → domain error types.
 *
 * The HTTP adapter wraps every non-2xx response and network failure into one
 * of these error classes so workspace consumers can branch on stable error
 * categories without inspecting HTTP details.
 *
 * Problem Details shape and `code` values follow API_CONTRACT.md §5.
 */

import {
  ConflictError,
  ForbiddenError,
  NotFoundError,
  RateLimitedError,
  SessionExpiredError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
} from "./errors";
import type { ValidationFieldError } from "./errors";

/** RFC 9457 Problem Details payload. */
export interface ProblemDetails {
  readonly type?: string;
  readonly title?: string;
  readonly status?: number;
  readonly detail?: string;
  readonly instance?: string;
  readonly code?: string;
  readonly request_id?: string;
  readonly errors?: readonly ProblemDetailsFieldError[];
}

/** Problem Details field errors remain transport-shaped but fit the pure model. */
export type ProblemDetailsFieldError = ValidationFieldError;

/** Parse Retry-After header (seconds or HTTP date) into milliseconds. */
function parseRetryAfter(headerValue: string | null): number | null {
  if (!headerValue) return null;
  const asSeconds = Number(headerValue);
  if (!Number.isNaN(asSeconds) && asSeconds >= 0) {
    return asSeconds * 1000;
  }
  const asDate = Date.parse(headerValue);
  if (!Number.isNaN(asDate)) {
    return Math.max(0, asDate - Date.now());
  }
  return null;
}

/**
 * Map a Problem Details response into a typed domain error.
 *
 * Caller is responsible for parsing the JSON body before calling this.
 */
export function mapProblemDetails(
  problem: ProblemDetails,
  responseHeaders: Headers,
): Error {
  const status = problem.status ?? 0;
  const code = problem.code ?? null;
  const detail = problem.detail ?? problem.title ?? "HTTP error";
  const fieldErrors = problem.errors ?? [];

  switch (status) {
    case 401:
      return new SessionExpiredError(detail);
    case 403:
      return new ForbiddenError(detail, code ?? "ACTION_FORBIDDEN");
    case 404:
      return new NotFoundError(detail, code ?? "NOT_FOUND");
    case 409:
      return new ConflictError(detail, code ?? "RUN_STATE_CONFLICT");
    case 415:
    case 422:
      return new ValidationError(
        detail,
        code ?? "SCHEMA_VALIDATION_FAILED",
        fieldErrors,
      );
    case 429:
      return new RateLimitedError(
        detail,
        parseRetryAfter(responseHeaders.get("Retry-After")),
      );
    case 502:
    case 503:
    case 504:
      return new UpstreamError(detail, code ?? "UPSTREAM_UNAVAILABLE", status);
    default:
      return new UnexpectedHttpError(detail, status, code);
  }
}

/** Parse an HTTP error response and map it to the stable adapter error model. */
export async function errorFromResponse(response: Response): Promise<Error> {
  let problem: ProblemDetails | null = null;
  try {
    const text = await response.clone().text();
    if (text) problem = JSON.parse(text) as ProblemDetails;
  } catch {
    // Invalid or empty error bodies fall back to the HTTP status metadata.
  }

  return mapProblemDetails(
    {
      ...problem,
      status: problem?.status ?? response.status,
      detail: problem?.detail ?? problem?.title ?? response.statusText,
    },
    response.headers,
  );
}
