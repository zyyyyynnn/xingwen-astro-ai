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
  const dir = mkdtempSync(join(tmpdir(), "agent-upstream-gate-"));
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
function loadLock(dir) {
  return JSON.parse(
    readFileSync(
      join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
      "utf8",
    ),
  );
}
function saveLock(dir, lock) {
  writeFileSync(
    join(dir, "apps/workspace/upstream/openhands/upstream-lock.json"),
    JSON.stringify(lock, null, 2),
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

// pick first REQUIRED_VENDOR scope entry for positive fixtures
function firstRequired(dir) {
  return loadScope(dir).files.find(
    (f) =>
      f.classification === "REQUIRED_VENDOR" ||
      f.classification === "REQUIRED_VENDOR",
  );
}

// ============ Positive ============

test("metadata-only root passes", () => {
  const dir = freshRepo();
  try {
    assertPass(dir, "metadata-only should pass");
  } finally {
    cleanup(dir);
  }
});

test("one exact unmodified allowed file passes", () => {
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
    const content = "export const k = 1;\n";
    writeFileSync(abs, content);
    const h = sha256(content);
    entry.source_sha256 = h;
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
    assertPass(dir, "one exact unmodified allowed file should pass");
  } finally {
    cleanup(dir);
  }
});

test("one properly modified allowed file passes", () => {
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
    assertPass(dir, "one properly modified allowed file should pass");
  } finally {
    cleanup(dir);
  }
});

// ============ Lock identity negatives ============

test("G2 wrong lock commit fails", () => {
  const dir = freshRepo();
  try {
    const lock = loadLock(dir);
    lock.commit = "0".repeat(40);
    saveLock(dir, lock);
    assertFail(dir, "wrong lock commit should fail");
  } finally {
    cleanup(dir);
  }
});
test("G2 wrong lock tag fails", () => {
  const dir = freshRepo();
  try {
    const lock = loadLock(dir);
    lock.tag = "v9.99.9";
    saveLock(dir, lock);
    assertFail(dir, "wrong lock tag should fail");
  } finally {
    cleanup(dir);
  }
});
test("G2 wrong lock repository fails", () => {
  const dir = freshRepo();
  try {
    const lock = loadLock(dir);
    lock.repository = "https://github.com/Other/Other.git";
    saveLock(dir, lock);
    assertFail(dir, "wrong lock repository should fail");
  } finally {
    cleanup(dir);
  }
});

// ============ Scope integrity negatives ============

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
test("duplicate scope upstream_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.files.push({ ...scope.files[0] });
    saveScope(dir, scope);
    assertFail(dir, "duplicate upstream_path should fail");
  } finally {
    cleanup(dir);
  }
});
test("scope summary mismatch fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.summary.REQUIRED_VENDOR += 1;
    saveScope(dir, scope);
    assertFail(dir, "summary mismatch should fail");
  } finally {
    cleanup(dir);
  }
});
test("scope total_src_files mismatch fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.total_src_files += 1;
    saveScope(dir, scope);
    assertFail(dir, "total_src_files mismatch should fail");
  } finally {
    cleanup(dir);
  }
});
test("scope source_sha256 invalid fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.files[0].source_sha256 = "zzz";
    saveScope(dir, scope);
    assertFail(dir, "invalid source_sha256 should fail");
  } finally {
    cleanup(dir);
  }
});
test("forbidden scope classification fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    scope.files[0].classification = "REWRITE";
    saveScope(dir, scope);
    assertFail(dir, "forbidden classification should fail");
  } finally {
    cleanup(dir);
  }
});
test("coding surface adopted fails", () => {
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

// ============ G9 private reasoning boundary negatives ============

test("private reasoning excluded path not EXCLUDED fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const p = scope.policy_sets.private_reasoning_excluded[0];
    const f = scope.files.find((x) => x.upstream_path === p);
    f.classification = "REQUIRED_VENDOR";
    saveScope(dir, scope);
    assertFail(dir, "private-reasoning-excluded not EXCLUDED should fail");
  } finally {
    cleanup(dir);
  }
});
test("public disclosure path missing PARTIAL_SURGICAL fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const p = scope.policy_sets.public_reasoning_disclosure[0];
    const f = scope.files.find((x) => x.upstream_path === p);
    f.classification = "REQUIRED_VENDOR";
    delete f.constraints;
    saveScope(dir, scope);
    assertFail(dir, "disclosure path not PARTIAL_SURGICAL should fail");
  } finally {
    cleanup(dir);
  }
});
test("public disclosure path missing constraints fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const p = scope.policy_sets.public_reasoning_disclosure[0];
    const f = scope.files.find((x) => x.upstream_path === p);
    delete f.constraints;
    saveScope(dir, scope);
    assertFail(dir, "disclosure path missing constraints should fail");
  } finally {
    cleanup(dir);
  }
});

// ============ G5 provenance negatives ============

