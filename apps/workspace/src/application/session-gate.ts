import type { QueryClient } from "@tanstack/react-query";
import type { SessionInfo, SessionManager } from "@xingwen/data-access";
import { SessionExpiredError } from "@xingwen/data-access/errors";
import type { PublicApplicationError } from "@xingwen/research-adapter";

import { isPrivateWorkspaceQuery } from "./query-keys";

export type SessionGateStatus = "checking" | "ready" | "required";

export interface SessionGateSnapshot {
  readonly status: SessionGateStatus;
  readonly publicError: PublicApplicationError | null;
}

interface SessionGateDependencies {
  readonly session: SessionManager;
  readonly queryClient: QueryClient;
  readonly toPublicError: (error: unknown) => PublicApplicationError;
}

export class SessionGateRequiredError extends Error {
  readonly publicError: PublicApplicationError;

  constructor(publicError: PublicApplicationError) {
    super(publicError.safeMessage);
    this.name = "SessionGateRequiredError";
    this.publicError = publicError;
  }
}

export function createSessionGate({
  session,
  queryClient,
  toPublicError,
}: SessionGateDependencies) {
  let snapshot: SessionGateSnapshot = {
    status: "checking",
    publicError: null,
  };
  let invalidateRouter: (() => void | Promise<void>) | null = null;
  const listeners = new Set<() => void>();

  const publish = (next: SessionGateSnapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };

  const clearPrivateQueries = () => {
    queryClient.removeQueries({
      predicate: (query) => isPrivateWorkspaceQuery(query.queryKey),
    });
  };

  const requireReentry = (publicError: PublicApplicationError) => {
    clearPrivateQueries();
    publish({ status: "required", publicError });
    void invalidateRouter?.();
  };

  const unsubscribeExpired = session.onSessionExpired(() => {
    requireReentry(
      toPublicError(new SessionExpiredError("The private session expired.")),
    );
  });

  return Object.freeze({
    async requireSession(): Promise<SessionInfo> {
      if (snapshot.status === "required") {
        throw new SessionGateRequiredError(
          snapshot.publicError ?? {
            kind: "session_required",
            safeMessage: "需要重新建立会话",
          },
        );
      }
      publish({ status: "checking", publicError: null });
      try {
        const info = await session.ensureSession();
        publish({ status: "ready", publicError: null });
        return info;
      } catch (error) {
        const publicError = toPublicError(error);
        requireReentry(publicError);
        throw new SessionGateRequiredError(publicError);
      }
    },
    async logout(): Promise<void> {
      try {
        await session.revokeSession();
      } finally {
        clearPrivateQueries();
        publish({ status: "checking", publicError: null });
      }
    },
    allowReentry() {
      publish({ status: "checking", publicError: null });
      void invalidateRouter?.();
    },
    bindRouterInvalidation(callback: () => void | Promise<void>) {
      invalidateRouter = callback;
    },
    getSnapshot(): SessionGateSnapshot {
      return snapshot;
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    dispose() {
      invalidateRouter = null;
      listeners.clear();
      unsubscribeExpired();
    },
  });
}

export type SessionGate = ReturnType<typeof createSessionGate>;
