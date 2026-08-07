#!/usr/bin/env node
/**
 * check-agent-upstream-adoption.test.mjs
 * Unit tests for the upstream adoption gate. Run: node --test scripts/check-agent-upstream-adoption.test.mjs
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  rmSync,
  cpSync,
  readFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkAgentUpstreamAdoption } from "./check-agent-upstream-adoption.mjs";

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const UPSTREAM = join(REPO_ROOT, "apps/workspace/upstream/openhands");

function freshRepo() {
  const dir = mkdtempSync(join(tmpdir(), "a21-gate-"));
  const up = join(dir, "apps/workspace/upstream/openhands");
  mkdirSync(up, { recursive: true });
  cpSync(UPSTREAM, up, { recursive: true });
  return dir;
}
function loadScope(dir) {
  return JSON.parse(
    readFileSync(
      join(dir, "apps/workspace/upstream/openhands/source-scope.json"),
      "utf8",
    ),
  );
}
function saveScope(dir, scope) {
  writeFileSync(
    join(dir, "apps/workspace/upstream/openhands/source-scope.json"),
    JSON.stringify(scope, null, 2),
  );
}
function sha256(s) {
  return createHash("sha256").update(s).digest("hex");
}
function cleanup(dir) {
  rmSync(dir, { recursive: true, force: true });
}
function run(root) {
  return checkAgentUpstreamAdoption(root);
}
function assertPass(root, msg) {
  const { failures } = run(root);
  assert.equal(failures.length, 0, `${msg}\n${failures.join("\n")}`);
}
function assertFail(root, msg) {
  const { failures } = run(root);
  assert.ok(failures.length > 0, `${msg} (expected failure, got pass)`);
}

// ---- Positive ----

test("metadata-only root (no src) passes", () => {
  const dir = freshRepo();
  try {
    assertPass(dir, "metadata-only should pass");
  } finally {
    cleanup(dir);
  }
});

test("one exact unmodified vendored file passes", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const entry = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    );
    const up = entry.upstream_path; // e.g. src/assets/chevron-left.tsx
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    const content = "export const k = 1;\n";
    writeFileSync(abs, content);
    const h = sha256(content);
    entry.source_sha256 = h; // fixture makes scope consistent with file
    saveScope(dir, scope);
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: localRel,
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertPass(dir, "one exact unmodified file should pass");
  } finally {
    cleanup(dir);
  }
});

test("one properly modified file with reason passes", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const entry = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    );
    const up = entry.upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    const content = "export const k = 2; // adapted\n";
    writeFileSync(abs, content);
    const h = sha256(content);
    const upstreamHash = "a".repeat(64);
    entry.source_sha256 = upstreamHash;
    saveScope(dir, scope);
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: localRel,
          upstream_source_sha256: upstreamHash,
          vendored_sha256: h,
          adoption_class: "KEEP_WITH_MINIMAL_PATCH",
          modified: true,
          modification_reason: "adapt constant for Xingwen domain",
          license: "MIT",
        },
      ]),
    );
    assertPass(dir, "one properly modified file should pass");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: exact ref ----

test("G2 wrong commit fails", () => {
  const dir = freshRepo();
  try {
    const lock = JSON.parse(
      readFileSync(
        join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
        "utf8",
      ),
    );
    lock.commit = "0".repeat(40);
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
      JSON.stringify(lock, null, 2),
    );
    assertFail(dir, "wrong commit should fail");
  } finally {
    cleanup(dir);
  }
});

test("G2 wrong tag fails", () => {
  const dir = freshRepo();
  try {
    const lock = JSON.parse(
      readFileSync(
        join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
        "utf8",
      ),
    );
    lock.tag = "v9.99.9";
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
      JSON.stringify(lock, null, 2),
    );
    assertFail(dir, "wrong tag should fail");
  } finally {
    cleanup(dir);
  }
});

test("G2 wrong repository fails", () => {
  const dir = freshRepo();
  try {
    const lock = JSON.parse(
      readFileSync(
        join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
        "utf8",
      ),
    );
    lock.repository = "https://github.com/Other/Other.git";
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
      JSON.stringify(lock, null, 2),
    );
    assertFail(dir, "wrong repository should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: alternate upstream root ----

test("alternate upstream root fails", () => {
  const dir = freshRepo();
  try {
    mkdirSync(join(dir, "apps/workspace/upstream/alternate-agent"), {
      recursive: true,
    });
    writeFileSync(
      join(dir, "apps/workspace/upstream/alternate-agent/upstream-lock.json"),
      "{}",
    );
    assertFail(dir, "alternate upstream root should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: forbidden adoption class in scope ----

test("forbidden adoption class in scope fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.files[0].classification = "REWRITE";
    saveScope(dir, scope);
    assertFail(dir, "forbidden adoption class should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: coding surface adopted ----

test("coding surface adopted as vendor fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.files[0].classification = "REQUIRED_VENDOR";
    scope.files[0].upstream_path = "components/terminal/xterm.tsx";
    saveScope(dir, scope);
    assertFail(dir, "coding surface adopted should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: missing provenance ----

test("on-disk file without provenance entry fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const y = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([]),
    );
    assertFail(dir, "missing provenance entry should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: dangling provenance (src/ exists, referenced file missing) ----

test("dangling provenance entry fails", () => {
  const dir = freshRepo();
  try {
    // create src/ so G5 runs, plus one real file so disk scan is non-empty
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const y = 1;\n");
    // provenance references a DIFFERENT (missing) local_path
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: "apps/workspace/upstream/openhands/src/missing.ts",
          upstream_source_sha256: "a".repeat(64),
          vendored_sha256: "a".repeat(64),
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "dangling provenance should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: duplicate local path ----

test("duplicate local_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    const content = "export const z = 1;\n";
    writeFileSync(abs, content);
    const h = sha256(content);
    const entry = {
      upstream_repository: "https://github.com/OpenHands/OpenHands.git",
      upstream_tag: "v1.10.0",
      upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
      upstream_path: up,
      local_path: localRel,
      upstream_source_sha256: h,
      vendored_sha256: h,
      adoption_class: "KEEP_AS_IS",
      modified: false,
      modification_reason: null,
      license: "MIT",
    };
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([entry, { ...entry }]),
    );
    assertFail(dir, "duplicate local_path should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: unknown upstream path ----

test("provenance referencing unknown upstream_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const z = 1;\n");
    const h = sha256("export const z = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: "src/does-not-exist.ts",
          local_path: localRel,
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "unknown upstream_path should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: excluded upstream path in provenance ----

test("provenance referencing EXCLUDED upstream_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const excludedEntry = scope.files.find(
      (f) => f.classification === "EXCLUDED",
    );
    const localRel = `apps/workspace/upstream/openhands/src/excluded.ts`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const z = 1;\n");
    const h = sha256("export const z = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: excludedEntry.upstream_path,
          local_path: localRel,
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "excluded upstream_path in provenance should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: vendored hash mismatch ----

test("vendored hash mismatch fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const z = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: localRel,
          upstream_source_sha256: "a".repeat(64),
          vendored_sha256: "b".repeat(64),
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "vendored hash mismatch should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: upstream source hash mismatch ----

test("upstream source hash mismatch vs scope fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const z = 1;\n");
    const h = sha256("export const z = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: localRel,
          upstream_source_sha256: "a".repeat(64),
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "upstream source hash mismatch should fail");
  } finally {
    cleanup(dir);
  }
});

// ---- Negative: unmodified content drift ----

test("modified=false with drifted vendored_sha256 fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const localRel = `apps/workspace/upstream/openhands/${up}`;
    const abs = join(dir, localRel);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const z = 1;\n");
    writeFileSync(
      join(dir, "apps/workspace/upstream/openhands/provenance.json"),
      JSON.stringify([
        {
          upstream_repository: "https://github.com/OpenHands/OpenHands.git",
          upstream_tag: "v1.10.0",
          upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
          upstream_path: up,
          local_path: localRel,
          upstream_source_sha256: "a".repeat(64),
          vendored_sha256: "b".repeat(64),
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "unmodified drift should fail");
  } finally {
    cleanup(dir);
  }
});
