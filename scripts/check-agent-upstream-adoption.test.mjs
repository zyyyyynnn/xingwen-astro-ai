#!/usr/bin/env node

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  cpSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { computeSelectedTreeSha256 } from "./agent-upstream-provenance.mjs";
import { checkAgentUpstreamAdoption } from "./check-agent-upstream-adoption.mjs";
import { generateAgentUpstreamProvenance } from "./generate-agent-upstream-provenance.mjs";

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const UPSTREAM_SOURCE = join(REPO_ROOT, UPSTREAM_ROOT);
const METADATA_FILES = [
  "upstream-lock.json",
  "source-scope.json",
  "source-policy.json",
  "vendor-blueprint.json",
  "provenance-schema.json",
  "LICENSE.upstream",
  "NOTICE.md",
];
const SOURCE = {
  repository: "https://github.com/OpenHands/OpenHands.git",
  tag: "v1.10.0",
  commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
  license: "MIT",
};
const ADOPTED_CLASSIFICATIONS = new Set([
  "REQUIRED_VENDOR",
  "REQUIRED_TRANSITIVE",
  "PARTIAL_SURGICAL",
]);

function freshRepo() {
  const root = mkdtempSync(join(tmpdir(), "agent-upstream-gate-"));
  const target = join(root, UPSTREAM_ROOT);
  mkdirSync(target, { recursive: true });
  for (const file of METADATA_FILES) {
    cpSync(join(UPSTREAM_SOURCE, file), join(target, file));
  }
  return root;
}

function cleanup(root) {
  rmSync(root, { recursive: true, force: true });
}

function load(root, file) {
  return JSON.parse(readFileSync(join(root, UPSTREAM_ROOT, file), "utf8"));
}

function save(root, file, value) {
  writeFileSync(
    join(root, UPSTREAM_ROOT, file),
    `${JSON.stringify(value, null, 2)}\n`,
    "utf8",
  );
}

function writeSource(root, upstreamPath, content) {
  const localPath = `${UPSTREAM_ROOT}/${upstreamPath}`;
  const absolute = join(root, localPath);
  mkdirSync(dirname(absolute), { recursive: true });
  writeFileSync(absolute, content, "utf8");
  return localPath;
}

function provenanceEntry({
  upstreamPath,
  localPath = `${UPSTREAM_ROOT}/${upstreamPath}`,
  modified = false,
  adoptionClass = modified ? "KEEP_WITH_MINIMAL_PATCH" : "KEEP_AS_IS",
  modificationReason = modified
    ? "Retained the approved shell mechanic."
    : null,
}) {
  return {
    upstream_path: upstreamPath,
    local_path: localPath,
    adoption_class: adoptionClass,
    modified,
    modification_reason: modificationReason,
  };
}

function saveProvenance(root, entries, overrides = {}) {
  const sourceDirectory = join(root, UPSTREAM_ROOT, "src");
  const keepAsIsPaths = entries
    .filter((entry) => entry.adoption_class === "KEEP_AS_IS")
    .map((entry) => entry.upstream_path.slice("src/".length));
  const keepAsIsDigest = computeSelectedTreeSha256(
    sourceDirectory,
    keepAsIsPaths,
  );
  const lock = load(root, "upstream-lock.json");
  lock.keep_as_is_tree_sha256 = keepAsIsDigest;
  save(root, "upstream-lock.json", lock);
  save(root, "provenance.json", {
    schema: "xingwen.agent-upstream.provenance/v2",
    generated_by: "test",
    source: SOURCE,
    keep_as_is_tree_sha256: keepAsIsDigest,
    entries,
    ...overrides,
  });
}

