/**
 * RunEvent listing and snapshot-first recovery tests.
 *
 * Covers the narrowed Run port:
 * - `listEvents`: aggregates every page in ascending order, and propagates a
 *   404 (parent run missing) rather than silently returning an empty list.
 * - `recoverEvents`: reads the authoritative `latest_event_sequence` from the
 *   Run snapshot and returns only events up to it — events beyond the snapshot
 *   sequence are excluded even when the stream still holds them.
 *
 * The MSW events handler honours the API's numeric sequence cursor.
 */

import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { createHttpRepositories } from "../src/http-adapter";
import { NotFoundError } from "../src/http-errors";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";

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
  return createHttpRepositories({
    baseUrl: TEST_BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  });
}

const RUN_ID = "run_01JEXAMPLE" as never;

it("listEvents aggregates all pages and preserves sequence order", async () => {
  const repos = setupRepos();
  const events = await repos.runs.listEvents(RUN_ID);
  expect(events).toHaveLength(9);
  for (let i = 0; i < events.length; i++) {
    expect(events[i]!.sequence).toBe(i + 1);
  }
});

it("listEvents applies each cursor to the base path without accumulating query parameters", async () => {
  const repos = setupRepos();
  const cursorValues: string[][] = [];
  let pageIndex = 0;
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId/events`, ({ request }) => {
      cursorValues.push(new URL(request.url).searchParams.getAll("cursor"));
      const event = exoplanetHostStarFixture.data.runEvents[pageIndex]!;
      pageIndex += 1;
      const hasMore = pageIndex < 3;
      return HttpResponse.json({
        data: [event],
        page: {
          next_cursor: hasMore ? String(event.sequence) : null,
          has_more: hasMore,
          limit: 1,
        },
      });
    }),
  );

  const events = await repos.runs.listEvents(RUN_ID);
  expect(events.map((event) => event.sequence)).toEqual([1, 2, 3]);
  expect(cursorValues).toEqual([[], ["1"], ["2"]]);
});

it("listEvents propagates NotFoundError when the run is missing", async () => {
  const repos = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId/events`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run not found"), {
        status: 404,
      }),
    ),
  );
  await expect(repos.runs.listEvents(RUN_ID)).rejects.toThrow(NotFoundError);
});

it("recoverEvents drains events up to the authoritative latest sequence", async () => {
  const repos = setupRepos();
  const result = await repos.runs.recoverEvents(RUN_ID);
  expect(result.latestSequence).toBe(9);
  expect(result.events).toHaveLength(9);
  for (let i = 0; i < result.events.length; i++) {
    expect(result.events[i]!.sequence).toBe(i + 1);
  }
});

it("recoverEvents resumes from a given cursor", async () => {
  const repos = setupRepos();
  const result = await repos.runs.recoverEvents(RUN_ID, "5");
  expect(result.latestSequence).toBe(9);
  expect(result.events.map((e) => e.sequence)).toEqual([6, 7, 8, 9]);
});

it("recoverEvents excludes events beyond the snapshot sequence", async () => {
  const repos = setupRepos();
  // The snapshot only knows about events 1-3, though the stream holds 9.
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId`, () =>
      HttpResponse.json({
        data: {
          id: "run_01JEXAMPLE",
          project_id: "proj_01JEXAMPLE",
          contract_id: "rc_01JEXAMPLE",
          execution_mode: "demo_replay",
          status: "cleaning_data",
          progress: 25,
          parent_run_id: null,
          derivation_kind: "original",
          retry_from_step: null,
          cache_policy: "fallback_on_recoverable_failure",
          started_at: "2026-07-21T08:16:00Z",
          finished_at: null,
          created_at: "2026-07-21T08:15:00Z",
          updated_at: "2026-07-21T08:21:00Z",
          latest_event_sequence: 3,
          failure_code: null,
          failure_summary: null,
        },
        meta: {
          request_id: "req_test",
          schema_version: "2.0.0",
          generated_at: "2026-07-21T08:21:00Z",
        },
      }),
    ),
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId/events`, () =>
      HttpResponse.json({
        data: exoplanetHostStarFixture.data.runEvents.slice(0, 5),
        page: { next_cursor: "5", has_more: true, limit: 5 },
      }),
    ),
  );
  const result = await repos.runs.recoverEvents(RUN_ID);
  expect(result.latestSequence).toBe(3);
  // Only the authoritative tail (sequences 1-3) is returned.
  expect(result.events.map((e) => e.sequence)).toEqual([1, 2, 3]);
  expect(result.nextCursor).toBe("3");
});

it("recoverEvents throws NotFoundError when the run does not exist", async () => {
  const repos = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run gone"), {
        status: 404,
      }),
    ),
  );
  await expect(repos.runs.recoverEvents(RUN_ID)).rejects.toThrow(NotFoundError);
});
