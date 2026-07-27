/**
 * Internal HTTP transport client shared by the `/api/v2` repositories.
 *
 * Wraps `fetch` with envelope parsing, RFC 9457 Problem Details → domain error
 * mapping, CSRF attachment for non-safe methods, and 401 session-expiry
 * notification. Repository modules define endpoint paths and required headers;
 * this client is the only place that executes fetch and parses envelopes.
 */

import { parseV2Dto, type V2CoreModelName } from "@xingwen/contracts";

import {
  errorFromResponse,
  NetworkError,
  NotFoundError,
  UnexpectedHttpError,
} from "./http-errors";
import type { SessionManager } from "./session";

/** Common envelope for single-resource responses (API_CONTRACT.md §4). */
export interface Envelope<T> {
  readonly data: T;
  readonly meta?: {
    readonly request_id?: string;
    readonly schema_version?: string;
    readonly generated_at?: string;
  };
  readonly links?: { readonly self?: string };
}

/** Envelope for collection responses with cursor pagination. */
export interface CollectionEnvelope<T> {
  readonly data: readonly T[];
  readonly meta?: Envelope<unknown>["meta"];
  readonly page?: {
    readonly next_cursor?: string | null;
    readonly has_more?: boolean;
    readonly limit?: number;
  };
}

export interface HttpAdapterConfig {
  /** API origin without trailing slash or version prefix, e.g. `http://127.0.0.1:8000`. */
  readonly baseUrl: string;
  /** Inject fetch implementation (defaults to global fetch). */
  readonly fetchImpl?: typeof fetch;
  /** Session manager for CSRF and session-expired handling. */
  readonly session: SessionManager;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** Internal HTTP client wrapping fetch with envelope parsing and error mapping. */
export class HttpClient {
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: HttpAdapterConfig) {
    this.fetchImpl = config.fetchImpl ?? globalThis.fetch;
  }

  private buildUrl(path: string): string {
    return `${this.config.baseUrl}${path}`;
  }

