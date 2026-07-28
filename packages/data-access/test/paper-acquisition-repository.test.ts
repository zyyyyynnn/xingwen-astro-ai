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
  paperCollectionReadFixture,
} from "../src/fixture/paper-acquisition";
import { FixtureSemanticError } from "../src/errors";
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
    // The MSW handler serves 2-item pages, so 4 candidates require 2 pages.
    expect(review.candidates).toHaveLength(4);
    expect(review.candidates.map((item) => item.stableRank)).toEqual([
      1, 2, 3, 4,
    ]);
    expect(review.candidates.map((item) => String(item.candidateId))).toEqual([
      "cand_paper_01",
      "cand_paper_02",
      "cand_paper_03",
      "cand_paper_04",
    ]);
  });

  it("maps selection, duplicates, conflicts, snapshot and evidence", async () => {
    const httpRepos = setupHttpRepos();
    const review = await httpRepos.paperAcquisition.getReview(VERSION_ID);
    const [first, second, , fourth] = review.candidates;
    expect(first?.selection).toEqual({
      kind: "selected",
      reason:
        "Top-ranked validated planet paper covering the contracted fields",
    });
    expect(second?.selection.kind).toBe("excluded");
    expect(second?.duplicateGroup.groupId).toBe("dupg_01");
    expect(second?.duplicateGroup.conflicts[0]?.classification).toBe(
      "uncertain_match",
    );
    expect(fourth?.selection).toEqual({
      kind: "excluded",
      reason: "Relevance 0.31 is below the selection threshold",
    });
    expect(first?.sourceSnapshot.id).toBe("snap_paper_ads_01");
    expect(first?.evidence[0]?.id).toBe("evd_paper_01");
    expect(review.sourceMode).toBe("fixture");
    expect(review.benchmark.benchmarkId).toBe(
      "exoplanet_host_star.paper_acquisition",
    );
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
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toThrowError(/did not advance|duplicate candidate/u);
  });

  it("fails on duplicate candidate ids across pages", async () => {
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
                  paperCandidateReadsFixture.slice(0, 2),
                  "page-2",
                  true,
                )
              : candidatePage(
                  paperCandidateReadsFixture.slice(0, 2),
                  null,
                  false,
                ),
          );
        },
      ),
    );
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toThrowError(/duplicate candidate id/u);
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
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toThrowError(/declares 4/u);
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
    await expect(
      httpRepos.paperAcquisition.getReview(VERSION_ID),
    ).rejects.toThrowError(/order drifted/u);
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

describe("paper acquisition fixture — Demo Replay semantics", () => {
  it("rejects a fixture whose paper collection claims live source mode", () => {
    const bundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        paperAcquisitions: [
          {
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
      FixtureSemanticError,
    );
  });

  it("rejects a fixture whose source execution claims cached source mode", () => {
    const collection = paperCollectionReadFixture;
    const bundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        paperAcquisitions: [
          {
            collection: {
              ...collection,
              collection: {
                ...collection.collection,
                source_executions: [
                  {
                    ...collection.collection.source_executions[0]!,
                    source_mode: "cached" as const,
                  },
                  ...collection.collection.source_executions.slice(1),
                ] as typeof collection.collection.source_executions,
              },
            },
            candidates: paperCandidateReadsFixture,
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(bundle)).toThrowError(
      FixtureSemanticError,
    );
  });
});