test("src without provenance json fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const abs = join(dir, `apps/workspace/upstream/openhands/${up}`);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const y = 1;\n");
    assertFail(dir, "src/ without provenance.json should fail");
  } finally {
    cleanup(dir);
  }
});
test("disk file missing provenance entry fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const abs = join(dir, `apps/workspace/upstream/openhands/${up}`);
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
test("dangling provenance entry fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const abs = join(dir, `apps/workspace/upstream/openhands/${up}`);
    mkdirSync(resolve(abs, ".."), { recursive: true });
    writeFileSync(abs, "export const y = 1;\n");
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
test("duplicate local_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) =>
        f.classification === "REQUIRED" ||
        f.classification === "REQUIRED_VENDOR",
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
test("unknown upstream_path fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const abs = join(dir, `apps/workspace/upstream/openhands/${up}`);
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
          local_path: `apps/workspace/upstream/openhands/${up}`,
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
test("EXCLUDED upstream_path in provenance fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const ex = scope.files.find((f) => f.classification === "EXCLUDED");
    const abs = join(dir, "apps/workspace/upstream/openhands/src/excluded.ts");
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
          upstream_path: ex.upstream_path,
          local_path: "apps/workspace/upstream/openhands/src/excluded.ts",
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "EXCLUDED upstream_path in provenance should fail");
  } finally {
    cleanup(dir);
  }
});
test("DEFERRED upstream_path in provenance fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const df = scope.files.find(
      (f) => f.classification === "DEFERRED_NOT_VENDORED",
    );
    const abs = join(dir, "apps/workspace/upstream/openhands/src/deferred.ts");
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
          upstream_path: df.upstream_path,
          local_path: "apps/workspace/upstream/openhands/src/deferred.ts",
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "DEFERRED upstream_path in provenance should fail");
  } finally {
    cleanup(dir);
  }
});

// ============ Parameterized: missing required provenance field ============

const REQUIRED_FIELDS = [
  "upstream_repository",
  "upstream_tag",
  "upstream_commit",
  "upstream_path",
  "local_path",
  "upstream_source_sha256",
  "vendored_sha256",
  "adoption_class",
  "modified",
  "license",
];
for (const field of REQUIRED_FIELDS) {
  test(`missing provenance field "${field}" fails`, () => {
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
      delete entry[field];
      writeFileSync(
        join(dir, "apps/workspace/upstream/openhands/provenance.json"),
        JSON.stringify([entry]),
      );
      assertFail(dir, `missing ${field} should fail`);
    } finally {
      cleanup(dir);
    }
  });
}

// ============ Exact identity / class / hash negatives ============

test("wrong provenance repository fails", () => {
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
          upstream_repository: "https://github.com/Other/Other.git",
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
    assertFail(dir, "wrong provenance repository should fail");
  } finally {
    cleanup(dir);
  }
});
test("wrong provenance tag fails", () => {
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
          upstream_tag: "v0.0.1",
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
    assertFail(dir, "wrong provenance tag should fail");
  } finally {
    cleanup(dir);
  }
});
test("wrong provenance commit fails", () => {
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
          upstream_commit: "0".repeat(40),
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
    assertFail(dir, "wrong provenance commit should fail");
  } finally {
    cleanup(dir);
  }
});
test("wrong provenance license fails", () => {
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
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "Apache-2.0",
        },
      ]),
    );
    assertFail(dir, "wrong provenance license should fail");
  } finally {
    cleanup(dir);
  }
});
test("invalid hash format fails", () => {
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
          upstream_source_sha256: "xyz",
          vendored_sha256: "xyz",
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "invalid hash format should fail");
  } finally {
    cleanup(dir);
  }
});
test("invalid adoption_class fails", () => {
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
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "REMOVE_CODING_SURFACE",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "REMOVE_CODING_SURFACE for actual file should fail");
  } finally {
    cleanup(dir);
  }
});
test("PARTIAL_SURGICAL + KEEP_AS_IS mismatch fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.policy_sets.public_reasoning_disclosure[0];
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
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "PARTIAL_SURGICAL + KEEP_AS_IS should fail");
  } finally {
    cleanup(dir);
  }
});
test("modified missing/non-boolean fails", () => {
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
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: "yes",
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "non-boolean modified should fail");
  } finally {
    cleanup(dir);
  }
});
test("modified=true without reason fails", () => {
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
          adoption_class: "KEEP_WITH_MINIMAL_PATCH",
          modified: true,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "modified=true without reason should fail");
  } finally {
    cleanup(dir);
  }
});
test("vendored file hash mismatch fails", () => {
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
test("modified=false content drift fails", () => {
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
      `[]`,
    );
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
test("local_path escaping upstream root fails", () => {
  const dir = freshRepo();
  try {
    const scope = loadScope(dir);
    const up = scope.files.find(
      (f) => f.classification === "REQUIRED_VENDOR",
    ).upstream_path;
    const abs = join(dir, `apps/workspace/upstream/openhands/${up}`);
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
          local_path: "apps/workspace/upstream/openhands/src/../../escape.ts",
          upstream_source_sha256: h,
          vendored_sha256: h,
          adoption_class: "KEEP_AS_IS",
          modified: false,
          modification_reason: null,
          license: "MIT",
        },
      ]),
    );
    assertFail(dir, "local_path traversal should fail");
  } finally {
    cleanup(dir);
  }
});
test("upstream_path traversal fails", () => {
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
          upstream_path: "../secrets.ts",
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
    assertFail(dir, "upstream_path traversal should fail");
  } finally {
    cleanup(dir);
  }
});
