/**
 * Literature Summary Reading Workspace React tests (A-06).
 *
 * Rendered through the real router + fixture runtime, plus an HTTP runtime
 * whose paper-summary repository is the REAL `createHttpRepositories` port
 * reading the pipeline-generated fixture through an injected fetch (HTTP
 * client, envelope parsing and contract validation all execute). Covers the
 * five reading regions, the three support statuses, statement → Evidence
 * selection into the Provenance Observatory, every non-ready state and the
 * non-ready idle reset.
 *
 * Boundary note: the HTTP path here is an HTTP-adapter integration against a
 * served copy of the validated fixture — not a real FastAPI/Compose runtime.
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
  createHttpRepositories,
  NetworkError,
  NotFoundError,
  paperSummaryReadFixture,
  ValidationError,
} from "@xingwen/data-access";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceRuntimeBoundaries } from "../../boundaries";
import { createAppRouter } from "../../router";
import { createWorkspaceRuntime } from "../../runtime";
import {
  LiteratureSummaryView,
  LiteratureSummaryWorkspace,
} from "./literature-summary-workspace";

const HTTP_BASE = "http://paper-summary-test.local";
const SUMMARY_VERSION_ID = paperSummaryReadFixture.artifact_version_id;

const GOAL_TEXT =
  "The paper delivers The Revised TESS Input Catalog and Candidate Target List to prioritize TESS targets.";
const LIMITATION_TEXT =
  "The catalog is claimed to be complete for all dwarf stars, without any cited evidence.";
const METHOD_TEXT =
  "The catalog compiles stellar parameters from photometric catalogs and parallax measurements.";

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

function sessionStub(): SessionManager {
  const sessionInfo: Awaited<ReturnType<SessionManager["ensureSession"]>> = {
    status: "active",
    createdAt: "2026-07-22T00:00:00Z",
    expiresAt: "2026-07-22T01:00:00Z",
    quota: {},
    csrfToken: "csrf-test-only",
  };
  return {
    ensureSession: vi.fn(async () => sessionInfo),
    getCurrent: () => null,
    revokeSession: vi.fn(async () => {}),
    attachCsrf: vi.fn(),
    onSessionExpired: vi.fn(() => () => {}),
    notifyExpired: vi.fn(),
  };
}

/** Serve the pipeline-generated fixture over the B-07 read protocol. */
function summaryHttpFetch(): typeof fetch {
  return async (input: RequestInfo | URL) => {
    const url = new URL(
      typeof input === "string" || input instanceof URL
        ? String(input)
        : input.url,
    );
    const meta = {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T09:00:00Z",
    };
    if (
      url.pathname ===
      `/api/artifact-versions/${SUMMARY_VERSION_ID}/paper-summary`
    ) {
      return Response.json({
        data: paperSummaryReadFixture,
        meta,
        links: { self: url.pathname },
      });
    }
    return Response.json(
      { type: "about:blank", status: 404, code: "RESOURCE_NOT_FOUND" },
      { status: 404 },
    );
  };
}

/**
 * HTTP runtime for the summary reading path: the paper-summary repository is
 * the real HTTP port; the surrounding workspace repositories stay fixture so
 * the page shell can load without replicating every endpoint.
 */
