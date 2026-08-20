import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { HttpClient } from "../src/http-client";
import { createRevisionRepository } from "../src/revision-repository";
import type { SessionManager } from "../src/session";

const PROJECT_ID = asEntityId("00000000-0000-0000-0000-000000000001");
const ARTIFACT_ID = asEntityId("00000000-0000-0000-0000-000000000002");
const VERSION_ID = asEntityId("00000000-0000-0000-0000-000000000003");
const FEEDBACK_ID = asEntityId("00000000-0000-0000-0000-000000000004");
const PLAN_ID = asEntityId("00000000-0000-0000-0000-000000000005");
const PARENT_RUN_ID = asEntityId("00000000-0000-0000-0000-000000000006");
const CONTRACT_ID = asEntityId("00000000-0000-0000-0000-000000000007");
const DERIVED_RUN_ID = asEntityId("00000000-0000-0000-0000-000000000008");
const HASH = `sha256:${"a".repeat(64)}`;

function session(): SessionManager {
  return {
    ensureSession: async () => {
      throw new Error("not used");
    },
    getCurrent: () => null,
    revokeSession: async () => undefined,
    attachCsrf: (headers) => headers.set("X-CSRF-Token", "csrf-revision"),
    onSessionExpired: () => () => undefined,
    notifyExpired: () => undefined,
  };
}

function envelope(data: unknown): Response {
  return new Response(
    JSON.stringify({
      data,
      meta: {
        request_id: "00000000-0000-0000-0000-000000000099",
        generated_at: "2026-08-18T00:00:00Z",
      },
      links: { self: "/api/test" },
    }),
    { status: 201, headers: { "Content-Type": "application/json" } },
  );
}

describe("RevisionRepository", () => {
  it("preserves version/revision concurrency facts and idempotency across the derived-run chain", async () => {
    const requests: Array<{
      readonly url: string;
      readonly headers: Headers;
      readonly body: unknown;
    }> = [];
    const responses = [
      {
        artifact_id: ARTIFACT_ID,
        baseline_artifact_version_id: VERSION_ID,
        baseline_content_hash: HASH,
        baseline_version_number: 3,
        category: "correction",
        created_at: "2026-08-18T00:00:00Z",
        feedback_hash: HASH,
        id: FEEDBACK_ID,
        project_id: PROJECT_ID,
        requested_change: "使用新增的正式约束重新计算",
        summary: "修正当前结果",
        target_id: VERSION_ID,
        target_locator: {},
        target_type: "artifact_version",
      },
      {
        affected_artifact_version_ids: [VERSION_ID],
        baseline_artifact_version_ids: [VERSION_ID],
        confirmed_run_id: null,
        conflicts: [],
        contract_id: CONTRACT_ID,
        created_at: "2026-08-18T00:00:01Z",
        feedback_ids: [FEEDBACK_ID],
        id: PLAN_ID,
        parent_run_id: PARENT_RUN_ID,
        parent_run_revision: 12,
        plan_hash: HASH,
        project_id: PROJECT_ID,
        recompute_steps: ["building_dataset"],
        reusable_artifact_version_ids: [],
        status: "proposed",
        version: 4,
        version_decisions: [
          {
            artifact_id: ARTIFACT_ID,
            artifact_kind: "dataset",
            artifact_version_id: VERSION_ID,
            decision: "recompute",
            step_key: "building_dataset",
            version_number: 3,
          },
        ],
      },
      {
        cache_policy: "disabled",
        contract_id: CONTRACT_ID,
        created_at: "2026-08-18T00:00:02Z",
        derivation_kind: "revision",
        execution_mode: "live",
        failure_code: null,
        failure_summary: null,
        feedback_ids: [FEEDBACK_ID],
        finished_at: null,
        id: DERIVED_RUN_ID,
        latest_event_sequence: 0,
        parent_run_id: PARENT_RUN_ID,
        progress: 0,
        project_id: PROJECT_ID,
        recompute_steps: ["building_dataset"],
        retry_from_step: null,
        reused_artifact_version_ids: [],
        revision: 1,
        revision_plan_id: PLAN_ID,
        started_at: null,
        status: "queued",
        updated_at: "2026-08-18T00:00:02Z",
      },
    ];
    const fetchImpl = (async (input, init) => {
      requests.push({
        url: String(input),
        headers: new Headers(init?.headers),
        body: init?.body ? JSON.parse(String(init.body)) : null,
      });
      const response = responses.shift();
      if (!response) throw new Error("unexpected request");
      return envelope(response);
    }) as typeof fetch;
    const repository = createRevisionRepository(
      new HttpClient({
        baseUrl: "http://test.local",
        fetchImpl,
        session: session(),
      }),
    );

    const feedback = await repository.createFeedback({
      artifactId: ARTIFACT_ID,
      artifactVersionId: VERSION_ID,
      expectedVersionNumber: 3,
      summary: "修正当前结果",
      requestedChange: "使用新增的正式约束重新计算",
      idempotencyKey: "feedback-key",
    });
    const plan = await repository.createPlan({
      projectId: PROJECT_ID,
      feedbackId: feedback.id,
      expectedParentRunRevision: 12,
      idempotencyKey: "plan-key",
    });
    const run = await repository.confirmPlan(
      plan.id,
      plan.version,
      "confirm-key",
    );

    expect(requests.map((item) => new URL(item.url).pathname)).toEqual([
      `/api/artifact-versions/${VERSION_ID}/feedback`,
      `/api/projects/${PROJECT_ID}/revision-plans`,
      `/api/revision-plans/${PLAN_ID}/confirm`,
    ]);
    expect(requests.map((item) => item.headers.get("Idempotency-Key"))).toEqual(
      ["feedback-key", "plan-key", "confirm-key"],
    );
    expect(
      requests.every(
        (item) => item.headers.get("X-CSRF-Token") === "csrf-revision",
      ),
    ).toBe(true);
    expect(requests[0]?.body).toEqual({
      expected_version_number: 3,
      target_type: "artifact_version",
      target_id: VERSION_ID,
      target_locator: {
        artifact_id: ARTIFACT_ID,
        artifact_version_id: VERSION_ID,
      },
      category: "correction",
      summary: "修正当前结果",
      requested_change: "使用新增的正式约束重新计算",
    });
    expect(requests[1]?.body).toEqual({
      feedback_ids: [FEEDBACK_ID],
      expected_parent_run_revision: 12,
    });
    expect(requests[2]?.body).toEqual({ expected_plan_version: 4 });
    expect(run.id).toBe(DERIVED_RUN_ID);
    expect(run.parentRunId).toBe(PARENT_RUN_ID);
    expect(run.derivationKind).toBe("revision");
    expect(run.revision).toBe(1);
  });
});
