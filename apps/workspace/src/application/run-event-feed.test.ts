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
const projectId = asEntityId("project-feed-test");

function runSnapshot(
  status: ResearchRun["status"] = "planning",
  latestEventSequence = 3,
): ResearchRun {
  return {
    id: runId,
    projectId,
    contractId: asEntityId("contract-feed-test"),
    executionMode: "live",
    status,
    progress: status === "completed" ? 100 : 10,
    revision: 1,
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

function event(sequence: number, overrides: Partial<RunEvent> = {}): RunEvent {
  return {
    runId,
    sequence,
    activityId: sequence === 3 ? `run:${runId}` : "tool:paper-search",
    activityKind: sequence === 3 ? "completion" : "tool",
    activityPhase: sequence === 1 ? "running" : "completed",
    activityName: sequence === 3 ? "研究任务" : "检索研究论文",
    stepKey: sequence === 3 ? null : asEntityId("searching_papers"),
    progress: sequence * 10,
    content: `研究事件 ${String(sequence)}`,
    details: sequence === 3 ? {} : { tool_kind: "search" },
    artifactVersionIds: [],
    occurredAt: `2026-08-11T00:00:0${String(sequence)}Z`,
    ...overrides,
  };
}

function runRepository(): RunRepository {
  return {
    getById: vi.fn(async () => runSnapshot()),
    create: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
    getCheckpoint: vi.fn(async () => null),
    submitCheckpointDecision: vi.fn(),
    listEvents: vi.fn(),
    recoverEvents: vi.fn(async () => ({
      events: [event(1), event(2), event(2), event(3)],
      nextCursor: "3",
      latestSequence: 3,
    })),
    listSteps: vi.fn(async () => []),
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
    projectId,
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
          workspaceQueryKeys.runEvents(projectId, runId),
        )
        ?.events.map((item) => item.id),
    ).toEqual(["tool:paper-search", `run:${runId}`]);
    expect(
      queryClient.getQueryData<{
        events: readonly { updates: readonly unknown[] }[];
      }>(workspaceQueryKeys.runEvents(projectId, runId))?.events[0]?.updates,
    ).toHaveLength(2);
    feed.stop();
  });

  it("refreshes frozen RunStep projections only when the event cursor advances", async () => {
    const { feed, queryClient } = makeFeed();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await feed.syncNow();
    await feed.syncNow();

    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.runSteps(projectId, runId),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.thread(projectId),
    });
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

  it("refreshes Thread and published results as soon as a live batch arrives", async () => {
    const repository = runRepository();
    vi.mocked(repository.getById).mockResolvedValue(runSnapshot("planning", 2));
    vi.mocked(repository.recoverEvents).mockResolvedValue({
      events: [
        event(1),
        event(2, { artifactVersionIds: [asEntityId("artifact-version-1")] }),
      ],
      nextCursor: "2",
      latestSequence: 2,
    });
    const { feed, queryClient } = makeFeed(repository);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await feed.syncNow();

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.thread(projectId),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.artifactsByRun(projectId, runId),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.artifactVersion(
        projectId,
        asEntityId("artifact-version-1"),
      ),
    });
    feed.stop();
  });

  it("stops at a terminal snapshot only after its event tail is complete", async () => {
    const repository = runRepository();
    vi.mocked(repository.getById).mockResolvedValue(
      runSnapshot("completed", 3),
    );
    const { feed, queryClient } = makeFeed(repository);
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await feed.syncNow();

    expect(feed.getSnapshot().status).toBe("stopped");
    expect(feed.getSnapshot().lastSequence).toBe(3);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: workspaceQueryKeys.artifactsByRun(projectId, runId),
    });
  });

  it("backs off within bounds and supports pause/resume without losing cursor", async () => {
    const { feed, repository, queryClient } = makeFeed();
    vi.mocked(repository.getById)
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(runSnapshot());

    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(2_000);
    expect(
      queryClient.getQueryData<{ error: unknown }>(
        workspaceQueryKeys.runEvents(projectId, runId),
      )?.error,
    ).toBeInstanceOf(Error);
    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(5_000);
    await feed.syncNow();
    expect(feed.getSnapshot().nextDelayMs).toBe(1_000);
    expect(
      queryClient.getQueryData<{ error: unknown }>(
        workspaceQueryKeys.runEvents(projectId, runId),
      )?.error,
    ).toBeNull();

    feed.pause();
    expect(feed.getSnapshot().status).toBe("paused");
    const cursor = feed.getSnapshot().cursor;
    feed.resume();
    expect(feed.getSnapshot()).toMatchObject({ status: "running", cursor });
    feed.stop();
  });

  it("resumes recovery from the cursor stored by the previous sync", async () => {
    const { feed, repository } = makeFeed();
    vi.mocked(repository.recoverEvents)
      .mockResolvedValueOnce({
        events: [event(1)],
        nextCursor: "cursor-1",
        latestSequence: 1,
      })
      .mockResolvedValueOnce({
        events: [event(2), event(3)],
        nextCursor: "cursor-3",
        latestSequence: 3,
      });

    await feed.syncNow();
    await feed.syncNow();

    expect(repository.recoverEvents).toHaveBeenNthCalledWith(
      2,
      runId,
      "cursor-1",
    );
    expect(feed.getSnapshot()).toMatchObject({
      cursor: "cursor-3",
      lastSequence: 3,
    });
    feed.stop();
  });
});