function httpSummaryRuntime(): WorkspaceRuntimeBoundaries {
  const fixture = fixtureRuntime();
  const session = sessionStub();
  const httpRepos = createHttpRepositories({
    baseUrl: HTTP_BASE,
    fetchImpl: summaryHttpFetch(),
    session,
  });
  return {
    adapterKind: "http",
    repositories: {
      ...fixture.repositories,
      paperSummary: httpRepos.paperSummary,
    },
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

async function openPaperSummary() {
  const artifactButton = await screen.findByRole("button", {
    name: "Paper summary",
  });
  fireEvent.click(artifactButton);
  await screen.findByRole("heading", { name: "文献总结阅读" });
  // Wait for the summary load to settle (ready or a non-ready state).
  await waitFor(() => {
    expect(
      screen.queryByText("正在读取文献总结产物。"),
    ).not.toBeInTheDocument();
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("LiteratureSummaryWorkspace — fixture main path", () => {
  it("renders the five reading regions with the real fixture content", async () => {
    renderWorkspace(fixtureRuntime());
    await openPaperSummary();

    for (const title of [
      "研究目标",
      "研究方法",
      "使用数据集",
      "核心发现",
      "局限与未来工作",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: GOAL_TEXT })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: METHOD_TEXT }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("The catalog release analyzed here dates to 2019."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "The published catalog is registered under DOI 10.3847/1538-3881/ab3467.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(LIMITATION_TEXT)).toBeInTheDocument();
    // Every fixture region carries statements, so the explicit empty-region
    // marker never appears — and no fabricated rows either.
    expect(screen.queryByText("本区域无陈述。")).not.toBeInTheDocument();
  });

  it("shows orthogonal mode labels and full producer provenance", async () => {
    renderWorkspace(fixtureRuntime());
    await openPaperSummary();

    const provenance = screen.getByTestId("paper-summary-provenance");
    expect(provenance).toHaveTextContent("execution: Demo Replay");
    expect(provenance).toHaveTextContent("source: Fixture");
    expect(provenance).not.toHaveTextContent("Fixture / Demo Replay");
    expect(provenance).toHaveTextContent(
      `paper: ${paperSummaryReadFixture.summary.paper_id}`,
    );
    expect(provenance).toHaveTextContent(paperSummaryReadFixture.paper.title);
    expect(provenance).toHaveTextContent(
      (paperSummaryReadFixture.paper.authors ?? []).join("、"),
    );
    expect(provenance).toHaveTextContent(
      String(paperSummaryReadFixture.paper.year),
    );
    expect(provenance).toHaveTextContent("版本 1（初始版本）");
    expect(provenance).toHaveTextContent(
      "benchmark: exoplanet_host_star.paper_reasoning v1.3.0",
    );
    expect(provenance).toHaveTextContent("model: fixture-model");
    expect(provenance).toHaveTextContent("prompt: paper_summary v2");
    expect(provenance).toHaveTextContent(
      `hash ${paperSummaryReadFixture.summary.producer.prompt_hash}`,
    );
    expect(provenance).toHaveTextContent(
      "producer: xingwen.paper_summary v1.0.0（completed）",
    );
    expect(provenance).toHaveTextContent("输入 PaperCollection artv_papcol_01");
    expect(provenance).toHaveTextContent(
      paperSummaryReadFixture.summary.input_versions
        .paper_collection_output_hash,
    );
    expect(screen.getByText(/确定性演示数据（Fixture/u)).toBeInTheDocument();
  });

  it("opens the three-column comparison from the real workspace", async () => {
    renderWorkspace(fixtureRuntime());
    await openPaperSummary();

    fireEvent.click(screen.getByRole("button", { name: "打开文献总结对比" }));

    expect(
      await screen.findByRole("region", { name: "文献总结对比" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "对比列 1" })).toHaveTextContent(
      paperSummaryReadFixture.paper.title,
    );
    expect(
      screen.getByRole("article", { name: "对比列 2（空）" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "对比列 3（空）" }),
    ).toBeInTheDocument();
  });

  it("marks supported, unsupported and unverifiable statements distinctly", async () => {
    renderWorkspace(fixtureRuntime());
    await openPaperSummary();

    expect(screen.getAllByText("有证据支持").length).toBeGreaterThan(0);
    expect(screen.getAllByText("无证据（未证实）").length).toBeGreaterThan(0);
    expect(screen.getAllByText("证据不可核验").length).toBeGreaterThan(0);
    // The unsupported limitation has no generic Evidence: the gap is stated
    // explicitly and never presented as a verified fact.
    expect(
      screen.getByText("无可核验证据：该陈述不能视为已验证事实。"),
    ).toBeInTheDocument();
  });

  it("lists inline summary evidence with quotes and safe locators", async () => {
    renderWorkspace(fixtureRuntime());
    await openPaperSummary();

    // Metadata locator: field + https link through the safeExternalUrl guard.
    expect(screen.getByText(/元数据字段 title/u)).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", {
        name: "https://doi.org/10.3847/1538-3881/ab3467",
      }).length,
    ).toBeGreaterThan(0);
    // Text locator: section and range, no fabricated link.
    expect(
      screen.getByText(
        /原文位置：章节 Methods・范围 paragraph 2, sentences 1-3/u,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "“Stellar parameters are compiled from all-sky photometric catalogs and parallax measurements.”",
      ),
    ).toBeInTheDocument();
  });

  it("clicking a supported statement selects its generic Evidence", async () => {
    const runtime = fixtureRuntime();
    renderWorkspace(runtime);
    await openPaperSummary();

    fireEvent.click(screen.getByRole("button", { name: GOAL_TEXT }));

    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      expect(state.status).toBe("draft");
      if (state.status === "draft") {
        expect(state.draft.pinnedEvidenceIds).toContain("evd_papsum_03");
      }
    });
    const observatory = within(
      screen.getByRole("complementary", { name: "Provenance Observatory" }),
    );
    expect(
      await observatory.findByRole("button", { name: "evd_papsum_03" }),
    ).toBeInTheDocument();
  });

  it("never selects Evidence for a statement without a generic record", async () => {
    const runtime = fixtureRuntime();
    renderWorkspace(runtime);
    await openPaperSummary();

    // The statement without a generic Evidence record is disabled: clicking
    // it must be a no-op instead of a silently enabled dead button.
    const limitationButton = screen.getByRole("button", {
      name: LIMITATION_TEXT,
    });
    expect(limitationButton).toBeDisabled();
    fireEvent.click(limitationButton);

    // No fabricated Evidence: the workspace draft never pins anything.
    await waitFor(() => {
      const state = runtime.workspaceController.getState();
      if (state.status === "draft") {
        expect(state.draft.pinnedEvidenceIds).toEqual([]);
      }
    });
  });

  it("renders the same domain review through the real HTTP repository", async () => {
    const fixture = fixtureRuntime();
    const [fixtureReview, httpReview] = await Promise.all([
      fixture.repositories.paperSummary.getSummary(SUMMARY_VERSION_ID as never),
      httpSummaryRuntime().repositories.paperSummary.getSummary(
        SUMMARY_VERSION_ID as never,
      ),
    ]);
    // Same domain model from both adapters, byte for byte.
    expect(httpReview).toEqual(fixtureReview);

    renderWorkspace(
      httpSummaryRuntime(),
      `/workspace?projectId=${String(fixture.bootstrap.projectId)}&runId=${String(fixture.bootstrap.runId)}`,
    );
    await openPaperSummary();
    const provenance = screen.getByTestId("paper-summary-provenance");
    expect(provenance).toHaveTextContent("source: Fixture");
    expect(screen.getByRole("button", { name: GOAL_TEXT })).toBeInTheDocument();
  });
});

