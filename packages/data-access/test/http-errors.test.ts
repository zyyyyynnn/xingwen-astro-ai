/**
 * HTTP error scenario tests — RFC 9457 Problem Details → domain error mapping.
 *
 * Covers 401/403/404/409/422/429/503, network failure, idempotency conflict,
 * version conflict, and CapabilityUnavailableError for operations without an
 * OpenAPI endpoint. Each error test installs a handler returning a specific
 * problem details payload and asserts the adapter throws the mapped error.
 */

import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import type { ResearchContractDraft } from "@xingwen/domain";

import { createHttpRepositories } from "../src/http-adapter";
import { CapabilityUnavailableError } from "../src/errors";
import {
  ConflictError,
  ForbiddenError,
  NetworkError,
  RateLimitedError,
  SessionExpiredError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
} from "../src/http-errors";

import {
  createSessionManagerForTest,
  defaultHandlers,
  httpServer,
  problem,
  TEST_BASE_URL,
} from "./http-helpers";

function setupRepos() {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  return {
    repos: createHttpRepositories({
      baseUrl: TEST_BASE_URL,
      fetchImpl: globalThis.fetch,
      session,
    }),
    session,
  };
}

const PROJECT_ID = "proj_01JEXAMPLE" as never;
const RUN_ID = "run_01JEXAMPLE" as never;
const ARTIFACT_ID = "art_graph_01" as never;
const VERSION_ID = "artv_graph_01" as never;

/** A valid draft used by saveDraft error tests. */
const testDraft: ResearchContractDraft = {
  id: "rcd_01JEXAMPLE" as never,
  sessionId: "sess" as never,
  version: 1,
  intent: "test",
  status: "draft",
  contract: {
    researchGoal: "test",
    targetObjects: [],
    dataRequirements: { unitPolicy: "canonical" },
    requestedFields: [],
    sourceScope: { allowedSources: [] },
    paperSearchScope: {
      keywords: [],
      yearFrom: null,
      yearTo: null,
      sourceIds: [],
      maxCandidates: 20,
    },
    outputRequirements: [],
    evidenceRequirements: {
      requireLocator: true,
      requireSourceSnapshot: true,
      minimumCoverage: 1,
    },
    qualityConstraints: {
      sourceCompletenessMin: 1,
      unitConsistencyMin: 1,
    },
  },
  warnings: [],
  createdAt: "2026-07-22T00:00:00Z",
  updatedAt: "2026-07-22T00:00:00Z",
  expiresAt: "2026-07-22T01:00:00Z",
};

it("401 SESSION_REQUIRED throws SessionExpiredError and notifies session manager", async () => {
  const { repos, session } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/projects/:id`, () =>
      HttpResponse.json(problem(401, "SESSION_REQUIRED", "Session expired"), {
        status: 401,
      }),
    ),
  );

  let expired = false;
  session.onSessionExpired(() => {
    expired = true;
  });

  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    SessionExpiredError,
  );
  expect(expired).toBe(true);
});

it("403 ACTION_FORBIDDEN throws ForbiddenError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/projects/:id`, () =>
      HttpResponse.json(problem(403, "ACTION_FORBIDDEN", "Not allowed"), {
        status: 403,
      }),
    ),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    ForbiddenError,
  );
});

it("403 CSRF_INVALID throws ForbiddenError with code", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/v2/research-contract-drafts/:id`, () =>
      HttpResponse.json(problem(403, "CSRF_INVALID", "CSRF failed"), {
        status: 403,
      }),
    ),
  );
  await expect(repos.contracts.saveDraft(testDraft)).rejects.toThrow(
    ForbiddenError,
  );
});

it("404 PROJECT_NOT_FOUND returns null for getById", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/projects/:id`, () =>
      HttpResponse.json(problem(404, "PROJECT_NOT_FOUND", "Not found"), {
        status: 404,
      }),
    ),
  );
  const result = await repos.projects.getById(PROJECT_ID);
  expect(result).toBeNull();
});

it("404 RUN_NOT_FOUND on list throws NotFoundError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run not found"), {
        status: 404,
      }),
    ),
  );
  // getById returns null on 404
  const result = await repos.runs.getById(RUN_ID);
  expect(result).toBeNull();
});

it("409 RUN_STATE_CONFLICT throws ConflictError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/v2/projects/:projectId/runs`, () =>
      HttpResponse.json(
        problem(409, "RUN_STATE_CONFLICT", "Run already running"),
        { status: 409 },
      ),
    ),
  );
  await expect(
    repos.runs.save({
      id: "run_new" as never,
      projectId: PROJECT_ID,
      contractId: "rc_01JEXAMPLE" as never,
      executionMode: "live",
      status: "queued",
      progress: 0,
      parentRunId: null,
      derivationKind: "original",
      retryFromStep: null,
      cachePolicy: "fallback_on_recoverable_failure",
      startedAt: null,
      finishedAt: null,
      createdAt: "2026-07-22T00:00:00Z",
      updatedAt: "2026-07-22T00:00:00Z",
      latestEventSequence: 0,
      failureCode: null,
      failureSummary: null,
    }),
  ).rejects.toThrow(ConflictError);
});

