#!/usr/bin/env node

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  cpSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { checkAgentUpstreamPolicy } from "./check-agent-upstream-policy.mjs";

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const UPSTREAM = "apps/workspace/upstream/openhands";
const UPSTREAM_ABS = join(REPO_ROOT, UPSTREAM);

function freshRepo() {
  const root = mkdtempSync(join(tmpdir(), "agent-upstream-policy-"));
  const target = join(root, UPSTREAM);
  mkdirSync(target, { recursive: true });
  cpSync(UPSTREAM_ABS, target, { recursive: true });
  return root;
}

function cleanup(root) {
  rmSync(root, { recursive: true, force: true });
}

function load(root, file) {
  return JSON.parse(readFileSync(join(root, UPSTREAM, file), "utf8"));
}

function save(root, file, value) {
  writeFileSync(
    join(root, UPSTREAM, file),
    `${JSON.stringify(value, null, 2)}\n`,
  );
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function assertPass(root, message) {
  const { failures } = checkAgentUpstreamPolicy(root);
  assert.deepEqual(failures, [], `${message}\n${failures.join("\n")}`);
}

function assertFail(root, pattern, message) {
  const { failures } = checkAgentUpstreamPolicy(root);
  assert.ok(failures.length > 0, `${message}: expected failure`);
  if (pattern) {
    assert.ok(
      failures.some((failure) => pattern.test(failure)),
      `${message}: expected ${pattern}, got\n${failures.join("\n")}`,
    );
  }
}

function writeVendoredFile(root, upstreamPath, content) {
  const localPath = `${UPSTREAM}/${upstreamPath}`;
  const absolute = join(root, localPath);
  mkdirSync(dirname(absolute), { recursive: true });
  writeFileSync(absolute, content);
  return { localPath, hash: sha256(content) };
}

function setScopeHash(root, upstreamPath, hash) {
  const scope = load(root, "source-scope.json");
  const entry = scope.files.find((item) => item.upstream_path === upstreamPath);
  assert.ok(entry, `scope path missing: ${upstreamPath}`);
  entry.source_sha256 = hash;
  save(root, "source-scope.json", scope);
}

function provenanceEntry({
  upstreamPath,
  localPath,
  upstreamHash,
  vendoredHash,
  adoptionClass = "KEEP_WITH_MINIMAL_PATCH",
  modified = true,
  modificationReason = "remove private reasoning semantics",
}) {
  return {
    upstream_repository: "https://github.com/OpenHands/OpenHands.git",
    upstream_tag: "v1.10.0",
    upstream_commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
    upstream_path: upstreamPath,
    local_path: localPath,
    upstream_source_sha256: upstreamHash,
    vendored_sha256: vendoredHash,
    adoption_class: adoptionClass,
    modified,
    modification_reason: modificationReason,
    license: "MIT",
  };
}

test("metadata-only semantic policy passes", () => {
  const root = freshRepo();
  try {
    assertPass(root, "metadata-only policy should pass");
  } finally {
    cleanup(root);
  }
});

test("missing source-policy fails", () => {
  const root = freshRepo();
  try {
    rmSync(join(root, UPSTREAM, "source-policy.json"));
    assertFail(root, /Missing source-policy\.json/, "missing policy");
  } finally {
    cleanup(root);
  }
});

test("source verification drift fails", () => {
  const root = freshRepo();
  try {
    const lock = load(root, "upstream-lock.json");
    lock.source_verification.commit = "0".repeat(40);
    save(root, "upstream-lock.json", lock);
    assertFail(root, /source_verification\.commit/, "verification drift");
  } finally {
    cleanup(root);
  }
});

test("unsafe vendored class contract drift fails", () => {
  const root = freshRepo();
  try {
    const lock = load(root, "upstream-lock.json");
    lock.vendored_file_adoption_classes.push("REMOVE_CODING_SURFACE");
    save(root, "upstream-lock.json", lock);
    assertFail(
      root,
      /vendored_file_adoption_classes/,
      "unsafe vendored class drift",
    );
  } finally {
    cleanup(root);
  }
});

test("missing source-scope hash fails", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    delete scope.files[0].source_sha256;
    save(root, "source-scope.json", scope);
    assertFail(root, /source_sha256/, "missing source hash");
  } finally {
    cleanup(root);
  }
});

