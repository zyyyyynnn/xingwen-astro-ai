import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import type { SessionInfo, SessionManager } from "@xingwen/data-access";
import { researchAdapter } from "@xingwen/research-adapter";
import { createWorkspaceController } from "@xingwen/workspace-core";
import { vi } from "vitest";

import { createWorkspaceApplication } from "../application/workspace-application";
import { createWorkspaceQueryClient } from "../application/query-client";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";

export function createTestRuntime(): WorkspaceRuntimeBoundaries {
  const repositories = createFixtureRepositories(exoplanetHostStarFixture);
  const queryClient = createWorkspaceQueryClient();
  const sessionInfo: SessionInfo = {
    status: "active",
    createdAt: "2026-08-11T00:00:00Z",
    expiresAt: "2026-08-11T01:00:00Z",
    quota: {},
    csrfToken: "csrf-test-only",
  };
  let expiredListener: (() => void) | undefined;
  const session: SessionManager = {
    ensureSession: vi.fn(async () => sessionInfo),
    getCurrent: vi.fn(() => sessionInfo),
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
  return {
    siteUrl: "http://localhost:4321",
    repositories,
    researchAdapter,
    session,
    queryClient,
    application: createWorkspaceApplication({
      repositories,
      researchAdapter,
      session,
      queryClient,
      createIdempotencyKey: () => `test-${crypto.randomUUID()}`,
    }),
    workspaceController: createWorkspaceController(repositories.workspaces),
  };
}