  private prepareHeaders(method: string, extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (method.toUpperCase() !== "GET" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (!SAFE_METHODS.has(method.toUpperCase())) {
      this.config.session.attachCsrf(headers);
    }
    return headers;
  }

  /** Single GET; returns parsed `data` or null on 404. */
  async get<T>(path: string): Promise<T | null> {
    try {
      const env = await this.request<Envelope<T>>("GET", path);
      return env ? env.data : null;
    } catch (err) {
      if (err instanceof NotFoundError) return null;
      throw err;
    }
  }

  /**
   * Collection GET aggregating every page in ascending order. The cursor is
   * applied against the *base* path each iteration (never accumulated), and a
   * 404 is NOT silently converted to an empty list — it propagates as
   * `NotFoundError` so the caller learns the parent resource is missing.
   */
  async list<T>(path: string): Promise<readonly T[]> {
    const aggregated: T[] = [];
    let cursor: string | null = null;
    do {
      const separator = path.includes("?") ? "&" : "?";
      const url: string = cursor
        ? `${path}${separator}cursor=${encodeURIComponent(cursor)}`
        : path;
      const env: CollectionEnvelope<T> | null = await this.request<
        CollectionEnvelope<T>
      >("GET", url);
      if (!env) break;
      aggregated.push(...env.data);
      cursor = env.page?.has_more ? (env.page?.next_cursor ?? null) : null;
    } while (cursor);
    return aggregated;
  }

  /**
   * Single-page collection GET (no cursor following); used by event recovery.
   *
   * A collection endpoint is contractually required to return a
   * `CollectionEnvelope`. A legitimately empty collection is `200` with a JSON
   * body `{"data":[],...}`, which `request` parses normally. A `204` or empty
   * body violates the collection contract, so it surfaces as
   * `UnexpectedHttpError` instead of being masked as a fake empty envelope; a
   * missing parent surfaces as `NotFoundError` (thrown inside `request`), not
   * a silent empty list.
   */
  async getPage<T>(path: string): Promise<CollectionEnvelope<T>> {
    const env = await this.request<CollectionEnvelope<T>>("GET", path);
    if (!env) {
      throw new UnexpectedHttpError(
        "Expected a collection envelope but received an empty body (204 or no content)",
        200,
        null,
      );
    }
    return env;
  }

  /** POST creating a resource; returns parsed `data`. */
  async post<T>(
    path: string,
    body: unknown,
    headers?: HeadersInit,
  ): Promise<T> {
    const env = await this.request<Envelope<T>>("POST", path, body, headers);
    if (!env) {
      throw new UnexpectedHttpError("Empty response body on POST", 200, null);
    }
    return env.data;
  }

  /** PATCH updating a resource; returns parsed `data`. */
  async patch<T>(
    path: string,
    body: unknown,
    headers?: HeadersInit,
  ): Promise<T> {
    const env = await this.request<Envelope<T>>("PATCH", path, body, headers);
    if (!env) {
      throw new UnexpectedHttpError("Empty response body on PATCH", 200, null);
    }
    return env.data;
  }

  /** PUT; returns parsed `data`. */
  async put<T>(path: string, body: unknown, headers?: HeadersInit): Promise<T> {
    const env = await this.request<Envelope<T>>("PUT", path, body, headers);
    if (!env) {
      throw new UnexpectedHttpError("Empty response body on PUT", 200, null);
    }
    return env.data;
  }

  /** DELETE; returns true on 204 or 404 (idempotent). */
  async delete(path: string): Promise<boolean> {
    const response = await this.rawRequest("DELETE", path);
    if (response.status === 204 || response.status === 404) return true;
    if (!response.ok) {
      await this.throwFromResponse(response);
    }
    return true;
  }

  private async rawRequest(
    method: string,
    path: string,
    body?: unknown,
    extraHeaders?: HeadersInit,
  ): Promise<Response> {
    const headers = this.prepareHeaders(method, extraHeaders);
    let response: Response;
    try {
      response = await this.fetchImpl(this.buildUrl(path), {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        credentials: "include",
      });
    } catch (err) {
      throw new NetworkError(
        err instanceof Error ? err.message : "Network request failed",
        err,
      );
    }
    if (response.status === 401) {
      this.config.session.notifyExpired();
      throw await errorFromResponse(response);
    }
    return response;
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    headers?: HeadersInit,
  ): Promise<T | null> {
    const response = await this.rawRequest(method, path, body, headers);
    if (response.status === 204) return null;
    if (response.status === 404) {
      throw await errorFromResponse(response);
    }
    if (!response.ok) {
      await this.throwFromResponse(response);
    }
    const text = await response.text();
    if (!text) return null;
    return JSON.parse(text) as T;
  }

  private async throwFromResponse(response: Response): Promise<never> {
    throw await errorFromResponse(response);
  }
}

/** Validate a payload against the generated contract, then map to a domain type. */
export function validateAndMap<TDto, TDomain>(
  model: V2CoreModelName,
  payload: unknown,
  map: (dto: TDto) => TDomain,
): TDomain {
  return map(parseV2Dto<TDto>(model, payload));
}

/**
 * Derive a deterministic Idempotency-Key from a request scope and body, so an
 * identical create/confirm retried by the caller reuses the same key and the
 * server replays the original result instead of duplicating work.
 */
export function stableIdempotencyKey(scope: string, body: unknown): string {
  const canonical = `${scope}:${JSON.stringify(body ?? null)}`;
  let hash = 5381;
  for (let i = 0; i < canonical.length; i += 1) {
    hash = ((hash << 5) + hash + canonical.charCodeAt(i)) >>> 0;
  }
  return `${scope}-${hash.toString(16).padStart(8, "0")}`;
}

/** Encode a path segment for safe interpolation. */
export function seg(value: string): string {
  return encodeURIComponent(value);
}
