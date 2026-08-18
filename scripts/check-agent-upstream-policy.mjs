#!/usr/bin/env node
/** Policy gate for the frozen OpenHands mechanics and local Agent event seam. */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const POLICY_FILE = "source-policy.json";
const EXACT_IDENTITY = Object.freeze({
  product: "OpenHands",
  repository: "https://github.com/OpenHands/OpenHands.git",
  tag: "v1.10.0",
  commit: "56638693908b8ac83a2fa3bde6eb6c33aae37f4b",
  license: "MIT",
});
const DISCLOSURE_PATH =
  "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx";
const EXPECTED_REASONING_CONSTRAINTS = [
  "source content only from the server-validated public_analysis tool argument",
  "provider reasoning_content never crosses the runtime boundary",
  "collapsed by default and expanded only by user intent",
  "same project and session authorization as Research Thread",
  "exclude from share snapshots, export and formal Artifact renderers",
  "never synthesize reasoning in the browser",
  "never expose credentials, transport bodies or unfiltered internal errors",
];
const FORBIDDEN_FOREIGN_RUNTIME_REFERENCES = [
  "#/types/agent-server",
  "#/stores/conversation-store",
  "#/hooks/use-agent-state",
  "event-thought-helpers",
  "thought-event-message",
];

function readJson(root, relativePath) {
  const path = resolve(root, relativePath);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf8"));
}

function sameStringSet(actual, expected) {
  if (!Array.isArray(actual)) return false;
  const left = [...new Set(actual)].sort();
  const right = [...new Set(expected)].sort();
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  );
}

function validateIdentity(value, label, failures) {
  for (const [key, expected] of Object.entries(EXACT_IDENTITY)) {
    if (value?.[key] !== expected) {
      failures.push(
        `${label}.${key} must be ${JSON.stringify(expected)}, found ${JSON.stringify(value?.[key])}.`,
      );
    }
  }
}

function validatePolicy(policy, failures) {
  validateIdentity(policy, "source-policy", failures);
  const reasoning = policy?.public_step_analysis;
  if (
    reasoning?.policy !==
    "validate-persist-and-render-inside-authorized-project-thread"
  ) {
    failures.push("public step analysis policy is missing or drifted.");
  }
  if (!sameStringSet(reasoning?.constraints, EXPECTED_REASONING_CONSTRAINTS)) {
    failures.push("public step analysis constraints drifted.");
  }
  if (!reasoning?.adopted_mechanics?.includes(DISCLOSURE_PATH)) {
    failures.push(
      "CollapsibleThinking is not registered as adopted reasoning mechanics.",
    );
  }
  if (
    reasoning?.local_contract !==
    "RunEvent reasoning Activity with a stable activity_id and running/completed phases"
  ) {
    failures.push("public step analysis local contract drifted.");
  }
  if (
    policy?.agent_activity?.lifecycle !==
    "one logical operation evolves in place by activity_id; started/completed duplicates are forbidden"
  ) {
    failures.push(
      "Agent Activity lifecycle no longer requires stable in-place updates.",
    );
  }
}

function validateScope(scope, policy, failures) {
  validateIdentity(scope, "source-scope", failures);
  const files = Array.isArray(scope?.files) ? scope.files : [];
  const disclosure = files.find(
    (entry) => entry?.upstream_path === DISCLOSURE_PATH,
  );
  if (disclosure?.classification !== "PARTIAL_SURGICAL") {
    failures.push("CollapsibleThinking must remain PARTIAL_SURGICAL.");
  }
  const embedded = scope?.policy_sets ?? {};
  if (
    !sameStringSet(embedded.public_step_analysis_disclosure, [DISCLOSURE_PATH])
  ) {
    failures.push("source-scope public step analysis disclosure set drifted.");
  }
  const foreignExcluded = embedded.foreign_runtime_excluded;
  if (!Array.isArray(foreignExcluded) || foreignExcluded.length === 0) {
    failures.push(
      "source-scope foreign runtime exclusion inventory is missing.",
    );
  }
  const adopted = policy.public_step_analysis.adopted_mechanics;
  for (const path of adopted) {
    if (!files.some((entry) => entry?.upstream_path === path)) {
      failures.push(
        `adopted reasoning mechanic is absent from source-scope: ${path}.`,
      );
    }
  }
}

