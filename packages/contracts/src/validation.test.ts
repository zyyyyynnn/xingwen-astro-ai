import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  CONTRACT_SCHEMA_VERSION,
  CORE_MODEL_NAMES,
  isDto,
  parseDto,
  validateDto,
} from "./validation";

const validProject = {
  id: "proj_test",
  session_id: "sess_test",
  name: "Test project",
  case_key: "exoplanet_host_star",
  thread_summary: {
    has_thread_entries: false,
    latest_thread_actor: null,
    has_unanswered_clarification: false,
  },
  created_at: "2026-07-21T08:00:00Z",
  updated_at: "2026-07-21T08:00:00Z",
  revision: 1,
};

describe("contract validation — ResearchProject", () => {
  it("accepts a valid project", () => {
    const result = validateDto("ResearchProject", validProject);
    expect(result.ok).toBe(true);
    expect(result.data).toEqual(validProject);
  });

  it("rejects a missing required field", () => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { revision: _removed, ...missingRevision } = validProject;
    const result = validateDto("ResearchProject", missingRevision);
    expect(result.ok).toBe(false);
    expect(result.errors.some((e) => e.keyword === "required")).toBe(true);
  });

  it("rejects additional properties", () => {
    const result = validateDto("ResearchProject", {
      ...validProject,
      extra_field: "not allowed",
    });
    expect(result.ok).toBe(false);
    expect(
      result.errors.some((e) => e.keyword === "additionalProperties"),
    ).toBe(true);
  });

  it("rejects an invalid date-time format", () => {
    const result = validateDto("ResearchProject", {
      ...validProject,
      created_at: "not-a-date",
    });
    expect(result.ok).toBe(false);
  });

  it("rejects an invalid case_key", () => {
    const result = validateDto("ResearchProject", {
      ...validProject,
      case_key: "invalid_case",
    });
    expect(result.ok).toBe(false);
  });
});

describe("contract validation — ResearchRun", () => {
  const validRun = {
    id: "run_test",
    project_id: "proj_test",
    contract_id: "rc_test",
    execution_mode: "demo_replay",
    status: "completed",
    progress: 100,
    derivation_kind: "original",
    cache_policy: "disabled",
    created_at: "2026-07-21T08:00:00Z",
    updated_at: "2026-07-21T08:30:00Z",
  };

  it("accepts a valid run", () => {
    expect(validateDto("ResearchRun", validRun).ok).toBe(true);
  });

  it("rejects an invalid execution_mode", () => {
    expect(
      validateDto("ResearchRun", { ...validRun, execution_mode: "test" }).ok,
    ).toBe(false);
  });

  it("rejects an invalid status enum", () => {
    expect(
      validateDto("ResearchRun", { ...validRun, status: "unknown" }).ok,
    ).toBe(false);
  });
});

describe("contract validation — parseDto", () => {
  it("returns typed data on success", () => {
    const data = parseDto("ResearchProject", validProject);
    expect(data).toEqual(validProject);
  });

  it("throws on invalid data with descriptive errors", () => {
    expect(() => parseDto("ResearchProject", { wrong: true })).toThrow(
      /ResearchProject/,
    );
  });
});

describe("contract validation — isDto type guard", () => {
  it("returns true for valid data", () => {
    expect(isDto("ResearchProject", validProject)).toBe(true);
  });

  it("returns false for invalid data", () => {
    expect(isDto("ResearchProject", { wrong: true })).toBe(false);
  });

  it("returns false for unknown model", () => {
    expect(isDto("Unknown" as never, validProject)).toBe(false);
  });
});

describe("contract — schema metadata", () => {
  it("exposes core and generic provenance read model names", () => {
    expect(CORE_MODEL_NAMES).toHaveLength(24);
    expect(CORE_MODEL_NAMES).toContain("ResearchProject");
    expect(CORE_MODEL_NAMES).toContain("ResearchThreadEntry");
    expect(CORE_MODEL_NAMES).toContain("ResearchTurnResult");
    expect(CORE_MODEL_NAMES).toContain("RunStepRead");
    expect(CORE_MODEL_NAMES).toContain("ModelExecutionRecord");
    expect(CORE_MODEL_NAMES).toContain("ResearchPlanningCatalog");
    expect(CORE_MODEL_NAMES).toContain("ArtifactVersion");
    expect(CORE_MODEL_NAMES).toContain("EvidenceRead");
    expect(CORE_MODEL_NAMES).toContain("SourceSnapshotDetail");
    expect(CORE_MODEL_NAMES).toContain("PaperCollectionRead");
    expect(CORE_MODEL_NAMES).toContain("PaperCollectionCandidateRead");
    expect(CORE_MODEL_NAMES).toContain("PaperSummaryRead");
    expect(CORE_MODEL_NAMES).toContain("SessionCreated");
    expect(CORE_MODEL_NAMES).toContain("WorkspaceSnapshot");
    expect(CORE_MODEL_NAMES).toContain("ShareSnapshot");
    expect(CORE_MODEL_NAMES).toContain("ShareSnapshotCreated");
    expect(CORE_MODEL_NAMES).toContain("PublicShareSnapshot");
  });

  it("exposes the manifest schema version", () => {
    expect(CONTRACT_SCHEMA_VERSION).toBe(1);
  });
});

describe("contract — drift guard", () => {
  const sourceRoot = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "../../schemas/generated/core",
  );
  const vendoredRoot = resolve(
    dirname(fileURLToPath(import.meta.url)),
    "generated/core",
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
    it(`vendored ${file} matches the Core Domain and Transport Contract source`, () => {
      const source = readFileSync(resolve(sourceRoot, file), "utf8");
      const vendored = readFileSync(resolve(vendoredRoot, file), "utf8");
      expect(vendored).toBe(source);
    });
  }
});
