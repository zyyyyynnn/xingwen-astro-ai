import { describe, expect, it } from "vitest";

import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";
import type { FixtureBundle } from "../src/fixture/bundle";
import { dataArtifactReads } from "../src/fixture/formal-artifacts";
import { createFixtureRepositories } from "../src/fixture-adapter";
import { createFixtureDataArtifactRepository } from "../src/data-artifact-repository";
import { FixtureSemanticError, FixtureValidationError } from "../src/errors";
import { ConflictError, NotFoundError } from "../src/errors";

const repos = createFixtureRepositories(exoplanetHostStarFixture);

const PROJECT_ID = "proj_01JEXAMPLE" as never;
const DRAFT_ID = "rcd_01JEXAMPLE" as never;
const EDITABLE_DRAFT_ID = "rcd_01JTOUR" as never;
const CONTRACT_ID = "rc_01JEXAMPLE" as never;
const RUN_ID = "run_01JEXAMPLE" as never;

// Canonical content hash of the fixture contract input — mirrors the backend
// `canonical_request_hash` over `ResearchContractInput`. The editable draft
// `rcd_01JTOUR` carries the same input as the pre-seeded contract
// `rc_01JEXAMPLE`, so confirming it must reproduce this exact hash.
const EXPECTED_CONTRACT_HASH =
  "sha256:82d51bd3fb5739b5ab1afeefa59c270de416bb20d6e780f39dca3c66c90d479a";
const ALL_ZERO_HASH = "sha256:" + "0".repeat(64);

