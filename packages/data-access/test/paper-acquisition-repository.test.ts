/**
 * Paper acquisition repository tests (A-05 over the B-06 read contract).
 *
 * Covers: contract validation of both read models, multi-page cursor
 * aggregation, integrity guards (non-advancing cursor, duplicate candidates,
 * count mismatch, ranking drift), Fixture/HTTP domain parity, HTTP error
 * classification (429/502/404-empty/422/network) and fixture source-mode
 * enforcement.
 */

import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createFixtureRepositories } from "../src/fixture-adapter";
import { createHttpRepositories } from "../src/http-adapter";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";
import {
  paperCandidateReadsFixture,
  paperCollectionArtifactVersionFixture,
  paperCollectionReadFixture,
} from "../src/fixture/paper-acquisition";
import {
  NetworkError,
  NotFoundError,
  RateLimitedError,
  UpstreamError,
  ValidationError,
} from "../src/http-errors";

import {
  createSessionManagerForTest,
  defaultHandlers,
  httpServer,
  problem,
  TEST_BASE_URL,
} from "./http-helpers";

const VERSION_ID = "artv_papcol_01" as never;

function setupHttpRepos() {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  return createHttpRepositories({
    baseUrl: TEST_BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  });
}

function envelope<T>(data: T) {
  return {
    data,
    meta: {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:00:00Z",
    },
    links: { self: "/api/v2/test" },
  };
}

function candidatePage(
  items: readonly unknown[],
  nextCursor: string | null,
  hasMore: boolean,
) {
  return {
    data: items,
    page: { next_cursor: nextCursor, has_more: hasMore, limit: 2 },
    meta: {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:00:00Z",
    },
  };
}

