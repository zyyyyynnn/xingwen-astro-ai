import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { researchAdapter } from "./research-adapter";

describe("researchAdapter facade", () => {
  it("exposes the complete stateless capability set", () => {
    expect(Object.keys(researchAdapter).sort()).toEqual([
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
      "toRunStepViewModel",
      "toRunViewModel",
    ]);
  });

  it("does not retain server facts or vary with call order", () => {
    const event = {
      runId: asEntityId("run_facade"),
      sequence: 1,
      eventType: asEntityId("run.queued"),
      stepKey: null,
      progress: 0,
      publicMessage: "Queued",
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
