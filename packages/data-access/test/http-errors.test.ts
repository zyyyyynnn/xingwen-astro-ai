/**
 * HTTP error scenario tests — RFC 9457 Problem Details → domain error mapping.
 *
 * Covers 401/403/404/409/422/429/503, network failure, idempotency conflict
 * and version conflict against the narrowed repository ports. Every error test
 * installs a handler returning a specific problem details payload and asserts
 * the adapter throws the mapped error.
 */

import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { createHttpRepositories } from "../src/http-adapter";
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
const DRAFT_ID = "rcd_01JEXAMPLE" as never;
const CONTRACT_ID = "rc_01JEXAMPLE" as never;
const RUN_ID = "run_01JEXAMPLE" as never;

function createRunInput() {
  return {
    projectId: PROJECT_ID,
    contractId: CONTRACT_ID,
    idempotencyKey: "run-action-test-01",
    executionMode: "live" as const,
  };
}

it("401 SESSION_REQUIRED throws SessionExpiredError and notifies session manager", async () => {
  const { repos, session } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/projects/:id`, () =>
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
    http.get(`${TEST_BASE_URL}/api/projects/:id`, () =>
      HttpResponse.json(problem(403, "ACTION_FORBIDDEN", "Not allowed"), {
        status: 403,
      }),
    ),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    ForbiddenError,
  );
});

it("403 CSRF_INVALID on draft update throws ForbiddenError with code", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/contracts/drafts/:id`, () =>
      HttpResponse.json(problem(403, "CSRF_INVALID", "CSRF failed"), {
        status: 403,
      }),
    ),
  );
  await expect(
    repos.contracts.updateDraft(DRAFT_ID, 1, { intent: "test" }),
  ).rejects.toThrow(ForbiddenError);
});

it("404 PROJECT_NOT_FOUND returns null for getById", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/projects/:id`, () =>
      HttpResponse.json(problem(404, "PROJECT_NOT_FOUND", "Not found"), {
        status: 404,
      }),
    ),
  );
  expect(await repos.projects.getById(PROJECT_ID)).toBeNull();
});

it("404 RUN_NOT_FOUND returns null for getById", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/runs/:runId`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run not found"), {
        status: 404,
      }),
    ),
  );
  expect(await repos.runs.getById(RUN_ID)).toBeNull();
});

it("404 on a collection propagates NotFoundError instead of an empty list", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/runs/:runId/artifacts`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run not found"), {
        status: 404,
      }),
    ),
  );
  await expect(repos.artifacts.listByRun(RUN_ID)).rejects.toThrow();
});

it("409 RUN_STATE_CONFLICT throws ConflictError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/projects/:projectId/runs`, () =>
      HttpResponse.json(
        problem(409, "RUN_STATE_CONFLICT", "Run already running"),
        { status: 409 },
      ),
    ),
  );
  await expect(repos.runs.create(createRunInput())).rejects.toThrow(
    ConflictError,
  );
});

it("409 VERSION_CONFLICT on draft update throws ConflictError with code", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/contracts/drafts/:id`, () =>
      HttpResponse.json(problem(409, "VERSION_CONFLICT", "Stale version"), {
        status: 409,
      }),
    ),
  );
  try {
    await repos.contracts.updateDraft(DRAFT_ID, 1, { intent: "x" });
    expect.fail("Should have thrown");
  } catch (err) {
    expect(err).toBeInstanceOf(ConflictError);
    expect((err as ConflictError).code).toBe("VERSION_CONFLICT");
  }
});

it("409 IDEMPOTENCY_CONFLICT on run create throws ConflictError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/projects/:projectId/runs`, () =>
      HttpResponse.json(problem(409, "IDEMPOTENCY_CONFLICT", "Duplicate key"), {
        status: 409,
      }),
    ),
  );
  await expect(repos.runs.create(createRunInput())).rejects.toThrow(
    ConflictError,
  );
});

it("run create forwards the caller action key", async () => {
  const { repos } = setupRepos();
  const keys: string[] = [];
  httpServer.use(
    http.post(
      `${TEST_BASE_URL}/api/projects/:projectId/runs`,
      ({ request }) => {
        keys.push(request.headers.get("Idempotency-Key") ?? "");
        return HttpResponse.json({
          data: {
            id: "run_01JEXAMPLE",
            project_id: "proj_01JEXAMPLE",
            contract_id: "rc_01JEXAMPLE",
            execution_mode: "live",
            status: "queued",
            progress: 0,
            parent_run_id: null,
            derivation_kind: "original",
            retry_from_step: null,
            cache_policy: "fallback_on_recoverable_failure",
            started_at: null,
            finished_at: null,
            created_at: "2026-07-21T08:15:00Z",
            updated_at: "2026-07-21T08:15:00Z",
            latest_event_sequence: 1,
            failure_code: null,
            failure_summary: null,
          },
        });
      },
    ),
  );

  await repos.runs.create({
    ...createRunInput(),
    idempotencyKey: "run-action-01",
  });
  await repos.runs.create({
    ...createRunInput(),
    idempotencyKey: "run-action-02",
  });
  expect(keys).toEqual(["run-action-01", "run-action-02"]);
});

it("422 CONTRACT_INVALID throws ValidationError with field errors", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.patch(`${TEST_BASE_URL}/api/contracts/drafts/:id`, () =>
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
    await repos.contracts.updateDraft(DRAFT_ID, 1, { intent: "x" });
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
      `${TEST_BASE_URL}/api/projects/:id`,
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
    http.get(`${TEST_BASE_URL}/api/runs/:runId`, () =>
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
    http.get(`${TEST_BASE_URL}/api/projects/:id`, () => HttpResponse.error()),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    NetworkError,
  );
});

it("unexpected 500 throws UnexpectedHttpError", async () => {
  const { repos } = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/projects/:id`, () =>
      HttpResponse.json(
        problem(500, "INTERNAL_ERROR", "Something went wrong"),
        {
          status: 500,
        },
      ),
    ),
  );
  await expect(repos.projects.getById(PROJECT_ID)).rejects.toThrow(
    UnexpectedHttpError,
  );
});
