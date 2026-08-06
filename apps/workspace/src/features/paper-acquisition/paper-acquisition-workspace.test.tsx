/**
 * Paper Acquisition Workspace React tests (A-05, post-merge corrective fix).
 *
 * Rendered through the real router + fixture runtime, plus an HTTP runtime
 * whose paper-acquisition repository is the REAL `createHttpRepositories`
 * port reading the pipeline-generated fixture through an injected fetch
 * (HTTP client, envelope parsing, contract parser and cursor pagination all
 * execute). Covers review visibility, filtering without rank changes,
 * candidate/Evidence selection, orthogonal execution/source labelling, every
 * non-ready state (incl. the non-empty 404) and stale-review cleanup.
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
  paperCandidateReadsFixture,
  paperCollectionReadFixture,
  RateLimitedError,
  UpstreamError,
  ValidationError,
} from "@xingwen/data-access";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceRuntimeBoundaries } from "../../boundaries";
import { createAppRouter } from "../../router";
import { createWorkspaceRuntime } from "../../runtime";
import { PaperAcquisitionWorkspace } from "./paper-acquisition-workspace";

const HTTP_BASE = "http://paper-test.local";

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

/**
 * Serve the pipeline-generated fixture over the B-06 read protocol: envelope
 * for the collection, 2-item cursor pages for the candidates. This drives
 * the real HttpClient → contract parser → cursor loop → assembly chain.
 */
function paperHttpFetch(
  collection: unknown = paperCollectionReadFixture,
): typeof fetch {
  const versionId = paperCollectionReadFixture.artifact_version_id;
  return async (input: RequestInfo | URL) => {
    const url = new URL(
      typeof input === "string" || input instanceof URL
        ? String(input)
        : input.url,
    );
    const meta = {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:00:00Z",
    };
    if (
      url.pathname === `/api/artifact-versions/${versionId}/paper-collection`
    ) {
      return Response.json({
        data: collection,
        meta,
        links: { self: url.pathname },
      });
    }
    if (
      url.pathname === `/api/artifact-versions/${versionId}/paper-candidates`
    ) {
      const cursor = url.searchParams.get("cursor");
      let start = 0;
      if (cursor) {
        const index = paperCandidateReadsFixture.findIndex(
          (item) => item.candidate.candidate_id === cursor,
        );
        if (index === -1) {
          return Response.json(
            { type: "about:blank", status: 400, code: "INVALID_CURSOR" },
            { status: 400 },
          );
        }
        start = index + 1;
      }
      const page = paperCandidateReadsFixture.slice(start, start + 2);
      const hasMore = start + page.length < paperCandidateReadsFixture.length;
      return Response.json({
        data: page,
        page: {
          next_cursor: hasMore
            ? (page[page.length - 1]?.candidate.candidate_id ?? null)
            : null,
          has_more: hasMore,
          limit: 2,
        },
        meta,
      });
    }
    return Response.json(
      { type: "about:blank", status: 404, code: "RESOURCE_NOT_FOUND" },
      { status: 404 },
    );
  };
}

/**
 * HTTP runtime for the paper review path: the paper-acquisition repository
 * is the real HTTP port; the surrounding workspace repositories stay fixture
 * so the page shell can load without replicating every endpoint.
 */
