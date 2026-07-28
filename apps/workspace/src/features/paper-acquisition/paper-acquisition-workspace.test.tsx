/**
 * Paper Acquisition Workspace React tests (A-05).
 *
 * Rendered through the real router + fixture runtime (and an HTTP-shaped
 * runtime for adapter parity), covering: review visibility (query, sources,
 * sort, reasons, duplicates, conflicts), filtering without rank changes,
 * candidate selection updating the Observatory, evidence selection feeding
 * pin/Share, Demo Replay labelling, and every non-ready state with retry.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import type { SessionManager } from "@xingwen/data-access";
import {
  NotFoundError,
  RateLimitedError,
  UpstreamError,
  ValidationError,
  NetworkError,
} from "@xingwen/data-access";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceRuntimeBoundaries } from "../../boundaries";
import { createAppRouter } from "../../router";
import { createWorkspaceRuntime } from "../../runtime";

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

function renderWorkspace(
  boundaries: WorkspaceRuntimeBoundaries,
  initialPath = "/workspace",
) {
  const history = createMemoryHistory({ initialEntries: [initialPath] });
  const router = createAppRouter(boundaries, history);
  render(<RouterProvider router={router} />);
  return router;
}

async function openRetrievedPapers() {
  const artifactButton = await screen.findByRole("button", {
    name: "Retrieved papers",
  });
  fireEvent.click(artifactButton);
  await screen.findByRole("heading", { name: "论文获取与候选审查" });
  // Wait for the review load to settle (ready or a non-ready state).
  await waitFor(() => {
    expect(
      screen.queryByText("正在读取论文获取产物与候选列表。"),
    ).not.toBeInTheDocument();
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PaperAcquisitionWorkspace — fixture main path", () => {
  it("shows query, sources, sort, metrics and the Demo Replay label", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    expect(
      screen.getByText(/Query: toi-1234 host star parameters/u),
    ).toBeInTheDocument();
    expect(screen.getByText(/排序: relevance_desc/u)).toBeInTheDocument();
    expect(screen.getByText(/候选上限: 100/u)).toBeInTheDocument();
    expect(screen.getByText(/年份: 2018–2026/u)).toBeInTheDocument();
    const sourceList = screen.getByRole("list", { name: "来源执行" });
    expect(sourceList).toHaveTextContent("nasa_ads");
    expect(sourceList).toHaveTextContent("arxiv");
    expect(
      screen.getByText(/source: Fixture \/ Demo Replay/u),
    ).toBeInTheDocument();
    expect(screen.getByText(/Demo Replay 确定性演示数据/u)).toBeInTheDocument();
    expect(
      screen.getByText(/benchmark: exoplanet_host_star.paper_acquisition/u),
    ).toBeInTheDocument();
    expect(screen.getByText(/候选 4/u)).toBeInTheDocument();
    expect(screen.getByText(/入选 2/u)).toBeInTheDocument();
  });

  it("lists candidates in stable order with reasons, duplicates and conflicts", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    const list = screen.getByRole("list", { name: "候选论文" });
    const items = list.querySelectorAll("li.candidate-item");
    expect(items).toHaveLength(4);
    expect(items[0]?.textContent).toContain("#1");
    expect(items[1]?.textContent).toContain(
      "排除原因：Duplicate of canonical paper paper_01 (DOI match)",
    );
    expect(items[1]?.textContent).toContain("重复组 dupg_01");
    expect(items[1]?.textContent).toContain("不确定匹配（year）");
    expect(items[3]?.textContent).toContain(
      "排除原因：Relevance 0.31 is below the selection threshold",
    );
  });

  it("keeps original stableRank when filtering and resets cleanly", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.change(screen.getByLabelText("入选状态"), {
      target: { value: "excluded" },
    });
    await screen.findByText(/显示 2 \/ 4 项/u);
    const list = screen.getByRole("list", { name: "候选论文" });
    const ranks = [...list.querySelectorAll(".candidate-rank")].map(
      (node) => node.textContent,
    );
    // Filtering hides rows but never renumbers the server ranking.
    expect(ranks).toEqual(["#2", "#4"]);

    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
    await screen.findByText(/显示 4 \/ 4 项/u);
  });

  it("filters by text and by duplicates without reordering", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.change(screen.getByLabelText("标题或作者"), {
      target: { value: "Spectroscopist" },
    });
    await screen.findByText(/显示 1 \/ 4 项/u);
    expect(
      screen.getByRole("list", { name: "候选论文" }).textContent,
    ).toContain("#3");

    fireEvent.change(screen.getByLabelText("标题或作者"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("重复与冲突"), {
      target: { value: "duplicates" },
    });
    await screen.findByText(/显示 2 \/ 4 项/u);
  });

  it("renders the non-http candidate URL as plain text, never a link", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    expect(
      screen.getByText(/ftp:\/\/mirror\.example\.org\/flares\.pdf/u),
    ).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    for (const link of links) {
      expect(link.getAttribute("href") ?? "").not.toContain("ftp://");
    }
    // Safe https URLs do render as links.
    expect(
      screen.getByRole("link", { name: "https://arxiv.org/abs/2406.05678" }),
    ).toBeInTheDocument();
  });

  it("selecting a candidate updates the Provenance Observatory", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Host-star Parameters of TOI-1234 from High-resolution Spectroscopy",
      }),
    );
    await screen.findByText("cand_paper_03 / canonical paper_02");
    const observatory = within(
      screen.getByRole("complementary", { name: "Provenance Observatory" }),
    );
    expect(
      observatory.getByText("snap_paper_arxiv_01 / arxiv"),
    ).toBeInTheDocument();
    expect(
      observatory.getByText(/retrieved 2026-07-21T08:24:30Z/u),
    ).toBeInTheDocument();
    expect(
      observatory.getByText(/license: arXiv metadata terms/u),
    ).toBeInTheDocument();
  });

  it("selecting candidate evidence pins it for the Share chain", async () => {
    const runtime = fixtureRuntime();
    renderWorkspace(runtime);
    await openRetrievedPapers();

    // The canonical and its duplicate share a title; pick the top-ranked one.
    fireEvent.click(
      screen.getAllByRole("button", {
        name: "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
      })[0]!,
    );
    const evidenceButton = await screen.findByRole("button", {
      name: "打开 Evidence evd_paper_01",
    });
    fireEvent.click(evidenceButton);

    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.pinnedEvidenceIds).toContain("evd_paper_01");
      }
    });
    // The generic Evidence panel now shows the pinned candidate evidence.
    expect(
      await screen.findByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/evd_paper_01/u).length).toBeGreaterThan(0);
  });

  it("renders through the same component under an HTTP-shaped runtime", async () => {
    const fixture = fixtureRuntime();
    renderWorkspace(
      httpShapedRuntime(fixture),
      `/workspace?projectId=${String(fixture.bootstrap.projectId)}&runId=${String(fixture.bootstrap.runId)}`,
    );
    await openRetrievedPapers();
    expect(
      screen.getByText(/source: Fixture \/ Demo Replay/u),
    ).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "候选论文" })).toBeInTheDocument();
  });
});

describe("PaperAcquisitionWorkspace — non-ready states and retry", () => {
  function runtimeWithReview(
    getReview: () => Promise<never> | Promise<unknown>,
  ): WorkspaceRuntimeBoundaries {
    const fixture = fixtureRuntime();
    return {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        paperAcquisition: {
          getReview: vi.fn(getReview) as never,
        },
      },
    };
  }

  it("shows the empty state for an empty collection", async () => {
    renderWorkspace(
      runtimeWithReview(async () => {
        throw new NotFoundError("empty", "PAPER_COLLECTION_EMPTY");
      }),
    );
    await openRetrievedPapers();
    expect(
      await screen.findByText("当前 ArtifactVersion 没有候选论文。"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "重新读取当前版本" }),
    ).toBeInTheDocument();
  });

  it("shows rate limiting with the retry window", async () => {
    renderWorkspace(
      runtimeWithReview(async () => {
        throw new RateLimitedError("slow down", 30_000);
      }),
    );
    await openRetrievedPapers();
    expect(
      await screen.findByText(/论文来源限流。约 30 秒后可重试。/u),
    ).toBeInTheDocument();
  });

  it("shows the source failure state", async () => {
    renderWorkspace(
      runtimeWithReview(async () => {
        throw new UpstreamError("bad", "PAPER_SOURCE_FAILED", 502);
      }),
    );
    await openRetrievedPapers();
    expect(await screen.findByText(/论文来源失败/u)).toBeInTheDocument();
  });

  it("shows the schema-invalid state", async () => {
    renderWorkspace(
      runtimeWithReview(async () => {
        throw new ValidationError("bad", "SCHEMA_VALIDATION_FAILED", []);
      }),
    );
    await openRetrievedPapers();
    expect(await screen.findByText(/产物校验失败/u)).toBeInTheDocument();
  });

  it("recovers from a network error after retry", async () => {
    const fixture = fixtureRuntime();
    let calls = 0;
    const runtime: WorkspaceRuntimeBoundaries = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        paperAcquisition: {
          getReview: vi.fn(async (id) => {
            calls += 1;
            if (calls === 1) throw new NetworkError("offline");
            return fixture.repositories.paperAcquisition.getReview(id);
          }) as never,
        },
      },
    };
    renderWorkspace(runtime);
    await openRetrievedPapers();
    const retry = await screen.findByRole("button", {
      name: "重新读取当前版本",
    });
    expect(screen.getByText(/网络错误/u)).toBeInTheDocument();
    fireEvent.click(retry);
    expect(
      await screen.findByRole("list", { name: "候选论文" }),
    ).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});