function validateProvenance(root, scope, failures) {
  const provenance = readJson(root, `${UPSTREAM_ROOT}/provenance.json`);
  if (!provenance || !Array.isArray(provenance.entries)) {
    failures.push("provenance.json is missing or malformed.");
    return;
  }
  const byPath = new Map(
    provenance.entries.map((entry) => [entry.upstream_path, entry]),
  );
  const disclosure = byPath.get(DISCLOSURE_PATH);
  if (!disclosure || disclosure.modified !== true) {
    failures.push(
      "CollapsibleThinking provenance must record a modified adoption.",
    );
  }
  for (const path of scope.policy_sets.foreign_runtime_excluded) {
    if (byPath.has(path)) {
      failures.push(
        `foreign OpenHands runtime path must not be vendored: ${path}.`,
      );
    }
  }
}

function validateLocalSeam(root, failures) {
  const files = [
    `${UPSTREAM_ROOT}/src/components/conversation-events/chat/event-message.tsx`,
    `${UPSTREAM_ROOT}/src/components/conversation-events/chat/group-events.ts`,
    `${UPSTREAM_ROOT}/src/components/conversation-events/chat/messages.tsx`,
    `${UPSTREAM_ROOT}/${DISCLOSURE_PATH}`,
  ];
  for (const relativePath of files) {
    const path = resolve(root, relativePath);
    if (!existsSync(path)) {
      failures.push(
        `adopted Agent message mechanic is missing: ${relativePath}.`,
      );
      continue;
    }
    const content = readFileSync(path, "utf8");
    for (const fragment of FORBIDDEN_FOREIGN_RUNTIME_REFERENCES) {
      if (content.includes(fragment)) {
        failures.push(
          `local Agent message seam imports foreign runtime ${JSON.stringify(fragment)}: ${relativePath}.`,
        );
      }
    }
  }
  const thinkingPath = resolve(root, UPSTREAM_ROOT, DISCLOSURE_PATH);
  if (existsSync(thinkingPath)) {
    const content = readFileSync(thinkingPath, "utf8");
    for (const required of [
      "CollapsibleThinking",
      "CollapsibleContent",
      "{content}",
    ]) {
      if (!content.includes(required)) {
        failures.push(
          `CollapsibleThinking public analysis composition is missing ${required}.`,
        );
      }
    }
  }
}

/** @returns {{ failures: string[], notes: string[] }} */
export function checkAgentUpstreamPolicy(root) {
  const failures = [];
  const notes = [];
  const lock = readJson(root, `${UPSTREAM_ROOT}/upstream-lock.json`);
  const scope = readJson(root, `${UPSTREAM_ROOT}/source-scope.json`);
  const policy = readJson(root, `${UPSTREAM_ROOT}/${POLICY_FILE}`);
  if (!lock) failures.push("Missing upstream-lock.json.");
  if (!scope) failures.push("Missing source-scope.json.");
  if (!policy) failures.push(`Missing ${POLICY_FILE}.`);
  if (failures.length) return { failures, notes };
  validateIdentity(lock, "upstream-lock", failures);
  validatePolicy(policy, failures);
  validateScope(scope, policy, failures);
  validateProvenance(root, scope, failures);
  validateLocalSeam(root, failures);
  return { failures, notes };
}

function runCli() {
  const { failures, notes } = checkAgentUpstreamPolicy(process.cwd());
  if (failures.length) {
    console.error("Agent upstream semantic policy check FAILED:\n");
    for (const failure of failures) console.error(`- ${failure}`);
    return 1;
  }
  console.log("Agent upstream semantic policy check passed.");
  for (const note of notes) console.log(`  (note) ${note}`);
  return 0;
}

if (
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))
) {
  process.exitCode = runCli();
}
