import { QueryClient } from "@tanstack/react-query";
import type { SessionInfo, SessionManager } from "@xingwen/data-access";
import {
  ForbiddenError,
  SessionExpiredError,
} from "@xingwen/data-access/errors";
import { researchAdapter } from "@xingwen/research-adapter";
import { describe, expect, it, vi } from "vitest";

import { workspaceQueryKeys } from "./query-keys";
import { SessionGateRequiredError, createSessionGate } from "./session-gate";

const activeSession: SessionInfo = {
  status: "active",
  createdAt: "2026-08-11T00:00:00Z",
  expiresAt: "2026-08-11T01:00:00Z",
  quota: {},
  csrfToken: "csrf-test-only",
};

function createSessionDouble() {
  let expiredListener: (() => void) | undefined;
  const session: SessionManager = {
    ensureSession: vi.fn(async () => activeSession),
    getCurrent: vi.fn(() => activeSession),
    revokeSession: vi.fn(async () => undefined),
    attachCsrf: vi.fn(),
    onSessionExpired: vi.fn((listener) => {
      expiredListener = listener;
      return () => {
        expiredListener = undefined;
      };
    }),
    notifyExpired: vi.fn(() => expiredListener?.()),
  };
  return { session, expire: () => expiredListener?.() };
}

describe("Session Gate", () => {
  it.each([
    ["expired", new SessionExpiredError("expired"), "session_required"],
    [
      "forbidden",
      new ForbiddenError("hidden ownership failure", "ACTION_FORBIDDEN"),
      "forbidden",
    ],
  ] as const)(
    "fails closed for %s private-session errors",
    async (_case, error, expectedKind) => {
      const { session } = createSessionDouble();
      vi.mocked(session.ensureSession).mockRejectedValueOnce(error);
      const gate = createSessionGate({
        session,
        queryClient: new QueryClient(),
        toPublicError: researchAdapter.toPublicApplicationError,
      });

      await expect(gate.requireSession()).rejects.toMatchObject({
        publicError: { kind: expectedKind },
      });
      expect(gate.getSnapshot().status).toBe("required");
      gate.dispose();
    },
  );

  it("clears only private Query state and invalidates the router on expiry", async () => {
    const { session, expire } = createSessionDouble();
    const queryClient = new QueryClient();
    queryClient.setQueryData(workspaceQueryKeys.projects(), ["private"]);
    queryClient.setQueryData(["public-share", "token"], "public");
    const invalidateRouter = vi.fn(async () => undefined);
    const gate = createSessionGate({
      session,
      queryClient,
      toPublicError: researchAdapter.toPublicApplicationError,
    });
    gate.bindRouterInvalidation(invalidateRouter);

    await gate.requireSession();
    expire();

    expect(gate.getSnapshot().status).toBe("required");
    expect(
      queryClient.getQueryData(workspaceQueryKeys.projects()),
    ).toBeUndefined();
    expect(queryClient.getQueryData(["public-share", "token"])).toBe("public");
    expect(invalidateRouter).toHaveBeenCalledOnce();
    await expect(gate.requireSession()).rejects.toBeInstanceOf(
      SessionGateRequiredError,
    );
    gate.dispose();
  });

  it("clears explicit logout without routing through the expiry error page", async () => {
    const { session } = createSessionDouble();
    const gate = createSessionGate({
      session,
      queryClient: new QueryClient(),
      toPublicError: researchAdapter.toPublicApplicationError,
    });

    await gate.requireSession();
    await gate.logout();
    expect(session.revokeSession).toHaveBeenCalledOnce();
    expect(gate.getSnapshot().status).toBe("checking");

    await expect(gate.requireSession()).resolves.toEqual(activeSession);
    expect(session.ensureSession).toHaveBeenCalledTimes(2);
    gate.dispose();
  });
});
