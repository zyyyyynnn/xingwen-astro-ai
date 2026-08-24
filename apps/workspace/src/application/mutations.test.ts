import { MutationObserver, QueryClient } from "@tanstack/react-query";
import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import { NetworkError } from "@xingwen/data-access/errors";
import {
  CASE_KEY,
  asEntityId,
  type ResearchContractInput,
} from "@xingwen/domain";
import {
  researchAdapter,
  type ResearchThreadEntryViewModel,
} from "@xingwen/research-adapter";
import { describe, expect, it, vi } from "vitest";

import {
  createWorkspaceMutations,
  mergeResearchThreadEntries,
} from "./mutations";
import { workspaceQueryKeys } from "./query-keys";

const contractInput: ResearchContractInput = {
  researchGoal: "Compare host-star properties for a reproducible sample",
  targetObjects: [asEntityId("Kepler-186")],
  dataRequirements: {
    unitPolicy: "canonical",
    documentSourcePolicy: "disabled",
  },
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
  it("deduplicates a polled user entry when the completed turn reaches the cache", () => {
    const userEntry = {
      id: asEntityId("user-entry"),
      sequence: 1,
    } as ResearchThreadEntryViewModel;
    const assistantEntry = {
      id: asEntityId("assistant-entry"),
      sequence: 2,
    } as ResearchThreadEntryViewModel;

    expect(
      mergeResearchThreadEntries([userEntry], [userEntry, assistantEntry]).map(
        (entry) => entry.id,
      ),
    ).toEqual([userEntry.id, assistantEntry.id]);
  });

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

    const draft = researchAdapter.toContractDraftViewModel(
      await repositories.contracts.createDraft(project.id, {
        intent: "Compare the selected host stars",
        contract: contractInput,
        idempotencyKey: "fixture-draft-setup",
      }),
    );
    expect(
      queryClient.getQueryData(workspaceQueryKeys.draft(project.id, draft.id)),
    ).toBeUndefined();

    const updatedDraft = await new MutationObserver(
      queryClient,
      mutations.draftUpdate(),
    ).mutate({
      projectId: project.id,
      draftId: draft.id,
      expectedVersion: draft.version,
      input: {
        intent: "Compare the selected host stars with evidence",
        contract: contractInput,
      },
    });
    expect(updatedDraft.version).toBeGreaterThan(draft.version);
    expect(
      queryClient.getQueryData(
        workspaceQueryKeys.draft(project.id, updatedDraft.id),
      ),
    ).toEqual(updatedDraft);

    const contract = await new MutationObserver(
      queryClient,
      mutations.contractConfirm(),
    ).mutate({
      projectId: project.id,
      draftId: updatedDraft.id,
      expectedDraftVersion: updatedDraft.version,
    });
    expect(
      queryClient.getQueryData(
        workspaceQueryKeys.contract(project.id, contract.id),
      ),
    ).toEqual(contract);

    const run = await new MutationObserver(
      queryClient,
      mutations.runCreate(),
    ).mutate({
      projectId: project.id,
      contractId: contract.id,
      executionMode: "demo_replay",
    });
    expect(
      queryClient.getQueryData(workspaceQueryKeys.run(project.id, run.id)),
    ).toEqual(run);
    expect(
      queryClient.getQueryData(workspaceQueryKeys.project(project.id)),
    ).toMatchObject({ latestRunId: run.id });
    expect(run.projectId).toBe(project.id);
  });

  it("removes every project-owned cache entry when the project is deleted", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const repositories = createFixtureRepositories(exoplanetHostStarFixture);
    const mutations = createWorkspaceMutations({
      repositories,
      researchAdapter,
      queryClient,
      createIdempotencyKey: () => "project-delete-cache-test",
    });
    const project = researchAdapter.toProjectViewModel(
      await repositories.projects.create({
        name: "Disposable project",
        description: "Project-owned cache scope verification",
        caseKey: CASE_KEY,
        idempotencyKey: "project-delete-setup",
      }),
    );
    const draftId = asEntityId("project-delete-draft");
    const runId = asEntityId("project-delete-run");

    queryClient.setQueryData(workspaceQueryKeys.project(project.id), project);
    queryClient.setQueryData(workspaceQueryKeys.thread(project.id), []);
    queryClient.setQueryData(workspaceQueryKeys.draft(project.id, draftId), {
      id: draftId,
    });
    queryClient.setQueryData(workspaceQueryKeys.runEvents(project.id, runId), {
      events: [],
    });

    await new MutationObserver(queryClient, mutations.projectDelete()).mutate({
      projectId: project.id,
      expectedRevision: project.revision,
    });

    expect(
      queryClient.getQueriesData({
        queryKey: workspaceQueryKeys.projectScope(project.id),
      }),
    ).toEqual([]);
  });

  it("reuses a create idempotency key until the same action is acknowledged", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const repositories = createFixtureRepositories(exoplanetHostStarFixture);
    const originalCreate = repositories.projects.create.bind(
      repositories.projects,
    );
    const observedKeys: string[] = [];
    let loseFirstResponse = true;
    vi.spyOn(repositories.projects, "create").mockImplementation(
      async (input) => {
        observedKeys.push(input.idempotencyKey);
        const project = await originalCreate(input);
        if (loseFirstResponse) {
          loseFirstResponse = false;
          throw new NetworkError("response lost");
        }
        return project;
      },
    );
    let sequence = 0;
    const mutations = createWorkspaceMutations({
      repositories,
      researchAdapter,
      queryClient,
      createIdempotencyKey: () => `retry-key-${String(++sequence)}`,
    });
    const input = {
      name: "Stable retry action",
      description: "The server commits before the first response is lost",
      caseKey: CASE_KEY,
    } as const;

    await expect(
      new MutationObserver(queryClient, mutations.projectCreate()).mutate(
        input,
      ),
    ).rejects.toBeInstanceOf(NetworkError);
    await expect(
      new MutationObserver(queryClient, mutations.projectCreate()).mutate(
        input,
      ),
    ).resolves.toMatchObject({ name: input.name });

    expect(observedKeys.slice(0, 2)).toEqual(["retry-key-1", "retry-key-1"]);

    await new MutationObserver(queryClient, mutations.projectCreate()).mutate(
      input,
    );
    expect(observedKeys[2]).toBe("retry-key-2");
  });

  it("uses the caller-owned action identity for each explicit research Turn", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const repositories = createFixtureRepositories(exoplanetHostStarFixture);
    const project = (await repositories.projects.list()).items[0];
    if (!project) throw new Error("Fixture project is required.");
    const observedKeys: string[] = [];
    vi.spyOn(repositories.researchThread, "submit").mockImplementation(
      async (_projectId, input) => {
        observedKeys.push(input.idempotencyKey);
        throw new NetworkError("provider unavailable");
      },
    );
    const createIdempotencyKey = vi.fn(() => "unrelated-generated-key");
    const mutations = createWorkspaceMutations({
      repositories,
      researchAdapter,
      queryClient,
      createIdempotencyKey,
    });
    const firstAction = {
      projectId: project.id,
      message: "Compare the selected host stars",
      answerToQuestionId: null,
      actionId: "research-turn-action-first",
    } as const;
    const secondAction = {
      ...firstAction,
      actionId: "research-turn-action-second",
    } as const;

    await expect(
      new MutationObserver(queryClient, mutations.researchTurnSubmit()).mutate(
        firstAction,
      ),
    ).rejects.toBeInstanceOf(NetworkError);
    await expect(
      new MutationObserver(queryClient, mutations.researchTurnSubmit()).mutate(
        secondAction,
      ),
    ).rejects.toBeInstanceOf(NetworkError);

    expect(observedKeys).toEqual([firstAction.actionId, secondAction.actionId]);
  });
});
