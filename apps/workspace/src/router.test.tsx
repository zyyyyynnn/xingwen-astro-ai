import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import {
  asEntityId,
  type ResearchPlanningCatalog,
  type ResearchProject,
  type ResearchRun,
  type ResearchThreadEntry,
  type ResearchTurn,
  type UtcIsoTimestamp,
} from "@xingwen/domain";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { workspaceQueryKeys } from "./application/query-keys";
import { createAppRouter } from "./router";
import { createTestRuntime } from "./test/runtime";

afterEach(cleanup);

function renderRoute(path: string, runtime: WorkspaceRuntimeBoundaries) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(runtime, history);
  render(
    <QueryClientProvider client={runtime.queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, history };
}

const TEST_PROJECT_ID = asEntityId("proj_01JEXAMPLE");

function createUserTurn(
  suffix: string,
  sequence: number,
  publicContent: string,
): ResearchTurn {
  const modelExecutionId = asEntityId(`model-execution-${suffix}`);
  return {
    outcome: "draft_ready",
    entries: [
      {
        id: asEntityId(`thread-entry-${suffix}`),
        projectId: TEST_PROJECT_ID,
        sequence,
        kind: "user_message",
        actor: "user",
        publicContent,
        structuredPayload: { answerToQuestionId: null },
        modelExecutionId,
        createdAt: "2026-08-13T00:00:00Z" as UtcIsoTimestamp,
      },
    ],
    activeDraftId: null,
    modelExecutionId,
  };
}

