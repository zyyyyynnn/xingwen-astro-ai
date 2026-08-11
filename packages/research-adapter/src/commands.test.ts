import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { toApplicationCommand, type ApplicationIntent } from "./commands";

const projectId = asEntityId("project_command");
const contractId = asEntityId("contract_command");
const draftId = asEntityId("draft_command");
const context = { idempotencyKey: "action-command-1" } as const;
const contract = {
  researchGoal: "Compare candidate objects",
  targetObjects: [asEntityId("candidate")],
  dataRequirements: { unitPolicy: "canonical" as const },
  requestedFields: [asEntityId("candidate.id")],
  sourceScope: { allowedSources: [asEntityId("source.primary")] },
  paperSearchScope: {
    keywords: [],
    yearFrom: null,
    yearTo: null,
    sourceIds: [],
    maxCandidates: 5,
  },
  outputRequirements: ["dataset" as const],
  evidenceRequirements: {
    requireLocator: true,
    requireSourceSnapshot: true,
    minimumCoverage: 1,
  },
  qualityConstraints: {
    sourceCompletenessMin: 1,
    unitConsistencyMin: 1,
  },
};

describe("UI intent to ApplicationCommand", () => {
  it("covers every real write capability with exact typed payloads", () => {
    const intents: ApplicationIntent[] = [
      {
        type: "project.create",
        input: {
          name: "Project",
          description: "Description",
          caseKey: "exoplanet_host_star",
        },
      },
      {
        type: "contract.draft.create",
        projectId,
        input: { intent: "Create draft", contract },
      },
      {
        type: "contract.draft.update",
        draftId,
        expectedVersion: 3,
        input: { intent: "Update draft" },
      },
      {
        type: "contract.confirm",
        projectId,
        draftId,
        expectedDraftVersion: 4,
      },
      {
        type: "run.create",
        projectId,
        contractId,
        executionMode: "live",
      },
      {
        type: "share.create",
        projectId,
        request: {
          title: "Public result",
          artifactVersionIds: [asEntityId("version_shared")],
          evidenceIds: [asEntityId("evidence_shared")],
          expiresAt: "2026-08-12T00:00:00Z",
          redactionPolicy: "public_metadata_only",
        },
      },
      {
        type: "share.revoke",
        projectId,
        shareId: asEntityId("share_command"),
      },
    ];

    const commands = intents.map((intent) =>
      toApplicationCommand(intent, context),
    );

    expect(commands.map((command) => command.type)).toEqual([
      "project.create",
      "contract.draft.create",
      "contract.draft.update",
      "contract.confirm",
      "run.create",
      "share.create",
      "share.revoke",
    ]);
    expect(commands[0]).toMatchObject({
      type: "project.create",
      input: {
        caseKey: "exoplanet_host_star",
        idempotencyKey: context.idempotencyKey,
      },
    });
    expect(commands[1]).toMatchObject({
      type: "contract.draft.create",
      projectId,
      input: { intent: "Create draft", idempotencyKey: context.idempotencyKey },
    });
    expect(commands[2]).toEqual({
      type: "contract.draft.update",
      draftId,
      expectedVersion: 3,
      input: { intent: "Update draft" },
    });
    expect(commands[3]).toEqual({
      type: "contract.confirm",
      projectId,
      draftId,
      expectedDraftVersion: 4,
    });
    expect(commands[4]).toMatchObject({
      type: "run.create",
      input: {
        projectId,
        contractId,
        executionMode: "live",
        idempotencyKey: context.idempotencyKey,
      },
    });
    expect(commands[5]).toMatchObject({
      type: "share.create",
      projectId,
      request: {
        artifactVersionIds: [asEntityId("version_shared")],
        evidenceIds: [asEntityId("evidence_shared")],
      },
    });
    expect(commands[6]).toEqual({
      type: "share.revoke",
      projectId,
      shareId: asEntityId("share_command"),
    });
  });

  it("is deterministic and contains no transport instruction", () => {
    const intent: ApplicationIntent = {
      type: "run.create",
      projectId,
      contractId,
      executionMode: "demo_replay",
    };

    const first = toApplicationCommand(intent, context);
    const second = toApplicationCommand(intent, context);

    expect(first).toEqual(second);
    expect(JSON.stringify(first)).not.toMatch(/\/api\/|method|url|dto/iu);
  });
});
