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

import { checkAgentUpstreamPolicy } from "./check-agent-upstream-policy.mjs";

const REPO_ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const UPSTREAM = "apps/workspace/upstream/openhands";
const UPSTREAM_ABS = join(REPO_ROOT, UPSTREAM);
const METADATA_FILES = [
  "upstream-lock.json",
  "source-scope.json",
  "source-policy.json",
  "provenance.json",
];
const MESSAGE_FILES = [
  "src/components/conversation-events/chat/event-message.tsx",
  "src/components/conversation-events/chat/group-events.ts",
  "src/components/conversation-events/chat/messages.tsx",
  "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx",
];
const DISCLOSURE_PATH = MESSAGE_FILES.at(-1);
const MECHANICS = "apps/workspace/src/mechanics";

function mechanicsPath(upstreamPath) {
  return `${MECHANICS}/${upstreamPath.slice("src/".length)}`;
}

function freshRepo() {
  const root = mkdtempSync(join(tmpdir(), "agent-upstream-policy-"));
  const target = join(root, UPSTREAM);
  mkdirSync(target, { recursive: true });
  for (const file of METADATA_FILES) {
    cpSync(join(UPSTREAM_ABS, file), join(target, file));
  }
  for (const file of MESSAGE_FILES) {
    const rel = mechanicsPath(file);
    const destination = join(root, rel);
    mkdirSync(dirname(destination), { recursive: true });
    cpSync(join(REPO_ROOT, rel), destination);
  }
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
    "utf8",
  );
}

function assertPass(root, message) {
  const { failures } = checkAgentUpstreamPolicy(root);
  assert.deepEqual(failures, [], `${message}\n${failures.join("\n")}`);
}

function assertFail(root, pattern, message) {
  const { failures } = checkAgentUpstreamPolicy(root);
  assert.ok(failures.length > 0, `${message}: expected failure`);
  assert.ok(
    failures.some((failure) => pattern.test(failure)),
    `${message}: expected ${pattern}, got\n${failures.join("\n")}`,
  );
}

test("current public Agent analysis policy passes", () => {
  assertPass(REPO_ROOT, "current repository");
});

test("missing source-policy fails", () => {
  const root = freshRepo();
  try {
    rmSync(join(root, UPSTREAM, "source-policy.json"));
    assertFail(root, /Missing source-policy\.json/u, "missing policy");
  } finally {
    cleanup(root);
  }
});

test("frozen OpenHands identity drift fails", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    policy.commit = "0".repeat(40);
    save(root, "source-policy.json", policy);
    assertFail(root, /source-policy\.commit/u, "identity drift");
  } finally {
    cleanup(root);
  }
});

test("public step analysis constraint drift fails", () => {
  const root = freshRepo();
  try {
    const policy = load(root, "source-policy.json");
    policy.public_step_analysis.constraints.pop();
    save(root, "source-policy.json", policy);
    assertFail(root, /public step analysis constraints/u, "constraint drift");
  } finally {
    cleanup(root);
  }
});

test("public step analysis disclosure inventory drift fails", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    scope.policy_sets.public_step_analysis_disclosure = [];
    save(root, "source-scope.json", scope);
    assertFail(
      root,
      /public step analysis disclosure set/u,
      "disclosure drift",
    );
  } finally {
    cleanup(root);
  }
});

test("foreign OpenHands runtime path cannot enter provenance", () => {
  const root = freshRepo();
  try {
    const scope = load(root, "source-scope.json");
    const provenance = load(root, "provenance.json");
    provenance.entries.push({
      upstream_path: scope.policy_sets.foreign_runtime_excluded[0],
      local_path: `${UPSTREAM}/${scope.policy_sets.foreign_runtime_excluded[0]}`,
      adoption_class: "KEEP_AS_IS",
      modified: false,
      modification_reason: null,
    });
    save(root, "provenance.json", provenance);
    assertFail(
      root,
      /foreign OpenHands runtime path must not be adopted/u,
      "foreign runtime",
    );
  } finally {
    cleanup(root);
  }
});

test("CollapsibleThinking must preserve the public analysis preview", () => {
  const root = freshRepo();
  try {
    const file = join(root, mechanicsPath(DISCLOSURE_PATH));
    const source = readFileSync(file, "utf8").replace("{content}", "{label}");
    writeFileSync(file, source, "utf8");
    assertFail(
      root,
      /public analysis composition is missing \{content\}/u,
      "public analysis preview",
    );
  } finally {
    cleanup(root);
  }
});
