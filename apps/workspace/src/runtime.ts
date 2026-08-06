import {
  createFixtureRepositories,
  createHttpRepositories,
  createSessionManager,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import { createWorkspaceController } from "@xingwen/workspace-core";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";

export interface WorkspaceRuntimeOptions {
  /** Public API origin, without an API version or path prefix. */
  readonly apiBaseUrl?: string;
  readonly fetchImpl?: typeof fetch;
}

function parseApiOrigin(value: string): string {
  let url: URL;
  try {
    url = new URL(value);
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
  const configuredApiBaseUrl =
    options.apiBaseUrl ?? import.meta.env.VITE_API_BASE_URL?.trim();

  if (!configuredApiBaseUrl) {
    const repositories = createFixtureRepositories(exoplanetHostStarFixture);
    return {
      adapterKind: "fixture",
      repositories,
      workspaceController: createWorkspaceController(repositories.workspaces),
    };
  }

  const baseUrl = parseApiOrigin(configuredApiBaseUrl);
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  const session = createSessionManager({
    baseUrl,
    fetchImpl,
  });
  const repositories = createHttpRepositories({
    baseUrl,
    fetchImpl,
    session,
  });

  return {
    adapterKind: "http",
    repositories,
    session,
    workspaceController: createWorkspaceController(repositories.workspaces),
  };
}