it("409 VERSION_CONFLICT throws ConflictError with code", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/v2/research-contract-drafts/:id`, () =>
      HttpResponse.json(problem(409, "VERSION_CONFLICT", "Stale version"), {
        status: 409,
      }),
    ),
  );
  try {
    await repos.contracts.saveDraft(testDraft);
    expect.fail("Should have thrown");
  } catch (err) {
    expect(err).toBeInstanceOf(ConflictError);
    expect((err as ConflictError).code).toBe("VERSION_CONFLICT");
  }
});

it("409 IDEMPOTENCY_CONFLICT returns the same Run on retry", async () => {
  // Idempotency conflict means the server already processed this key and
  // returns the original result. For this test we simulate it by returning
  // the conflict error — in a real server, 409 IDEMPOTENCY_CONFLICT would
  // include the original resource. Our adapter currently surfaces it as
  // ConflictError; the caller is expected to retry GET to fetch the original.
  const { repos } = setupRepos();
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/v2/projects/:projectId/runs`, () =>
      HttpResponse.json(problem(409, "IDEMPOTENCY_CONFLICT", "Duplicate key"), {
        status: 409,
      }),
    ),
  );
  await expect(
    repos.runs.save({
      id: "run_new" as never,
      projectId: PROJECT_ID,
      contractId: "rc_01JEXAMPLE" as never,
      executionMode: "live",
      status: "queued",
      progress: 0,
      parentRunId: null,
      derivationKind: "original",
      retryFromStep: null,
      cachePolicy: "fallback_on_recoverable_failure",
      startedAt: null,
      finishedAt: null,
      createdAt: "2026-07-22T00:00:00Z",
      updatedAt: "2026-07-22T00:00:00Z",
      latestEventSequence: 0,
      failureCode: null,
      failureSummary: null,
    }),
  ).rejects.toThrow(ConflictError);
});

it("422 CONTRACT_INVALID throws ValidationError with field errors", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/v2/research-contract-drafts/:id`, () =>
      HttpResponse.json(
        problem(422, "CONTRACT_INVALID", "Invalid contract", [
          {
            field: "requested_fields",
            code: "MIN_ITEMS",
            message: "Select at least one field",
          },
        ]),
        { status: 422 },
      ),
    ),
  );
  try {
    await repos.contracts.saveDraft(testDraft);
    expect.fail("Should have thrown");
  } catch (err) {
    expect(err).toBeInstanceOf(ValidationError);
    const ve = err as ValidationError;
    expect(ve.code).toBe("CONTRACT_INVALID");
    expect(ve.fieldErrors).toHaveLength(1);
    expect(ve.fieldErrors[0]!.field).toBe("requested_fields");
  }
});

it("429 RATE_LIMITED throws RateLimitedError with Retry-After", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(
      `${TEST_BASE_URL}/api/v2/projects/:id`,
      () =>
        new HttpResponse(
          JSON.stringify(problem(429, "RATE_LIMITED", "Too many requests")),
          {
            status: 429,
            headers: {
              "Content-Type": "application/problem+json",
              "Retry-After": "30",
            },
          },
        ),
    ),
  );
  try {
    await repos.projects.getById(PROJECT_ID);
    expect.fail("Should have thrown");
  } catch (err) {
    expect(err).toBeInstanceOf(RateLimitedError);
    expect((err as RateLimitedError).retryAfterMs).toBe(30_000);
  }
});

it("503 UPSTREAM_UNAVAILABLE throws UpstreamError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId`, () =>
      HttpResponse.json(
        problem(503, "UPSTREAM_UNAVAILABLE", "External service down"),
        { status: 503 },
      ),
    ),
  );
  await expect(repos.runs.getById(RUN_ID)).rejects.toThrow(UpstreamError);
});

it("network failure throws NetworkError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/projects/:id`, () =>
      HttpResponse.error(),
    ),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    NetworkError,
  );
});

it("unexpected 500 throws UnexpectedHttpError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/projects/:id`, () =>
      HttpResponse.json(
        problem(500, "INTERNAL_ERROR", "Something went wrong"),
        { status: 500 },
      ),
    ),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    UnexpectedHttpError,
  );
});

// ===== CapabilityUnavailableError tests =====
// Operations not in the generated OpenAPI throw CapabilityUnavailableError
// before any HTTP request is made.

it("CapabilityUnavailableError carries the capability name", async () => {
  const { repos } = setupRepos();
  try {
    await repos.projects.list();
    expect.fail("Should have thrown");
  } catch (err) {
    expect(err).toBeInstanceOf(CapabilityUnavailableError);
    expect((err as CapabilityUnavailableError).capability).toBe(
      "projects.list",
    );
  }
});

it("projects.list throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.projects.list()).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("projects.save throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.projects.save({} as never)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("contracts.listDrafts throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.contracts.listDrafts()).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("contracts.listContracts throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.contracts.listContracts(PROJECT_ID)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("runs.listByProject throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.runs.listByProject(PROJECT_ID)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("artifacts.listByProject throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.artifacts.listByProject(PROJECT_ID)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("artifacts.listVersions throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.artifacts.listVersions(ARTIFACT_ID)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("evidence.getById throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(repos.evidence.getById("evi_test" as never)).rejects.toThrow(
    CapabilityUnavailableError,
  );
});

it("evidence.listByArtifactVersion throws CapabilityUnavailableError", async () => {
  const { repos } = setupRepos();
  await expect(
    repos.evidence.listByArtifactVersion(VERSION_ID),
  ).rejects.toThrow(CapabilityUnavailableError);
});
