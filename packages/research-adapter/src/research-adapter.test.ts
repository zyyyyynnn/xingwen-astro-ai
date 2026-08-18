import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { researchAdapter } from "./research-adapter";

describe("researchAdapter facade", () => {
  it("exposes the complete stateless capability set", () => {
    expect(Object.keys(researchAdapter).sort()).toEqual([
      "mergeActivityPresentationEvents",
      "toActivityPresentationEvent",
      "toApplicationCommand",
      "toArtifactVersionViewModel",
      "toArtifactViewModel",
      "toContractDraftViewModel",
      "toContractViewModel",
      "toDataArtifactViewModel",
      "toEvidenceViewModel",
      "toGraphArtifactViewModel",
      "toLiteratureArtifactViewModel",
      "toPaperAcquisitionViewModel",
      "toProjectViewModel",
      "toPublicApplicationError",
      "toResearchThreadEntryViewModel",
      "toResearchTurnViewModel",
      "toRunCheckpointViewModel",
      "toRunStepViewModel",
      "toRunViewModel",
    ]);
  });

  it("does not retain server facts or vary with call order", () => {
    const event = {
      runId: asEntityId("run_facade"),
      sequence: 1,
      activityId: "run:run_facade",
      activityKind: "status" as const,
      activityPhase: "queued" as const,
      activityName: "研究任务",
      stepKey: null,
      progress: 0,
      content: "研究任务已进入执行队列。",
      details: {},
      artifactVersionIds: [],
      occurredAt: "2026-08-11T00:09:00Z",
    };
    const first = researchAdapter.toActivityPresentationEvent(event);

    researchAdapter.toPublicApplicationError(new Error("internal"));
    researchAdapter.toApplicationCommand(
      {
        type: "share.revoke",
        projectId: asEntityId("project_facade"),
        shareId: asEntityId("share_facade"),
      },
      { idempotencyKey: "facade-action" },
    );

    expect(researchAdapter.toActivityPresentationEvent(event)).toEqual(first);
  });
});
