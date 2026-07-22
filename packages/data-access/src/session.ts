/**
 * Session manager — anonymous session lifecycle and CSRF token handling.
 *
 * POST /api/v2/sessions creates an isolated temporary session. The server
 * identifies the session via a Secure, HttpOnly, SameSite Cookie managed by
 * the browser; the client never reads the token. The createSession response
 * returns an in-memory CSRF token that must be attached to every non-safe
 * method via the `X-CSRF-Token` header.
 *
 * A 401 SESSION_REQUIRED from any repository call triggers `onSessionExpired`,
 * letting the workspace surface a re-auth prompt without each call site
 * inspecting error types.
 */

export interface SessionInfo {
  readonly sessionId: string;
  readonly expiresAt: string;
  readonly quota: SessionQuota;
  readonly csrfToken: string;
}

export interface SessionQuota {
  readonly runsPerDay: number;
  readonly sharesPerHour: number;
  readonly feedbacksPerHour: number;
}

/** Listener invoked when the session is detected as expired. */
export type SessionExpiredListener = () => void;

export interface SessionManager {
  /** Ensure a session exists; create one if none exists yet. */
  ensureSession(): Promise<SessionInfo>;
  /** Current session info, or null if not yet created / expired. */
  getCurrent(): SessionInfo | null;
  /** Explicitly revoke the session (DELETE /api/v2/sessions/current). */
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

interface CreateSessionResponse {
  readonly data: {
    readonly id: string;
    readonly expires_at: string;
    readonly quota: {
      readonly runs_per_day: number;
      readonly shares_per_hour: number;
      readonly feedbacks_per_hour: number;
    };
    readonly csrf_token: string;
  };
}

export function createSessionManager(
  config: SessionManagerConfig,
): SessionManager {
  let current: SessionInfo | null = null;
  const listeners = new Set<SessionExpiredListener>();

  return {
    async ensureSession(): Promise<SessionInfo> {
      if (current) return current;
      const response = await config.fetchImpl(
        `${config.baseUrl}/api/v2/sessions`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
        },
      );
      if (!response.ok) {
        throw new Error(
          `Failed to create session: ${response.status} ${response.statusText}`,
        );
      }
      const payload = (await response.json()) as CreateSessionResponse;
      current = {
        sessionId: payload.data.id,
        expiresAt: payload.data.expires_at,
        quota: {
          runsPerDay: payload.data.quota.runs_per_day,
          sharesPerHour: payload.data.quota.shares_per_hour,
          feedbacksPerHour: payload.data.quota.feedbacks_per_hour,
        },
        csrfToken: payload.data.csrf_token,
      };
      return current;
    },

    getCurrent() {
      return current;
    },

    async revokeSession() {
      if (!current) return;
      const response = await config.fetchImpl(
        `${config.baseUrl}/api/v2/sessions/current`,
        {
          method: "DELETE",
          credentials: "include",
          headers: { "X-CSRF-Token": current.csrfToken },
        },
      );
      // 204 No Content or 404 (already gone) are both acceptable.
      if (!response.ok && response.status !== 404) {
        throw new Error(
          `Failed to revoke session: ${response.status} ${response.statusText}`,
        );
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
