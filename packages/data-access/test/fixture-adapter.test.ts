import { describe, expect, it } from "vitest";

import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";
import type { FixtureBundle } from "../src/fixture/bundle";
import { createFixtureRepositories } from "../src/fixture-adapter";
import { FixtureSemanticError, FixtureValidationError } from "../src/errors";
import { ConflictError } from "../src/http-errors";

const repos = createFixtureRepositories(exoplanetHostStarFixture);

const PROJECT_ID = "proj_01JEXAMPLE" as never;
const DRAFT_ID = "rcd_01JEXAMPLE" as never;
const CONTRACT_ID = "rc_01JEXAMPLE" as never;
const RUN_ID = "run_01JEXAMPLE" as never;

describe("Fixture adapter — provenance and semantics", () => {
  it("reports demo_replay execution mode and fixture source mode", () => {
    const { state } = repos.provenance;
    expect(state.executionMode).toBe("demo_replay");
    expect(state.sourceMode).toBe("fixture");
    expect(state.schemaVersion).toBe("2.0.0");
    expect(state.note).toContain("Demo Replay");
  });

  it("reports evidence completeness from the fixture", () => {
    const { state } = repos.provenance;
    expect(state.evidenceCompleteness.covered).toBe(3);
    expect(state.evidenceCompleteness.total).toBe(3);
  });
});

describe("Fixture adapter — reads map DTO to domain", () => {
  it("returns a project with camelCase domain keys", async () => {
    const project = await repos.projects.getById(PROJECT_ID);
    expect(project).not.toBeNull();
    expect(project!).toHaveProperty("sessionId");
    expect(project!).not.toHaveProperty("session_id");
  });

  it("gets a draft and a contract by id", async () => {
    const draft = await repos.contracts.getDraftById(DRAFT_ID);
    const contract = await repos.contracts.getContractById(CONTRACT_ID);
    expect(draft!.intent).toContain("exoplanet");
    expect(contract!.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/u);
  });

  it("gets a run and lists its events in sequence order", async () => {
    const run = await repos.runs.getById(RUN_ID);
    expect(run!.executionMode).toBe("demo_replay");
    const events = await repos.runs.listEvents(RUN_ID);
    expect(events).toHaveLength(9);
    for (let i = 1; i < events.length; i++) {
      expect(events[i]!.sequence).toBe(events[i - 1]!.sequence + 1);
    }
  });

  it("recovers events capped to the latest sequence", async () => {
    const recovery = await repos.runs.recoverEvents(RUN_ID);
    expect(recovery.latestSequence).toBe(9);
    expect(recovery.events).toHaveLength(9);
  });

  it("lists artifacts produced by a run and reads detail projections", async () => {
    const artifacts = await repos.artifacts.listByRun(RUN_ID);
    expect(artifacts).toHaveLength(9);
    const artifact = await repos.artifacts.getArtifact("art_graph_01" as never);
    expect(artifact!.kind).toBe("graph");
    const version = await repos.artifacts.getVersion(
      "artv_dataset_01" as never,
    );
    expect(version!.content.kind).toBe("dataset");
    const evidence = await repos.artifacts.getEvidence("evd_01" as never);
    expect(evidence!.evidenceType).toBe("database_query");
  });
});

describe("Fixture adapter — draft update and contract confirm", () => {
  it("rejects a draft update with a stale expected version", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    await expect(
      fresh.contracts.updateDraft(DRAFT_ID, 99, { intent: "stale" }),
    ).rejects.toBeInstanceOf(ConflictError);
  });

  it("updates a draft and bumps its version", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const updated = await fresh.contracts.updateDraft(DRAFT_ID, 1, {
      intent: "Refined intent",
    });
    expect(updated.intent).toBe("Refined intent");
    expect(updated.version).toBe(2);
  });

  it("confirms a contract from a draft (version-checked)", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const contract = await fresh.contracts.confirm(PROJECT_ID, DRAFT_ID, 1);
    expect(contract.projectId).toBe(PROJECT_ID);
    expect(contract.researchGoal).toContain("exoplanet");
    await expect(
      fresh.contracts.confirm(PROJECT_ID, DRAFT_ID, 99),
    ).rejects.toBeInstanceOf(ConflictError);
  });
});