function httpPaperRuntime(): WorkspaceRuntimeBoundaries {
  const fixture = fixtureRuntime();
  const session = sessionStub();
  const httpRepos = createHttpRepositories({
    baseUrl: HTTP_BASE,
    fetchImpl: paperHttpFetch(),
    session,
  });
  return {
    adapterKind: "http",
    repositories: {
      ...fixture.repositories,
      paperAcquisition: httpRepos.paperAcquisition,
    },
    tour: fixture.tour,
    workspaceController: fixture.workspaceController,
    queryClient: fixture.queryClient,
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

const TOP_TITLE =
  "TESS Objects of Interest Catalog from the TESS Prime Mission";
const REVISED_TITLE =
  "The Revised TESS Input Catalog and Candidate Target List";

describe("PaperAcquisitionWorkspace — fixture main path", () => {
  it("shows query, sources, metrics and orthogonal mode labels", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    // Frozen-scenario query facts (2014–2021, real normalized keywords).
    expect(
      screen.getByText(
        paperCollectionReadFixture.collection.query.normalized_query_string,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("2014–2021")).toBeInTheDocument();
    expect(
      screen.getByText(
        "nearby bright stars、tess、tess input catalog、tess objects of interest",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/page_size 5 \/ max_pages 5 \/ 候选上限 25/u),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        String(paperCollectionReadFixture.collection.query.query_id),
      ),
    ).toBeInTheDocument();
    // Orthogonal labels: execution and source never merge into one string.
    const provenance = screen.getByTestId("paper-review-provenance");
    expect(provenance).toHaveTextContent("execution: Demo Replay");
    expect(provenance).toHaveTextContent("source: Fixture");
    expect(provenance).not.toHaveTextContent("Fixture / Demo Replay");
    // Real frozen benchmark identity.
    expect(provenance).toHaveTextContent(
      "benchmark: exoplanet_host_star.paper_reasoning v1.3.0",
    );
    expect(provenance).toHaveTextContent(
      "scenario: search.tess_mission_and_catalogs",
    );
    expect(screen.getByText(/确定性演示数据（Fixture/u)).toBeInTheDocument();
    // Metrics from the real pipeline (7 candidates, 3 selected, recall 4/4).
    expect(screen.getByText(/候选 7/u)).toBeInTheDocument();
    expect(screen.getByText(/入选 3/u)).toBeInTheDocument();
    expect(
      screen.getByText(/期望 4 \/ 召回 4（recall 1）/u),
    ).toBeInTheDocument();
    // Per-source execution audit exposes reproduction hashes.
    const sourceList = screen.getByRole("list", { name: "来源执行" });
    expect(sourceList).toHaveTextContent("crossref");
    const execution =
      paperCollectionReadFixture.collection.source_executions[0]!;
    expect(sourceList).toHaveTextContent(execution.request_parameters_hash);
  });

  it("lists candidates in stable order with real pipeline reasons", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    const list = screen.getByRole("list", { name: "候选论文" });
    const items = list.querySelectorAll("li.candidate-item");
    expect(items).toHaveLength(7);
    expect(items[0]?.textContent).toContain("#1");
    expect(items[0]?.textContent).toContain(
      "入选原因：highest ranked representative within selection limit",
    );
    expect(items[1]?.textContent).toContain(
      "排除原因：duplicate of higher-ranked candidate",
    );
    expect(items[1]?.textContent).toContain("doi_exact");
    expect(items[6]?.textContent).toContain(
      "排除原因：selection limit reached after deterministic ranking",
    );
    // Uncertain title/year match surfaces on the affected candidates.
    expect(list.textContent).toContain("不确定匹配（authors）");
    // The three synthetic records carry an explicit per-candidate label;
    // the four real seed papers never do.
    const syntheticNotes = list.querySelectorAll(".candidate-synthetic-note");
    expect(syntheticNotes).toHaveLength(3);
    expect(syntheticNotes[0]?.textContent).toContain("合成演示记录");
    expect(syntheticNotes[0]?.textContent).toContain("Not a real publication");
    expect(items[2]?.querySelector(".candidate-synthetic-note")).toBeNull();
  });

  it("keeps original stableRank when filtering and resets cleanly", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.change(screen.getByLabelText("入选状态"), {
      target: { value: "excluded" },
    });
    await screen.findByText(/显示 4 \/ 7 项/u);
    const list = screen.getByRole("list", { name: "候选论文" });
    const ranks = [...list.querySelectorAll(".candidate-rank")].map(
      (node) => node.textContent,
    );
    // Filtering hides rows but never renumbers the server ranking.
    expect(ranks).toEqual(["#2", "#5", "#6", "#7"]);

    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
    await screen.findByText(/显示 7 \/ 7 项/u);
  });

  it("filters by text and by duplicates without reordering", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.change(screen.getByLabelText("标题或作者"), {
      target: { value: "Revised TESS Input" },
    });
    await screen.findByText(/显示 1 \/ 7 项/u);
    expect(
      screen.getByRole("list", { name: "候选论文" }).textContent,
    ).toContain("#3");

    fireEvent.change(screen.getByLabelText("标题或作者"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("重复与冲突"), {
      target: { value: "duplicates" },
    });
    await screen.findByText(/显示 2 \/ 7 项/u);
  });

  it("renders the non-http raw record URL as plain text, never a link", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    expect(
      screen.getByText(/ftp:\/\/mirror\.example\.org\/flares\.pdf/u),
    ).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    for (const link of links) {
      expect(link.getAttribute("href") ?? "").not.toContain("ftp://");
    }
    // Canonicalised https URLs do render as links.
    expect(
      screen.getByRole("link", {
        name: "https://doi.org/10.3847/1538-3881/ab3467",
      }),
    ).toBeInTheDocument();
  });

  it("selecting a candidate updates the Provenance Observatory", async () => {
    renderWorkspace(fixtureRuntime());
    await openRetrievedPapers();

    fireEvent.click(screen.getByRole("button", { name: REVISED_TITLE }));
    const observatory = within(
      screen.getByRole("region", { name: "Provenance Observatory" }),
    );
    await waitFor(() => {
      expect(
        observatory.getByText("snap_paper_crossref_01 / crossref"),
      ).toBeInTheDocument();
    });
    expect(
      observatory.getByText(/retrieved 2026-07-21T08:24:30Z/u),
    ).toBeInTheDocument();
  });

  it("selecting candidate evidence pins it for the Share chain", async () => {
    const runtime = fixtureRuntime();
    renderWorkspace(runtime);
    await openRetrievedPapers();

    fireEvent.click(screen.getByRole("button", { name: TOP_TITLE }));
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
    expect(
      await screen.findByRole("heading", { name: "Evidence" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/evd_paper_01/u).length).toBeGreaterThan(0);
  });

  it("renders the same domain review through the real HTTP repository", async () => {
    const fixture = fixtureRuntime();
    const [fixtureReview, httpReview] = await Promise.all([
      fixture.repositories.paperAcquisition.getReview(
        paperCollectionReadFixture.artifact_version_id as never,
      ),
      httpPaperRuntime().repositories.paperAcquisition.getReview(
        paperCollectionReadFixture.artifact_version_id as never,
      ),
    ]);
    // Same domain model from both adapters, byte for byte.
    expect(httpReview).toEqual(fixtureReview);

    renderWorkspace(
      httpPaperRuntime(),
      `/workspace?projectId=${String(fixture.bootstrap.projectId)}&runId=${String(fixture.bootstrap.runId)}`,
    );
    await openRetrievedPapers();
    const provenance = screen.getByTestId("paper-review-provenance");
    expect(provenance).toHaveTextContent("source: Fixture");
    const list = screen.getByRole("list", { name: "候选论文" });
    expect(list.querySelectorAll("li.candidate-item")).toHaveLength(7);
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

  it("shows the empty state only for the explicit empty-collection code", async () => {
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

  it("shows the unavailable state for any other 404 code", async () => {
    renderWorkspace(
      runtimeWithReview(async () => {
        throw new NotFoundError("missing", "RESOURCE_NOT_FOUND");
      }),
    );
    await openRetrievedPapers();
    expect(
      await screen.findByText(
        "当前 ArtifactVersion 不存在或不可访问，请重新选择 Artifact。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("当前 ArtifactVersion 没有候选论文。"),
    ).not.toBeInTheDocument();
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

describe("PaperAcquisitionWorkspace — stale review cleanup", () => {
  it("never shows the previous version's review after switching versions", async () => {
    const fixture = fixtureRuntime();
    const review = await fixture.repositories.paperAcquisition.getReview(
      paperCollectionReadFixture.artifact_version_id as never,
    );
    const repository = {
      getReview: vi.fn((id: unknown) =>
        String(id) === paperCollectionReadFixture.artifact_version_id
          ? Promise.resolve(review)
          : new Promise<never>(() => {}),
      ),
    } as never;
    const noop = () => {};
    const { rerender } = render(
      <PaperAcquisitionWorkspace
        artifactVersionId={
          paperCollectionReadFixture.artifact_version_id as never
        }
        repository={repository}
        executionMode="demo_replay"
        ready
        disabled={false}
        selectedCandidateId={null}
        onSelectCandidate={noop}
        onSelectEvidence={noop}
      />,
    );
    await screen.findByRole("list", { name: "候选论文" });

    rerender(
      <PaperAcquisitionWorkspace
        artifactVersionId={"artv_other_version" as never}
        repository={repository}
        executionMode="demo_replay"
        ready
        disabled={false}
        selectedCandidateId={null}
        onSelectCandidate={noop}
        onSelectEvidence={noop}
      />,
    );
    // The slow second version must show loading, never the stale review.
    await waitFor(() => {
      expect(
        screen.queryByRole("list", { name: "候选论文" }),
      ).not.toBeInTheDocument();
    });
    expect(
      screen.getByText("正在读取论文获取产物与候选列表。"),
    ).toBeInTheDocument();
  });

  it("resets to idle when the session is no longer ready", async () => {
    const fixture = fixtureRuntime();
    const noop = () => {};
    const props = {
      artifactVersionId:
        paperCollectionReadFixture.artifact_version_id as never,
      repository: fixture.repositories.paperAcquisition,
      executionMode: "demo_replay" as const,
      disabled: false,
      selectedCandidateId: null,
      onSelectCandidate: noop,
      onSelectEvidence: noop,
    };
    const { rerender } = render(<PaperAcquisitionWorkspace {...props} ready />);
    await screen.findByRole("list", { name: "候选论文" });

    rerender(<PaperAcquisitionWorkspace {...props} ready={false} />);
    await waitFor(() => {
      expect(
        screen.queryByRole("list", { name: "候选论文" }),
      ).not.toBeInTheDocument();
    });
  });
});

describe("PaperAcquisitionWorkspace — cached provenance", () => {
  function cachedCollectionPayload() {
    const clone = JSON.parse(JSON.stringify(paperCollectionReadFixture)) as {
      source_mode: string;
      collection: { source_executions: Array<Record<string, unknown>> };
      source_snapshots: Array<{
        cache_version?: string | null;
        request_metadata: Record<string, unknown>;
      }>;
    };
    clone.source_mode = "cached";
    for (const execution of clone.collection.source_executions) {
      execution.source_mode = "cached";
      execution.data_level = "real_run_cache";
      execution.cache_applicability =
        "query_hash matches the cached acquisition run";
      execution.live_failure_class = "timeout";
      execution.live_failure_code = "CROSSREF_TIMEOUT";
    }
    clone.source_snapshots[0]!.cache_version = "cache_v1";
    clone.source_snapshots[0]!.request_metadata = {
      ...clone.source_snapshots[0]!.request_metadata,
      origin_run_id: "run_origin_01",
      origin_artifact_version_id: "artv_origin_01",
    };
    return clone;
  }

  it("pairs each cached execution with its own origin snapshot", async () => {
    const fixture = fixtureRuntime();
    const session = sessionStub();
    const httpRepos = createHttpRepositories({
      baseUrl: HTTP_BASE,
      fetchImpl: paperHttpFetch(cachedCollectionPayload()),
      session,
    });
    renderWorkspace(
      {
        adapterKind: "http",
        repositories: {
          ...fixture.repositories,
          paperAcquisition: httpRepos.paperAcquisition,
        },
        tour: fixture.tour,
        workspaceController: fixture.workspaceController,
        queryClient: fixture.queryClient,
        session,
      },
      `/workspace?projectId=${String(fixture.bootstrap.projectId)}&runId=${String(fixture.bootstrap.runId)}`,
    );
    await openRetrievedPapers();

    // One cached execution renders as one grouped entry that carries both the
    // execution audit and its paired origin snapshot — not two disjoint lists.
    const audit = screen.getByRole("region", { name: "缓存审计" });
    const entries = audit.querySelectorAll(".paper-cached-entry");
    expect(entries).toHaveLength(1);
    const entry = entries[0]!;
    expect(entry.textContent).toContain("crossref");
    expect(entry.textContent).toContain(
      "query_hash matches the cached acquisition run",
    );
    expect(entry.textContent).toContain("run_origin_01");
    expect(entry.textContent).toContain("artv_origin_01");
    expect(entry.textContent).toContain("cache_v1");
  });
});
