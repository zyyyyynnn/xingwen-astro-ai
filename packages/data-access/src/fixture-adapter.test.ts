import { describe, expect, it } from "vitest";

import { exoplanetHostStarFixture } from "./fixture/exoplanet-host-star";
import type { FixtureBundle } from "./fixture/bundle";
import { createFixtureRepositories } from "./fixture-adapter";
import { FixtureSemanticError, FixtureValidationError } from "./errors";

const repos = createFixtureRepositories(exoplanetHostStarFixture);

describe("Fixture adapter — contract validation", () => {
  it("loads the exoplanet-host-star fixture without error", () => {
    expect(repos).toBeDefined();
  });

  it("exposes all five repositories", () => {
    expect(repos.projects).toBeDefined();
    expect(repos.contracts).toBeDefined();
    expect(repos.runs).toBeDefined();
    expect(repos.artifacts).toBeDefined();
    expect(repos.evidence).toBeDefined();
  });
});

describe("Fixture adapter — provenance and semantics", () => {
  it("reports demo_replay execution mode and fixture source mode", () => {
    const { state } = repos.provenance;
    expect(state.executionMode).toBe("demo_replay");
    expect(state.sourceMode).toBe("fixture");
  });

  it("carries the scenario schema version and provenance note", () => {
    const { state } = repos.provenance;
    expect(state.schemaVersion).toBe("2.0.0");
    expect(state.note).toContain("Demo Replay");
    expect(state.note).toContain("exoplanet host-star");
  });

  it("reports evidence completeness from the fixture", () => {
    const { state } = repos.provenance;
    expect(state.evidenceCompleteness.covered).toBe(3);
    expect(state.evidenceCompleteness.total).toBe(3);
  });
});

describe("Fixture adapter — DTO does not leak to domain", () => {
  it("returns domain entities with camelCase keys, not snake_case DTO keys", async () => {
    const project = await repos.projects.getById("proj_01JEXAMPLE" as never);
    expect(project).not.toBeNull();
    expect(project!).toHaveProperty("sessionId");
    expect(project!).toHaveProperty("caseKey");
    expect(project!).toHaveProperty("createdAt");
    expect(project!).not.toHaveProperty("session_id");
    expect(project!).not.toHaveProperty("case_key");
    expect(project!).not.toHaveProperty("created_at");
  });

  it("maps artifact version content discriminator correctly", async () => {
    const version = await repos.artifacts.getVersionById(
      "artv_dataset_01" as never,
    );
    expect(version).not.toBeNull();
    expect(version!.content.kind).toBe("dataset");
    expect(version!.content).toHaveProperty("fieldIds");
    expect(version!.content).not.toHaveProperty("field_ids");
  });
});

describe("Fixture adapter — repository reads", () => {
  it("lists projects", async () => {
    const projects = await repos.projects.list();
    expect(projects).toHaveLength(1);
    expect(projects[0]!.id).toBe("proj_01JEXAMPLE" as never);
  });

  it("gets a contract by id", async () => {
    const contract = await repos.contracts.getContractById(
      "rc_01JEXAMPLE" as never,
    );
    expect(contract).not.toBeNull();
    expect(contract!.researchGoal).toContain("exoplanet");
    expect(contract!.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/);
  });

  it("lists contracts by project", async () => {
    const contracts = await repos.contracts.listContracts(
      "proj_01JEXAMPLE" as never,
    );
    expect(contracts).toHaveLength(1);
  });

  it("gets a draft by id", async () => {
    const draft = await repos.contracts.getDraftById("rcd_01JEXAMPLE" as never);
    expect(draft).not.toBeNull();
    expect(draft!.status).toBe("confirmed");
  });

  it("gets a run by id with demo_replay mode", async () => {
    const run = await repos.runs.getById("run_01JEXAMPLE" as never);
    expect(run).not.toBeNull();
    expect(run!.executionMode).toBe("demo_replay");
    expect(run!.status).toBe("completed");
    expect(run!.progress).toBe(100);
  });

  it("lists run events in sequence order", async () => {
    const events = await repos.runs.getEvents("run_01JEXAMPLE" as never);
    expect(events).toHaveLength(9);
    expect(events[0]!.eventType).toBe("run.queued" as never);
    expect(events[8]!.eventType).toBe("run.completed" as never);
    for (let i = 1; i < events.length; i++) {
      expect(events[i]!.sequence).toBe(events[i - 1]!.sequence + 1);
    }
  });

  it("lists artifacts by project", async () => {
    const artifacts = await repos.artifacts.listByProject(
      "proj_01JEXAMPLE" as never,
    );
    expect(artifacts).toHaveLength(9);
  });

  it("lists artifact versions by artifact", async () => {
    const versions = await repos.artifacts.listVersions(
      "art_graph_01" as never,
    );
    expect(versions).toHaveLength(1);
    expect(versions[0]!.sourceMode).toBe("fixture");
  });

  it("lists evidence by artifact version", async () => {
    const evidence = await repos.evidence.listByArtifactVersion(
      "artv_dataset_01" as never,
    );
    expect(evidence).toHaveLength(1);
    expect(evidence[0]!.evidenceType).toBe("database_query");
  });
});

describe("Fixture adapter — writes and subscriptions", () => {
  it("saves a new project and notifies subscribers", async () => {
    const repos2 = createFixtureRepositories(exoplanetHostStarFixture);
    const received: number[] = [];
    repos2.projects.subscribe(() => received.push(received.length));

    await repos2.projects.save({
      id: "proj_new" as never,
      sessionId: "sess_test" as never,
      name: "New project",
      description: "",
      caseKey: "exoplanet_host_star",
      activeContractId: null,
      latestRunId: null,
      createdAt: "2026-07-22T00:00:00Z",
      updatedAt: "2026-07-22T00:00:00Z",
      revision: 1,
    });

    expect(received).toHaveLength(1);
    const all = await repos2.projects.list();
    expect(all).toHaveLength(2);
    const found = await repos2.projects.getById("proj_new" as never);
    expect(found).not.toBeNull();
  });

  it("appends a run event", async () => {
    const repos2 = createFixtureRepositories(exoplanetHostStarFixture);
    await repos2.runs.appendEvent({
      runId: "run_01JEXAMPLE" as never,
      sequence: 10,
      eventType: "run.custom" as never,
      stepKey: null,
      progress: 100,
      publicMessage: "Custom event",
      artifactVersionIds: [],
      occurredAt: "2026-07-21T08:35:00Z",
    });
    const events = await repos2.runs.getEvents("run_01JEXAMPLE" as never);
    expect(events).toHaveLength(10);
    expect(events[9]!.publicMessage).toBe("Custom event");
  });
});

describe("Fixture adapter — semantic constraints", () => {
  it("rejects a bundle with live execution_mode on a run", () => {
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        runs: [
          {
            ...exoplanetHostStarFixture.data.runs[0]!,
            execution_mode: "live",
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureSemanticError,
    );
  });

  it("rejects a bundle with cached source_mode on an artifact version", () => {
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        artifactVersions: [
          {
            ...exoplanetHostStarFixture.data.artifactVersions[0]!,
            source_mode: "cached",
          },
        ],
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureSemanticError,
    );
  });
});

describe("Fixture adapter — contract validation errors", () => {
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