describe("LiteratureSummaryWorkspace — non-ready states and retry", () => {
  function runtimeWithSummary(
    getSummary: () => Promise<never> | Promise<unknown>,
  ): WorkspaceRuntimeBoundaries {
    const fixture = fixtureRuntime();
    return {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        paperSummary: {
          getSummary: vi.fn(getSummary) as never,
        },
      },
    };
  }

  it("shows the unavailable state for an unknown version 404", async () => {
    renderWorkspace(
      runtimeWithSummary(async () => {
        throw new NotFoundError("missing", "ARTIFACT_VERSION_NOT_FOUND");
      }),
    );
    await openPaperSummary();
    expect(
      await screen.findByText(
        "当前 ArtifactVersion 不存在或不可访问，请重新选择 Artifact。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "重新读取当前版本" }),
    ).toBeInTheDocument();
  });

  it("shows the unavailable state for any other 404 code", async () => {
    renderWorkspace(
      runtimeWithSummary(async () => {
        throw new NotFoundError("missing", "RESOURCE_NOT_FOUND");
      }),
    );
    await openPaperSummary();
    expect(
      await screen.findByText(
        "当前 ArtifactVersion 不存在或不可访问，请重新选择 Artifact。",
      ),
    ).toBeInTheDocument();
  });

  it("shows the schema-invalid state", async () => {
    renderWorkspace(
      runtimeWithSummary(async () => {
        throw new ValidationError("bad", "SCHEMA_VALIDATION_FAILED", []);
      }),
    );
    await openPaperSummary();
    expect(await screen.findByText(/产物校验失败/u)).toBeInTheDocument();
  });

  it("recovers from a network error after retry", async () => {
    const fixture = fixtureRuntime();
    let calls = 0;
    const runtime: WorkspaceRuntimeBoundaries = {
      ...fixture,
      repositories: {
        ...fixture.repositories,
        paperSummary: {
          getSummary: vi.fn(async (id) => {
            calls += 1;
            if (calls === 1) throw new NetworkError("offline");
            return fixture.repositories.paperSummary.getSummary(id);
          }) as never,
        },
      },
    };
    renderWorkspace(runtime);
    await openPaperSummary();
    const retry = await screen.findByRole("button", {
      name: "重新读取当前版本",
    });
    expect(
      screen.getByText("网络错误，无法读取文献总结数据。"),
    ).toBeInTheDocument();
    fireEvent.click(retry);
    expect(
      await screen.findByRole("button", { name: GOAL_TEXT }),
    ).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});

describe("LiteratureSummaryWorkspace — stale summary cleanup", () => {
  it("never shows the previous version's summary after switching versions", async () => {
    const fixture = fixtureRuntime();
    const review = await fixture.repositories.paperSummary.getSummary(
      SUMMARY_VERSION_ID as never,
    );
    const repository = {
      getSummary: vi.fn((id: unknown) =>
        String(id) === SUMMARY_VERSION_ID
          ? Promise.resolve(review)
          : new Promise<never>(() => {}),
      ),
    } as never;
    const noop = () => {};
    const { rerender } = render(
      <LiteratureSummaryWorkspace
        artifactVersionId={SUMMARY_VERSION_ID as never}
        repository={repository}
        executionMode="demo_replay"
        ready
        disabled={false}
        selectedEvidenceId={null}
        onSelectEvidence={noop}
      />,
    );
    await screen.findByRole("button", { name: GOAL_TEXT });

    rerender(
      <LiteratureSummaryWorkspace
        artifactVersionId={"artv_other_version" as never}
        repository={repository}
        executionMode="demo_replay"
        ready
        disabled={false}
        selectedEvidenceId={null}
        onSelectEvidence={noop}
      />,
    );
    // The slow second version must show loading, never the stale summary.
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: GOAL_TEXT }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("正在读取文献总结产物。")).toBeInTheDocument();
  });

  it("resets to idle when the session is no longer ready", async () => {
    const fixture = fixtureRuntime();
    const noop = () => {};
    const props = {
      artifactVersionId: SUMMARY_VERSION_ID as never,
      repository: fixture.repositories.paperSummary,
      executionMode: "demo_replay" as const,
      disabled: false,
      selectedEvidenceId: null,
      onSelectEvidence: noop,
    };
    const { rerender } = render(
      <LiteratureSummaryWorkspace {...props} ready />,
    );
    await screen.findByRole("button", { name: GOAL_TEXT });

    rerender(<LiteratureSummaryWorkspace {...props} ready={false} />);
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: GOAL_TEXT }),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText("正在读取文献总结产物。")).toBeInTheDocument();
  });
});