function saveResolution(root, provenanceEntries) {
  const scope = load(root, "source-scope.json");
  const adoptedPaths = new Set(
    provenanceEntries.map((entry) => entry.upstream_path),
  );
  for (const entry of scope.files) {
    if (
      ADOPTED_CLASSIFICATIONS.has(entry.classification) &&
      !adoptedPaths.has(entry.upstream_path)
    ) {
      entry.classification = "EXCLUDED";
      entry.reason = "Excluded from this isolated test dependency closure.";
      delete entry.constraints;
      delete entry.preserved_mechanics;
      delete entry.removed_domain;
    }
  }
  scope.approved_mechanics = scope.approved_mechanics
    .map((surface) => ({
      ...surface,
      upstream_paths: surface.upstream_paths.filter((path) =>
        adoptedPaths.has(path),
      ),
    }))
    .filter((surface) => surface.upstream_paths.length > 0);
  scope.transitive_mechanics = (scope.transitive_mechanics ?? [])
    .map((surface) => ({
      ...surface,
      upstream_paths: surface.upstream_paths.filter((path) =>
        adoptedPaths.has(path),
      ),
    }))
    .filter((surface) => surface.upstream_paths.length > 0);
  scope.summary = {
    REQUIRED_VENDOR: 0,
    REQUIRED_TRANSITIVE: 0,
    PARTIAL_SURGICAL: 0,
    EXCLUDED: 0,
    DEFERRED_NOT_VENDORED: 0,
  };
  for (const entry of scope.files) scope.summary[entry.classification] += 1;
  scope.policy_sets.public_reasoning_disclosure =
    scope.policy_sets.public_reasoning_disclosure.filter((path) =>
      adoptedPaths.has(path),
    );
  save(root, "source-scope.json", scope);

  const entries = provenanceEntries.map((entry) => ({
    upstream_path: entry.upstream_path,
    status: entry.modified ? "SURGICALLY_ADAPTED" : "VENDORED",
    reason: "test fixture disposition",
    proof: "reachable-from-single-src/root.tsx-import-closure",
  }));
  const summary = {
    VENDORED: entries.filter((entry) => entry.status === "VENDORED").length,
    SURGICALLY_ADAPTED: entries.filter(
      (entry) => entry.status === "SURGICALLY_ADAPTED",
    ).length,
  };
  save(root, "source-resolution.json", {
    schema: "xingwen.agent-upstream.source-resolution/v1",
    ...SOURCE,
    entrypoint: "src/root.tsx",
    summary,
    total: entries.length,
    entries,
  });
}

function createSingleFileFixture(root, options = {}) {
  const upstreamPath = options.upstreamPath ?? "src/root.tsx";
  const content = options.content ?? "export const root = true;\n";
  const localPath = writeSource(root, upstreamPath, content);
  const entry = provenanceEntry({
    upstreamPath,
    localPath,
    modified: options.modified,
    adoptionClass: options.adoptionClass,
    modificationReason: options.modificationReason,
  });
  saveProvenance(root, [entry]);
  saveResolution(root, [entry]);
  return { entry, localPath };
}

function assertPass(root, message) {
  const { failures } = checkAgentUpstreamAdoption(root);
  assert.deepEqual(failures, [], `${message}\n${failures.join("\n")}`);
}

function assertFail(root, pattern, message) {
  const { failures } = checkAgentUpstreamAdoption(root);
  assert.ok(failures.length > 0, `${message}: expected a failure`);
  assert.ok(
    failures.some((failure) => pattern.test(failure)),
    `${message}: expected ${pattern}, got\n${failures.join("\n")}`,
  );
}

test("metadata-only root passes", () => {
  const root = freshRepo();
  try {
    assertPass(root, "metadata-only root");
  } finally {
    cleanup(root);
  }
});

test("current vendored workspace passes", () => {
  assertPass(REPO_ROOT, "current repository");
});

test("one mapped source file passes with the aggregate manifest", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root);
    assertPass(root, "single source fixture");
  } finally {
    cleanup(root);
  }
});

test("a mapped adapted source file passes with an explicit reason", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root, { modified: true });
    assertPass(root, "adapted source fixture");
  } finally {
    cleanup(root);
  }
});

