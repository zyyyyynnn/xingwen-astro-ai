import {
  createHttpRepositories,
  createSessionManager,
} from "@xingwen/data-access";
import { researchAdapter } from "@xingwen/research-adapter";
import { createWorkspaceController } from "@xingwen/workspace-core";

import { createWorkspaceApplication } from "./application/workspace-application";
import { createWorkspaceQueryClient } from "./application/query-client";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";

export interface WorkspaceRuntimeOptions {
  /** Public API origin, without an API version or path prefix. */
  readonly apiBaseUrl?: string;
  /** Public Brand Site origin used by the explicit system-exit action. */
  readonly siteUrl?: string;
  readonly fetchImpl?: typeof fetch;
}

function parseSiteOrigin(value: string | undefined): string {
  const developmentFallback =
    import.meta.env.DEV && typeof globalThis.location !== "undefined"
      ? `${globalThis.location.protocol}//${globalThis.location.hostname}:4321`
      : undefined;
  const candidate = value?.trim() || developmentFallback;
  if (!candidate) {
    throw new Error(
      "VITE_SITE_URL is required for the production Workspace exit boundary.",
    );
  }
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new Error("VITE_SITE_URL must be a valid HTTP Site origin.");
  }
  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "VITE_SITE_URL must be an HTTP Site origin without a path, query, or fragment.",
    );
  }
  return url.origin;
}

function parseApiOrigin(value: string | undefined): string {
  if (!value?.trim()) {
    throw new Error(
      "VITE_API_BASE_URL is required for the production Workspace runtime.",
    );
  }

  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new Error("VITE_API_BASE_URL must be a valid HTTP API origin.");
  }

  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "VITE_API_BASE_URL must be an HTTP API origin without a path, query, or fragment.",
    );
  }

  return url.origin;
}

export function createWorkspaceRuntime(
  options: WorkspaceRuntimeOptions = {},
): WorkspaceRuntimeBoundaries {
  const baseUrl = parseApiOrigin(
    options.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL,
  );
  const siteUrl = parseSiteOrigin(
    options.siteUrl ?? import.meta.env.VITE_SITE_URL,
  );
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const session = createSessionManager({ baseUrl, fetchImpl });
  const repositories = createHttpRepositories({ baseUrl, fetchImpl, session });
  const queryClient = createWorkspaceQueryClient();

  return {
    siteUrl,
    repositories,
    researchAdapter,
    session,
    queryClient,
    application: createWorkspaceApplication({
      repositories,
      researchAdapter,
      session,
      queryClient,
    }),
    workspaceController: createWorkspaceController(repositories.workspaces),
  };
}
