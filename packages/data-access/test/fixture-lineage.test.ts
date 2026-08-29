/**
 * Fixture lineage gate — every Project closes the
 * Project → Contract → Run → Artifact → ArtifactVersion chain, and all
 * scientific capabilities are reachable through the normal listByRun path.
 */

import { expect, it } from "vitest";

import { createFixtureRepositories } from "../src/fixture-adapter";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";

const repos = createFixtureRepositories(exoplanetHostStarFixture);

const PROJECT_A = "proj_01JEXAMPLE" as never;
const PROJECT_B = "proj_toi_transit" as never;
const PROJECT_C = "proj_l9859_spectroscopy" as never;

async function kindsOf(runId: string): Promise<readonly string[]> {
  const artifacts = await repos.artifacts.listByRun(runId as never);
  return artifacts.map((artifact) => artifact.kind).sort();
}

it("every project run executes the project's own confirmed contract", async () => {
  for (const projectId of [PROJECT_A, PROJECT_B, PROJECT_C]) {
    const project = await repos.projects.getById(projectId);
    expect(project).not.toBeNull();
    expect(project!.activeContractId).not.toBeNull();
    const run = await repos.runs.getById(project!.latestRunId!);
    expect(run).not.toBeNull();
    expect(run!.contractId).toBe(project!.activeContractId);
  }
});

it("Project B listByRun exposes the AutoAstro-derived capability set", async () => {
  const project = await repos.projects.getById(PROJECT_B);
  expect(await kindsOf(project!.latestRunId!)).toEqual([
    "analysis_report",
    "light_curve",
    "model_artifact",
    "model_evaluation",
    "visualization",
  ]);
});

it("Project C listByRun exposes the MAVIS-derived capability set", async () => {
  const project = await repos.projects.getById(PROJECT_C);
  const artifacts = await repos.artifacts.listByRun(
    project!.latestRunId as never,
  );
  const kinds = artifacts.map((artifact) => artifact.kind).sort();
  expect(kinds).toEqual([
    "analysis_report",
    "spectrum",
    "visualization",
    "visualization",
  ]);
});

it("no artifact version references a missing run or another project", async () => {
  const bundle = exoplanetHostStarFixture.data;
  const runIds = new Set(bundle.runs.map((run) => run.id));
  const artifactProject = new Map(
    bundle.artifacts.map((artifact) => [artifact.id, artifact.project_id]),
  );
  for (const version of bundle.artifactVersions) {
    expect(
      runIds.has(version.created_by_run_id),
      `version ${version.id} references missing run ${version.created_by_run_id}`,
    ).toBe(true);
    expect(
      artifactProject.get(version.artifact_id),
      `version ${version.id} references missing artifact ${version.artifact_id}`,
    ).toBe(version.project_id);
  }
});
