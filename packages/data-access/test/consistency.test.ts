/**
 * Fixture/HTTP consistency test — Frontend Workspace Epic exit criteria.
 *
 * Verifies that the fixture adapter and HTTP adapter (backed by MSW mocks
 * serving the same fixture DTOs) return deep-equal domain entities for the
 * exoplanet-host-star scenario. This is the structural guarantee that both
 * adapters share the same mapping layer and produce identical domain models.
 *
 * Only read operations backed by the generated OpenAPI are exercised here.
 */

import { expect, it } from "vitest";

import { createFixtureRepositories } from "../src/fixture-adapter";
import { createHttpRepositories } from "../src/http-adapter";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";

import {
  createSessionManagerForTest,
  defaultHandlers,
  httpServer,
} from "./http-helpers";

const fixtureRepos = createFixtureRepositories(exoplanetHostStarFixture);

function setupHttpRepos() {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  return createHttpRepositories({
    baseUrl: "http://test.local",
    fetchImpl: globalThis.fetch,
    session,
  });
}

const PROJECT_ID = "proj_01JEXAMPLE" as never;
const RUN_ID = "run_01JEXAMPLE" as never;
const DRAFT_ID = "rcd_01JEXAMPLE" as never;
const EDITABLE_DRAFT_ID = "rcd_01JTOUR" as never;
const CONTRACT_ID = "rc_01JEXAMPLE" as never;
const ARTIFACT_ID = "art_graph_01" as never;
const VERSION_ID = "artv_graph_01" as never;
const PAPER_SUMMARY_VERSION_ID = "artv_papsum_01" as never;
const EVIDENCE_ID = "evd_01" as never;
const SOURCE_SNAPSHOT_ID = "snap_host_star_toi_recorded" as never;

it("projects.getById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureProject, httpProject] = await Promise.all([
    fixtureRepos.projects.getById(PROJECT_ID),
    httpRepos.projects.getById(PROJECT_ID),
  ]);
  expect(httpProject).toEqual(fixtureProject);
});

it("projects.list returns the same domain entities and cursor shape", async () => {
  const httpRepos = setupHttpRepos();
  const [fixturePage, httpPage] = await Promise.all([
    fixtureRepos.projects.list(),
    httpRepos.projects.list(),
  ]);
  expect(httpPage.items).toEqual(fixturePage.items);
  // The seeded fixture holds a single project, so the first page is terminal.
  expect(fixturePage.nextCursor).toBeNull();
  expect(httpPage.nextCursor).toBeNull();
  expect(httpPage.items.map((p) => p.id)).toContain(PROJECT_ID);
});

it("projects.create returns the same domain entity via both adapters", async () => {
  const freshFixture = createFixtureRepositories(exoplanetHostStarFixture);
  const httpRepos = setupHttpRepos();
  const input = {
    name: "Consistency project",
    description: "Created through both adapters",
    caseKey: "exoplanet_host_star" as never,
    idempotencyKey: "consistency-project-1",
  };
  const [fixtureProject, httpProject] = await Promise.all([
    freshFixture.projects.create(input),
    httpRepos.projects.create(input),
  ]);
  // Identity/timestamp metadata differs by construction; the client-authored
  // fields and the frozen defaults must agree.
  expect(httpProject.name).toBe(fixtureProject.name);
  expect(httpProject.description).toBe(fixtureProject.description);
  expect(httpProject.caseKey).toBe(fixtureProject.caseKey);
  expect(httpProject.activeContractId).toBeNull();
  expect(fixtureProject.activeContractId).toBeNull();
  expect(httpProject.revision).toBe(fixtureProject.revision);
});

it("contracts.createDraft returns the same domain entity via both adapters", async () => {
  const freshFixture = createFixtureRepositories(exoplanetHostStarFixture);
  const httpRepos = setupHttpRepos();
  const base = await freshFixture.contracts.getDraftById(EDITABLE_DRAFT_ID);
  const input = {
    intent: "Integrate exoplanet candidates and host-star parameters",
    contract: base!.contract,
    idempotencyKey: "consistency-draft-1",
  };
  const [fixtureDraft, httpDraft] = await Promise.all([
    freshFixture.contracts.createDraft(PROJECT_ID, input),
    httpRepos.contracts.createDraft(PROJECT_ID, input),
  ]);
  expect(httpDraft.intent).toBe(fixtureDraft.intent);
  expect(httpDraft.status).toBe("draft");
  expect(fixtureDraft.status).toBe("draft");
  expect(httpDraft.version).toBe(1);
  expect(fixtureDraft.version).toBe(1);
  expect(httpDraft.contract).toEqual(fixtureDraft.contract);
});

it("contracts.getDraftById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureDraft, httpDraft] = await Promise.all([
    fixtureRepos.contracts.getDraftById(DRAFT_ID),
    httpRepos.contracts.getDraftById(DRAFT_ID),
  ]);
  expect(httpDraft).toEqual(fixtureDraft);
});

