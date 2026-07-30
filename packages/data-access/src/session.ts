/**
 * Session manager — anonymous session lifecycle and CSRF token handling.
 *
 * POST /api/sessions creates an isolated temporary session. The server
 * identifies the session via a Secure, HttpOnly, SameSite Cookie managed by
 * the browser; the client never reads the token. The createSession response
 * returns an in-memory CSRF token that must be attached to every non-safe
 * method via the `X-CSRF-Token` header.
 *
 * A 401 SESSION_REQUIRED from any repository call triggers `onSessionExpired`,
 * letting the workspace surface a re-auth prompt without each call site
 * inspecting error types.
 */

import { parseDto, type SessionCreated } from "@xingwen/contracts";

import { errorFromResponse, NetworkError } from "./http-errors";

export interface SessionInfo {
  readonly status: SessionCreated["status"];
  readonly createdAt: string;
  readonly expiresAt: string;
  readonly quota: SessionQuota;
  readonly csrfToken: string;
}

export interface SessionQuota {
  readonly maxProjects?: number;
  readonly maxRuns?: number;
}

/** Listener invoked when the session is detected as expired. */
export type SessionExpiredListener = () => void;

export interface SessionManager {
  /** Ensure a session exists; create one if none exists yet. */
  ensureSession(): Promise<SessionInfo>;
  /** Current session info, or null if not yet created / expired. */
  getCurrent(): SessionInfo | null;
  /** Explicitly revoke the session (DELETE /api/sessions/current). */
  revokeSession(): Promise<void>;
  /** Attach CSRF header to a mutable Headers for non-safe methods. */
  attachCsrf(headers: Headers): void;
  /** Subscribe to session-expired events. Returns an unsubscribe function. */
  onSessionExpired(listener: SessionExpiredListener): () => void;
  /** Mark the session as expired and notify listeners. */
  notifyExpired(): void;
}

export interface SessionManagerConfig {
  readonly baseUrl: string;
  readonly fetchImpl: typeof fetch;
}

interface CreateSessionEnvelope {
  readonly data: unknown;
}

async function fetchSession(
  config: SessionManagerConfig,
  path: string,
  init: RequestInit,
): Promise<Response> {
  try {
    return await config.fetchImpl(`${config.baseUrl}${path}`, init);
  } catch (error) {
    throw new NetworkError(
      error instanceof Error ? error.message : "Network request failed",
      error,
    );
  }
}

export function createSessionManager(
  config: SessionManagerConfig,
): SessionManager {
  let current: SessionInfo | null = null;
  // Dedupe concurrent cold-start calls: without an existing cookie, two
  // simultaneous ensureSession() calls (e.g. a StrictMode double-invoked
  // effect) would each POST /sessions and create *two* sessions, leaving the
  // cookie and the in-memory CSRF token pointing at different sessions (→ 403
  // on the next mutation). Memoizing the in-flight promise guarantees a single
  // creation is shared by all callers.
  let inFlight: Promise<SessionInfo> | null = null;
  const listeners = new Set<SessionExpiredListener>();

  return {
    async ensureSession(): Promise<SessionInfo> {
      if (current) return current;
      if (inFlight) return inFlight;
      inFlight = (async () => {
        const response = await fetchSession(config, "/api/sessions", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        });
        if (!response.ok) {
          throw await errorFromResponse(response);
        }
        const payload = (await response.json()) as CreateSessionEnvelope;
        const data = parseDto<SessionCreated>("SessionCreated", payload.data);
        current = {
          status: data.status,
          createdAt: data.created_at,
          expiresAt: data.expires_at,
          quota: {
            maxProjects: data.quota.max_projects,
            maxRuns: data.quota.max_runs,
          },
          csrfToken: data.csrf_token,
        };
        return current;
      })();
      try {
        return await inFlight;
      } finally {
        inFlight = null;
      }
    },

    getCurrent() {
      return current;
    },

    async revokeSession() {
      if (!current) return;
      const response = await fetchSession(config, "/api/sessions/current", {
        method: "DELETE",
        credentials: "include",
        headers: { "X-CSRF-Token": current.csrfToken },
      });
      // 204 No Content or 404 (already gone) are both acceptable.
      if (!response.ok && response.status !== 404) {
        if (response.status === 401) this.notifyExpired();
        throw await errorFromResponse(response);
      }
      current = null;
    },

    attachCsrf(headers: Headers) {
      if (current) {
        headers.set("X-CSRF-Token", current.csrfToken);
      }
    },

    onSessionExpired(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },

    notifyExpired() {
      current = null;
      for (const listener of listeners) {
        listener();
      }
    },
  };
}
