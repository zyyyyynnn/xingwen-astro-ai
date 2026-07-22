/**
 * Shared test helpers for HTTP adapter tests.
 *
 * Builds MSW handlers from fixture DTOs so the HTTP adapter receives the same
 * payloads the fixture adapter validates internally — this is the structural
 * basis for the Fixture/HTTP consistency test.
 */

import { http, HttpResponse } from "msw";

import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";

const BASE_URL = "http://test.local";

function envelope<T>(data: T): { data: T; meta: Record<string, unknown> } {
  return {
    data,
    meta: {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:00:00Z",
    },
  };
}

/** Default handlers serving the exoplanet-host-star fixture over HTTP. */
export const defaultHandlers = [
  http.get(`${BASE_URL}/api/v2/projects/:projectId`, ({ params }) => {
    const project = exoplanetHostStarFixture.data.projects.find(
      (p) => p.id === params.projectId,
    );
    if (!project) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(project));
  }),
  http.get(
    `${BASE_URL}/api/v2/research-contract-drafts/:draftId`,
    ({ params }) => {
      const draft = exoplanetHostStarFixture.data.contractDrafts.find(
        (d) => d.id === params.draftId,
      );
      if (!draft) return new HttpResponse(null, { status: 404 });
      return HttpResponse.json(envelope(draft));
    },
  ),
  http.patch(`${BASE_URL}/api/v2/research-contract-drafts/:draftId`, async () =>
    HttpResponse.json(
      envelope(exoplanetHostStarFixture.data.contractDrafts[0]),
    ),
  ),
  http.get(
    `${BASE_URL}/api/v2/research-contracts/:contractId`,
    ({ params }) => {
      const contract = exoplanetHostStarFixture.data.contracts.find(
        (c) => c.id === params.contractId,
      );
      if (!contract) return new HttpResponse(null, { status: 404 });
      return HttpResponse.json(envelope(contract));
    },
  ),
  http.post(
    `${BASE_URL}/api/v2/projects/:projectId/contracts`,
    async ({ request }) => {
      const body = (await request.json()) as {
        draft_id: string;
        expected_draft_version: number;
      };
      const draft = exoplanetHostStarFixture.data.contractDrafts.find(
        (d) => d.id === body.draft_id,
      );
      if (!draft) return new HttpResponse(null, { status: 404 });
      const contract = exoplanetHostStarFixture.data.contracts.find(
        (c) => c.created_from_draft_id === draft.id,
      );
      if (!contract) return new HttpResponse(null, { status: 404 });
      return HttpResponse.json(envelope(contract), { status: 201 });
    },
  ),
  http.get(`${BASE_URL}/api/v2/runs/:runId`, ({ params }) => {
    const run = exoplanetHostStarFixture.data.runs.find(
      (r) => r.id === params.runId,
    );
    if (!run) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(run));
  }),
  http.get(`${BASE_URL}/api/v2/runs/:runId/events`, ({ params, request }) => {
    const events = exoplanetHostStarFixture.data.runEvents.filter(
      (e) => e.run_id === params.runId,
    );
    // Honour cursor-based pagination for the recovery tests. Cursor is an
    // opaque string of the form `seq:<N>` meaning "resume after sequence N".
    // When no cursor is supplied, return the first page (limit 5).
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor");
    const limitParam = url.searchParams.get("limit");
    const limit = limitParam ? Number(limitParam) : 100;
    let slice = events;
    if (cursor) {
      const match = /^seq:(\d+)$/.exec(cursor);
      if (match) {
        const after = Number(match[1]);
        slice = events.filter((e) => e.sequence > after);
      }
    }
    const page = slice.slice(0, limit);
    const hasMore = slice.length > limit;
    const nextCursor =
      hasMore && page.length > 0
        ? `seq:${page[page.length - 1]!.sequence}`
        : null;
    return HttpResponse.json({
      data: page,
      page: { next_cursor: nextCursor, has_more: hasMore, limit },
      meta: {
        request_id: "req_test",
        schema_version: "2.0.0",
        generated_at: "2026-07-21T08:00:00Z",
      },
    });
  }),
  http.get(`${BASE_URL}/api/v2/artifacts/:artifactId`, ({ params }) => {
    const artifact = exoplanetHostStarFixture.data.artifacts.find(
      (a) => a.id === params.artifactId,
    );
    if (!artifact) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(artifact));
  }),
  http.get(`${BASE_URL}/api/v2/artifact-versions/:versionId`, ({ params }) => {
    const version = exoplanetHostStarFixture.data.artifactVersions.find(
      (v) => v.id === params.versionId,
    );
    if (!version) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(version));
  }),
  http.post(`${BASE_URL}/api/v2/sessions`, () =>
    HttpResponse.json(
      envelope({
        id: "sess_01JEXAMPLE",
        expires_at: "2026-07-21T09:00:00Z",
        quota: {
          runs_per_day: 50,
          shares_per_hour: 20,
          feedbacks_per_hour: 30,
        },
        csrf_token: "csrf_test_token",
      }),
    ),
  ),
  http.delete(`${BASE_URL}/api/v2/sessions`, ({ request }) => {
    const csrf = request.headers.get("X-CSRF-Token");
    if (csrf !== "csrf_test_token") {
      return HttpResponse.json(
        problem(403, "CSRF_INVALID", "Missing or invalid CSRF token"),
        { status: 403 },
      );
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.post(`${BASE_URL}/api/v2/projects/:projectId/runs`, ({ request }) => {
    void request;
    return HttpResponse.json(envelope(exoplanetHostStarFixture.data.runs[0]), {
      status: 201,
    });
  }),
];

/** Build a Problem Details response body. */
export function problem(
  status: number,
  code: string,
  detail: string,
  errors?: readonly { field: string; code: string; message: string }[],
): {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  errors?: readonly { field: string; code: string; message: string }[];
} {
  return {
    type: `https://xingwen.example/errors/${code.toLowerCase()}`,
    title: detail,
    status,
    detail,
    code,
    errors,
  };
}

/** Base URL used by all HTTP adapter tests. */
export const TEST_BASE_URL = BASE_URL;

/** Create an HTTP adapter config pointing at the MSW server. */
export function createTestHttpConfig(
  session: ReturnType<typeof createSessionManagerForTest>,
) {
  return {
    baseUrl: BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  };
}

/** Re-export to avoid circular type imports in test files. */
import { createSessionManager } from "../src/session";
export function createSessionManagerForTest() {
  return createSessionManager({
    baseUrl: BASE_URL,
    fetchImpl: globalThis.fetch,
  });
}

/** Re-export the MSW server singleton so tests can install handlers. */
export { httpServer } from "./msw-server";