describe("Workspace routes", () => {
  it("gates /workspace, lists real repository projects, and replaces /", async () => {
    const runtime = createTestRuntime();
    const { history } = renderRoute("/", runtime);

    await screen.findByRole("heading", { name: "新研究", level: 1 });
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
    expect(runtime.session.ensureSession).toHaveBeenCalled();
    expect(history.location.pathname).toBe("/workspace");
    expect(
      await screen.findByText("Exoplanet host-star integration"),
    ).toBeInTheDocument();

    act(() => history.back());
    await waitFor(() => expect(history.location.pathname).toBe("/workspace"));
  });

  it("performs the project ownership read before rendering the OpenHands shell", async () => {
    const runtime = createTestRuntime();
    const getById = vi.spyOn(runtime.repositories.projects, "getById");
    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    await screen.findByRole("heading", {
      name: "Exoplanet host-star integration",
      level: 1,
    });
    expect(getById).toHaveBeenCalled();
    expect(
      await screen.findByRole("textbox", { name: "输入研究消息" }),
    ).toHaveAttribute("contenteditable", "true");
    expect(await screen.findByLabelText("右侧研究栏")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "关闭右侧研究栏" }),
    ).toBeEnabled();
    expect(screen.getByRole("button", { name: "新建研究" })).toBeEnabled();
    expect(screen.queryByText("运行服务未连接")).not.toBeInTheDocument();
  });

  it("pins one ArtifactVersion through Thread, Research Rail, Fullscreen, and URL", async () => {
    const runtime = createTestRuntime();
    const { history } = renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    expect(await screen.findByLabelText("右侧研究栏")).toBeInTheDocument();
    const resultBlock = await screen.findByTestId(
      "artifact-result-artv_papsum_01",
    );
    expect(resultBlock).toBeInTheDocument();
    expect(
      within(resultBlock).getByRole("button", {
        name: "打开：核心文献研读报告",
      }),
    ).toBeInTheDocument();
    expect(within(resultBlock).queryByText("演示数据")).not.toBeInTheDocument();
    expect(within(resultBlock).queryByText(/^v\d+$/u)).not.toBeInTheDocument();
    expect(
      within(resultBlock).queryByText("有证据支持"),
    ).not.toBeInTheDocument();
    expect(within(resultBlock).queryByText("已完成")).not.toBeInTheDocument();
    expect(within(resultBlock).queryByText("已生成")).not.toBeInTheDocument();
    expect(
      within(resultBlock).queryByText("已加入研究结果"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("未支持的研究产物")).not.toBeInTheDocument();
    const openButton = within(resultBlock).getByRole("button", {
      name: "打开：核心文献研读报告",
    });
    openButton.focus();
    fireEvent.click(openButton);

    await waitFor(() =>
      expect(history.location.search).toBe("?artifactVersionId=artv_papsum_01"),
    );
    const fullscreenReport = await screen.findByTestId(
      "artifact-fullscreen-workspace",
    );
    await waitFor(() =>
      expect(fullscreenReport).toHaveTextContent(
        "The Revised TESS Input Catalog and Candidate Target List",
      ),
    );
    expect(
      fullscreenReport.querySelector("[data-artifact-version-id]"),
    ).toHaveAttribute("data-artifact-version-id", "artv_papsum_01");
    expect(fullscreenReport.querySelector("[data-source-mode]")).toBeNull();
    expect(
      within(fullscreenReport).queryByText("演示数据"),
    ).not.toBeInTheDocument();
    expect(fullscreenReport).toHaveAttribute("role", "dialog");
    expect(fullscreenReport).toHaveAttribute("aria-modal", "true");
    const returnButton = within(fullscreenReport).getByRole("button", {
      name: "返回研究",
    });
    await waitFor(() => expect(returnButton).toHaveFocus());

    fireEvent.click(returnButton);
    await waitFor(() =>
      expect(
        screen.queryByTestId("artifact-fullscreen-workspace"),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(history.location.search).toBe(""));
    await waitFor(() => expect(openButton).toHaveFocus());
    expect(screen.getByLabelText("右侧研究栏")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭右侧研究栏" }));
    expect(screen.getByLabelText("右侧研究栏")).toHaveAttribute(
      "data-collapsed",
      "true",
    );
    expect(screen.getByLabelText("右侧研究栏")).toHaveStyle({ width: "0px" });
    fireEvent.click(screen.getByRole("button", { name: "打开右侧研究栏" }));
    expect(screen.getByLabelText("右侧研究栏")).toBeInTheDocument();
  });

  it("does not present a partial artifact collection as completed research", async () => {
    const runtime = createTestRuntime();
    const originalGetRun = runtime.repositories.runs.getById.bind(
      runtime.repositories.runs,
    );
    vi.spyOn(runtime.repositories.runs, "getById").mockImplementation(
      async (runId) => {
        const run = await originalGetRun(runId);
        return run
          ? { ...run, status: "reasoning_literature", progress: 71 }
          : null;
      },
    );

    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    await screen.findByRole("heading", {
      name: "Exoplanet host-star integration",
      level: 1,
    });
    await waitFor(() =>
      expect(screen.queryByText("研究产物已生成")).not.toBeInTheDocument(),
    );
  });

  it("enters the Thread layout as soon as the first message is submitted", async () => {
    const runtime = createTestRuntime();
    const source = await runtime.repositories.projects.getById(TEST_PROJECT_ID);
    if (!source) throw new Error("Fixture project is missing.");
    const emptyProject = {
      ...source,
      activeContractId: null,
      latestRunId: null,
      threadSummary: {
        hasThreadEntries: false,
        latestThreadActor: null,
        hasUnansweredClarification: false,
      },
    };
    vi.spyOn(runtime.repositories.projects, "getById").mockResolvedValue(
      emptyProject,
    );
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [emptyProject],
      nextCursor: null,
    });
    vi.spyOn(runtime.repositories.researchThread, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    let resolveTurn: ((turn: ResearchTurn) => void) | undefined;
    vi.spyOn(runtime.repositories.researchThread, "submit").mockImplementation(
      () =>
        new Promise<ResearchTurn>((resolve) => {
          resolveTurn = resolve;
        }),
    );
    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    expect(
      await screen.findByRole("heading", { name: "开始你的研究" }),
    ).toBeInTheDocument();
    const composer = screen.getByRole("textbox", { name: "输入研究消息" });
    composer.textContent = "比较 TESS 与 Gaia 的观测选择偏差";
    fireEvent.input(composer);
    fireEvent.click(screen.getByRole("button", { name: "发送研究消息" }));

    expect(
      await screen.findByText("比较 TESS 与 Gaia 的观测选择偏差"),
    ).toBeInTheDocument();
    expect(screen.getByText("正在发送…")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "开始你的研究" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("chat-scroll-container")).toHaveClass("grow");

    await act(async () => {
      resolveTurn?.({
        outcome: "draft_ready",
        entries: [],
        activeDraftId: null,
        modelExecutionId: asEntityId("model-execution-first-turn"),
      });
    });
  });

  it("keeps two explicitly submitted identical messages as distinct Turns", async () => {
    const runtime = createTestRuntime();
    const message = "比较 TESS 与 Gaia 的观测选择偏差";
    let persistedEntries: readonly ResearchThreadEntry[] = [];
    vi.spyOn(runtime.repositories.researchThread, "list").mockImplementation(
      async () => ({ items: persistedEntries, nextCursor: null }),
    );
    const firstTurn = createUserTurn("same-message-first", 1, message);
    const secondTurn = createUserTurn("same-message-second", 2, message);
    let resolveSecondTurn: ((turn: ResearchTurn) => void) | undefined;
    const submit = vi
      .spyOn(runtime.repositories.researchThread, "submit")
      .mockImplementationOnce(async () => {
        persistedEntries = firstTurn.entries;
        return firstTurn;
      })
      .mockImplementationOnce(
        () =>
          new Promise<ResearchTurn>((resolve) => {
            resolveSecondTurn = (turn) => {
              persistedEntries = turn.entries;
              resolve(turn);
            };
          }),
      );
    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    const composer = await screen.findByRole("textbox", {
      name: "输入研究消息",
    });
    composer.textContent = message;
    fireEvent.input(composer);
    fireEvent.click(screen.getByRole("button", { name: "发送研究消息" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    await screen.findByText(message);

    composer.textContent = message;
    fireEvent.input(composer);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "发送研究消息" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "发送研究消息" }));

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText(message)).toHaveLength(2);

    await act(async () => {
      resolveSecondTurn?.({
        ...secondTurn,
        entries: [...firstTurn.entries, ...secondTurn.entries],
      });
    });
  });

  it("reports submit failures outside the workspace flow and restores the composer", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.researchThread, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    vi.spyOn(runtime.repositories.researchThread, "submit").mockRejectedValue(
      new Error("network unavailable"),
    );
    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    const composer = await screen.findByRole("textbox", {
      name: "输入研究消息",
    });
    composer.textContent = "比较 TESS 与 Gaia 的观测选择偏差";
    fireEvent.input(composer);
    fireEvent.click(screen.getByRole("button", { name: "发送研究消息" }));

    const toastTitle = await screen.findByText("消息发送失败");
    expect(screen.getByRole("main")).not.toContainElement(toastTitle);
    expect(composer).toHaveTextContent("比较 TESS 与 Gaia 的观测选择偏差");
    expect(
      screen.queryByRole("button", { name: "重试" }),
    ).not.toBeInTheDocument();
    expect(runtime.repositories.researchThread.submit).toHaveBeenCalledTimes(1);
  });

  it("keeps public share outside the private Session Gate", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.shares, "getPublic").mockResolvedValue(null);
    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
    expect(screen.queryByText("demo-token")).not.toBeInTheDocument();
  });

  it("replaces a missing or cross-session project deep link with the neutral workspace", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "getById").mockResolvedValue(null);
    const { history } = renderRoute("/workspace/hidden-project", runtime);

    expect(
      await screen.findByTestId("missing-project-notice"),
    ).toHaveTextContent("这个研究已不存在。");
    expect(history.location.pathname).toBe("/workspace");
    expect(
      screen.queryByRole("heading", { name: "页面载入失败" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("hidden-project")).not.toBeInTheDocument();
  });

  it("rejects an invalid project identifier before the ownership repository", async () => {
    const runtime = createTestRuntime();
    const getById = vi.spyOn(runtime.repositories.projects, "getById");
    renderRoute(`/workspace/${"a".repeat(129)}`, runtime);

    await screen.findByRole("heading", { name: "页面载入失败" });
    expect(screen.getByText("项目标识无效")).toBeInTheDocument();
    expect(getById).not.toHaveBeenCalled();
  });

  it("restores the persisted Thread and resets the composer when navigation changes owner", async () => {
    const runtime = createTestRuntime();
    const source = await runtime.repositories.projects.getById(
      asEntityId("proj_01JEXAMPLE"),
    );
    if (!source) throw new Error("Fixture project is missing.");
    const projectA = {
      ...source,
      id: asEntityId("project-a"),
      name: "Project A",
      activeContractId: null,
      latestRunId: null,
    };
    const projectB = {
      ...source,
      id: asEntityId("project-b"),
      name: "Project B",
      activeContractId: null,
      latestRunId: null,
    };
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [projectA, projectB],
      nextCursor: null,
    });
    vi.spyOn(runtime.repositories.projects, "getById").mockImplementation(
      async (id) =>
        [projectA, projectB].find((project) => project.id === id) ?? null,
    );
    const persistedEntry: ResearchThreadEntry = {
      id: asEntityId("entry-project-a"),
      projectId: projectA.id,
      sequence: 1,
      kind: "user_message",
      actor: "user",
      publicContent: "Project A persisted research message",
      structuredPayload: { answerToQuestionId: null },
      modelExecutionId: null,
      createdAt: "2026-08-11T00:00:00Z" as UtcIsoTimestamp,
    };
    vi.spyOn(runtime.repositories.researchThread, "list").mockImplementation(
      async (projectId) => ({
        items: projectId === projectA.id ? [persistedEntry] : [],
        nextCursor: null,
      }),
    );
    const { router } = renderRoute("/workspace/project-a", runtime);

    await screen.findByRole("heading", { name: "Project A", level: 1 });
    expect(
      await screen.findByText("Project A persisted research message"),
    ).toBeInTheDocument();
    const composer = screen.getByRole("textbox", { name: "输入研究消息" });
    composer.textContent = "Project A private research intent";
    fireEvent.input(composer);

    await act(async () => {
      await router.navigate({
        to: "/workspace/$projectId",
        params: { projectId: projectB.id },
      });
    });

    await screen.findByRole("heading", { name: "Project B", level: 1 });
    expect(
      screen.getByRole("textbox", { name: "输入研究消息" }),
    ).toHaveTextContent("");
    expect(
      screen.queryByText("Project A persisted research message"),
    ).not.toBeInTheDocument();
  });

  it("renders the polled Run snapshot instead of the create response", async () => {
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    const runtime = createTestRuntime();
    const projectId = asEntityId("proj_01JEXAMPLE");
    const source = await runtime.repositories.projects.getById(projectId);
    if (!source) throw new Error("Fixture project is missing.");
    const researchCatalog = {
      projectId,
      caseKey: source.caseKey,
      targetObjects: [
        {
          value: asEntityId("exoplanet_candidate"),
          label: "系外行星候选体",
          description: "",
          group: null,
        },
        {
          value: asEntityId("host_star"),
          label: "宿主恒星",
          description: "",
          group: null,
        },
      ],
      requestedFields: [
        {
          value: asEntityId("planet.toi_id"),
          label: "TOI 编号",
          description: "",
          group: null,
        },
        {
          value: asEntityId("star.tic_id"),
          label: "TIC 编号",
          description: "",
          group: null,
        },
      ],
      allowedSources: [
        {
          value: asEntityId("nasa_exoplanet_archive"),
          label: "NASA 系外行星档案",
          description: "",
          group: null,
        },
      ],
      outputRequirements: [
        {
          value: "dataset",
          label: "结构化数据",
          description: "",
          group: "common",
        },
        {
          value: "graph",
          label: "证据图谱",
          description: "",
          group: "common",
        },
      ],
      scientificSkills: [],
    } satisfies ResearchPlanningCatalog;
    vi.spyOn(
      runtime.repositories.researchCatalog,
      "getForProject",
    ).mockResolvedValue(researchCatalog);
    let projectRead: typeof source = {
      ...source,
      activeDraftId: asEntityId("rcd_01JTOUR"),
      activeContractId: null,
      latestRunId: null,
    };
    vi.spyOn(runtime.repositories.projects, "getById").mockImplementation(
      async () => projectRead,
    );
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [projectRead],
      nextCursor: null,
    });
    const createdRun: ResearchRun = {
      id: asEntityId("run-created-in-ui"),
      projectId,
      contractId: source.activeContractId ?? asEntityId("missing-contract"),
      executionMode: "live",
      status: "queued",
      progress: 0,
      revision: 1,
      parentRunId: null,
      derivationKind: "original",
      retryFromStep: null,
      cachePolicy: "disabled",
      startedAt: null,
      finishedAt: null,
      createdAt: "2026-08-11T00:00:00Z",
      updatedAt: "2026-08-11T00:00:00Z",
      latestEventSequence: 1,
      failureCode: null,
      failureSummary: null,
    };
    const createRun = vi
      .spyOn(runtime.repositories.runs, "create")
      .mockImplementation(async () => {
        projectRead = { ...projectRead, latestRunId: createdRun.id };
        return createdRun;
      });
    const seededContract = await runtime.repositories.contracts.getContractById(
      source.activeContractId ?? asEntityId("missing-contract"),
    );
    if (!seededContract) throw new Error("Fixture contract is missing.");
    vi.spyOn(runtime.repositories.contracts, "confirm").mockImplementation(
      async () => {
        projectRead = {
          ...projectRead,
          activeDraftId: null,
          activeContractId: seededContract.id,
        };
        return seededContract;
      },
    );
    const originalGetRun = runtime.repositories.runs.getById.bind(
      runtime.repositories.runs,
    );
    const getRun = vi
      .spyOn(runtime.repositories.runs, "getById")
      .mockImplementation(async (runId) => {
        if (runId === createdRun.id) {
          return {
            ...createdRun,
            status: "completed",
            progress: 100,
            finishedAt: "2026-08-11T00:02:00Z",
          };
        }
        const run = await originalGetRun(runId);
        return run;
      });
    vi.spyOn(runtime.repositories.runs, "listSteps").mockResolvedValue([]);
    renderRoute(`/workspace/${projectId}`, runtime);

    await screen.findByRole("heading", {
      name: "Exoplanet host-star integration",
      level: 1,
    });
    expect(
      runtime.queryClient.getQueryData<{ latestRunId: string | null }>(
        workspaceQueryKeys.project(projectId),
      )?.latestRunId,
    ).toBeNull();
    fireEvent.click(
      await screen.findByRole("button", { name: "研究协议 · 草稿" }),
    );
    const protocolDialog = await screen.findByRole("dialog");
    fireEvent.click(
      within(protocolDialog).getByRole("button", {
        name: "确认并开始研究",
      }),
    );

    await waitFor(() => expect(createRun).toHaveBeenCalledOnce());
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({ executionMode: "demo_replay" }),
    );
    await waitFor(() =>
      expect(
        runtime.queryClient.getQueryData<{ latestRunId: string | null }>(
          workspaceQueryKeys.project(projectId),
        )?.latestRunId,
      ).toBe(createdRun.id),
    );
    await waitFor(() => expect(getRun).toHaveBeenCalledWith(createdRun.id));
    await waitFor(() =>
      expect(
        runtime.queryClient.getQueryData<{ status: string }>(
          workspaceQueryKeys.run(projectId, createdRun.id),
        )?.status,
      ).toBe("completed"),
    );
    await screen.findByRole("region", { name: "Agent 消息流" });
    expect((await screen.findAllByText("研究已完成")).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.queryByRole("tab", { name: "上下文" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the confirmed protocol visible so research can start without reopening it", async () => {
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
    const runtime = createTestRuntime();
    const source = await runtime.repositories.projects.getById(TEST_PROJECT_ID);
    const draft = await runtime.repositories.contracts.getDraftById(
      asEntityId("rcd_01JEXAMPLE"),
    );
    if (!source || !draft || !source.activeContractId) {
      throw new Error("Fixture protocol state is incomplete.");
    }
    const contract = await runtime.repositories.contracts.getContractById(
      source.activeContractId,
    );
    if (!contract) throw new Error("Fixture contract is missing.");
    const catalog = {
      projectId: TEST_PROJECT_ID,
      caseKey: source.caseKey,
      targetObjects: draft.contract.targetObjects.map((value) => ({
        value,
        label: String(value),
        description: "",
        group: null,
      })),
      requestedFields: draft.contract.requestedFields.map((value) => ({
        value,
        label: String(value),
        description: "",
        group: null,
      })),
      allowedSources: draft.contract.sourceScope.allowedSources.map(
        (value) => ({
          value,
          label: String(value),
          description: "",
          group: null,
        }),
      ),
      outputRequirements: draft.contract.outputRequirements.map((value) => ({
        value,
        label: value,
        description: "",
        group: "common" as const,
      })),
      scientificSkills: [],
    } satisfies ResearchPlanningCatalog;

    let projectRead: ResearchProject = {
      ...source,
      activeDraftId: draft.id,
      activeContractId: null,
      latestRunId: null,
    };
    vi.spyOn(runtime.repositories.projects, "getById").mockImplementation(
      async () => projectRead,
    );
    vi.spyOn(runtime.repositories.projects, "list").mockImplementation(
      async () => ({ items: [projectRead], nextCursor: null }),
    );
    vi.spyOn(
      runtime.repositories.researchCatalog,
      "getForProject",
    ).mockResolvedValue(catalog);
    vi.spyOn(runtime.repositories.contracts, "getDraftById").mockResolvedValue({
      ...draft,
      status: "draft",
    });
    vi.spyOn(
      runtime.repositories.contracts,
      "getContractById",
    ).mockResolvedValue(contract);
    const confirm = vi
      .spyOn(runtime.repositories.contracts, "confirm")
      .mockImplementation(async () => {
        projectRead = {
          ...projectRead,
          activeDraftId: null,
          activeContractId: contract.id,
        };
        return contract;
      });
    const createRun = vi
      .spyOn(runtime.repositories.runs, "create")
      .mockImplementation(async (input) => ({
        id: asEntityId("run-one-action-start"),
        projectId: TEST_PROJECT_ID,
        contractId: input.contractId,
        executionMode: input.executionMode,
        status: "queued",
        progress: 0,
        revision: 1,
        parentRunId: null,
        derivationKind: "original",
        retryFromStep: null,
        cachePolicy: "disabled",
        startedAt: null,
        finishedAt: null,
        createdAt: "2026-08-14T00:00:00Z" as UtcIsoTimestamp,
        updatedAt: "2026-08-14T00:00:00Z" as UtcIsoTimestamp,
        latestEventSequence: 1,
        failureCode: null,
        failureSummary: null,
      }));

    renderRoute(`/workspace/${TEST_PROJECT_ID}`, runtime);

    fireEvent.click(
      await screen.findByRole("button", { name: "研究协议 · 草稿" }),
    );
    const protocolDialog = await screen.findByRole("dialog");
    await within(protocolDialog).findByRole("heading", {
      name: "研究协议草案",
    });
    fireEvent.click(
      within(protocolDialog).getByRole("button", { name: "确认并开始研究" }),
    );

    await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
    // One-action Confirm -> Create Run: the research starts from the single
    // confirm click, so no separate start control is required afterwards.
    await waitFor(() => expect(createRun).toHaveBeenCalledOnce());
    expect(createRun).toHaveBeenCalledWith(
      expect.objectContaining({
        contractId: contract.id,
        executionMode: "demo_replay",
      }),
    );
    expect(
      await screen.findByRole("button", { name: "研究协议 · 已确认" }),
    ).toBeInTheDocument();
  });
});
