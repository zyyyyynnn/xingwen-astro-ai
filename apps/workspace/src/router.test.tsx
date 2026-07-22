import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionManager } from "@xingwen/data-access";
import { createWorkspaceController } from "@xingwen/workspace-core";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { createAppRouter } from "./router";
import { createWorkspaceRuntime } from "./runtime";

type EntityId = Parameters<
  WorkspaceRuntimeBoundaries["repositories"]["projects"]["getById"]
>[0];
type ShareRequest = Parameters<
  WorkspaceRuntimeBoundaries["repositories"]["shares"]["create"]
>[1];
type CreateRunInput = Parameters<
  WorkspaceRuntimeBoundaries["repositories"]["runs"]["create"]
>[0];

afterEach(cleanup);

function fixtureRuntime(): Extract<
  WorkspaceRuntimeBoundaries,
  { adapterKind: "fixture" }
> {
  const runtime = createWorkspaceRuntime({ apiBaseUrl: "" });
  if (runtime.adapterKind !== "fixture") {
    throw new Error("Expected Fixture runtime.");
  }
  return runtime;
}

function renderRoute(path: string, boundaries: WorkspaceRuntimeBoundaries) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(boundaries, history);
  render(<RouterProvider router={router} />);
  return router;
}

function httpShapedRuntime(
  fixture = fixtureRuntime(),
): WorkspaceRuntimeBoundaries & { readonly session: SessionManager } {
  const sessionInfo: Awaited<ReturnType<SessionManager["ensureSession"]>> = {
    status: "active",
    createdAt: "2026-07-22T00:00:00Z",
    expiresAt: "2026-07-22T01:00:00Z",
    quota: {},
    csrfToken: "csrf-test-only",
  };
  const session: SessionManager = {
    ensureSession: vi.fn(async () => sessionInfo),
    getCurrent: () => null,
    revokeSession: vi.fn(async () => {}),
    attachCsrf: vi.fn(),
    onSessionExpired: vi.fn(() => () => {}),
    notifyExpired: vi.fn(),
  };

  return {
    adapterKind: "http",
    repositories: fixture.repositories,
    tour: fixture.tour,
    workspaceController: fixture.workspaceController,
    session,
  };
}

async function createFixtureShare(
  runtime: Extract<WorkspaceRuntimeBoundaries, { adapterKind: "fixture" }>,
) {
  const versionId = "artv_dataset_01" as EntityId;
  const evidenceId = "evd_01" as EntityId;
  const request: ShareRequest = {
    title: "Frozen dataset share" as ShareRequest["title"],
    artifactVersionIds: [versionId],
    evidenceIds: [evidenceId],
    expiresAt: "2026-12-31T00:00:00Z" as ShareRequest["expiresAt"],
    redactionPolicy: "public_metadata_only",
  };
  return runtime.repositories.shares.create(
    runtime.bootstrap.projectId,
    request,
  );
}

