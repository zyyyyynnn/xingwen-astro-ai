import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { expect, type Page } from "@playwright/test";

const execute = promisify(execFile);

interface RuntimeSnapshot {
  qwen_route: string;
  run: {
    id: string;
    status: string;
    lease_owner: string | null;
    lease_generation: number;
    lease_expires_at: string | null;
    latest_event_sequence: number;
  };
  worker: { state: string; started_at: string; heartbeat_at: string };
  attempts: { id: string; step: string; status: string }[];
  artifact_version_ids: string[];
  duplicate_publications: number;
  duplicate_completions: number;
  events: { count: number; min: number; max: number };
  document_parses: {
    id: string;
    research_input_id: string;
    overall_quality: string;
    native_engine: string;
    visual_engine: string | null;
  }[];
}

function composeArguments() {
  const project = process.env.RELEASE_CANDIDATE_COMPOSE_PROJECT;
  const head = process.env.RELEASE_CANDIDATE_SOURCE_COMMIT;
  if (!head || !project?.startsWith("xingwen-rc-" + head.slice(0, 8) + "-")) {
    throw new Error(
      "Runtime smoke may only access its exact-HEAD release Compose namespace",
    );
  }
  return [
    "compose",
    "-f",
    "docker-compose.yml",
    "-f",
    "docker-compose.paddle-local.yml",
    "-p",
    project,
  ];
}

// Read-only projection from production tables. No provider body, session
// credential, lease token, or private reasoning leaves the container.
const READ_RUNTIME = String.raw`
import json, sys
from urllib.parse import urlsplit
from uuid import UUID
from sqlalchemy import text
from app.config import settings
from app.db.session import create_engine_from_url

run_id = str(UUID(sys.argv[1]))
route = urlsplit(settings.DASHSCOPE_BASE_URL)
if (route.scheme != "https" or route.hostname != "dashscope.aliyuncs.com"
        or route.path.rstrip("/") != "/compatible-mode/v1"
        or route.username or route.password or route.query or route.fragment):
    raise RuntimeError("Qualifying evidence requires the configured official DashScope route")
engine = create_engine_from_url(settings.DATABASE_URL.get_secret_value())
with engine.connect() as connection:
    def rows(sql):
        return [dict(row) for row in connection.execute(text(sql), {"run": run_id}).mappings()]
    run = rows("SELECT id, status, lease_owner, lease_generation, lease_expires_at, latest_event_sequence FROM research_runs WHERE id = :run")[0]
    worker = rows("SELECT state, started_at, heartbeat_at FROM workflow_workers WHERE worker_id = 'api-research-run-worker'")[0]
    attempts = rows("SELECT a.id, s.key AS step, a.status FROM step_attempts a JOIN run_steps s ON s.id = a.run_step_id WHERE s.run_id = :run ORDER BY s.position, a.attempt_number")
    versions = rows("SELECT id FROM artifact_versions WHERE created_by_run_id = :run ORDER BY created_at, id")
    duplicate_publications = rows("SELECT count(*) AS count FROM (SELECT artifact_id FROM artifact_versions WHERE created_by_run_id = :run GROUP BY artifact_id HAVING count(*) > 1) duplicates")[0]["count"]
    duplicate_completions = rows("SELECT count(*) AS count FROM (SELECT activity_id, activity_kind FROM run_events WHERE run_id = :run AND activity_phase = 'completed' GROUP BY activity_id, activity_kind HAVING count(*) > 1) duplicates")[0]["count"]
    events = rows("SELECT count(*) AS count, min(sequence) AS min, max(sequence) AS max FROM run_events WHERE run_id = :run")[0]
    parses = rows("SELECT id, research_input_id, overall_quality, native_engine, visual_engine FROM document_parses WHERE created_by_run_id = :run")
    print(json.dumps({"qwen_route": route.geturl(), "run": run, "worker": worker, "attempts": attempts, "artifact_version_ids": [row["id"] for row in versions], "duplicate_publications": duplicate_publications, "duplicate_completions": duplicate_completions, "events": events, "document_parses": parses}, default=str))
engine.dispose()
`;

export async function readReleaseRuntime(
  runId: string,
): Promise<RuntimeSnapshot> {
  const { stdout } = await execute("docker", [
    ...composeArguments(),
    "exec",
    "-T",
    "api",
    "python",
    "-c",
    READ_RUNTIME,
    runId,
  ]);
  return JSON.parse(stdout) as RuntimeSnapshot;
}

export async function restartActiveWorker(page: Page, runId: string) {
  let before = await readReleaseRuntime(runId);
  await expect
    .poll(
      async () => {
        before = await readReleaseRuntime(runId);
        return before.attempts.some((attempt) => attempt.status === "running");
      },
      { timeout: 60_000, intervals: [500, 1_000] },
    )
    .toBe(true);
  expect(before.run.lease_owner).toBe("api-research-run-worker");
  const requestedAt = new Date().toISOString();

  // The worker lives inside api. Its shutdown drains the active run; allow that
  // drain instead of Docker's default ten-second SIGKILL during a provider call.
  await execute(
    "docker",
    [...composeArguments(), "restart", "--timeout", "1800", "api"],
    { timeout: 31 * 60_000 },
  );
  const apiOrigin =
    process.env.REAL_INTEGRATION_API_ORIGIN ?? "http://127.0.0.1:8000";
  await expect
    .poll(
      async () => {
        const response = await page.request
          .get(apiOrigin + "/api/health")
          .catch(() => null);
        return response?.ok() ?? false;
      },
      { timeout: 60_000, intervals: [1_000] },
    )
    .toBe(true);
  const after = await readReleaseRuntime(runId);
  expect(after.worker.state).toBe("accepting");
  expect(after.worker.started_at).not.toBe(before.worker.started_at);
  expect(after.run.status).toBe("completed");
  expect(after.run.lease_owner).toBeNull();
  expect(after.attempts.some((attempt) => attempt.status === "running")).toBe(
    false,
  );
  expect(after.duplicate_publications).toBe(0);
  expect(after.duplicate_completions).toBe(0);
  expect(after.events.min).toBe(1);
  expect(after.events.count).toBe(after.events.max);
  expect(after.events.max).toBe(after.run.latest_event_sequence);
  return {
    source_commit: process.env.RELEASE_CANDIDATE_SOURCE_COMMIT,
    run_id: runId,
    mode: "graceful_active_run_drain_and_restart",
    restart_requested_at: requestedAt,
    before,
    after,
    result: "passed",
  };
}
