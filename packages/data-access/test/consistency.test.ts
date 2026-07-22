/**
 * Fixture/HTTP consistency test — A-02 Epic exit criteria.
 *
 * Verifies that the fixture adapter and HTTP adapter (backed by MSW mocks
 * serving the same fixture DTOs) return deep-equal domain entities for the
 * exoplanet-host-star scenario. This is the structural guarantee that both
 * adapters share the same mapping layer and produce identical domain models.
 *
 * Only operations backed by the generated OpenAPI are exercised here.
 * Operations without a corresponding server endpoint throw
 * `CapabilityUnavailableError` and are covered in http-errors.test.ts.
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
const CONTRACT_ID = "rc_01JEXAMPLE" as never;
const ARTIFACT_ID = "art_graph_01" as never;
const VERSION_ID = "artv_graph_01" as never;

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

it("runs.getEvents returns the same domain entities in sequence order", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureEvents, httpEvents] = await Promise.all([
    fixtureRepos.runs.getEvents(RUN_ID),
    httpRepos.runs.getEvents(RUN_ID),
  ]);
  expect(httpEvents).toEqual(fixtureEvents);
});

it("artifacts.getArtifactById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureArtifact, httpArtifact] = await Promise.all([
    fixtureRepos.artifacts.getArtifactById(ARTIFACT_ID),
    httpRepos.artifacts.getArtifactById(ARTIFACT_ID),
  ]);
  expect(httpArtifact).toEqual(fixtureArtifact);
});

it("artifacts.getVersionById returns the same domain entity", async () => {
  const httpRepos = setupHttpRepos();
  const [fixtureVersion, httpVersion] = await Promise.all([
    fixtureRepos.artifacts.getVersionById(VERSION_ID),
    httpRepos.artifacts.getVersionById(VERSION_ID),
  ]);
  expect(httpVersion).toEqual(fixtureVersion);
});
