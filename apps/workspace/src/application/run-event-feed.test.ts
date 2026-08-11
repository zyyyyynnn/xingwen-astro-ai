import { QueryClient } from "@tanstack/react-query";
import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import type { RepositorySet, RunRepository } from "@xingwen/data-access/ports";
import { asEntityId, type ResearchRun, type RunEvent } from "@xingwen/domain";
import { researchAdapter } from "@xingwen/research-adapter";
import { describe, expect, it, vi } from "vitest";

import { createWorkspaceQueries } from "./queries";
import { workspaceQueryKeys } from "./query-keys";
import { createRunEventFeed } from "./run-event-feed";

const runId = asEntityId("run-feed-test");

function runSnapshot(
  status: ResearchRun["status"] = "planning",
  latestEventSequence = 3,
): ResearchRun {
  return {
    id: runId,
    projectId: asEntityId("project-feed-test"),
    contractId: asEntityId("contract-feed-test"),
    executionMode: "live",
    status,
    progress: status === "completed" ? 100 : 10,
    parentRunId: null,
    derivationKind: "original",
    retryFromStep: null,
    cachePolicy: "disabled",
    startedAt: "2026-08-11T00:00:00Z",
    finishedAt: status === "completed" ? "2026-08-11T00:02:00Z" : null,
    createdAt: "2026-08-11T00:00:00Z",
    updatedAt: "2026-08-11T00:01:00Z",
    latestEventSequence,
    failureCode: null,
    failureSummary: null,
  };
}

function event(sequence: number): RunEvent {
  return {
    runId,
    sequence,
    eventType: asEntityId(sequence === 3 ? "run.completed" : "step.progress"),
    stepKey: asEntityId("collect"),
    progress: sequence * 10,
    publicMessage: `Public event ${String(sequence)}`,
    artifactVersionIds: [],
    occurredAt: `2026-08-11T00:00:0${String(sequence)}Z`,
  };
}

function runRepository(): RunRepository {
  return {
    getById: vi.fn(async () => runSnapshot()),
    create: vi.fn(),
    listEvents: vi.fn(),
    recoverEvents: vi.fn(async () => ({
      events: [event(1), event(2), event(2), event(3)],
      nextCursor: "3",
      latestSequence: 3,
    })),
  };
}

function makeFeed(repository = runRepository()) {
  const queryClient = new QueryClient();
  const fixtureRepositories = createFixtureRepositories(
    exoplanetHostStarFixture,
  );
  const queries = createWorkspaceQueries({
    repositories: {
      ...fixtureRepositories,
      runs: repository,
    } satisfies RepositorySet,
    researchAdapter,
  });
  const feed = createRunEventFeed({
    runId,
    runs: repository,
    researchAdapter,
    queryClient,
    runQuery: queries.run,
  });
  return { feed, repository, queryClient };
}

describe("RunEventFeed", () => {
  it("loads the authoritative snapshot first, then dedupes and orders events", async () => {
    const { feed, repository, queryClient } = makeFeed();
    const calls: string[] = [];
    vi.mocked(repository.getById).mockImplementation(async () => {
      calls.push("snapshot");
      return runSnapshot();
    });
    vi.mocked(repository.recoverEvents).mockImplementation(async () => {
      calls.push("events");
      return {
        events: [event(3), event(1), event(2), event(2)],
        nextCursor: "3",
        latestSequence: 3,
      };
    });

    await feed.syncNow();

    expect(calls).toEqual(["snapshot", "events"]);
    expect(
      queryClient
        .getQueryData<{ events: readonly { id: string }[] }>(
          workspaceQueryKeys.runEvents(runId),
        )
        ?.events.map((item) => item.id),
    ).toEqual([`${runId}:1`, `${runId}:2`, `${runId}:3`]);
    feed.stop();
  });

  it("restarts snapshot-first recovery when an incremental gap is observed", async () => {
    const { feed, repository } = makeFeed();
    vi.mocked(repository.recoverEvents)
      .mockResolvedValueOnce({
        events: [event(1)],
        nextCursor: "1",
        latestSequence: 3,
      })
      .mockResolvedValueOnce({
        events: [event(3)],
        nextCursor: "3",
        latestSequence: 3,
      })
      .mockResolvedValueOnce({
        events: [event(1), event(2), event(3)],
        nextCursor: "3",
        latestSequence: 3,
      });

    await feed.syncNow();
    await feed.syncNow();

    expect(repository.recoverEvents).toHaveBeenLastCalledWith(runId, null);
    expect(feed.getSnapshot().lastSequence).toBe(3);
    feed.stop();
  });

  it("stops at a terminal snapshot only after its event tail is complete", async () => {
    const repository = runRepository();
    vi.mocked(repository.getById).mockResolvedValue(
      runSnapshot("completed", 3),
    );
    const { feed } = makeFeed(repository);

    await feed.syncNow();

    expect(feed.getSnapshot().status).toBe("stopped");
    expect(feed.getSnapshot().lastSequence).toBe(3);
  });

  it("backs off within bounds and supports pause/resume without losing cursor", async () => {
    const { feed, repository } = makeFeed();
    vi.mocked(repository.getById)
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(runSnapshot());

    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(2_000);
    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(5_000);
    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(1_000);

    feed.pause();
    expect(feed.getSnapshot().status).toBe("paused");
    const cursor = feed.getSnapshot().cursor;
    feed.resume();
    expect(feed.getSnapshot()).toMatchObject({ status: "running", cursor });
    feed.stop();
  });
});