describe("Workspace routes", () => {
  it("binds the Fixture Guided Tour FSM and keeps Live visibly unavailable", async () => {
    renderRoute("/tour", fixtureRuntime());

    await screen.findByRole("heading", { name: "研究引导" });
    expect(screen.getByRole("list", { name: "引导阶段" })).toHaveTextContent(
      "SIGNAL",
    );
    expect(screen.getByRole("list", { name: "引导阶段" })).toHaveTextContent(
      "CONTINUE",
    );
    const live = screen.getByRole("radio", { name: "Live" });
    expect(live).toBeDisabled();
    expect(live).toHaveAttribute(
      "aria-describedby",
      "fixture-live-unavailable",
    );
    expect(
      screen.getByText("Fixture 模式只支持 Demo Replay。"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "开始引导" }));
    expect(screen.getByText("阶段：SIGNAL")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    expect(screen.getByText(/已暂停/u)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "继续" }));
    fireEvent.click(screen.getByRole("button", { name: "跳过本步" }));
    expect(screen.getByText("阶段：QUESTION")).toBeInTheDocument();
  });

  it("requires a non-empty intent and a four-character research goal before saving a Draft", async () => {
    const fixture = fixtureRuntime();
    const draft = await fixture.repositories.contracts.getDraftById(
      fixture.bootstrap.draftId,
    );
    if (!draft) {
      throw new Error("Fixture Draft context is incomplete.");
    }
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        contracts: {
          ...fixture.repositories.contracts,
          getDraftById: vi.fn(async () => ({
            ...draft,
            status: "draft" as const,
          })),
        },
      },
    };
    renderRoute("/tour", runtime);

    const intent = await screen.findByLabelText("研究意图");
    const researchGoal = screen.getByLabelText("研究目标");
    fireEvent.change(intent, { target: { value: " " } });
    fireEvent.change(researchGoal, { target: { value: "abc" } });

    expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "确认 Contract" }),
    ).toBeDisabled();
    expect(
      screen.getByText("研究意图不能为空；研究目标需要 4 至 500 个字符。"),
    ).toBeInTheDocument();

    fireEvent.change(intent, { target: { value: "valid intent" } });
    fireEvent.change(researchGoal, { target: { value: "x".repeat(501) } });
    expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
  });

  it("locks the Contract Draft after a successful confirmation", async () => {
    const fixture = fixtureRuntime();
    const existingDraft = await fixture.repositories.contracts.getDraftById(
      fixture.bootstrap.draftId,
    );
    const contract = await fixture.repositories.contracts.getContractById(
      fixture.bootstrap.contractId,
    );
    if (!existingDraft || !contract) {
      throw new Error("Fixture Tour context is incomplete.");
    }
    const editableDraft = { ...existingDraft, status: "draft" as const };
    const updateDraft = vi.fn(
      async (
        id: EntityId,
        version: number,
        input: Parameters<typeof fixture.repositories.contracts.updateDraft>[2],
      ) => ({
        ...editableDraft,
        id,
        intent: input.intent ?? editableDraft.intent,
        contract: input.contract ?? editableDraft.contract,
        version: version + 1,
      }),
    );
    const confirm = vi.fn(async () => contract);
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        contracts: {
          ...fixture.repositories.contracts,
          getDraftById: vi.fn(async () => editableDraft),
          updateDraft,
          confirm,
        },
      },
    };

    renderRoute("/tour", runtime);

    const intent = await screen.findByLabelText("研究意图");
    expect(intent).not.toBeDisabled();
    fireEvent.change(intent, { target: { value: "更新后的研究意图" } });

    fireEvent.click(screen.getByRole("button", { name: "确认 Contract" }));

    await waitFor(() => {
      expect(updateDraft).toHaveBeenCalledWith(
        editableDraft.id,
        editableDraft.version,
        expect.objectContaining({ intent: "更新后的研究意图" }),
      );
      expect(confirm).toHaveBeenCalledWith(
        fixture.bootstrap.projectId,
        editableDraft.id,
        editableDraft.version + 1,
      );
      expect(screen.getByLabelText("研究意图")).toBeDisabled();
      expect(screen.getByLabelText("研究目标")).toBeDisabled();
    });
  });

  it("keeps a confirmed Fixture Draft read-only after reloading the Tour", async () => {
    const runtime = fixtureRuntime();
    renderRoute("/tour", runtime);

    fireEvent.click(
      await screen.findByRole("button", { name: "确认 Contract" }),
    );
    await waitFor(() => {
      expect(screen.getByLabelText("研究意图")).toBeDisabled();
    });

    cleanup();
    renderRoute("/tour", runtime);

    expect(await screen.findByLabelText("研究意图")).toBeDisabled();
    expect(screen.getByLabelText("研究目标")).toBeDisabled();
  });

  it("loads HTTP Tour context without a contractId query", async () => {
    const fixture = fixtureRuntime();
    const runtime = httpShapedRuntime(fixture);
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    await screen.findByRole("heading", { name: "已确认 Contract" });
    expect(
      screen.queryByText("缺少 Project、Draft、Contract 或 Run 上下文。"),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "启动运行" })).toBeEnabled();
  });

  it("creates a Run after confirming a Draft without an existing Run", async () => {
    const fixture = fixtureRuntime();
    const project = await fixture.repositories.projects.getById(
      fixture.bootstrap.projectId,
    );
    const draft = await fixture.repositories.contracts.getDraftById(
      fixture.bootstrap.draftId,
    );
    const contract = await fixture.repositories.contracts.getContractById(
      fixture.bootstrap.contractId,
    );
    if (!project || !draft || !contract) {
      throw new Error("Fixture Tour context is incomplete.");
    }
    const createRun = vi.fn(async (input: CreateRunInput) => ({
      ...(await fixture.repositories.runs.getById(fixture.bootstrap.runId))!,
      contractId: input.contractId,
      executionMode: input.executionMode,
    }));
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        projects: {
          getById: vi.fn(async () => ({ ...project, activeContractId: null })),
        },
        contracts: {
          ...fixture.repositories.contracts,
          getDraftById: vi.fn(async () => ({
            ...draft,
            status: "draft" as const,
          })),
          getContractById: vi.fn(async () => null),
          confirm: vi.fn(async () => contract),
        },
        runs: {
          ...fixture.repositories.runs,
          getById: vi.fn(async () => null),
          create: createRun,
        },
      },
    };
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    await screen.findByLabelText("研究意图");
    fireEvent.click(screen.getByRole("button", { name: "确认 Contract" }));
    const startRun = await screen.findByRole("button", { name: "启动运行" });
    fireEvent.click(startRun);
    await waitFor(() => {
      expect(createRun).toHaveBeenCalledWith(
        expect.objectContaining({ contractId: contract.id }),
      );
    });
  });

  it("passes the HTTP Live selection to the Run port", async () => {
    const fixture = fixtureRuntime();
    const existingRun = await fixture.repositories.runs.getById(
      fixture.bootstrap.runId,
    );
    if (!existingRun) {
      throw new Error("Fixture Run context is incomplete.");
    }
    const createRun = vi.fn(async (input: CreateRunInput) => ({
      ...existingRun,
      executionMode: input.executionMode,
    }));
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        runs: { ...fixture.repositories.runs, create: createRun },
      },
    };
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      contractId: String(fixture.bootstrap.contractId),
      runId: String(fixture.bootstrap.runId),
    });

    const router = renderRoute(`/tour?${search.toString()}`, runtime);

    await waitFor(() => {
      expect(router.state.location.search).toEqual({
        projectId: String(fixture.bootstrap.projectId),
        draftId: String(fixture.bootstrap.draftId),
        contractId: String(fixture.bootstrap.contractId),
        runId: String(fixture.bootstrap.runId),
      });
    });

    const live = await screen.findByRole("radio", { name: "Live" });
    expect(live).not.toBeDisabled();
    fireEvent.click(live);
    fireEvent.click(screen.getByRole("button", { name: "启动运行" }));

    await waitFor(() => {
      expect(createRun).toHaveBeenCalledTimes(1);
    });
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ executionMode: "live" }),
    );
  });

  it("keeps HTTP Project and Run context when entering Workspace from Tour", async () => {
    const fixture = fixtureRuntime();
    const runtime = httpShapedRuntime(fixture);
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    const enterWorkspace = await screen.findByRole("link", {
      name: "进入工作区",
    });
    fireEvent.click(enterWorkspace);

    await screen.findByRole("heading", { name: "科研工作区" });
    await screen.findByText("Exoplanet host-star integration");
    expect(screen.queryByText("缺少 Project 或 Run 上下文。")).toBeNull();
  });

  it("keeps HTTP context through primary navigation", async () => {
    const fixture = fixtureRuntime();
    const runtime = httpShapedRuntime(fixture);
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    fireEvent.click(await screen.findByRole("link", { name: "工作区" }));
    await screen.findByRole("heading", { name: "科研工作区" });
    await screen.findByText("Exoplanet host-star integration");
    expect(screen.queryByText("缺少 Project 或 Run 上下文。")).toBeNull();

    fireEvent.click(screen.getByRole("link", { name: "引导" }));
    await screen.findByRole("heading", { name: "研究引导" });
    await screen.findByLabelText("研究意图");
    expect(screen.queryByText("缺少 Project 或 Draft 上下文。")).toBeNull();
  });

  it("shows a retry action when a private HTTP session expires", async () => {
    const fixture = fixtureRuntime();
    const baseRuntime = httpShapedRuntime(fixture);
    let expireListener: (() => void) | null = null;
    const session = {
      ...baseRuntime.session,
      onSessionExpired: vi.fn((listener) => {
        expireListener = listener;
        return () => {};
      }),
    };
    const runtime = { ...baseRuntime, session };
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    await screen.findByRole("heading", { name: "研究引导" });
    await waitFor(() =>
      expect(session.onSessionExpired).toHaveBeenCalledTimes(1),
    );
    if (!expireListener) {
      throw new Error("Expected session expiry listener.");
    }
    act(() => expireListener!());

    await screen.findByText("会话已过期，请重新建立研究上下文。");
    fireEvent.click(screen.getByRole("button", { name: "重新建立会话" }));
    await waitFor(() => {
      expect(session.ensureSession).toHaveBeenCalledTimes(2);
    });
  });

  it("keeps a dirty Workspace Draft through a private HTTP session retry", async () => {
    const fixture = fixtureRuntime();
    const baseRuntime = httpShapedRuntime(fixture);
    let expireListener: (() => void) | null = null;
    const session = {
      ...baseRuntime.session,
      onSessionExpired: vi.fn((listener) => {
        expireListener = listener;
        return () => {};
      }),
    };
    const runtime = { ...baseRuntime, session };
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/workspace?${search.toString()}`, runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    await waitFor(() => {
      expect(runtime.workspaceController.getState().status).toBe("draft");
    });
    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.layoutPreset).toBe("focus");
      }
    });
    if (!expireListener) {
      throw new Error("Expected session expiry listener.");
    }
    act(() => expireListener!());
    await screen.findByText("会话已过期，请重新建立研究上下文。");
    fireEvent.click(screen.getByRole("button", { name: "重新建立会话" }));

    await waitFor(() => {
      expect(session.ensureSession).toHaveBeenCalledTimes(2);
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.layoutPreset).toBe("focus");
      }
    });
  });

  it("reuses the Run idempotency key when a start action is retried", async () => {
    const fixture = fixtureRuntime();
    const existingRun = await fixture.repositories.runs.getById(
      fixture.bootstrap.runId,
    );
    if (!existingRun) {
      throw new Error("Fixture Run context is incomplete.");
    }
    let attempts = 0;
    const createRun = vi.fn(async (input: CreateRunInput) => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("Run transport unavailable");
      }
      return { ...existingRun, executionMode: input.executionMode };
    });
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        runs: { ...fixture.repositories.runs, create: createRun },
      },
    };
    const search = new URLSearchParams({
      projectId: String(fixture.bootstrap.projectId),
      draftId: String(fixture.bootstrap.draftId),
      contractId: String(fixture.bootstrap.contractId),
      runId: String(fixture.bootstrap.runId),
    });

    renderRoute(`/tour?${search.toString()}`, runtime);

    const startRun = await screen.findByRole("button", { name: "启动运行" });
    fireEvent.click(startRun);
    await screen.findByRole("alert");
    fireEvent.click(startRun);

    await waitFor(() => {
      expect(createRun).toHaveBeenCalledTimes(2);
    });
    expect(createRun.mock.calls[1]?.[0].idempotencyKey).toBe(
      createRun.mock.calls[0]?.[0].idempotencyKey,
    );
  });

  it("shows a Workspace conflict and adopts the server revision only on request", async () => {
    const runtime = fixtureRuntime();
    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    await waitFor(() => {
      expect(runtime.workspaceController.getState().status).toBe("draft");
    });
    const state = runtime.workspaceController.getState();
    if (state.status !== "draft") {
      throw new Error("Expected a local Workspace Draft.");
    }
    await runtime.repositories.workspaces.save(
      runtime.bootstrap.projectId,
      state.draft,
      0,
    );

    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存工作区" }));

    await screen.findByRole("heading", { name: "工作区版本冲突" });
    expect(screen.getByText("本地更改尚未保存。")).toBeInTheDocument();
    expect(screen.getByText("服务器 revision 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存工作区" })).toBeDisabled();
    expect(screen.getByLabelText("布局")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "采用服务器最新版本" }));
    await waitFor(() => {
      expect(screen.getByText("已保存 revision 1")).toBeInTheDocument();
    });
  });

  it("keeps a local Workspace Draft visible after a non-conflict save failure", async () => {
    const fixture = fixtureRuntime();
    const save = vi.fn(async () => {
      throw new Error("Workspace transport unavailable");
    });
    const runtime = {
      ...fixture,
      workspaceController: createWorkspaceController({
        getByProjectId: async () => null,
        save,
      }),
    };

    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    await waitFor(() => {
      expect(runtime.workspaceController.getState().status).toBe("draft");
    });
    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存工作区" }));

    await screen.findByText("保存失败，本地更改仍保留。");
    expect(save).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "再次保存" }));
    await waitFor(() => {
      expect(save).toHaveBeenCalledTimes(2);
    });
  });

  it("recovers Run events without discarding a dirty local Workspace Draft", async () => {
    const runtime = fixtureRuntime();
    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.layoutPreset).toBe("focus");
      }
    });

    fireEvent.click(screen.getByRole("button", { name: "恢复运行事件" }));

    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.layoutPreset).toBe("focus");
      }
    });
  });

  it("loads the target Project instead of carrying another Project's local Draft or Run", async () => {
    const fixture = fixtureRuntime();
    const sourceProject = await fixture.repositories.projects.getById(
      fixture.bootstrap.projectId,
    );
    if (!sourceProject)
      throw new Error("Fixture Project context is incomplete.");
    const targetProjectId = "proj_TARGET" as EntityId;
    const getByProjectId = vi.fn(async () => null);
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        projects: {
          getById: vi.fn(async (id: EntityId) =>
            id === targetProjectId
              ? {
                  ...sourceProject,
                  id: targetProjectId,
                  name: "Target Project",
                  activeContractId: null,
                  latestRunId: null,
                }
              : fixture.repositories.projects.getById(id),
          ),
        },
        shares: {
          ...fixture.repositories.shares,
          list: vi.fn(async (projectId: EntityId) =>
            projectId === targetProjectId
              ? []
              : fixture.repositories.shares.list(projectId),
          ),
        },
      },
      workspaceController: createWorkspaceController({
        getByProjectId,
        save: async (projectId, input, expectedRevision) => ({
          id: `ws_${projectId}` as EntityId,
          projectId,
          revision: expectedRevision + 1,
          ...input,
          updatedAt: "2026-07-23T00:00:00Z" as never,
        }),
      }),
    };
    const router = renderRoute(
      `/workspace?projectId=${fixture.bootstrap.projectId}`,
      runtime,
    );

    const runSelect = await screen.findByLabelText("选择 Run");
    fireEvent.change(runSelect, {
      target: { value: fixture.bootstrap.runId },
    });
    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.projectId).toBe(fixture.bootstrap.projectId);
        expect(state.dirty).toBe(true);
      }
    });

    await act(async () => {
      await router.navigate({
        to: "/workspace",
        search: { projectId: String(targetProjectId) },
      });
    });

    await screen.findByText("Target Project");
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.projectId).toBe(targetProjectId);
        expect(state.dirty).toBe(false);
        expect(state.draft.activeRunId).toBeNull();
      }
    });
    expect(getByProjectId).toHaveBeenLastCalledWith(targetProjectId);
    expect(screen.queryByLabelText("选择 Run")).toBeNull();
  });

  it("selects ArtifactVersion and Evidence before creating and revoking a frozen Share", async () => {
    const runtime = fixtureRuntime();
    const artifacts = await runtime.repositories.artifacts.listByRun(
      runtime.bootstrap.runId,
    );
    const artifact = artifacts[0];
    if (!artifact?.latestVersionId) {
      throw new Error("Fixture Artifact context is incomplete.");
    }
    const version = await runtime.repositories.artifacts.getVersion(
      artifact.latestVersionId,
    );
    const evidenceId = version?.evidenceIds[0];
    if (!version || !evidenceId) {
      throw new Error(
        "Fixture ArtifactVersion Evidence context is incomplete.",
      );
    }

    renderRoute("/workspace", runtime);

    const selectArtifact = await screen.findByRole("button", {
      name: artifact.title,
    });
    fireEvent.click(selectArtifact);
    await screen.findByRole("heading", { name: artifact.title });
    fireEvent.click(screen.getByRole("button", { name: String(evidenceId) }));
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.pinnedEvidenceIds).toContain(evidenceId);
      }
    });

    fireEvent.click(screen.getByRole("button", { name: "创建只读分享" }));
    const shareTitle = `${artifact.title} v${version.versionNumber}`;
    const revoke = await screen.findByRole("button", {
      name: `撤销 ${shareTitle}`,
    });
    fireEvent.click(revoke);

    await screen.findByText("revoked");
  });

  it("distinguishes unavailable and network failures for private Share actions", async () => {
    const fixture = fixtureRuntime();
    const existingShare = await createFixtureShare(fixture);
    const unavailable = new Error("Selected share resource is unavailable");
    unavailable.name = "NotFoundError";
    const create = vi.fn(async () => {
      throw unavailable;
    });
    const revoke = vi.fn(async () => {
      throw new Error("Share transport unavailable");
    });
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        shares: { ...fixture.repositories.shares, create, revoke },
      },
    };

    renderRoute("/workspace", runtime);

    fireEvent.click(
      await screen.findByRole("button", { name: "创建只读分享" }),
    );
    await screen.findByText("共享资源不可用，可能已撤销或过期。");

    fireEvent.click(
      await screen.findByRole("button", {
        name: `撤销 ${existingShare.title}`,
      }),
    );
    await screen.findByText("无法完成分享操作，请检查网络后重试。");
    expect(create).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith(
      fixture.bootstrap.projectId,
      existingShare.id,
    );
  });

  it("shows a selection error when an ArtifactVersion read fails", async () => {
    const fixture = fixtureRuntime();
    const artifacts = await fixture.repositories.artifacts.listByRun(
      fixture.bootstrap.runId,
    );
    const artifact = artifacts[0];
    if (!artifact?.latestVersionId) {
      throw new Error("Fixture Artifact context is incomplete.");
    }
    const version = await fixture.repositories.artifacts.getVersion(
      artifact.latestVersionId,
    );
    if (!version) {
      throw new Error("Fixture ArtifactVersion context is incomplete.");
    }
    const getVersion = vi
      .fn()
      .mockResolvedValueOnce(version)
      .mockRejectedValueOnce(new Error("ArtifactVersion unavailable"));
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        artifacts: { ...fixture.repositories.artifacts, getVersion },
      },
    };

    renderRoute("/workspace", runtime);

    const selectArtifact = await screen.findByRole("button", {
      name: artifact.title,
    });
    fireEvent.click(selectArtifact);

    await screen.findByText("无法选择当前 ArtifactVersion 或 Evidence。");
  });

  it("loads the Fixture workspace, saves an explicit local draft, and creates a frozen share", async () => {
    const runtime = fixtureRuntime();
    const contract = await runtime.repositories.contracts.getContractById(
      runtime.bootstrap.contractId,
    );
    if (!contract) {
      throw new Error("Fixture Contract context is incomplete.");
    }
    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    expect(
      screen.getAllByText("Exoplanet host-star integration").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(contract.researchGoal)).toBeInTheDocument();
    expect(screen.getAllByText(/completed/u).length).toBeGreaterThan(0);
    await screen.findByRole("button", { name: "Exoplanet host-star dataset" });

    fireEvent.change(screen.getByLabelText("布局"), {
      target: { value: "focus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存工作区" }));

    await waitFor(() => {
      expect(screen.getByText(/已保存 revision 1/u)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "创建只读分享" }));
    const shareLink = await screen.findByRole("link", { name: "打开只读分享" });
    expect(shareLink).toHaveAttribute(
      "href",
      expect.stringContaining("/share/"),
    );
    expect(screen.queryByText(/token_share/u)).not.toBeInTheDocument();
  });

  it("restores ArtifactVersion and Evidence selection from a saved WorkspaceSnapshot", async () => {
    const runtime = fixtureRuntime();
    const artifact = await runtime.repositories.artifacts.getArtifact(
      "art_rels_01" as EntityId,
    );
    if (!artifact?.latestVersionId) {
      throw new Error("Fixture relation Artifact context is incomplete.");
    }
    const version = await runtime.repositories.artifacts.getVersion(
      artifact.latestVersionId,
    );
    const evidenceId = version?.evidenceIds[0];
    if (!version || !evidenceId) {
      throw new Error(
        "Fixture relation ArtifactVersion Evidence context is incomplete.",
      );
    }
    await runtime.repositories.workspaces.save(
      runtime.bootstrap.projectId,
      {
        layoutPreset: "focus",
        activeRunId: runtime.bootstrap.runId,
        panelSlots: [
          {
            slotId: "primary",
            panelType: "observatory",
            artifactVersionId: version.id,
            evidenceId,
          },
        ],
        pinnedEvidenceIds: [evidenceId],
        atlasState: null,
        observatoryState: null,
        selectedObjectRef: null,
      },
      0,
    );

    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: artifact.title });
    expect(screen.getByLabelText("布局")).toHaveValue("focus");
    expect(
      screen.getByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(String(evidenceId)).length).toBeGreaterThan(0);
  });

  it("restores a saved active Run before Fixture bootstrap context", async () => {
    const fixture = fixtureRuntime();
    const currentRun = await fixture.repositories.runs.getById(
      fixture.bootstrap.runId,
    );
    if (!currentRun) {
      throw new Error("Fixture Run context is incomplete.");
    }
    const alternateRun = {
      ...currentRun,
      id: "run_01JRESTORED" as EntityId,
      status: "queued" as const,
    };
    await fixture.repositories.workspaces.save(
      fixture.bootstrap.projectId,
      {
        layoutPreset: "comparative",
        activeRunId: alternateRun.id,
        panelSlots: [],
        pinnedEvidenceIds: [],
        atlasState: null,
        observatoryState: null,
        selectedObjectRef: null,
      },
      0,
    );
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        runs: {
          ...fixture.repositories.runs,
          getById: vi.fn(async (id: EntityId) =>
            id === alternateRun.id
              ? alternateRun
              : fixture.repositories.runs.getById(id),
          ),
          recoverEvents: vi.fn(async (id: EntityId, cursor?: string | null) =>
            fixture.repositories.runs.recoverEvents(
              id === alternateRun.id ? currentRun.id : id,
              cursor,
            ),
          ),
        },
        artifacts: {
          ...fixture.repositories.artifacts,
          listByRun: vi.fn(async (id: EntityId) =>
            fixture.repositories.artifacts.listByRun(
              id === alternateRun.id ? currentRun.id : id,
            ),
          ),
        },
      },
    };

    renderRoute("/workspace", runtime);

    await expect(screen.findByLabelText("选择 Run")).resolves.toHaveValue(
      alternateRun.id,
    );
  });

  it("selects an available Run through the Workspace keyboard control", async () => {
    const fixture = fixtureRuntime();
    const currentRun = await fixture.repositories.runs.getById(
      fixture.bootstrap.runId,
    );
    const project = await fixture.repositories.projects.getById(
      fixture.bootstrap.projectId,
    );
    if (!currentRun || !project) {
      throw new Error("Fixture Run selection context is incomplete.");
    }
    const alternateRun = {
      ...currentRun,
      id: "run_01JALTERNATE" as EntityId,
      status: "queued" as const,
    };
    const getRunById = vi.fn(async (id: EntityId) => {
      if (id === alternateRun.id) return alternateRun;
      return fixture.repositories.runs.getById(id);
    });
    const recoverEvents = vi.fn(async (id: EntityId, cursor?: string | null) =>
      fixture.repositories.runs.recoverEvents(
        id === alternateRun.id ? currentRun.id : id,
        cursor,
      ),
    );
    const listByRun = vi.fn(async (id: EntityId) =>
      fixture.repositories.artifacts.listByRun(
        id === alternateRun.id ? currentRun.id : id,
      ),
    );
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        projects: {
          getById: vi.fn(async () => ({
            ...project,
            latestRunId: alternateRun.id,
          })),
        },
        runs: {
          ...fixture.repositories.runs,
          getById: getRunById,
          recoverEvents,
        },
        artifacts: { ...fixture.repositories.artifacts, listByRun },
      },
    };

    renderRoute(
      `/workspace?projectId=${fixture.bootstrap.projectId}&runId=${fixture.bootstrap.runId}`,
      runtime,
    );

    const runSelect = await screen.findByLabelText("选择 Run");
    fireEvent.change(runSelect, { target: { value: alternateRun.id } });

    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.activeRunId).toBe(alternateRun.id);
      }
    });
    await waitFor(() => {
      expect(screen.getByLabelText("选择 Run")).toHaveValue(alternateRun.id);
    });
  });

  it("uses the app public-share route when an HTTP adapter returns an API share URL", async () => {
    const fixture = fixtureRuntime();
    let shareToken: string | null = null;
    const create = vi.fn(
      async (
        ...args: Parameters<typeof fixture.repositories.shares.create>
      ) => {
        const created = await fixture.repositories.shares.create(...args);
        shareToken = created.shareToken;
        return {
          ...created,
          shareUrl: `/api/v2/shares/${created.shareToken}`,
        };
      },
    );
    const runtime = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        shares: { ...fixture.repositories.shares, create },
      },
    };

    renderRoute("/workspace", runtime);

    await screen.findByRole("button", { name: "创建只读分享" });
    fireEvent.click(screen.getByRole("button", { name: "创建只读分享" }));
    const shareLink = await screen.findByRole("link", { name: "打开只读分享" });

    expect(shareToken).not.toBeNull();
    expect(shareLink).toHaveAttribute("href", `/share/${shareToken}`);
  });

  it("shows Project, Run, adapter, execution, and source state in the Workspace status rail", async () => {
    renderRoute("/workspace", fixtureRuntime());

    await screen.findByRole("heading", { name: "科研工作区" });
    await waitFor(() => {
      const rail = screen.getByLabelText("当前状态");
      expect(rail).toHaveTextContent(
        "Project: Exoplanet host-star integration",
      );
      expect(rail).toHaveTextContent("Run: run_01JEXAMPLE");
      expect(rail).toHaveTextContent("Adapter: Fixture");
      expect(rail).toHaveTextContent("Execution: demo_replay");
      expect(rail).toHaveTextContent("Source: fixture");
      expect(rail).toHaveTextContent("Status: completed");
    });
  });

  it("opens a just-created Fixture Share through SPA navigation", async () => {
    const runtime = fixtureRuntime();
    const artifacts = await runtime.repositories.artifacts.listByRun(
      runtime.bootstrap.runId,
    );
    const artifact = artifacts[0];
    const version = artifact?.latestVersionId
      ? await runtime.repositories.artifacts.getVersion(
          artifact.latestVersionId,
        )
      : null;
    if (!artifact || !version) {
      throw new Error("Fixture Artifact context is incomplete.");
    }

    renderRoute("/workspace", runtime);

    await screen.findByRole("heading", { name: "科研工作区" });
    fireEvent.click(screen.getByRole("button", { name: "创建只读分享" }));
    const shareLink = await screen.findByRole("link", { name: "打开只读分享" });
    fireEvent.click(shareLink);

    await screen.findByRole("heading", {
      name: `${artifact.title} v${version.versionNumber}`,
    });
    expect(screen.queryByRole("navigation", { name: "主要导航" })).toBeNull();
  });

  it("renders a frozen public share without private navigation or raw token text", async () => {
    const runtime = fixtureRuntime();
    const created = await createFixtureShare(runtime);

    renderRoute(`/share/${created.shareToken}`, runtime);

    await screen.findByRole("heading", { name: "Frozen dataset share" });
    expect(screen.getByText("只读共享结果")).toBeInTheDocument();
    expect(screen.getAllByText("artv_dataset_01").length).toBeGreaterThan(0);
    expect(screen.queryByRole("navigation", { name: "主要导航" })).toBeNull();
    expect(screen.queryByText(created.shareToken)).toBeNull();
  });

  it("uses the same public page with an HTTP-shaped boundary without creating a session", async () => {
    const fixture = fixtureRuntime();
    const created = await createFixtureShare(fixture);
    const runtime = httpShapedRuntime(fixture);

    renderRoute(`/share/${created.shareToken}`, runtime);

    await screen.findByRole("heading", { name: "Frozen dataset share" });
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
  });

  it("renders an unavailable public Share without creating a session", async () => {
    const fixture = fixtureRuntime();
    const getPublic = vi.fn(async () => null);
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        shares: { ...fixture.repositories.shares, getPublic },
      },
    };

    renderRoute("/share/revoked-share-token", runtime);

    await screen.findByRole("heading", { name: "共享结果不可用" });
    expect(getPublic).toHaveBeenCalledWith("revoked-share-token");
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
    expect(screen.queryByText("revoked-share-token")).toBeNull();
  });

  it("keeps a public Share network failure distinct from an unavailable Share", async () => {
    const fixture = fixtureRuntime();
    const runtime = {
      ...httpShapedRuntime(fixture),
      repositories: {
        ...fixture.repositories,
        shares: {
          ...fixture.repositories.shares,
          getPublic: vi.fn(async () => {
            throw new Error("Public Share transport unavailable");
          }),
        },
      },
    };

    renderRoute("/share/network-failure-token", runtime);

    await screen.findByRole("heading", { name: "无法读取共享结果" });
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
    expect(screen.queryByText("network-failure-token")).toBeNull();
  });
});
