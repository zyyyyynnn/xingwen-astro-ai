import { QueryClientProvider } from "@tanstack/react-query";
import { asEntityId, type ResearchContractInput } from "@xingwen/domain";
import { researchAdapter } from "@xingwen/research-adapter";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  OpenHandsWorkspaceRoot,
  type ResearchWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import { useCommandMenuStore } from "../upstream/openhands/src/stores/command-menu-store";
import { useSidebarStore } from "../upstream/openhands/src/stores/sidebar-store";
import { ContractCheckpoint } from "./components/contract-checkpoint";
import { createTestRuntime } from "./test/runtime";
import { WorkspaceEntry } from "./workspace-host";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  useCommandMenuStore.setState({ isOpen: false });
  useSidebarStore.setState({ collapsed: false });
});

describe("Workspace product UI", () => {
  it("teaches the empty Project state and creates through the real mutation", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    const onOpenProject = vi.fn();
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <WorkspaceEntry runtime={runtime} onOpenProject={onOpenProject} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("建立第一个研究项目")).toBeInTheDocument();
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
    expect(screen.getByLabelText("工作台侧栏")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建研究项目" }));
    fireEvent.change(screen.getByLabelText("项目名称"), {
      target: { value: "近邻宿主星比较" },
    });
    fireEvent.change(screen.getByLabelText("研究说明"), {
      target: { value: "比较关键恒星参数" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建并进入项目" }));

    await waitFor(() => expect(onOpenProject).toHaveBeenCalledOnce());
  });

  it("keeps Contract fields explicit and reuses domain invariant validation", async () => {
    const onCreateDraft =
      vi.fn<
        (intent: string, contract: ResearchContractInput) => Promise<void>
      >();
    onCreateDraft.mockResolvedValue(undefined);
    render(
      <ContractCheckpoint
        intent="比较近邻宿主星"
        draft={null}
        contract={null}
        run={null}
        pendingAction={null}
        errorMessage={null}
        onCreateDraft={onCreateDraft}
        onSaveDraft={vi.fn()}
        onConfirmContract={vi.fn()}
        onCreateRun={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("研究目标"), {
      target: { value: "比较目标宿主星的质量与半径" },
    });
    fireEvent.change(screen.getByLabelText("目标对象"), {
      target: { value: "Kepler-186" },
    });
    fireEvent.change(screen.getByLabelText("请求字段"), {
      target: { value: "stellar_mass, stellar_radius" },
    });
    fireEvent.change(screen.getByLabelText("允许来源"), {
      target: { value: "nasa_exoplanet_archive" },
    });
    fireEvent.change(screen.getByLabelText("输出类型"), {
      target: { value: "dataset, paper_collection" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建协议草稿" }));

    await waitFor(() => expect(onCreateDraft).toHaveBeenCalledOnce());
    expect(onCreateDraft.mock.calls[0]?.[1]).toMatchObject({
      dataRequirements: { unitPolicy: "canonical" },
      paperSearchScope: { maxCandidates: 20 },
      evidenceRequirements: { minimumCoverage: 1 },
      qualityConstraints: { sourceCompletenessMin: 1, unitConsistencyMin: 1 },
    });
  });

  it("renders only Research Adapter public activity and keeps OpenHands mechanics", async () => {
    const activity = researchAdapter.toActivityPresentationEvent({
      runId: asEntityId("run-ui"),
      sequence: 1,
      eventType: asEntityId("run.queued"),
      stepKey: null,
      progress: null,
      publicMessage: "研究运行已进入队列",
      artifactVersionIds: [],
      occurredAt: "2026-08-11T00:00:00Z",
    });
    const runtime: ResearchWorkspaceRuntime = {
      project: { name: "宿主星研究" },
      run: { status: "queued", executionMode: "live" },
      navigation: {
        projects: [],
        onOpenProject: vi.fn(),
        onNewResearch: vi.fn(),
        onLogout: vi.fn(),
      },
      composer: {
        canSubmitIntent: false,
        submitting: false,
        submitIntent: vi.fn(),
      },
      activation: null,
      activityEvents: [activity],
      contextPanel: <p>协议已确认</p>,
    };
    render(<OpenHandsWorkspaceRoot runtime={runtime} />);

    fireEvent.click(screen.getByRole("tab", { name: "活动" }));
    expect(screen.getByRole("log", { name: "研究活动" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Run queued/u }));
    expect(screen.getByText("研究运行已进入队列")).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "退出系统" }));
    expect(runtime.navigation.onLogout).toHaveBeenCalledOnce();

    const trigger = screen.getByRole("button", { name: "打开命令菜单" });
    trigger.focus();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const search = await screen.findByRole("combobox", { name: "搜索命令" });
    await waitFor(() => expect(search).toHaveFocus());
  });
});
