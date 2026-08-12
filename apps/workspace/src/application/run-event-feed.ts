import type { QueryClient } from "@tanstack/react-query";
import type { RunRepository } from "@xingwen/data-access/ports";
import type { DomainEntityId, RunEvent } from "@xingwen/domain";
import type {
  ResearchAdapter,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";
import {
  EMPTY_RUN_EVENT_FEED,
  type RunEventFeedCache,
  type WorkspaceQueries,
} from "./queries";

const NORMAL_DELAY_MS = 1_000;
const FIRST_FAILURE_DELAY_MS = 2_000;
const MAX_FAILURE_DELAY_MS = 5_000;

export interface RunEventFeedSnapshot extends RunEventFeedCache {
  readonly status: "idle" | "running" | "paused" | "stopped";
  readonly nextDelayMs: number;
}

interface VisibilitySource {
  readonly hidden: boolean;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

interface RunEventFeedDependencies {
  readonly projectId: DomainEntityId;
  readonly runId: DomainEntityId;
  readonly runs: RunRepository;
  readonly researchAdapter: ResearchAdapter;
  readonly queryClient: QueryClient;
  readonly runQuery: WorkspaceQueries["run"];
  readonly visibilitySource?: VisibilitySource;
}

function emptyCache(): RunEventFeedCache {
  return EMPTY_RUN_EVENT_FEED;
}

function sortedUniqueEvents(events: readonly RunEvent[]): readonly RunEvent[] {
  const bySequence = new Map<number, RunEvent>();
  for (const event of events) {
    if (!bySequence.has(event.sequence)) bySequence.set(event.sequence, event);
  }
  return [...bySequence.values()].sort(
    (left, right) => left.sequence - right.sequence,
  );
}

export function createRunEventFeed({
  projectId,
  runId,
  runs,
  researchAdapter,
  queryClient,
  runQuery,
  visibilitySource,
}: RunEventFeedDependencies) {
  let cache =
    queryClient.getQueryData<RunEventFeedCache>(
      workspaceQueryKeys.runEvents(projectId, runId),
    ) ?? emptyCache();
  let status: RunEventFeedSnapshot["status"] = "idle";
  let failureCount = 0;
  let nextDelayMs = NORMAL_DELAY_MS;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let syncing: Promise<void> | null = null;

  const writeCache = (next: RunEventFeedCache) => {
    cache = next;
    queryClient.setQueryData(
      workspaceQueryKeys.runEvents(projectId, runId),
      next,
    );
  };

  const cancelTimer = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };

  const schedule = () => {
    cancelTimer();
    if (status !== "running") return;
    timer = setTimeout(() => void syncNow(), nextDelayMs);
  };

  const recover = async (
    snapshot: ResearchRunViewModel,
    fromCursor: string | null,
    previous: RunEventFeedCache,
  ): Promise<{ readonly cache: RunEventFeedCache; readonly gap: boolean }> => {
    const recovery = await runs.recoverEvents(runId, fromCursor);
    const events = sortedUniqueEvents(recovery.events).filter(
      (event) => event.sequence > previous.lastSequence,
    );
    const first = events[0]?.sequence;
    const expected = previous.lastSequence + 1;
    const gap = first !== undefined && first !== expected;
    if (gap) return { cache: previous, gap: true };

    const allEvents = [
      ...previous.events,
      ...events.map(researchAdapter.toActivityPresentationEvent),
    ];
    const lastSequence = events.at(-1)?.sequence ?? previous.lastSequence;
    return {
      gap: false,
      cache: {
        events: allEvents,
        cursor: recovery.nextCursor,
        lastSequence,
        latestSequence: snapshot.latestEventSequence,
        error: null,
      },
    };
  };

  const performSync = async () => {
    if (status === "paused" || status === "stopped") return;
    status = "running";
    try {
      let snapshot = await queryClient.fetchQuery({
        ...runQuery(projectId, runId),
        staleTime: 0,
      });
      let recovered = await recover(snapshot, cache.cursor, cache);
      if (recovered.gap) {
        writeCache(emptyCache());
        snapshot = await queryClient.fetchQuery({
          ...runQuery(projectId, runId),
          staleTime: 0,
        });
        recovered = await recover(snapshot, null, emptyCache());
        if (recovered.gap) {
          throw new Error(
            "Run event recovery returned a non-contiguous sequence.",
          );
        }
      }
      const previousLastSequence = cache.lastSequence;
      writeCache(recovered.cache);
      if (recovered.cache.lastSequence > previousLastSequence) {
        await queryClient.invalidateQueries({
          queryKey: workspaceQueryKeys.runSteps(projectId, runId),
        });
      }
      failureCount = 0;
      nextDelayMs = NORMAL_DELAY_MS;
      if (
        snapshot.isTerminal &&
        recovered.cache.lastSequence >= snapshot.latestEventSequence
      ) {
        status = "stopped";
        cancelTimer();
        return;
      }
    } catch (reason) {
      failureCount += 1;
      nextDelayMs =
        failureCount === 1 ? FIRST_FAILURE_DELAY_MS : MAX_FAILURE_DELAY_MS;
      writeCache({ ...cache, error: reason });
    }
    schedule();
  };

  const syncNow = async () => {
    if (syncing) return syncing;
    syncing = performSync().finally(() => {
      syncing = null;
    });
    return syncing;
  };

  const handleVisibilityChange = () => {
    if (!visibilitySource) return;
    if (visibilitySource.hidden) {
      api.pause();
    } else {
      api.resume();
    }
  };

  const api = Object.freeze({
    start() {
      if (status === "stopped") return;
      status = visibilitySource?.hidden ? "paused" : "running";
      visibilitySource?.addEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
      if (status === "running") void syncNow();
    },
    syncNow,
    pause() {
      if (status === "stopped") return;
      status = "paused";
      cancelTimer();
    },
    resume() {
      if (status === "stopped") return;
      status = "running";
      void syncNow();
    },
    stop() {
      status = "stopped";
      cancelTimer();
      visibilitySource?.removeEventListener(
        "visibilitychange",
        handleVisibilityChange,
      );
    },
    getSnapshot(): RunEventFeedSnapshot {
      return { ...cache, status, nextDelayMs };
    },
  });

  return api;
}

export type RunEventFeed = ReturnType<typeof createRunEventFeed>;