describe("Fixture adapter — run create (deterministic clock/id)", () => {
  it("creates a queued run with a seeded run.queued event", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture, {
      idFactory: (prefix) => `${prefix}_test` as never,
      clock: () => "2026-07-21T09:00:00Z" as never,
    });
    const run = await fresh.runs.create({
      projectId: PROJECT_ID,
      contractId: CONTRACT_ID,
      executionMode: "live",
    });
    expect(run.id).toBe("run_test");
    expect(run.status).toBe("queued");
    expect(run.executionMode).toBe("live");
    const events = await fresh.runs.listEvents(run.id);
    expect(events).toHaveLength(1);
    expect(events[0]!.eventType).toBe("run.queued");
  });
});

describe("Fixture adapter — workspace save and conflict", () => {
  const input = {
    layoutPreset: "comparative",
    activeRunId: null,
    panelSlots: [],
    pinnedEvidenceIds: [],
    atlasState: null,
    observatoryState: null,
    selectedObjectRef: null,
  };

  it("saves a new snapshot at revision 1 and reloads it", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const saved = await fresh.workspaces.save(PROJECT_ID, input, 0);
    expect(saved.revision).toBe(1);
    const reloaded = await fresh.workspaces.getByProjectId(PROJECT_ID);
    expect(reloaded).toEqual(saved);
  });

  it("rejects a stale expected revision", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    await fresh.workspaces.save(PROJECT_ID, input, 0);
    await expect(
      fresh.workspaces.save(PROJECT_ID, input, 0),
    ).rejects.toBeInstanceOf(ConflictError);
  });
});

describe("Fixture adapter — share create resolves a frozen public projection", () => {
  const request = {
    title: "Public dataset evidence",
    artifactVersionIds: ["artv_dataset_01" as never],
    evidenceIds: ["evd_01" as never],
    redactionPolicy: "public_metadata_only" as const,
    expiresAt: "2026-07-22T09:00:00Z" as never,
  };

  it("freezes and returns real ArtifactVersion/Evidence (not null)", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const created = await fresh.shares.create(PROJECT_ID, request);
    expect(created.shareToken).toBeTruthy();

    const listed = await fresh.shares.list(PROJECT_ID);
    expect(listed).toHaveLength(1);

    const publicShare = await fresh.shares.getPublic(created.shareToken);
    expect(publicShare).not.toBeNull();
    expect(publicShare!.artifactVersions).toHaveLength(1);
    expect(publicShare!.artifactVersions[0]!.id).toBe("artv_dataset_01");
    expect(publicShare!.artifactVersions[0]!.kind).toBe("dataset");
    expect(publicShare!.evidence).toHaveLength(1);
    expect(publicShare!.evidence[0]!.id).toBe("evd_01");
  });

  it("returns null for a revoked share", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const created = await fresh.shares.create(PROJECT_ID, request);
    await fresh.shares.revoke(PROJECT_ID, created.id);
    expect(await fresh.shares.getPublic(created.shareToken)).toBeNull();
  });
});

describe("Fixture adapter — semantic and contract validation", () => {
  it("rejects a bundle with live execution_mode on a run", () => {
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        runs: [
          { ...exoplanetHostStarFixture.data.runs[0]!, execution_mode: "live" },
        ],
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureSemanticError,
    );
  });

  it("rejects a bundle with an invalid project DTO", () => {
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        projects: [
          {
            ...exoplanetHostStarFixture.data.projects[0]!,
            case_key: "invalid",
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureValidationError,
    );
  });
});