describe("Fixture adapter — provenance and semantics", () => {
  it("uses entity identifiers rather than the last coordinate in a crossmatch identity", async () => {
    const source = dataArtifactReads[0]!;
    const row = source.dataset.rows[0]!;
    if (!("logical_key" in row.row_authority))
      throw new Error("crossmatch row required");
    const authority = row.row_authority;
    const values = [
      { field_id: "star.name", normalized_value: "gj 806" },
      { field_id: "star.tic_id", normalized_value: "TIC 239332587" },
      { field_id: "system.right_ascension", normalized_value: "311.2697" },
      { field_id: "system.declination", normalized_value: "44.500235" },
    ].map((value) => ({ ...value, normalization_rule_version: "1.0.0" }));
    for (const identityValues of [values, [...values].reverse()]) {
      const repository = createFixtureDataArtifactRepository([
        {
          ...source,
          dataset: {
            ...source.dataset,
            rows: [
              {
                ...row,
                row_authority: {
                  ...authority,
                  entity_level: "host_star",
                  canonical_row_identity: {
                    ...authority.canonical_row_identity,
                    entity_level: "host_star",
                    member_entities: [
                      {
                        entity_level: "host_star",
                        identity_values: identityValues,
                      },
                    ],
                  },
                },
              },
            ],
          },
        },
      ]);
      const mapped = await repository.getDataset(
        source.artifact_version_id as never,
      );
      expect(mapped.rows[0]?.identity).toBe("gj 806");
      expect(mapped.rows[0]?.sourceSnapshotIds).toEqual(
        row.source_snapshot_ids,
      );
      expect(mapped.rows[0]?.evidenceIds).toEqual(row.evidence_ids);
      expect(mapped.rows[0]?.cells).toHaveLength(row.fields.length);
    }
  });

  it("labels numeric TOI identities as catalogue identifiers", async () => {
    const source = dataArtifactReads[0]!;
    const row = source.dataset.rows[0]!;
    if (!("logical_key" in row.row_authority))
      throw new Error("crossmatch row required");
    const authority = row.row_authority;
    const repository = createFixtureDataArtifactRepository([
      {
        ...source,
        dataset: {
          ...source.dataset,
          rows: [
            {
              ...row,
              fields: row.fields.filter(
                (field) => field.canonical_field_id !== "planet.toi_id",
              ),
              row_authority: {
                ...authority,
                canonical_row_identity: {
                  ...authority.canonical_row_identity,
                  member_entities: [
                    {
                      entity_level: "planet_candidate",
                      identity_values: [
                        {
                          field_id: "planet.toi_id",
                          normalized_value: "455.01",
                          normalization_rule_version: "1.0.0",
                        },
                      ],
                    },
                  ],
                },
              },
            },
          ],
        },
      },
    ]);
    const mapped = await repository.getDataset(
      source.artifact_version_id as never,
    );
    expect(mapped.rows[0]?.identity).toBe("TOI-455.01");
  });

  it("maps Dataset cell pipeline Evidence references to persisted Evidence ids", async () => {
    const source = dataArtifactReads[0]!;
    const sourceRow = source.dataset.rows[0]!;
    const pipelineEvidenceId = "evidence.transformation.fixture-cell";
    const persistedEvidenceId = source.evidence[0]!.id;
    const read = {
      ...source,
      evidence: [source.evidence[0]!],
      dataset: {
        ...source.dataset,
        evidence_ids: [pipelineEvidenceId],
        rows: [
          {
            ...sourceRow,
            fields: sourceRow.fields.map((field, index) =>
              index === 0
                ? {
                    ...field,
                    transformation_evidence_ids: [pipelineEvidenceId],
                  }
                : field,
            ),
          },
          ...source.dataset.rows.slice(1),
        ],
      },
    };
    const repository = createFixtureDataArtifactRepository([read]);

    const dataset = await repository.getDataset(
      source.artifact_version_id as never,
    );

    expect(dataset.rows[0]!.cells[0]!.evidenceIds).toEqual([
      persistedEvidenceId,
    ]);
  });

  it("rejects a Dataset cell Evidence reference without a persisted binding", async () => {
    const source = dataArtifactReads[0]!;
    const sourceRow = source.dataset.rows[0]!;
    const read = {
      ...source,
      dataset: {
        ...source.dataset,
        rows: [
          {
            ...sourceRow,
            fields: sourceRow.fields.map((field, index) =>
              index === 0
                ? {
                    ...field,
                    transformation_evidence_ids: [
                      "evidence.transformation.unbound",
                    ],
                  }
                : field,
            ),
          },
          ...source.dataset.rows.slice(1),
        ],
      },
    };
    const repository = createFixtureDataArtifactRepository([read]);

    await expect(
      repository.getDataset(source.artifact_version_id as never),
    ).rejects.toMatchObject({ code: "SCHEMA_VALIDATION_FAILED" });
  });

  it("reports demo_replay execution mode and fixture source mode", () => {
    const { state } = repos.provenance;
    expect(state.executionMode).toBe("demo_replay");
    expect(state.sourceMode).toBe("fixture");
    expect(state.schemaVersion).toBe("2.0.0");
    expect(state.note).toContain("Demo Replay");
  });

  it("reports evidence completeness from the fixture", () => {
    const { state } = repos.provenance;
    const evidenceCount = exoplanetHostStarFixture.data.evidence.length;
    expect(state.evidenceCompleteness.covered).toBe(evidenceCount);
    expect(state.evidenceCompleteness.total).toBe(evidenceCount);
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
    expect(contract!.contentHash).toBe(EXPECTED_CONTRACT_HASH);
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
    expect(artifacts.some((artifact) => artifact.kind === "export")).toBe(true);
    const artifact = await repos.artifacts.getArtifact("art_graph_01" as never);
    expect(artifact!.kind).toBe("graph");
    const version = await repos.artifacts.getVersion(
      "artv_dataset_01" as never,
    );
    // Generic version reads are narrowed to metadata: identity + provenance
    // only, never the scientific content payload.
    expect(version!.versionNumber).toBe(1);
    expect(version!.sourceMode).toBe("fixture");
    expect(version!).not.toHaveProperty("content");
    const evidence = await repos.artifacts.getEvidence("evd_01" as never);
    expect(evidence!.evidenceType).toBe("database_query");
  });

  it("serves a TAN-projected FITS fixture that the WWT renderer can open", async () => {
    const artifactVersionId = "artv_c_fits_01" as never;
    const review = await repos.scientificArtifacts.getReview(artifactVersionId);
    expect("content" in review).toBe(true);
    if (!("content" in review) || review.content.kind !== "visualization") {
      throw new Error("Expected the FITS fixture to be a visualization read");
    }
    if (review.content.spec.mode !== "fits_image") {
      throw new Error("Expected the FITS fixture to use fits_image mode");
    }
    const bytes = await repos.scientificArtifacts.getContent(
      artifactVersionId,
      review.content.spec.contentHash,
    );
    const header = new TextDecoder("ascii").decode(bytes.slice(0, 2880));
    expect(header).toContain("CTYPE1");
    expect(header).toContain("'RA---TAN'");
    expect(header).toContain("CTYPE2");
    expect(header).toContain("'DEC--TAN'");
  });

  it("serves WWT table fixtures as CRLF-delimited CSV", async () => {
    const artifactVersionId = "artv_c_wwt_01" as never;
    const review = await repos.scientificArtifacts.getReview(artifactVersionId);
    if (!("content" in review) || review.content.kind !== "visualization") {
      throw new Error("Expected the WWT fixture to be a visualization read");
    }
    if (review.content.spec.mode !== "wwt_scene") {
      throw new Error("Expected the WWT fixture to use wwt_scene mode");
    }
    const tableLayer = review.content.spec.tableLayers[0];
    expect(tableLayer).toBeDefined();
    const bytes = await repos.scientificArtifacts.getContent(
      artifactVersionId,
      tableLayer!.contentHash,
    );
    const csv = new TextDecoder().decode(bytes);
    const rows = csv.split("\r\n");
    expect(rows[0]).toBe("ra,dec,phot_g_mean_mag");
    expect(rows).toHaveLength(42);
    expect(rows.at(-1)).toBe("");
    expect(csv.replaceAll("\r\n", "")).not.toContain("\n");
  });

  it("reads paper collection version metadata from its rich immutable version", async () => {
    const acquisition = exoplanetHostStarFixture.data.paperAcquisitions[0]!;
    expect(acquisition.version.content).toEqual(
      acquisition.collection.collection,
    );
    expect(acquisition.version.content_hash).toBe(
      acquisition.collection.content_hash,
    );
    expect(
      exoplanetHostStarFixture.data.artifactVersions.some(
        (version) => version.id === acquisition.version.id,
      ),
    ).toBe(false);

    const version = await repos.artifacts.getVersion(
      acquisition.version.id as never,
    );
    expect(version).not.toBeNull();
    expect(version!.contentHash).toBe(acquisition.collection.content_hash);
    expect(version).not.toHaveProperty("content");
  });

  it("classifies a missing paper collection version like the HTTP adapter", async () => {
    const failure = await repos.paperAcquisition
      .getReview("artv_missing" as never)
      .then(
        () => null,
        (error: unknown) => error,
      );

    expect(failure).toBeInstanceOf(NotFoundError);
    expect((failure as NotFoundError).code).toBe("ARTIFACT_VERSION_NOT_FOUND");
  });
});