describe("LiteratureSummaryView — cached provenance", () => {
  it("shows cache applicability, live failure and immutable origin", async () => {
    const fixture = fixtureRuntime();
    const review = await fixture.repositories.paperSummary.getSummary(
      SUMMARY_VERSION_ID as never,
    );

    render(
      <LiteratureSummaryView
        review={{
          ...review,
          sourceMode: "cached",
          cacheAudits: [
            {
              sourceId: "crossref" as never,
              sourceSnapshotId: "snapshot-cached" as never,
              cacheVersion: "cache-v3",
              cacheApplicability: "same normalized query",
              liveFailureClass: "timeout",
              liveFailureCode: "CROSSREF_TIMEOUT",
              originRunId: "run-origin" as never,
              originArtifactVersionId: "version-origin" as never,
            },
          ],
        }}
        executionMode="live"
        disabled={false}
        selectedEvidenceId={null}
        onSelectEvidence={() => {}}
      />,
    );

    const audit = screen.getByRole("note", { name: "Cached 来源审计" });
    expect(audit).toHaveTextContent("cache-v3");
    expect(audit).toHaveTextContent("same normalized query");
    expect(audit).toHaveTextContent("timeout / CROSSREF_TIMEOUT");
    expect(audit).toHaveTextContent("run-origin / version-origin");
  });
});
