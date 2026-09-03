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
const PROJECT_FAILED = "proj_failed_demo" as never;

async function kindsOf(runId: string): Promise<readonly string[]> {
  const artifacts = await repos.artifacts.listByRun(runId as never);
  return artifacts.map((artifact) => artifact.kind).sort();
}

it("every project run executes the project's own confirmed contract", async () => {
  for (const projectId of [PROJECT_A, PROJECT_B, PROJECT_C, PROJECT_FAILED]) {
    const project = await repos.projects.getById(projectId);
    expect(project).not.toBeNull();
    expect(project!.activeContractId).not.toBeNull();
    const run = await repos.runs.getById(project!.latestRunId!);
    expect(run).not.toBeNull();
    expect(run!.contractId).toBe(project!.activeContractId);
  }
});

it("Project B listByRun exposes the catalog-replay capability set", async () => {
  const project = await repos.projects.getById(PROJECT_B);
  expect(await kindsOf(project!.latestRunId!)).toEqual([
    "analysis_report",
    "light_curve",
    "model_artifact",
    "model_evaluation",
    "visualization",
  ]);
});

it("Project C listByRun exposes the recorded spectroscopy capability set", async () => {
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

it("scientific reads close run, source snapshot, and evidence provenance", () => {
  const bundle = exoplanetHostStarFixture.data;
  const versions = new Map(
    bundle.artifactVersions.map((version) => [version.id, version]),
  );

  for (const read of bundle.scientificArtifactReads ?? []) {
    const version = versions.get(read.artifact_version_id);
    expect(
      version,
      `missing version ${read.artifact_version_id}`,
    ).toBeDefined();
    expect(read.producer_execution.run_id).toBe(version!.created_by_run_id);

    const readSnapshotIds = new Set(
      read.source_snapshots.map((snapshot) => snapshot.id),
    );
    expect(new Set(version!.source_snapshot_ids)).toEqual(readSnapshotIds);
    expect(new Set(read.content.source_snapshot_ids)).toEqual(readSnapshotIds);

    const readEvidenceIds = new Set(read.evidence.map((item) => item.id));
    expect(new Set(version!.evidence_ids)).toEqual(readEvidenceIds);
    expect(new Set(read.content.evidence_ids)).toEqual(readEvidenceIds);
    for (const evidence of read.evidence) {
      expect(readSnapshotIds.has(evidence.source_snapshot_id)).toBe(true);
      expect(evidence.target_id).toBe(evidence.source_snapshot_id);
    }
  }
});

it("Project C never reuses the TOI-1233 scientific snapshot", () => {
  const reads = (
    exoplanetHostStarFixture.data.scientificArtifactReads ?? []
  ).filter((read) => read.project_id === PROJECT_C);

  expect(reads).not.toHaveLength(0);
  for (const read of reads) {
    expect(read.source_snapshots.map((snapshot) => snapshot.id)).not.toContain(
      "snap_sci_01",
    );
    for (const snapshot of read.source_snapshots) {
      expect(JSON.stringify(snapshot.query).replaceAll(" ", "")).toContain(
        "L98-59",
      );
    }
  }
});
