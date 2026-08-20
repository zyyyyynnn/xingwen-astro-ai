/**
 * Shared test helpers for HTTP adapter tests.
 *
 * Builds MSW handlers from fixture DTOs so the HTTP adapter receives the same
 * payloads the fixture adapter validates internally — the structural basis for
 * the Fixture/HTTP consistency test. Single artifact/version reads are served
 * as the richer `*Detail` projections the runtime returns.
 */

import { http, HttpResponse } from "msw";

import {
  datasetEvidenceRead,
  exoplanetHostStarFixture,
} from "../src/fixture/exoplanet-host-star";
import {
  paperCandidateReadsFixture,
  paperCollectionReadFixture,
} from "../src/fixture/paper-acquisition";
import { paperSummaryReadFixture } from "../src/fixture/paper-summary";

const BASE_URL = "http://test.local";

function hash(char: string): string {
  return `sha256:${char.repeat(64)}`;
}

function envelope<T>(data: T): { data: T; meta: Record<string, unknown> } {
  return {
    data,
    meta: {
      request_id: "req_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:00:00Z",
    },
  };
}

/** A deterministic, schema-valid ProducerExecutionDetail for version details. */
const PRODUCER_EXECUTION = {
  id: "pexec_01",
  run_id: "run_01JEXAMPLE",
  step_key: "cleaning_data",
  step_attempt_id: "att_01",
  producer: { type: "pipeline", name: "data", version: "1.0.0" },
  parameters: {},
  parameters_hash: hash("e"),
  input_hash: hash("c"),
  output_hash: hash("b"),
  status: "completed",
  started_at: "2026-07-21T08:16:00Z",
  finished_at: "2026-07-21T08:21:00Z",
};

type ArtifactDto = (typeof exoplanetHostStarFixture.data.artifacts)[number];

/**
 * Single source of truth for every immutable version the HTTP handlers
 * serve: generic versions plus the rich paper-collection and paper-summary
 * version details (which live on the dedicated paperAcquisitions /
 * paperSummaries entries, exactly like the fixture adapter consumes them).
 */
const ALL_VERSION_DTOS = [
  ...exoplanetHostStarFixture.data.artifactVersions,
  ...exoplanetHostStarFixture.data.paperAcquisitions.map(
    (item) => item.version,
  ),
  ...exoplanetHostStarFixture.data.paperSummaries.map((item) => item.version),
];
type VersionDto = (typeof ALL_VERSION_DTOS)[number];

/** Build a ResearchArtifactDetail payload from a base artifact fixture. */
function artifactDetail(artifact: ArtifactDto): Record<string, unknown> {
  const versions = ALL_VERSION_DTOS.filter(
    (v) => v.artifact_id === artifact.id,
  ).map((v) => ({
    id: v.id,
    artifact_id: v.artifact_id,
    version_number: v.version_number,
    schema_version: v.schema_version,
    content_hash: v.content_hash,
    source_mode: v.source_mode,
    supersedes_version_id: v.supersedes_version_id ?? null,
    created_at: v.created_at,
  }));
  return { ...artifact, versions };
}

/**
 * Build an ArtifactVersionDetail payload from a version fixture. Generic
 * versions get stub detail arrays; the rich paper-collection version already
 * carries its real producer execution, snapshots and evidence, which win.
 */
function versionDetail(version: VersionDto): Record<string, unknown> {
  return {
    producer_execution: PRODUCER_EXECUTION,
    source_snapshots: [],
    evidence: [],
    ...version,
  };
}

/**
 * A schema-valid EvidenceRead for evd_01 (which has a source snapshot).
 * Served verbatim from the fixture bundle so the HTTP and fixture adapters
 * project the same domain entity through the shared mapping layer.
 */
const EVIDENCE_READ = datasetEvidenceRead;

const WORKSPACE_ARTIFACT_VERSION = {
  id: "artv_dataset_01",
  artifact_id: "art_dataset_01",
  kind: "dataset",
  title: "Exoplanet host-star dataset",
  version_number: 1,
  schema_version: "2.0.0",
  content_hash: hash("b"),
  source_mode: "fixture",
  created_at: "2026-07-21T08:21:00Z",
};

const PUBLIC_SHARE = {
  id: "share_01",
  title: "Public dataset evidence",
  redaction_policy: "public_metadata_only",
  created_at: "2026-07-21T09:00:00Z",
  expires_at: "2026-07-22T09:00:00Z",
  artifact_versions: [WORKSPACE_ARTIFACT_VERSION],
  evidence: [
    {
      id: "evd_01",
      artifact_version_id: "artv_dataset_01",
      source_snapshot_id: "snap_01",
    },
  ],
};