test("private reasoning inventory shrink fails", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    policy.private_reasoning.mandatory_surgery.pop();
    save(root, "source-policy.json", policy);
    assertFail(
      root,
      /mandatory_surgery/,
      "private reasoning inventory shrink",
    );
  } finally {
    cleanup(root);
  }
});

test("embedded source-scope policy drift fails", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    scope.policy_sets.private_reasoning_excluded = [];
    save(root, "source-scope.json", scope);
    assertFail(
      root,
      /private_reasoning_excluded policy set/,
      "embedded policy drift",
    );
  } finally {
    cleanup(root);
  }
});

test("clean mandatory-surgery file passes when explicitly modified", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    const upstreamPath = policy.private_reasoning.mandatory_surgery[0];
    const upstreamHash = "a".repeat(64);
    const content = 'export const publicActivity = "safe";\n';
    const { localPath, hash } = writeVendoredFile(root, upstreamPath, content);
    setScopeHash(root, upstreamPath, upstreamHash);
    save(root, "provenance.json", [
      provenanceEntry({
        upstreamPath,
        localPath,
        upstreamHash,
        vendoredHash: hash,
      }),
    ]);
    assertPass(root, "clean mandatory surgery should pass");
  } finally {
    cleanup(root);
  }
});

test("mandatory-surgery file cannot use KEEP_AS_IS", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    const upstreamPath = policy.private_reasoning.mandatory_surgery[0];
    const upstreamHash = "a".repeat(64);
    const content = 'export const publicActivity = "safe";\n';
    const { localPath, hash } = writeVendoredFile(root, upstreamPath, content);
    setScopeHash(root, upstreamPath, upstreamHash);
    save(root, "provenance.json", [
      provenanceEntry({
        upstreamPath,
        localPath,
        upstreamHash,
        vendoredHash: hash,
        adoptionClass: "KEEP_AS_IS",
        modified: false,
        modificationReason: null,
      }),
    ]);
    assertFail(
      root,
      /must be modified=true|patched adoption class|KEEP_AS_IS/,
      "KEEP_AS_IS surgery",
    );
  } finally {
    cleanup(root);
  }
});

test("vendored raw reasoning token fails", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    const upstreamPath = policy.private_reasoning.mandatory_surgery[0];
    const upstreamHash = "a".repeat(64);
    const content = "export const leaked = event.reasoning_content;\n";
    const { localPath, hash } = writeVendoredFile(root, upstreamPath, content);
    setScopeHash(root, upstreamPath, upstreamHash);
    save(root, "provenance.json", [
      provenanceEntry({
        upstreamPath,
        localPath,
        upstreamHash,
        vendoredHash: hash,
      }),
    ]);
    assertFail(
      root,
      /forbidden private-reasoning token/,
      "raw reasoning token",
    );
  } finally {
    cleanup(root);
  }
});

test("excluded private reasoning source cannot appear in provenance", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    const upstreamPath = policy.private_reasoning.excluded[0];
    const upstreamHash = "a".repeat(64);
    const content = 'export const leaked = "private";\n';
    const { localPath, hash } = writeVendoredFile(root, upstreamPath, content);
    setScopeHash(root, upstreamPath, upstreamHash);
    save(root, "provenance.json", [
      provenanceEntry({
        upstreamPath,
        localPath,
        upstreamHash,
        vendoredHash: hash,
      }),
    ]);
    assertFail(
      root,
      /must never be vendored/,
      "excluded private reasoning provenance",
    );
  } finally {
    cleanup(root);
  }
});

test("private reasoning import fragment fails in any vendored source", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    const target = scope.files.find(
      (entry) => entry.classification === "REQUIRED_VENDOR",
    );
    const upstreamPath = target.upstream_path;
    const content =
      'import { helper } from "./event-thought-helpers";\nexport { helper };\n';
    const { localPath, hash } = writeVendoredFile(root, upstreamPath, content);
    setScopeHash(root, upstreamPath, hash);
    save(root, "provenance.json", [
      provenanceEntry({
        upstreamPath,
        localPath,
        upstreamHash: hash,
        vendoredHash: hash,
        adoptionClass: "KEEP_AS_IS",
        modified: false,
        modificationReason: null,
      }),
    ]);
    assertFail(
      root,
      /forbidden private-reasoning import\/reference/,
      "private reasoning import fragment",
    );
  } finally {
    cleanup(root);
  }
});