describe("Fixture adapter — draft update and contract confirm", () => {
  it("rejects a draft update with a stale expected version", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    await expect(
      fresh.contracts.updateDraft(EDITABLE_DRAFT_ID, 99, { intent: "stale" }),
    ).rejects.toBeInstanceOf(ConflictError);
  });

  it("updates a draft and bumps its version", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const updated = await fresh.contracts.updateDraft(EDITABLE_DRAFT_ID, 1, {
      intent: "Refined intent",
    });
    expect(updated.intent).toBe("Refined intent");
    expect(updated.version).toBe(2);
  });

  it("confirms a contract from a draft (version-checked)", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const contract = await fresh.contracts.confirm(
      PROJECT_ID,
      EDITABLE_DRAFT_ID,
      1,
    );
    expect(contract.projectId).toBe(PROJECT_ID);
    expect(contract.version).toBe(2);
    expect(contract.researchGoal).toContain("exoplanet");
    expect(
      (await fresh.contracts.getDraftById(EDITABLE_DRAFT_ID))?.status,
    ).toBe("confirmed");
    expect((await fresh.projects.getById(PROJECT_ID))?.activeContractId).toBe(
      contract.id,
    );
    await expect(
      fresh.contracts.updateDraft(EDITABLE_DRAFT_ID, 1, {
        intent: "edited after confirmation",
      }),
    ).rejects.toBeInstanceOf(ConflictError);
    await expect(
      fresh.contracts.confirm(PROJECT_ID, EDITABLE_DRAFT_ID, 1),
    ).rejects.toBeInstanceOf(ConflictError);
  });
});