function shareCreated(body: {
  title: string;
  artifact_version_ids: readonly string[];
  evidence_ids: readonly string[];
  redaction_policy: string;
  expires_at: string;
}): Record<string, unknown> {
  return {
    id: "share_01",
    project_id: "proj_01JEXAMPLE",
    title: body.title,
    status: "active",
    redaction_policy: body.redaction_policy,
    artifact_version_ids: body.artifact_version_ids,
    evidence_ids: body.evidence_ids,
    created_at: "2026-07-21T09:00:00Z",
    expires_at: body.expires_at,
    revoked_at: null,
    share_token: "raw-share-token-value-01",
    share_url: "/api/public/shares/raw-share-token-value-01",
  };
}

function workspaceSnapshot(
  projectId: string,
  body: Record<string, unknown>,
  revision: number,
): Record<string, unknown> {
  return {
    ...body,
    id: `ws_${projectId}`,
    project_id: projectId,
    revision,
    updated_at: "2026-07-21T09:00:00Z",
  };
}

/** Default handlers serving the exoplanet-host-star fixture over HTTP. */
export const defaultHandlers = [
  http.get(`${BASE_URL}/api/projects`, ({ request }) => {
    // Session-scoped listing seeded with the fixture project only; the cursor
    // is an opaque base64 project id, mirroring the runtime keyset cursor.
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor");
    const ordered = [...exoplanetHostStarFixture.data.projects];
    let start = 0;
    if (cursor) {
      let anchor: string;
      try {
        anchor = atob(
          cursor.padEnd(cursor.length + ((4 - (cursor.length % 4)) % 4), "="),
        );
      } catch {
        return HttpResponse.json(
          problem(400, "INVALID_CURSOR", "Invalid cursor"),
          { status: 400 },
        );
      }
      const index = ordered.findIndex((p) => p.id === anchor);
      if (index === -1) {
        return HttpResponse.json(
          problem(400, "INVALID_CURSOR", "Invalid cursor"),
          { status: 400 },
        );
      }
      start = index + 1;
    }
    const page = ordered.slice(start, start + 20);
    const hasMore = start + page.length < ordered.length;
    const nextCursor =
      hasMore && page.length > 0
        ? btoa(String(page[page.length - 1]!.id)).replace(/=+$/u, "")
        : null;
    return HttpResponse.json({
      data: page,
      page: { next_cursor: nextCursor, has_more: hasMore, limit: 20 },
      meta: {
        request_id: "req_test",
        schema_version: "2.0.0",
        generated_at: "2026-07-21T08:00:00Z",
      },
    });
  }),
  http.post(`${BASE_URL}/api/projects`, async ({ request }) => {
    if (!request.headers.get("Idempotency-Key")) {
      return HttpResponse.json(
        problem(400, "INVALID_REQUEST", "Idempotency-Key required"),
        { status: 400 },
      );
    }
    const body = (await request.json()) as {
      name: string;
      description?: string;
      case_key: string;
    };
    const base = exoplanetHostStarFixture.data.projects[0]!;
    return HttpResponse.json(
      envelope({
        ...base,
        name: body.name,
        description: body.description ?? "",
        case_key: body.case_key,
        active_contract_id: null,
        latest_run_id: null,
      }),
      { status: 201 },
    );
  }),
  http.post(
    `${BASE_URL}/api/projects/:projectId/contract-drafts`,
    async ({ request }) => {
      if (!request.headers.get("Idempotency-Key")) {
        return HttpResponse.json(
          problem(400, "INVALID_REQUEST", "Idempotency-Key required"),
          { status: 400 },
        );
      }
      const body = (await request.json()) as {
        intent: string;
        contract: unknown;
      };
      const base = exoplanetHostStarFixture.data.contractDrafts.find(
        (d) => d.status === "draft",
      )!;
      return HttpResponse.json(
        envelope({
          ...base,
          intent: body.intent,
          contract: body.contract,
          status: "draft",
          version: 1,
        }),
        { status: 201 },
      );
    },
  ),
  http.get(`${BASE_URL}/api/projects/:projectId`, ({ params }) => {
    const project = exoplanetHostStarFixture.data.projects.find(
      (p) => p.id === params.projectId,
    );
    if (!project) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(project));
  }),
  http.get(`${BASE_URL}/api/contracts/drafts/:draftId`, ({ params }) => {
    const draft = exoplanetHostStarFixture.data.contractDrafts.find(
      (d) => d.id === params.draftId,
    );
    if (!draft) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(draft));
  }),
  http.patch(`${BASE_URL}/api/contracts/drafts/:draftId`, ({ request }) => {
    // Draft PATCH must carry an integer If-Match (the draft version).
    const ifMatch = request.headers.get("If-Match");
    if (!ifMatch || !/^\d+$/.test(ifMatch)) {
      return HttpResponse.json(
        problem(428, "PRECONDITION_REQUIRED", "If-Match required"),
        { status: 428 },
      );
    }
    const base = exoplanetHostStarFixture.data.contractDrafts[0]!;
    return HttpResponse.json(
      envelope({ ...base, version: Number(ifMatch) + 1 }),
    );
  }),
  http.get(`${BASE_URL}/api/contracts/:contractId`, ({ params }) => {
    const contract = exoplanetHostStarFixture.data.contracts.find(
      (c) => c.id === params.contractId,
    );
    if (!contract) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(contract));
  }),
  http.post(
    `${BASE_URL}/api/projects/:projectId/contracts`,
    async ({ request }) => {
      if (!request.headers.get("Idempotency-Key")) {
        return HttpResponse.json(
          problem(400, "INVALID_REQUEST", "Idempotency-Key required"),
          { status: 400 },
        );
      }
      const body = (await request.json()) as { draft_id: string };
      const draft = exoplanetHostStarFixture.data.contractDrafts.find(
        (d) => d.id === body.draft_id,
      );
      if (!draft) return new HttpResponse(null, { status: 404 });
      const contract = exoplanetHostStarFixture.data.contracts.find(
        (c) => c.created_from_draft_id === draft.id,
      );
      if (!contract) return new HttpResponse(null, { status: 404 });
      return HttpResponse.json(envelope(contract), { status: 201 });
    },
  ),
  http.get(`${BASE_URL}/api/runs/:runId`, ({ params }) => {
    const run = exoplanetHostStarFixture.data.runs.find(
      (r) => r.id === params.runId,
    );
    if (!run) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(run));
  }),
  http.get(`${BASE_URL}/api/runs/:runId/events`, ({ params, request }) => {
    const events = exoplanetHostStarFixture.data.runEvents.filter(
      (e) => e.run_id === params.runId,
    );
    const url = new URL(request.url);
    const cursor = url.searchParams.get("cursor");
    const limitParam = url.searchParams.get("limit");
    const limit = limitParam ? Number(limitParam) : 100;
    let slice = events;
    if (cursor) {
      const after = Number(cursor);
      if (Number.isInteger(after)) {
        slice = events.filter((event) => event.sequence > after);
      }
    }
    const page = slice.slice(0, limit);
    const hasMore = slice.length > limit;
    const nextCursor =
      hasMore && page.length > 0
        ? String(page[page.length - 1]!.sequence)
        : null;
    return HttpResponse.json({
      data: page,
      page: { next_cursor: nextCursor, has_more: hasMore, limit },
      meta: {
        request_id: "req_test",
        schema_version: "2.0.0",
        generated_at: "2026-07-21T08:00:00Z",
      },
    });
  }),
  http.get(`${BASE_URL}/api/runs/:runId/artifacts`, ({ params }) => {
    const artifacts = exoplanetHostStarFixture.data.artifacts.filter((a) =>
      ALL_VERSION_DTOS.some(
        (v) => v.artifact_id === a.id && v.created_by_run_id === params.runId,
      ),
    );
    return HttpResponse.json({
      data: artifacts,
      page: { next_cursor: null, has_more: false, limit: 20 },
      meta: {
        request_id: "req_test",
        schema_version: "2.0.0",
        generated_at: "2026-07-21T08:00:00Z",
      },
    });
  }),
  http.get(`${BASE_URL}/api/artifacts/:artifactId`, ({ params }) => {
    const artifact = exoplanetHostStarFixture.data.artifacts.find(
      (a) => a.id === params.artifactId,
    );
    if (!artifact) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(artifactDetail(artifact)));
  }),
  http.get(`${BASE_URL}/api/artifact-versions/:versionId`, ({ params }) => {
    const version = ALL_VERSION_DTOS.find((v) => v.id === params.versionId);
    if (!version) return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(envelope(versionDetail(version)));
  }),
  // PaperCollection API paper acquisition read boundary. Candidates are deliberately served
  // in 2-item pages so the adapter's cursor loop is exercised by default.
  http.get(
    `${BASE_URL}/api/artifact-versions/:versionId/paper-collection`,
    ({ params }) => {
      if (params.versionId !== paperCollectionReadFixture.artifact_version_id) {
        return HttpResponse.json(
          problem(404, "PAPER_COLLECTION_EMPTY", "Paper collection is empty"),
          { status: 404 },
        );
      }
      return HttpResponse.json(envelope(paperCollectionReadFixture));
    },
  ),
  http.get(
    `${BASE_URL}/api/artifact-versions/:versionId/paper-candidates`,
    ({ params, request }) => {
      if (params.versionId !== paperCollectionReadFixture.artifact_version_id) {
        return HttpResponse.json(
          problem(404, "PAPER_COLLECTION_EMPTY", "Paper collection is empty"),
          { status: 404 },
        );
      }
      const url = new URL(request.url);
      const cursor = url.searchParams.get("cursor");
      const pageSize = 2;
      let start = 0;
      if (cursor) {
        const index = paperCandidateReadsFixture.findIndex(
          (item) => item.candidate.candidate_id === cursor,
        );
        if (index === -1) {
          return HttpResponse.json(
            problem(400, "INVALID_CURSOR", "Invalid cursor"),
            { status: 400 },
          );
        }
        start = index + 1;
      }
      const page = paperCandidateReadsFixture.slice(start, start + pageSize);
      const hasMore = start + page.length < paperCandidateReadsFixture.length;
      const nextCursor =
        hasMore && page.length > 0
          ? (page[page.length - 1]?.candidate.candidate_id ?? null)
          : null;
      return HttpResponse.json({
        data: page,
        page: { next_cursor: nextCursor, has_more: hasMore, limit: pageSize },
        meta: {
          request_id: "req_test",
          schema_version: "2.0.0",
          generated_at: "2026-07-21T08:00:00Z",
        },
      });
    },
  ),
  // PaperSummary API paper summary read boundary (single required read, no pagination).
  http.get(
    `${BASE_URL}/api/artifact-versions/:versionId/paper-summary`,
    ({ params }) => {
      if (params.versionId !== paperSummaryReadFixture.artifact_version_id) {
        // Mirrors PaperSummary API: an unknown version id is a generic 404, never an
        // "empty summary" contract state.
        return HttpResponse.json(
          problem(
            404,
            "ARTIFACT_VERSION_NOT_FOUND",
            "Artifact version not found",
          ),
          { status: 404 },
        );
      }
      return HttpResponse.json(envelope(paperSummaryReadFixture));
    },
  ),
  // PaperSummary API authorized full-text read boundary. The fixture data
  // carries no authorized PaperCandidate → ResearchInput binding, so the
  // authorized relation is always absent.
  http.get(
    `${BASE_URL}/api/artifact-versions/:versionId/paper-summary/document-source`,
    ({ params }) => {
      if (params.versionId !== paperSummaryReadFixture.artifact_version_id) {
        return HttpResponse.json(
          problem(
            404,
            "ARTIFACT_VERSION_NOT_FOUND",
            "Artifact version not found",
          ),
          { status: 404 },
        );
      }
      return HttpResponse.json(envelope({ research_input: null }));
    },
  ),
  http.get(`${BASE_URL}/api/evidence/:evidenceId`, ({ params }) => {
    if (params.evidenceId !== "evd_01") {
      return new HttpResponse(null, { status: 404 });
    }
    return HttpResponse.json(envelope(EVIDENCE_READ));
  }),
  http.get(
    `${BASE_URL}/api/projects/:projectId/workspace-snapshot`,
    ({ params }) => {
      if (params.projectId === "proj_empty") {
        return new HttpResponse(null, { status: 404 });
      }
      return HttpResponse.json(
        envelope(
          workspaceSnapshot(
            String(params.projectId),
            { layout_preset: "comparative", active_run_id: null },
            1,
          ),
        ),
      );
    },
  ),
  http.put(
    `${BASE_URL}/api/projects/:projectId/workspace-snapshot`,
    async ({ params, request }) => {
      const ifMatch = request.headers.get("If-Match");
      // The contract requires a bare integer revision, never a quoted ETag.
      if (!ifMatch || !/^\d+$/.test(ifMatch)) {
        return HttpResponse.json(
          problem(428, "PRECONDITION_REQUIRED", "Integer If-Match required"),
          { status: 428 },
        );
      }
      const body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        envelope(
          workspaceSnapshot(
            String(params.projectId),
            body,
            Number(ifMatch) + 1,
          ),
        ),
      );
    },
  ),
  http.get(`${BASE_URL}/api/projects/:projectId/shares`, () =>
    HttpResponse.json({
      data: [
        {
          id: "share_01",
          project_id: "proj_01JEXAMPLE",
          title: "Public dataset evidence",
          status: "active",
          redaction_policy: "public_metadata_only",
          artifact_version_ids: ["artv_dataset_01"],
          evidence_ids: ["evd_01"],
          created_at: "2026-07-21T09:00:00Z",
          expires_at: "2026-07-22T09:00:00Z",
          revoked_at: null,
        },
      ],
      page: { next_cursor: null, has_more: false, limit: 20 },
      meta: {
        request_id: "req_test",
        schema_version: "2.0.0",
        generated_at: "2026-07-21T08:00:00Z",
      },
    }),
  ),
  http.post(
    `${BASE_URL}/api/projects/:projectId/shares`,
    async ({ request }) => {
      if (request.headers.get("X-CSRF-Token") !== "csrf_test_token") {
        return HttpResponse.json(
          problem(403, "CSRF_INVALID", "Missing CSRF token"),
          { status: 403 },
        );
      }
      const body = (await request.json()) as Parameters<typeof shareCreated>[0];
      return HttpResponse.json(envelope(shareCreated(body)), { status: 201 });
    },
  ),
  http.delete(
    `${BASE_URL}/api/projects/:projectId/shares/:shareId`,
    ({ request }) => {
      if (request.headers.get("X-CSRF-Token") !== "csrf_test_token") {
        return HttpResponse.json(
          problem(403, "CSRF_INVALID", "Missing CSRF token"),
          { status: 403 },
        );
      }
      return new HttpResponse(null, { status: 204 });
    },
  ),
  http.get(`${BASE_URL}/api/public/shares/:shareToken`, ({ params }) => {
    if (params.shareToken === "revoked-token") {
      return HttpResponse.json(
        problem(404, "SHARE_NOT_FOUND", "Resource not found"),
        { status: 404 },
      );
    }
    return HttpResponse.json(envelope(PUBLIC_SHARE));
  }),
  http.post(`${BASE_URL}/api/sessions`, () =>
    HttpResponse.json(
      envelope({
        status: "active",
        created_at: "2026-07-21T08:00:00Z",
        expires_at: "2026-07-21T09:00:00Z",
        quota: {
          max_projects: 10,
          max_runs: 50,
        },
        csrf_token: "csrf_test_token",
      }),
    ),
  ),
  http.delete(`${BASE_URL}/api/sessions/current`, ({ request }) => {
    const csrf = request.headers.get("X-CSRF-Token");
    if (csrf !== "csrf_test_token") {
      return HttpResponse.json(
        problem(403, "CSRF_INVALID", "Missing or invalid CSRF token"),
        { status: 403 },
      );
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.post(`${BASE_URL}/api/projects/:projectId/runs`, ({ request }) => {
    if (!request.headers.get("Idempotency-Key")) {
      return HttpResponse.json(
        problem(400, "INVALID_REQUEST", "Idempotency-Key required"),
        { status: 400 },
      );
    }
    return HttpResponse.json(envelope(exoplanetHostStarFixture.data.runs[0]), {
      status: 201,
    });
  }),
];

/** Build a Problem Details response body. */
export function problem(
  status: number,
  code: string,
  detail: string,
  errors?: readonly { field: string; code: string; message: string }[],
): {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  errors?: readonly { field: string; code: string; message: string }[];
} {
  return {
    type: `https://xingwen.example/errors/${code.toLowerCase()}`,
    title: detail,
    status,
    detail,
    code,
    errors,
  };
}

/** Base URL used by all HTTP adapter tests. */
export const TEST_BASE_URL = BASE_URL;

/** Create an HTTP adapter config pointing at the MSW server. */
export function createTestHttpConfig(
  session: ReturnType<typeof createSessionManagerForTest>,
) {
  return {
    baseUrl: BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  };
}

import { createSessionManager } from "../src/session";
export function createSessionManagerForTest() {
  return createSessionManager({
    baseUrl: BASE_URL,
    fetchImpl: globalThis.fetch,
  });
}

/** Re-export the MSW server singleton so tests can install handlers. */
export { httpServer } from "./msw-server";
