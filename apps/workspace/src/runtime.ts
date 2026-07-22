import {
  createFixtureRepositories,
  createHttpRepositories,
  createSessionManager,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import type { RepositorySet } from "@xingwen/data-access";
import {
  createGuidedTourController,
  createWorkspaceController,
} from "@xingwen/workspace-core";

import type {
  FixtureBootstrapContext,
  WorkspaceRuntimeBoundaries,
} from "./boundaries";

type RepositoryEntityId = Parameters<RepositorySet["projects"]["getById"]>[0];

export interface WorkspaceRuntimeOptions {
  /** Public API origin, without an API version or path prefix. */
  readonly apiBaseUrl?: string;
  readonly fetchImpl?: typeof fetch;
}

function asRepositoryEntityId(value: string): RepositoryEntityId {
  return value as RepositoryEntityId;
}

export const FIXTURE_BOOTSTRAP: FixtureBootstrapContext = {
  projectId: asRepositoryEntityId("proj_01JEXAMPLE"),
  draftId: asRepositoryEntityId("rcd_01JTOUR"),
  contractId: asRepositoryEntityId("rc_01JEXAMPLE"),
  runId: asRepositoryEntityId("run_01JEXAMPLE"),
};

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
      bootstrap: FIXTURE_BOOTSTRAP,
      tour: createGuidedTourController(),
      workspaceController: createWorkspaceController(repositories.workspaces),
    };
  }

  const baseUrl = parseApiOrigin(configuredApiBaseUrl);
  const session = createSessionManager({
    baseUrl,
    fetchImpl: options.fetchImpl ?? globalThis.fetch,
  });
  const repositories = createHttpRepositories({
    baseUrl,
    fetchImpl: options.fetchImpl,
    session,
  });

  return {
    adapterKind: "http",
    repositories,
    session,
    tour: createGuidedTourController(),
    workspaceController: createWorkspaceController(repositories.workspaces),
  };
}
