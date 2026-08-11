import { MutationObserver, QueryClient } from "@tanstack/react-query";
import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import {
  CASE_KEY,
  asEntityId,
  type ResearchContractInput,
} from "@xingwen/domain";
import { researchAdapter } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { createWorkspaceMutations } from "./mutations";
import { workspaceQueryKeys } from "./query-keys";

const contractInput: ResearchContractInput = {
  researchGoal: "Compare host-star properties for a reproducible sample",
  targetObjects: [asEntityId("Kepler-186")],
  dataRequirements: { unitPolicy: "canonical" },
  requestedFields: [asEntityId("stellar_mass")],
  sourceScope: { allowedSources: [asEntityId("nasa_exoplanet_archive")] },
  paperSearchScope: {
    keywords: ["Kepler-186"],
    yearFrom: 2014,
    yearTo: 2026,
    sourceIds: [],
    maxCandidates: 20,
  },
  outputRequirements: ["dataset", "paper_collection"],
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

describe("Workspace mutation chain", () => {
  it("owns the real Project → Draft → Update → Confirm → Run cache lifecycle", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const repositories = createFixtureRepositories(exoplanetHostStarFixture);
    let key = 0;
    const mutations = createWorkspaceMutations({
      repositories,
      researchAdapter,
      queryClient,
      createIdempotencyKey: () => `mutation-test-${String(++key)}`,
    });

    const project = await new MutationObserver(
      queryClient,
      mutations.projectCreate(),
    ).mutate({
      name: "Host-star comparison",
      description: "A real mutation-chain test",
      caseKey: CASE_KEY,
    });
    expect(
      queryClient.getQueryData(workspaceQueryKeys.project(project.id)),
    ).toEqual(project);

    const draft = await new MutationObserver(
      queryClient,
      mutations.draftCreate(),
    ).mutate({
      projectId: project.id,
      intent: "Compare the selected host stars",
      contract: contractInput,
    });
    expect(
      queryClient.getQueryData(workspaceQueryKeys.draft(draft.id)),
    ).toEqual(draft);

    const updatedDraft = await new MutationObserver(
      queryClient,
      mutations.draftUpdate(),
    ).mutate({
      draftId: draft.id,
      expectedVersion: draft.version,
      input: {
        intent: "Compare the selected host stars with evidence",
        contract: contractInput,
      },
    });
    expect(updatedDraft.version).toBeGreaterThan(draft.version);

    const contract = await new MutationObserver(
      queryClient,
      mutations.contractConfirm(),
    ).mutate({
      projectId: project.id,
      draftId: updatedDraft.id,
      expectedDraftVersion: updatedDraft.version,
    });
    expect(
      queryClient.getQueryData(workspaceQueryKeys.contract(contract.id)),
    ).toEqual(contract);

    const run = await new MutationObserver(
      queryClient,
      mutations.runCreate(),
    ).mutate({
      projectId: project.id,
      contractId: contract.id,
      executionMode: "demo_replay",
    });
    expect(queryClient.getQueryData(workspaceQueryKeys.run(run.id))).toEqual(
      run,
    );
    expect(run.projectId).toBe(project.id);
  });
});
