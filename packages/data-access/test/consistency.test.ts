/**
 * Fixture/HTTP consistency test — A-02 Epic exit criteria.
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
const EVIDENCE_ID = "evd_01" as never;

it("projects.getById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureProject, httpProject] = await Promise.all([
    fixtureRepos.projects.getById(PROJECT_ID),
    httpRepos.projects.getById(PROJECT_ID),
  ]);
  expect(httpProject).toEqual(fixtureProject);
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
    "sha256:d43c90e165cbe6b068f2c95247703ff5bfed6e371a4826831afa17ee733b9986";
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