describe("paperAcquisition.getReview — Fixture/HTTP parity", () => {
  it("returns the identical domain review from both adapters", async () => {
    const fixtureRepos = createFixtureRepositories(exoplanetHostStarFixture);
    const httpRepos = setupHttpRepos();
    const [fixtureReview, httpReview] = await Promise.all([
      fixtureRepos.paperAcquisition.getReview(VERSION_ID),
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ]);
    expect(httpReview).toEqual(fixtureReview);
  });

  it("aggregates every cursor page in authoritative ranking order", async () => {
    const httpRepos = setupHttpRepos();
    const review = await httpRepos.paperAcquisition.getReview(VERSION_ID);
    // The MSW handler serves 2-item pages, so 7 candidates require 4 pages.
    expect(review.candidates).toHaveLength(7);
    expect(review.candidates.map((item) => item.stableRank)).toEqual([
      1, 2, 3, 4, 5, 6, 7,
    ]);
    expect(review.candidates.map((item) => String(item.candidateId))).toEqual(
      paperCandidateReadsFixture.map((item) => item.candidate.candidate_id),
    );
  });

  it("maps selection, duplicates, conflicts, snapshot and evidence", async () => {
    const httpRepos = setupHttpRepos();
    const review = await httpRepos.paperAcquisition.getReview(VERSION_ID);
    const first = review.candidates[0];
    const duplicate = review.candidates[1];
    const last = review.candidates[review.candidates.length - 1];
    // Real pipeline reasons: the top representative is selected, the same-DOI
    // aggregator entry is excluded as a duplicate, the low-relevance record
    // falls out of the selection limit.
    expect(first?.selection).toEqual({
      kind: "selected",
      reason: "highest ranked representative within selection limit",
    });
    expect(duplicate?.selection.kind).toBe("excluded");
    expect(duplicate?.selection.reason).toMatch(
      /^duplicate of higher-ranked candidate /u,
    );
    expect(duplicate?.duplicateGroup.candidateIds).toHaveLength(2);
    expect(duplicate?.duplicateGroup.matchBasis).toContain("doi_exact");
    expect(
      duplicate?.duplicateGroup.conflicts.some(
        (conflict) =>
          conflict.field === "title" && conflict.classification === "conflict",
      ),
    ).toBe(true);
    expect(
      review.candidates.some((candidate) =>
        candidate.conflicts.some(
          (conflict) => conflict.classification === "uncertain_match",
        ),
      ),
    ).toBe(true);
    expect(last?.selection).toEqual({
      kind: "excluded",
      reason: "selection limit reached after deterministic ranking",
    });
    expect(first?.sourceSnapshot.id).toBe("snap_paper_crossref_01");
    expect(first?.evidence[0]?.id).toBe("evd_paper_01");
    // The raw ftp URL from the synthetic low-relevance record survives into
    // the raw record audit surface (and only there).
    expect(
      review.candidates.some(
        (candidate) =>
          candidate.rawRecord.url === "ftp://mirror.example.org/flares.pdf" &&
          candidate.url === null,
      ),
    ).toBe(true);
    expect(review.sourceMode).toBe("fixture");
    // Benchmark identity is the frozen package, never an invented id.
    expect(String(review.benchmark.benchmarkId)).toBe(
      "exoplanet_host_star.paper_reasoning",
    );
    expect(String(review.benchmark.scenarioId)).toBe(
      "search.tess_mission_and_catalogs",
    );
  });

  it("exposes the full reproduction parameters in the domain review", async () => {
    const httpRepos = setupHttpRepos();
    const review = await httpRepos.paperAcquisition.getReview(VERSION_ID);
    const dtoQuery = paperCollectionReadFixture.collection.query;
    expect(String(review.query.queryId)).toBe(dtoQuery.query_id);
    expect(review.query.normalizationRuleVersion).toBe(
      dtoQuery.normalization_rule_version,
    );
    expect(review.query.originalKeywords).toEqual([
      ...dtoQuery.original_keywords,
    ]);
    expect(review.query.normalizedKeywords).toEqual([
      ...dtoQuery.normalized_keywords,
    ]);
    expect(review.query.pagination).toEqual({
      pageSize: dtoQuery.pagination.page_size,
      maxPages: dtoQuery.pagination.max_pages,
      candidateLimit: dtoQuery.pagination.candidate_limit,
    });
    // Source parameters are exposed as deterministically sorted entries.
    expect(review.query.sourceParameters).toHaveLength(1);
    const crossref = review.query.sourceParameters[0];
    expect(String(crossref?.sourceId)).toBe("crossref");
    const keys = (crossref?.parameters ?? []).map((entry) => entry.key);
    expect(keys).toEqual([...keys].sort());
    expect(
      crossref?.parameters.every(
        (entry) => typeof entry.value === "string" && entry.value.length > 0,
      ),
    ).toBe(true);

    const execution = review.sourceExecutions[0];
    const dtoExecution =
      paperCollectionReadFixture.collection.source_executions[0];
    expect(String(execution?.requestParametersHash)).toBe(
      dtoExecution?.request_parameters_hash,
    );
    expect(execution?.pagination.pageSize).toBe(
      dtoExecution?.pagination.page_size,
    );
    expect(execution?.cache).toBeNull();
    const page = execution?.pages[0];
    const dtoPage = dtoExecution?.pages?.[0];
    expect(page?.offset).toBe(dtoPage?.offset);
    expect(page?.requestedRows).toBe(dtoPage?.requested_rows);
    expect(page?.totalResults).toBe(dtoPage?.total_results ?? null);
    expect(String(page?.requestHash)).toBe(dtoPage?.request_hash);
    expect(String(page?.responseHash)).toBe(dtoPage?.response_hash);
    // Two pages were actually executed by the demo build (5 + 2 rows).
    expect(execution?.pages.map((item) => item.pageNumber)).toEqual([1, 2]);

    const snapshot = review.sourceSnapshots[0];
    expect(String(snapshot?.id)).toBe("snap_paper_crossref_01");
    expect(snapshot?.requestMetadata.map((entry) => entry.key)).toEqual([
      "adapter_name",
      "data_level",
      "demo_note",
    ]);
    expect(snapshot?.cachedOrigin).toBeNull();
  });
});