for (const [field, value] of [
  ["repository", "https://github.com/Other/Other.git"],
  ["tag", "latest"],
  ["commit", "0".repeat(40)],
]) {
  test(`lock ${field} drift fails`, () => {
    const root = freshRepo();
    try {
      const lock = load(root, "upstream-lock.json");
      lock[field] = value;
      save(root, "upstream-lock.json", lock);
      assertFail(root, /G2|G3|mismatch/u, `lock ${field}`);
    } finally {
      cleanup(root);
    }
  });
}

test("a competing upstream root fails", () => {
  const root = freshRepo();
  try {
    mkdirSync(join(root, "apps/workspace/upstream/other/src"), {
      recursive: true,
    });
    assertFail(root, /competing vendor root/u, "competing source");
  } finally {
    cleanup(root);
  }
});

test("scope summary drift fails", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    scope.summary.REQUIRED_VENDOR += 1;
    save(root, "source-scope.json", scope);
    assertFail(root, /Scope summary mismatch/u, "scope summary");
  } finally {
    cleanup(root);
  }
});

test("vendored source without provenance fails", () => {
  const root = freshRepo();
  try {
    writeSource(root, "src/root.tsx", "export const root = true;\n");
    assertFail(root, /provenance\.json missing/u, "missing provenance");
  } finally {
    cleanup(root);
  }
});

test("the retired array provenance shape fails", () => {
  const root = freshRepo();
  try {
    const { entry } = createSingleFileFixture(root);
    save(root, "provenance.json", [entry]);
    assertFail(root, /v2 manifest object contract/u, "retired manifest shape");
  } finally {
    cleanup(root);
  }
});

test("the frozen KEEP_AS_IS aggregate detects source drift", () => {
  const root = freshRepo();
  try {
    const { localPath } = createSingleFileFixture(root);
    writeFileSync(
      join(root, localPath),
      "export const root = false;\n",
      "utf8",
    );
    assertFail(root, /frozen upstream aggregate digest/u, "tree drift");
  } finally {
    cleanup(root);
  }
});

test("provenance generation cannot rewrite frozen source dispositions", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root, {
      modified: true,
      adoptionClass: "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
    });
    const resolutionPath = join(root, UPSTREAM_ROOT, "source-resolution.json");
    const before = readFileSync(resolutionPath, "utf8");
    generateAgentUpstreamProvenance(root);
    assert.equal(readFileSync(resolutionPath, "utf8"), before);
  } finally {
    cleanup(root);
  }
});

test("provenance generation rejects source outside the entrypoint closure", () => {
  const root = freshRepo();
  try {
    const rootEntry = provenanceEntry({
      upstreamPath: "src/root.tsx",
      localPath: writeSource(
        root,
        "src/root.tsx",
        "export const root = true;\n",
      ),
      modified: true,
      adoptionClass: "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
    });
    const storePath = "src/stores/command-menu-store.ts";
    const storeEntry = provenanceEntry({
      upstreamPath: storePath,
      localPath: writeSource(root, storePath, "export const store = true;\n"),
    });
    saveProvenance(root, [rootEntry, storeEntry]);
    saveResolution(root, [rootEntry, storeEntry]);

    assert.throws(
      () => generateAgentUpstreamProvenance(root),
      /outside the src\/root\.tsx dependency closure/u,
    );
  } finally {
    cleanup(root);
  }
});

test("provenance generation cannot legitimize KEEP_AS_IS drift", () => {
  const root = freshRepo();
  try {
    const rootEntry = provenanceEntry({
      upstreamPath: "src/root.tsx",
      localPath: writeSource(
        root,
        "src/root.tsx",
        'import "#/stores/command-menu-store";\nexport const root = true;\n',
      ),
      modified: true,
      adoptionClass: "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
    });
    const storePath = "src/stores/command-menu-store.ts";
    const storeEntry = provenanceEntry({
      upstreamPath: storePath,
      localPath: writeSource(root, storePath, "export const store = true;\n"),
    });
    saveProvenance(root, [rootEntry, storeEntry]);
    saveResolution(root, [rootEntry, storeEntry]);
    writeFileSync(
      join(root, storeEntry.local_path),
      "export const changed = true;\n",
    );
    assert.throws(
      () => generateAgentUpstreamProvenance(root),
      /differs from the aggregate digest frozen/u,
    );
  } finally {
    cleanup(root);
  }
});