it("contracts.getContractById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureContract, httpContract] = await Promise.all([
    fixtureRepos.contracts.getContractById(CONTRACT_ID),
    httpRepos.contracts.getContractById(CONTRACT_ID),
  ]);
  expect(httpContract).toEqual(fixtureContract);
});

it("runs.getById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureRun, httpRun] = await Promise.all([
    fixtureRepos.runs.getById(RUN_ID),
    httpRepos.runs.getById(RUN_ID),
  ]);
  expect(httpRun).toEqual(fixtureRun);
});

it("runs.listEvents returns the same domain entities in sequence order", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureEvents, httpEvents] = await Promise.all([
    fixtureRepos.runs.listEvents(RUN_ID),
    httpRepos.runs.listEvents(RUN_ID),
  ]);
  expect(httpEvents).toEqual(fixtureEvents);
});

it("artifacts.listByRun returns the same domain entities", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureArtifacts, httpArtifacts] = await Promise.all([
    fixtureRepos.artifacts.listByRun(RUN_ID),
    httpRepos.artifacts.listByRun(RUN_ID),
  ]);
  expect(httpArtifacts).toEqual(fixtureArtifacts);
});

it("artifacts.getArtifact returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureArtifact, httpArtifact] = await Promise.all([
    fixtureRepos.artifacts.getArtifact(ARTIFACT_ID),
    httpRepos.artifacts.getArtifact(ARTIFACT_ID),
  ]);
  expect(httpArtifact).toEqual(fixtureArtifact);
});

it("artifacts.getVersion returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureVersion, httpVersion] = await Promise.all([
    fixtureRepos.artifacts.getVersion(VERSION_ID),
    httpRepos.artifacts.getVersion(VERSION_ID),
  ]);
  expect(httpVersion).toEqual(fixtureVersion);
});

it("artifacts.getEvidence returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureEvidence, httpEvidence] = await Promise.all([
    fixtureRepos.artifacts.getEvidence(EVIDENCE_ID),
    httpRepos.artifacts.getEvidence(EVIDENCE_ID),
  ]);
  expect(httpEvidence).toEqual(fixtureEvidence);
});

it("artifacts.getSourceSnapshot returns the same version-bound provenance", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureSnapshot, httpSnapshot] = await Promise.all([
    fixtureRepos.artifacts.getSourceSnapshot(SOURCE_SNAPSHOT_ID),
    httpRepos.artifacts.getSourceSnapshot(SOURCE_SNAPSHOT_ID),
  ]);
  expect(httpSnapshot).toEqual(fixtureSnapshot);
});

it("paperSummary.getSummary returns the same paper_summary domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureSummary, httpSummary] = await Promise.all([
    fixtureRepos.paperSummary.getSummary(PAPER_SUMMARY_VERSION_ID),
    httpRepos.paperSummary.getSummary(PAPER_SUMMARY_VERSION_ID),
  ]);
  expect(httpSummary).toEqual(fixtureSummary);
});

/**
 * PR-1 Fix 4 — explicit contentHash parity regression.
 *
 * The pre-seeded contract `rc_01JEXAMPLE` and the editable draft share the
 * same contract input, so the Fixture `confirm()` (which now computes the real
 * canonical hash) and the HTTP contract read must agree on `contentHash`.
 * `toEqual` above already compares `contentHash` (it is never excluded), but
 * this test pins the canonical value explicitly so a regression to the
 * all-zero placeholder or a canonicalization mismatch fails loudly.
 */
it("contract contentHash is a real canonical hash shared by Fixture and HTTP", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureContract, httpContract] = await Promise.all([
    fixtureRepos.contracts.getContractById(CONTRACT_ID),
    httpRepos.contracts.getContractById(CONTRACT_ID),
  ]);
  const expectedHash =
    "sha256:82d51bd3fb5739b5ab1afeefa59c270de416bb20d6e780f39dca3c66c90d479a";
  expect(fixtureContract!.contentHash).toBe(expectedHash);
  expect(httpContract!.contentHash).toBe(expectedHash);
  expect(httpContract!.contentHash).toBe(fixtureContract!.contentHash);
  expect(fixtureContract!.contentHash).not.toBe("sha256:" + "0".repeat(64));
});

it("Fixture confirm() and HTTP contract read agree on the confirmed contentHash", async () => {
  const freshFixture = createFixtureRepositories(exoplanetHostStarFixture);
  const httpRepos = setupHttpRepos();
  const [confirmed, httpContract] = await Promise.all([
    freshFixture.contracts.confirm(PROJECT_ID, EDITABLE_DRAFT_ID, 1),
    httpRepos.contracts.getContractById(CONTRACT_ID),
  ]);
  // The editable draft carries the same input as the pre-seeded contract, so
  // confirm() reproduces the same canonical hash the HTTP read returns.
  expect(confirmed.contentHash).toBe(httpContract!.contentHash);
  expect(confirmed.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/u);
});
