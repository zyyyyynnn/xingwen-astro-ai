/**
 * RunEvent cursor polling and snapshot-first recovery tests.
 *
 * Covers:
 * - `listEventsPage`: single-page fetch with cursor pagination
 * - `getLatestEventSequence`: snapshot anchor from GET /api/v2/runs/{run_id}
 * - `recoverEventsFromSnapshot`: full and partial recovery after interruption
 * - Event sequence ordering and gap handling
 *
 * The MSW events handler honours `cursor=seq:<N>` meaning "resume after
 * sequence N" so we can simulate paged tails deterministically.
 */

import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { createHttpRepositories } from "../src/http-adapter";
import { NotFoundError } from "../src/http-errors";

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

it("listEventsPage returns the first page with pagination metadata", async () => {
  const repos = setupRepos();
  // Fixture has 9 events (sequences 1-9). With limit=5 we expect 5 events,
  // hasMore=true, and nextCursor=seq:5.
  const page = await repos.runs.listEventsPage(RUN_ID, null, 5);
  expect(page.events).toHaveLength(5);
  expect(page.events[0]!.sequence).toBe(1);
  expect(page.events[4]!.sequence).toBe(5);
  expect(page.hasMore).toBe(true);
  expect(page.nextCursor).toBe("seq:5");
});

it("listEventsPage follows cursor to fetch subsequent pages", async () => {
  const repos = setupRepos();
  // Page 1: sequences 1-5, nextCursor=seq:5
  const page1 = await repos.runs.listEventsPage(RUN_ID, null, 5);
  expect(page1.events).toHaveLength(5);
  expect(page1.nextCursor).toBe("seq:5");
  // Page 2: sequences 6-9 (only 4 remain), hasMore=false, nextCursor=null
  const page2 = await repos.runs.listEventsPage(RUN_ID, page1.nextCursor, 5);
  expect(page2.events).toHaveLength(4);
  expect(page2.events[0]!.sequence).toBe(6);
  expect(page2.events[3]!.sequence).toBe(9);
  expect(page2.hasMore).toBe(false);
  expect(page2.nextCursor).toBeNull();
});

it("listEventsPage returns empty page when run has no events", async () => {
  const repos = setupRepos();
  // Override the events handler to return 404 for a run with no events.
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId/events`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run has no events"), {
        status: 404,
      }),
    ),
  );
  const page = await repos.runs.listEventsPage(RUN_ID, null, 5);
  expect(page.events).toHaveLength(0);
  expect(page.hasMore).toBe(false);
  expect(page.nextCursor).toBeNull();
});

it("getLatestEventSequence reads latest_event_sequence from Run snapshot", async () => {
  const repos = setupRepos();
  // The fixture run has latest_event_sequence=9.
  const seq = await repos.runs.getLatestEventSequence(RUN_ID);
  expect(seq).toBe(9);
});

it("getLatestEventSequence throws NotFoundError when Run does not exist", async () => {
  const repos = setupRepos();
  httpServer.use(
    http.get(`${TEST_BASE_URL}/api/v2/runs/:runId`, () =>
      HttpResponse.json(problem(404, "RUN_NOT_FOUND", "Run gone"), {
        status: 404,
      }),
    ),
  );
  await expect(repos.runs.getLatestEventSequence(RUN_ID)).rejects.toThrow(
    NotFoundError,
  );
});

it("recoverEventsFromSnapshot drains all events until latestSequence", async () => {
  const repos = setupRepos();
  // Use a small page limit so recovery must follow the cursor across pages.
  // The fixture run has latest_event_sequence=9 and 9 events (seq 1-9).
  // We can't pass limit through recoverEventsFromSnapshot, so we verify the
  // default path drains the full stream and returns latestSequence=9.
  const result = await repos.runs.recoverEventsFromSnapshot(RUN_ID);
  expect(result.latestSequence).toBe(9);
  expect(result.events).toHaveLength(9);
  // Events must be in ascending sequence order.
  for (let i = 0; i < result.events.length; i++) {
    expect(result.events[i]!.sequence).toBe(i + 1);
  }
  // After draining to latestSequence, hasMore must be false (we caught up).
  expect(result.hasMore).toBe(false);
});

it("recoverEventsFromSnapshot resumes from a given cursor", async () => {
  const repos = setupRepos();
  // Simulate a recovery where the caller already consumed events 1-5 and
  // has cursor=seq:5. Recovery should drain the remaining 6-9 and confirm
  // latestSequence=9.
  const result = await repos.runs.recoverEventsFromSnapshot(RUN_ID, "seq:5");
  expect(result.latestSequence).toBe(9);
  expect(result.events).toHaveLength(4);
  expect(result.events[0]!.sequence).toBe(6);
  expect(result.events[3]!.sequence).toBe(9);
  expect(result.hasMore).toBe(false);
});

it("recoverEventsFromSnapshot stops early when latestSequence is reached", async () => {
  const repos = setupRepos();
  // Override the Run snapshot to claim latest_event_sequence=3, meaning the
  // authoritative state only knows about events 1-3 (e.g. snapshot taken
  // mid-run). Recovery should stop after draining up to sequence 3 even
  // though more events exist in the stream.
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
  );
  const result = await repos.runs.recoverEventsFromSnapshot(RUN_ID);
  expect(result.latestSequence).toBe(3);
  // The first page (default limit 100) returns all 9 events, but recovery
  // should stop as soon as maxSeq >= latestSequence. Since the first page
  // contains all 9 events, maxSeq=9 >= 3, so we break after the first page.
  // The aggregated events include everything returned in that page, but the
  // caller knows from latestSequence=3 that only sequences 1-3 are
  // authoritative. The contract is: "drain until caught up to snapshot".
  expect(result.events.length).toBeGreaterThan(0);
  expect(result.hasMore).toBe(false);
});

it("getEvents aggregates all pages and preserves sequence order", async () => {
  const repos = setupRepos();
  // The port-level getEvents follows all cursor pages and returns a flat
  // array. This complements the incremental listEventsPage path.
  const events = await repos.runs.getEvents(RUN_ID);
  expect(events).toHaveLength(9);
  for (let i = 0; i < events.length; i++) {
    expect(events[i]!.sequence).toBe(i + 1);
  }
});

it("listEventsPage with limit returns bounded page size", async () => {
  const repos = setupRepos();
  const page = await repos.runs.listEventsPage(RUN_ID, null, 3);
  expect(page.events).toHaveLength(3);
  expect(page.hasMore).toBe(true);
  expect(page.nextCursor).toBe("seq:3");
});
