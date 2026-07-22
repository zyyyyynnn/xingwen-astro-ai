import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  V2_CONTRACT_SCHEMA_VERSION,
  V2_CORE_MODEL_NAMES,
  isV2Dto,
  parseV2Dto,
  validateV2Dto,
} from "./validation";

const validProject = {
  id: "proj_test",
  session_id: "sess_test",
  name: "Test project",
  case_key: "exoplanet_host_star",
  created_at: "2026-07-21T08:00:00Z",
  updated_at: "2026-07-21T08:00:00Z",
  revision: 1,
};

describe("v2 contract validation — ResearchProject", () => {
  it("accepts a valid project", () => {
    const result = validateV2Dto("ResearchProject", validProject);
    expect(result.ok).toBe(true);
    expect(result.data).toEqual(validProject);
  });

  it("rejects a missing required field", () => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { revision: _removed, ...missingRevision } = validProject;
    const result = validateV2Dto("ResearchProject", missingRevision);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.keyword === "required")).toBe(true);
  });

  it("rejects additional properties", () => {
    const result = validateV2Dto("ResearchProject", {
      ...validProject,
      extra_field: "not allowed",
    });
    expect(result.ok).toBe(false);
    expect(
      result.errors.some((e) => e.keyword === "additionalProperties"),
    ).toBe(true);
  });

  it("rejects an invalid date-time format", () => {
    const result = validateV2Dto("ResearchProject", {
      ...validProject,
      created_at: "not-a-date",
    });
    expect(result.ok).toBe(false);
  });

  it("rejects an invalid case_key", () => {
    const result = validateV2Dto("ResearchProject", {
      ...validProject,
      case_key: "invalid_case",
    });
    expect(result.ok).toBe(false);
  });
});

describe("v2 contract validation — ResearchRun", () => {
  const validRun = {
    id: "run_test",
    project_id: "proj_test",
    contract_id: "rc_test",
    execution_mode: "demo_replay",
    status: "completed",
    progress: 100,
    derivation_kind: "original",
    cache_policy: "fallback_on_recoverable_failure",
    created_at: "2026-07-21T08:00:00Z",
    updated_at: "2026-07-21T08:30:00Z",
  };

  it("accepts a valid run", () => {
    expect(validateV2Dto("ResearchRun", validRun).ok).toBe(true);
  });

  it("rejects an invalid execution_mode", () => {
    expect(
      validateV2Dto("ResearchRun", { ...validRun, execution_mode: "test" }).ok,
    ).toBe(false);
  });

  it("rejects an invalid status enum", () => {
    expect(
      validateV2Dto("ResearchRun", { ...validRun, status: "unknown" }).ok,
    ).toBe(false);
  });
});

describe("v2 contract validation — parseV2Dto", () => {
  it("returns typed data on success", () => {
    const data = parseV2Dto("ResearchProject", validProject);
    expect(data).toEqual(validProject);
  });

  it("throws on invalid data with descriptive errors", () => {
    expect(() => parseV2Dto("ResearchProject", { wrong: true })).toThrow(
      /ResearchProject/,
    );
  });
});

describe("v2 contract validation — isV2Dto type guard", () => {
  it("returns true for valid data", () => {
    expect(isV2Dto("ResearchProject", validProject)).toBe(true);
  });

  it("returns false for invalid data", () => {
    expect(isV2Dto("ResearchProject", { wrong: true })).toBe(false);
  });

  it("returns false for unknown model", () => {
    expect(isV2Dto("Unknown" as never, validProject)).toBe(false);
  });
});

describe("v2 contract — schema metadata", () => {
  it("exposes core and generic provenance read model names", () => {
    expect(V2_CORE_MODEL_NAMES).toHaveLength(15);
    expect(V2_CORE_MODEL_NAMES).toContain("ResearchProject");
    expect(V2_CORE_MODEL_NAMES).toContain("ArtifactVersion");
    expect(V2_CORE_MODEL_NAMES).toContain("EvidenceRead");
    expect(V2_CORE_MODEL_NAMES).toContain("SourceSnapshotDetail");
    expect(V2_CORE_MODEL_NAMES).toContain("WorkspaceSnapshot");
    expect(V2_CORE_MODEL_NAMES).toContain("ShareSnapshot");
    expect(V2_CORE_MODEL_NAMES).toContain("ShareSnapshotCreated");
    expect(V2_CORE_MODEL_NAMES).toContain("PublicShareSnapshot");
  });

  it("exposes the manifest schema version", () => {
    expect(V2_CONTRACT_SCHEMA_VERSION).toBe(1);
  });
});

describe("v2 contract — drift guard", () => {
  const sourceRoot = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../schemas/generated/v2-core",
  );
  const vendoredRoot = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "generated/v2-core",
  );

  for (const file of [
    "manifest.json",
    "json/ResearchProject.schema.json",
    "json/ResearchContractDraft.schema.json",
    "json/ResearchContract.schema.json",
    "json/ResearchRun.schema.json",
    "json/RunEvent.schema.json",
    "json/ArtifactVersion.schema.json",
    "json/ResearchArtifact.schema.json",
  ]) {
    it(`vendored ${file} matches the B-15 source`, () => {
      const source = readFileSync(resolve(sourceRoot, file), "utf8");
      const vendored = readFileSync(resolve(vendoredRoot, file), "utf8");
      expect(vendored).toBe(source);
    });
  }
});