describe("paperAcquisition.getReview — integrity guards", () => {
  it("fails when the cursor does not advance", async () => {
    const httpRepos = setupHttpRepos();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () =>
          HttpResponse.json(
            candidatePage(
              paperCandidateReadsFixture.slice(0, 2),
              "stuck-cursor",
              true,
            ),
          ),
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CURSOR_NOT_ADVANCING");
    expect((error as Error).message).toMatch(/did not advance/u);
  });

  it("fails on duplicate candidate ids across pages", async () => {
    const httpRepos = setupHttpRepos();
    let call = 0;
    // Two pages totalling the declared 7 candidates, but one id repeats.
    const pageOne = paperCandidateReadsFixture.slice(0, 4);
    const pageTwo = [
      paperCandidateReadsFixture[3]!,
      ...paperCandidateReadsFixture.slice(4, 6),
    ];
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () => {
          call += 1;
          return HttpResponse.json(
            call === 1
              ? candidatePage(pageOne, "page-2", true)
              : candidatePage(pageTwo, null, false),
          );
        },
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CANDIDATE_DUPLICATE");
    expect((error as Error).message).toMatch(/duplicate candidate id/u);
  });

  it("fails when the candidate count mismatches the collection", async () => {
    const httpRepos = setupHttpRepos();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () =>
          HttpResponse.json(
            candidatePage(paperCandidateReadsFixture.slice(0, 2), null, false),
          ),
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe(
      "PAPER_CANDIDATE_COUNT_MISMATCH",
    );
    expect((error as Error).message).toMatch(/declares 7/u);
  });

  it("fails when pages exceed the declared candidate total", async () => {
    const httpRepos = setupHttpRepos();
    let call = 0;
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () => {
          call += 1;
          return HttpResponse.json(
            candidatePage(
              paperCandidateReadsFixture.slice(0, 4),
              `page-${String(call + 1)}`,
              true,
            ),
          );
        },
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CURSOR_EXCEEDED_TOTAL");
    expect((error as Error).message).toMatch(/exceeded the declared total/u);
  });

  it("fails when has_more persists after the declared total is reached", async () => {
    const httpRepos = setupHttpRepos();
    let call = 0;
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () => {
          call += 1;
          return HttpResponse.json(
            call === 1
              ? candidatePage(
                  paperCandidateReadsFixture.slice(0, 4),
                  "page-2",
                  true,
                )
              : candidatePage(
                  paperCandidateReadsFixture.slice(4, 7),
                  "page-3",
                  true,
                ),
          );
        },
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CURSOR_EXCEEDED_TOTAL");
    expect((error as Error).message).toMatch(
      /after the declared\s+total was reached/u,
    );
  });

  it("fails when the page order drifts from the collection ranking", async () => {
    const httpRepos = setupHttpRepos();
    const reversed = [...paperCandidateReadsFixture].reverse();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () => HttpResponse.json(candidatePage(reversed, null, false)),
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CANDIDATE_ORDER_DRIFT");
    expect((error as Error).message).toMatch(/order drifted/u);
  });

  it("fails when a page reports has_more but returns no items", async () => {
    const httpRepos = setupHttpRepos();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-candidates`,
        () => HttpResponse.json(candidatePage([], "page-2", true)),
      ),
    );
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ValidationError);
    expect((error as ValidationError).code).toBe("PAPER_CURSOR_EMPTY_PAGE");
    expect((error as Error).message).toMatch(/has_more without returning/u);
  });
});

describe("paperAcquisition.getReview — HTTP error classification", () => {
  function overrideCollection(status: number, code: string) {
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-collection`,
        () => HttpResponse.json(problem(status, code, "problem"), { status }),
      ),
    );
  }

  it("classifies 429 as RateLimitedError", async () => {
    const httpRepos = setupHttpRepos();
    overrideCollection(429, "PAPER_SOURCE_RATE_LIMITED");
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toBeInstanceOf(RateLimitedError);
  });

  it("classifies 502 as UpstreamError", async () => {
    const httpRepos = setupHttpRepos();
    overrideCollection(502, "PAPER_SOURCE_FAILED");
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toBeInstanceOf(UpstreamError);
  });

  it("classifies 404 as NotFoundError with the empty-collection code", async () => {
    const httpRepos = setupHttpRepos();
    overrideCollection(404, "PAPER_COLLECTION_EMPTY");
    const failure = await httpRepos.paperAcquisition.getReview(VERSION_ID).then(
      () => null,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(NotFoundError);
    expect((failure as NotFoundError).code).toBe("PAPER_COLLECTION_EMPTY");
  });

  it("preserves a non-empty 404 code for missing versions", async () => {
    const httpRepos = setupHttpRepos();
    overrideCollection(404, "RESOURCE_NOT_FOUND");
    const failure = await httpRepos.paperAcquisition.getReview(VERSION_ID).then(
      () => null,
      (error: unknown) => error,
    );
    expect(failure).toBeInstanceOf(NotFoundError);
    // The UI must be able to distinguish "empty collection" from "missing
    // version"; the repository never collapses the code.
    expect((failure as NotFoundError).code).toBe("RESOURCE_NOT_FOUND");
  });

  it("classifies an invalid payload as ValidationError", async () => {
    const httpRepos = setupHttpRepos();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-collection`,
        () => HttpResponse.json(envelope({ not: "a-collection" })),
      ),
    );
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toBeInstanceOf(ValidationError);
  });

  it("classifies a transport failure as NetworkError", async () => {
    const httpRepos = setupHttpRepos();
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-collection`,
        () => HttpResponse.error(),
      ),
    );
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("paperAcquisition.getReview — cached provenance audit", () => {
  function cachedRead(
    mutate?: (read: typeof paperCollectionReadFixture) => void,
  ) {
    const clone = JSON.parse(
      JSON.stringify(paperCollectionReadFixture),
    ) as typeof paperCollectionReadFixture & {
      source_mode: string;
      collection: {
        source_executions: Array<Record<string, unknown>>;
        source_snapshots: Array<Record<string, unknown>>;
        source_snapshot_ids: string[];
      };
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
    mutate?.(clone as typeof paperCollectionReadFixture);
    return clone;
  }

  function overrideCollectionPayload(payload: unknown) {
    httpServer.use(
      http.get(
        `${TEST_BASE_URL}/api/v2/artifact-versions/:versionId/paper-collection`,
        () => HttpResponse.json(envelope(payload)),
      ),
    );
  }

  it("maps the cached audit context and snapshot origin into the domain", async () => {
    const httpRepos = setupHttpRepos();
    overrideCollectionPayload(cachedRead());
    const review = await httpRepos.paperAcquisition.getReview(VERSION_ID);
    expect(review.sourceMode).toBe("cached");
    const execution = review.sourceExecutions[0];
    expect(execution?.cache).toEqual({
      applicability: "query_hash matches the cached acquisition run",
      liveFailureClass: "timeout",
      liveFailureCode: "CROSSREF_TIMEOUT",
    });
    const snapshot = review.sourceSnapshots[0];
    expect(snapshot?.cacheVersion).toBe("cache_v1");
    expect(snapshot?.cachedOrigin).toEqual({
      originRunId: "run_origin_01",
      originArtifactVersionId: "artv_origin_01",
    });
  });

  it("rejects a cached execution without cache_applicability", async () => {
    const httpRepos = setupHttpRepos();
    const payload = cachedRead();
    for (const execution of payload.collection.source_executions) {
      delete (execution as Record<string, unknown>)["cache_applicability"];
    }
    overrideCollectionPayload(payload);
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect((error as ValidationError).code).toBe(
      "PAPER_CACHED_LACKS_APPLICABILITY",
    );
    expect((error as Error).message).toMatch(/lacks cache_applicability/u);
  });

  it("rejects a cached execution without the live failure context", async () => {
    const httpRepos = setupHttpRepos();
    const payload = cachedRead();
    for (const execution of payload.collection.source_executions) {
      delete (execution as Record<string, unknown>)["live_failure_class"];
      delete (execution as Record<string, unknown>)["live_failure_code"];
    }
    overrideCollectionPayload(payload);
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect((error as ValidationError).code).toBe(
      "PAPER_CACHED_LACKS_LIVE_FAILURE",
    );
    expect((error as Error).message).toMatch(/lacks the live failure/u);
  });

  it("rejects a cached snapshot without a cache_version", async () => {
    const httpRepos = setupHttpRepos();
    const payload = cachedRead();
    payload.source_snapshots[0]!.cache_version = null;
    overrideCollectionPayload(payload);
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect((error as ValidationError).code).toBe("PAPER_CACHED_LACKS_VERSION");
    expect((error as Error).message).toMatch(/lacks a snapshot cache_version/u);
  });

  it("rejects blank cached audit values", async () => {
    const cases: Array<(payload: ReturnType<typeof cachedRead>) => void> = [
      (payload) => {
        payload.collection.source_executions[0]!["cache_applicability"] = "   ";
      },
      (payload) => {
        payload.collection.source_executions[0]!["live_failure_code"] = "   ";
      },
      (payload) => {
        payload.source_snapshots[0]!.cache_version = "   ";
      },
    ];

    for (const mutate of cases) {
      const httpRepos = setupHttpRepos();
      const payload = cachedRead();
      mutate(payload);
      overrideCollectionPayload(payload);
      await expect(
        httpRepos.paperAcquisition.getReview(VERSION_ID),
      ).rejects.toThrowError(/cached source execution|cache_version/u);
    }
  });

  it("binds origin provenance per execution, not collection-wide", async () => {
    const httpRepos = setupHttpRepos();
    const payload = cachedRead();
    // Add a second cached execution whose own snapshot has NO origin, while
    // the first execution's snapshot does: a collection-wide "some snapshot
    // has origin" guard would wrongly accept this payload.
    const firstExecution = payload.collection.source_executions[0]!;
    const firstRecord = payload.collection.source_snapshots[0]!;
    payload.collection.source_snapshots.push({
      ...firstRecord,
      snapshot_id: "snapshot.arxiv.demo2",
      source_id: "arxiv",
      content_hash: `sha256:${"b".repeat(64)}`,
    });
    payload.collection.source_snapshot_ids = [
      ...payload.collection.source_snapshot_ids,
      "snapshot.arxiv.demo2",
    ].sort();
    payload.collection.source_executions.push({
      ...firstExecution,
      source_id: "arxiv",
      source_snapshot_id: "snapshot.arxiv.demo2",
    });
    const persisted = payload.source_snapshots as Array<
      Record<string, unknown>
    >;
    persisted.push({
      ...persisted[0]!,
      id: "snap_paper_arxiv_02",
      source_id: "arxiv",
      content_hash: `sha256:${"b".repeat(64)}`,
      cache_version: "cache_v1",
      request_metadata: { adapter_name: "arxiv_demo_fixture" },
    });
    overrideCollectionPayload(payload);
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect((error as ValidationError).code).toBe("PAPER_CACHED_LACKS_ORIGIN");
    expect((error as Error).message).toMatch(
      /cached source execution arxiv lacks origin Run\/ArtifactVersion/u,
    );
  });

  it("rejects a cached execution without origin Run/ArtifactVersion", async () => {
    const httpRepos = setupHttpRepos();
    const payload = cachedRead();
    payload.source_snapshots[0]!.request_metadata = {
      adapter_name: "crossref_demo_fixture",
    };
    overrideCollectionPayload(payload);
    const error = await httpRepos.paperAcquisition
      .getReview(VERSION_ID)
      .catch((cause: unknown) => cause);
    expect((error as ValidationError).code).toBe("PAPER_CACHED_LACKS_ORIGIN");
    expect((error as Error).message).toMatch(
      /lacks origin Run\/ArtifactVersion/u,
    );
  });
});

describe("paper acquisition fixture — Demo Replay semantics", () => {
  it("rejects a fixture whose paper collection claims live source mode", () => {
    const bundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        paperAcquisitions: [
          {
            // Keep the version identity consistent so the semantic check on
            // source_mode (not the identity guard) is what rejects it.
            version: {
              ...paperCollectionArtifactVersionFixture,
              source_mode: "live" as const,
            },
            collection: {
              ...paperCollectionReadFixture,
              source_mode: "live" as const,
            },
            candidates: paperCandidateReadsFixture,
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(bundle)).toThrowError(
      /must have source_mode "fixture"/u,
    );
  });

  it("rejects a fixture whose source execution claims cached source mode", () => {
    const collection = paperCollectionReadFixture;
    const tamperedCollection = {
      ...collection.collection,
      source_executions: [
        {
          ...collection.collection.source_executions[0]!,
          source_mode: "cached" as const,
        },
        ...collection.collection.source_executions.slice(1),
      ] as typeof collection.collection.source_executions,
    };
    const bundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        paperAcquisitions: [
          {
            // Mirror the tampered content into the version so the identity
            // guard passes and the per-execution semantic check fires.
            version: {
              ...paperCollectionArtifactVersionFixture,
              content:
                tamperedCollection as unknown as (typeof paperCollectionArtifactVersionFixture)["content"],
            },
            collection: {
              ...collection,
              collection: tamperedCollection,
            },
            candidates: paperCandidateReadsFixture,
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(bundle)).toThrowError(
      /source execution.*must stay "fixture"|source_mode "fixture"/u,
    );
  });

  it("rejects an old-shaped bundle without the rich immutable version", () => {
    const bundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        paperAcquisitions: [
          {
            collection: paperCollectionReadFixture,
            candidates: paperCandidateReadsFixture,
          } as never,
        ],
      },
    };
    expect(() => createFixtureRepositories(bundle)).toThrowError(
      /must\s+carry its full immutable ArtifactVersion detail/u,
    );
  });
});