test("manifest source identity drift fails once at the manifest boundary", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root);
    const provenance = load(root, "provenance.json");
    provenance.source.commit = "0".repeat(40);
    save(root, "provenance.json", provenance);
    assertFail(root, /provenance source commit mismatch/u, "source identity");
  } finally {
    cleanup(root);
  }
});

test("disk and provenance paths must have exact one-to-one coverage", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root);
    const provenance = load(root, "provenance.json");
    provenance.entries = [];
    save(root, "provenance.json", provenance);
    assertFail(
      root,
      /on-disk file has no provenance entry/u,
      "missing mapping",
    );
  } finally {
    cleanup(root);
  }
});

test("local paths must preserve the upstream relative path", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root);
    const provenance = load(root, "provenance.json");
    provenance.entries[0].upstream_path = "src/renamed.tsx";
    save(root, "provenance.json", provenance);
    assertFail(root, /preserve the upstream relative path/u, "path mapping");
  } finally {
    cleanup(root);
  }
});

for (const field of [
  "upstream_path",
  "local_path",
  "adoption_class",
  "modified",
]) {
  test(`missing provenance entry field ${field} fails`, () => {
    const root = freshRepo();
    try {
      createSingleFileFixture(root);
      const provenance = load(root, "provenance.json");
      delete provenance.entries[0][field];
      save(root, "provenance.json", provenance);
      assertFail(
        root,
        new RegExp(`missing required field "${field}"`, "u"),
        field,
      );
    } finally {
      cleanup(root);
    }
  });
}

test("adapted source requires a reason and a patched class", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root, {
      modified: true,
      adoptionClass: "KEEP_AS_IS",
      modificationReason: null,
    });
    assertFail(
      root,
      /requires non-empty modification_reason|patched adoption class/u,
      "adaptation metadata",
    );
  } finally {
    cleanup(root);
  }
});

test("unmodified source requires KEEP_AS_IS", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root, {
      modified: false,
      adoptionClass: "KEEP_WITH_MINIMAL_PATCH",
    });
    assertFail(root, /modified=false requires KEEP_AS_IS/u, "unmodified class");
  } finally {
    cleanup(root);
  }
});

test("every adopted scope path requires one final resolution", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root);
    const resolution = load(root, "source-resolution.json");
    resolution.entries.pop();
    save(root, "source-resolution.json", resolution);
    assertFail(root, /has no final resolution/u, "resolution coverage");
  } finally {
    cleanup(root);
  }
});

test("every vendored file must be reachable from the workspace root", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    const orphanPath = scope.files.find(
      (entry) =>
        entry.classification === "REQUIRED_VENDOR" &&
        entry.upstream_path !== "src/root.tsx",
    ).upstream_path;
    const rootEntry = provenanceEntry({
      upstreamPath: "src/root.tsx",
      localPath: writeSource(
        root,
        "src/root.tsx",
        "export const root = true;\n",
      ),
    });
    const orphanEntry = provenanceEntry({
      upstreamPath: orphanPath,
      localPath: writeSource(root, orphanPath, "export const orphan = true;\n"),
    });
    const entries = [rootEntry, orphanEntry];
    saveProvenance(root, entries);
    saveResolution(root, entries);
    assertFail(
      root,
      /outside the src\/root\.tsx dependency closure/u,
      "import closure",
    );
  } finally {
    cleanup(root);
  }
});

test("reachable source cannot retain an unresolved local import", () => {
  const root = freshRepo();
  try {
    createSingleFileFixture(root, {
      content: 'import "#/stores/missing";\nexport const root = true;\n',
    });
    assertFail(root, /unresolved local imports/u, "unresolved local import");
  } finally {
    cleanup(root);
  }
});