describe("Fixture adapter — contract content hash", () => {
  it("computes a real canonical hash, not the all-zero placeholder", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const contract = await fresh.contracts.confirm(
      PROJECT_ID,
      EDITABLE_DRAFT_ID,
      1,
    );
    expect(contract.contentHash).toBe(EXPECTED_CONTRACT_HASH);
    expect(contract.contentHash).not.toBe(ALL_ZERO_HASH);
    expect(contract.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/u);
  });

  it("is deterministic: identical input yields the same hash across repos", async () => {
    const a = createFixtureRepositories(exoplanetHostStarFixture);
    const b = createFixtureRepositories(exoplanetHostStarFixture);
    const first = await a.contracts.confirm(PROJECT_ID, EDITABLE_DRAFT_ID, 1);
    const second = await b.contracts.confirm(PROJECT_ID, EDITABLE_DRAFT_ID, 1);
    expect(second.contentHash).toBe(first.contentHash);
    expect(second.contentHash).toBe(EXPECTED_CONTRACT_HASH);
  });

  it("changes when the contract content changes", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const base = (await fresh.contracts.getDraftById(EDITABLE_DRAFT_ID))!
      .contract;
    const updated = await fresh.contracts.updateDraft(EDITABLE_DRAFT_ID, 1, {
      contract: {
        ...base,
        researchGoal: "Integrate stellar ages and metallicities" as never,
      },
    });
    const contract = await fresh.contracts.confirm(
      PROJECT_ID,
      EDITABLE_DRAFT_ID,
      updated.version,
    );
    expect(contract.contentHash).not.toBe(EXPECTED_CONTRACT_HASH);
    expect(contract.contentHash).not.toBe(ALL_ZERO_HASH);
    expect(contract.contentHash).toMatch(/^sha256:[0-9a-f]{64}$/u);
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
      idempotencyKey: "fixture-run-action-01",
      executionMode: "demo_replay",
    });
    expect(run.id).toBe("run_test");
    expect(run.status).toBe("queued");
    expect(run.executionMode).toBe("demo_replay");
    const events = await fresh.runs.listEvents(run.id);
    expect(events).toHaveLength(1);
    expect(events[0]!.activityPhase).toBe("queued");
  });

  it("replays one action key but allows a new identical action", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const input = {
      projectId: PROJECT_ID,
      contractId: CONTRACT_ID,
      idempotencyKey: "fixture-run-action-01",
      executionMode: "demo_replay" as const,
    };
    const first = await fresh.runs.create(input);
    const replay = await fresh.runs.create(input);
    const next = await fresh.runs.create({
      ...input,
      idempotencyKey: "fixture-run-action-02",
    });

    expect(replay).toEqual(first);
    expect(next.id).not.toBe(first.id);
    await expect(
      fresh.runs.create({
        ...input,
        contractId: "rc_other" as never,
      }),
    ).rejects.toMatchObject({ code: "IDEMPOTENCY_CONFLICT" });
  });

  it("rejects live execution in the Demo Replay adapter", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    await expect(
      fresh.runs.create({
        projectId: PROJECT_ID,
        contractId: CONTRACT_ID,
        idempotencyKey: "invalid-live-action",
        executionMode: "live",
      }),
    ).rejects.toBeInstanceOf(FixtureSemanticError);
  });

  it("uses NotFoundError consistently for events of an unknown run", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const missing = "run_missing" as never;
    await expect(fresh.runs.listEvents(missing)).rejects.toBeInstanceOf(
      NotFoundError,
    );
    await expect(fresh.runs.recoverEvents(missing)).rejects.toBeInstanceOf(
      NotFoundError,
    );
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
    expect(saved.atlasState).toEqual({
      focusMode: null,
      selectedObjectRef: null,
    });
    expect(saved.observatoryState).toEqual({
      activeArtifactVersionId: null,
      activeEvidenceId: null,
    });
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
    redactionPolicy: "redacted_public_snapshot" as const,
    expiresAt: "2026-07-22T09:00:00Z" as never,
  };

  it("freezes and returns real ArtifactVersion/Evidence (not null)", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const created = await fresh.shares.create(PROJECT_ID, request);
    expect(created.shareToken).toBeTruthy();
    expect(created.shareUrl).toBe(`/api/public/shares/${created.shareToken}`);

    const listed = await fresh.shares.list(PROJECT_ID);
    expect(listed).toHaveLength(1);

    const publicShare = await fresh.shares.getPublic(created.shareToken);
    expect(publicShare).not.toBeNull();
    expect(publicShare!.artifactVersions).toHaveLength(1);
    expect(publicShare!.artifactVersions[0]!.id).toBe("artv_dataset_01");
    expect(publicShare!.artifactVersions[0]!.kind).toBe("dataset");
    const publicContent = JSON.stringify(
      publicShare!.artifactVersions[0]!.presentation,
    );
    expect(publicContent).not.toContain("source_snapshot_id");
    expect(publicContent).not.toContain("input_hash");
    expect(publicContent).not.toContain("producer");
    expect(publicShare!.evidence.map((item) => item.id)).toEqual(
      publicShare!.artifactVersions[0]!.evidenceIds,
    );
    expect(created.evidenceIds).toEqual(
      publicShare!.artifactVersions[0]!.evidenceIds,
    );
    expect(publicShare!.evidence[0]!.id).toBe("evd_01");
    expect(
      Object.keys(publicShare!.evidence[0]!.source.requestMetadata).every(
        (key) =>
          ["source_url", "url", "original_url", "landing_url"].includes(key),
      ),
    ).toBe(true);
  });

  it("returns null for a revoked share", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const created = await fresh.shares.create(PROJECT_ID, request);
    await fresh.shares.revoke(PROJECT_ID, created.id);
    expect(await fresh.shares.getPublic(created.shareToken)).toBeNull();
  });

  it("marks a previously created share expired and hides its public projection", async () => {
    let now = "2026-07-21T09:00:00Z" as never;
    const fresh = createFixtureRepositories(exoplanetHostStarFixture, {
      clock: () => now,
    });
    const created = await fresh.shares.create(PROJECT_ID, request);
    now = "2026-07-23T09:00:00Z" as never;
    expect((await fresh.shares.list(PROJECT_ID))[0]?.status).toBe("expired");
    expect(await fresh.shares.getPublic(created.shareToken)).toBeNull();
  });

  it("rejects expired and out-of-scope share requests", async () => {
    const expired = createFixtureRepositories(exoplanetHostStarFixture, {
      clock: () => "2026-07-23T09:00:00Z" as never,
    });
    await expect(
      expired.shares.create(PROJECT_ID, request),
    ).rejects.toBeInstanceOf(FixtureValidationError);

    const bundle: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        evidence: exoplanetHostStarFixture.data.evidence.map((evidence) =>
          evidence.id === "evd_01"
            ? { ...evidence, artifactVersionId: "artv_claims_01" as never }
            : evidence,
        ),
      },
    };
    const fresh = createFixtureRepositories(bundle);
    await expect(
      fresh.shares.create(PROJECT_ID, request),
    ).rejects.toBeInstanceOf(FixtureValidationError);
  });

  it.each([
    { title: " " as never },
    { title: "x".repeat(201) as never },
    {
      artifactVersionIds: Array.from(
        { length: 101 },
        (_, index) => `artv_${index}` as never,
      ),
    },
    { redactionPolicy: "private" as never },
    { expiresAt: "2026-07-24T09:00:00+08:00" as never },
  ])(
    "rejects a Share request outside the API contract: %o",
    async (override) => {
      const fresh = createFixtureRepositories(exoplanetHostStarFixture);
      await expect(
        fresh.shares.create(PROJECT_ID, { ...request, ...override }),
      ).rejects.toBeInstanceOf(FixtureValidationError);
    },
  );

  it("normalizes Share titles like the API authoring model", async () => {
    const fresh = createFixtureRepositories(exoplanetHostStarFixture);
    const created = await fresh.shares.create(PROJECT_ID, {
      ...request,
      title: "  Public dataset evidence  " as never,
    });

    expect(created.title).toBe("Public dataset evidence");
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

  it("validates fixture presentations against the generated Contract", () => {
    const current =
      exoplanetHostStarFixture.data.artifactPresentations.artv_claims_01!;
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        artifactPresentations: {
          ...exoplanetHostStarFixture.data.artifactPresentations,
          artv_claims_01: { ...current, facts: [{ label: "", values: [] }] },
        } as never,
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureValidationError,
    );
  });

  it("rejects presentation Evidence outside its immutable version", () => {
    const current =
      exoplanetHostStarFixture.data.artifactPresentations.artv_claims_01!;
    const entry = current.entries?.[0];
    expect(entry).toBeDefined();
    const tampered: FixtureBundle = {
      ...exoplanetHostStarFixture,
      data: {
        ...exoplanetHostStarFixture.data,
        artifactPresentations: {
          ...exoplanetHostStarFixture.data.artifactPresentations,
          artv_claims_01: {
            ...current,
            entries: [
              { ...entry!, evidence_ids: ["evidence-from-other-version"] },
            ],
          },
        },
      },
    };
    expect(() => createFixtureRepositories(tampered)).toThrow(
      FixtureSemanticError,
    );
  });
});
