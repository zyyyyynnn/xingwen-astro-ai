#!/usr/bin/env node
/**
 * Semantic policy gate for the frozen OpenHands source baseline.
 *
 * Complements check-agent-upstream-adoption.mjs:
 * - source-scope.json records reachability and source classification;
 * - source-policy.json records semantic/privacy constraints;
 * - provenance.json records files actually vendored.
 *
 * This gate prevents model-private reasoning semantics from crossing the
 * Xingwen product boundary while preserving approved OpenHands mechanics.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const SRC_DIR = `${UPSTREAM_ROOT}/src`;
const POLICY_FILE = "source-policy.json";
const EXACT_REPOSITORY = "https://github.com/OpenHands/OpenHands.git";
const EXACT_TAG = "v1.10.0";
const EXACT_COMMIT = "56638693908b8ac83a2fa3bde6eb6c33aae37f4b";
const EXACT_LICENSE = "MIT";
const SAFE_VENDORED_CLASSES = [
  "KEEP_AS_IS",
  "KEEP_WITH_MINIMAL_PATCH",
  "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
];
const PATCHED_CLASSES = [
  "KEEP_WITH_MINIMAL_PATCH",
  "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
];
const FORBIDDEN_CLASSES = ["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"];
const REQUIRED_PROVENANCE_FIELDS = [
  "upstream_path",
  "local_path",
  "adoption_class",
  "modified",
];

const EXPECTED_PRIVATE_EXCLUDED = [
  "src/components/conversation-events/chat/event-content-helpers/get-action-content.ts",
  "src/components/conversation-events/chat/event-content-helpers/get-action-event-title.ts",
  "src/components/conversation-events/chat/event-content-helpers/get-event-content.tsx",
  "src/components/conversation-events/chat/event-content-helpers/get-observation-content.ts",
  "src/components/conversation-events/chat/event-content-helpers/should-render-event.ts",
  "src/components/conversation-events/chat/event-thought-helpers.ts",
  "src/components/conversation-events/chat/event-message-components/index.ts",
  "src/components/conversation-events/chat/event-message-components/observation-pair-event-message.tsx",
  "src/components/conversation-events/chat/event-message-components/thought-event-message.tsx",
  "src/components/conversation-events/chat/event-message-components/user-assistant-event-message.tsx",
  "src/components/features/chat/typing-indicator.tsx",
  "src/hooks/chat/record-model-switch-message.ts",
  "src/types/agent-server/core/base/action.ts",
  "src/types/agent-server/core/base/event.ts",
  "src/types/agent-server/core/base/observation.ts",
  "src/types/agent-server/core/events/action-event.ts",
  "src/types/agent-server/core/events/streaming-delta-event.ts",
  "src/utils/handle-event-for-ui.ts",
  "src/utils/transcript-export/index.ts",
];

const EXPECTED_DISCLOSURE = [
  "src/components/conversation-events/chat/event-message-components/collapsible-thinking.tsx",
];

const EXPECTED_DISCLOSURE_CONSTRAINTS = [
  "preserve-disclosure-mechanics",
  "forbid-private-reasoning-input",
  "public-auditable-reasoning-only",
];

const FORBIDDEN_SOURCE_TOKENS = [
  "reasoning_content",
  "thinking_blocks",
  "ThinkAction",
  "ThinkObservation",
  "<think>",
  "event.thought",
  "action.thought",
];

const FORBIDDEN_IMPORT_FRAGMENTS = [
  "event-thought-helpers",
  "thought-event-message",
];

function readJson(root, rel) {
  const path = resolve(root, rel);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf8"));
}

function sameStringSet(actual, expected) {
  if (!Array.isArray(actual)) return false;
  const a = [...new Set(actual)].sort();
  const e = [...new Set(expected)].sort();
  return a.length === e.length && a.every((v, i) => v === e[i]);
}

function overlaps(a, b) {
  const bs = new Set(b);
  return a.filter((v) => bs.has(v));
}

function toPosix(path) {
  return path.split(sep).join("/");
}

function walkFiles(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir)) {
    const path = resolve(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) out.push(...walkFiles(path));
    else if (stat.isFile()) out.push(path);
  }
  return out;
}

function readTextIfTextLike(path) {
  const bytes = readFileSync(path);
  if (bytes.includes(0)) return null;
  return bytes.toString("utf8");
}

function validateExactIdentity(value, failures, label) {
  const checks = [
    ["product", "OpenHands"],
    ["repository", EXACT_REPOSITORY],
    ["tag", EXACT_TAG],
    ["commit", EXACT_COMMIT],
    ["license", EXACT_LICENSE],
  ];
  for (const [key, expected] of checks) {
    if (value?.[key] !== expected) {
      failures.push(
        `${label}.${key} must be ${JSON.stringify(expected)}, found ${JSON.stringify(value?.[key])}.`,
      );
    }
  }
}

function validateSourceScope(scope, failures) {
  const files = scope?.files;
  if (!Array.isArray(files)) {
    failures.push("source-scope.files must be an array.");
    return new Map();
  }

  const byPath = new Map();
  for (const entry of files) {
    if (typeof entry?.upstream_path !== "string" || !entry.upstream_path) {
      failures.push("source-scope entry missing upstream_path.");
      continue;
    }
    if (byPath.has(entry.upstream_path)) {
      failures.push(
        `source-scope duplicate upstream_path: ${entry.upstream_path}.`,
      );
    }
    byPath.set(entry.upstream_path, entry);
  }
  return byPath;
}

function validatePolicy(policy, scope, scopeByPath, failures) {
  validateExactIdentity(policy, failures, "source-policy");

  if (
    policy?.precedence !==
    "source-policy constraints override any KEEP_AS_IS interpretation from source reachability."
  ) {
    failures.push("source-policy precedence statement is missing or drifted.");
  }

  const privateReasoning = policy?.private_reasoning ?? {};
  if (!sameStringSet(privateReasoning.excluded, EXPECTED_PRIVATE_EXCLUDED)) {
    failures.push(
      "source-policy private_reasoning.excluded does not match the frozen private-reasoning inventory.",
    );
  }
  if (
    !sameStringSet(privateReasoning.disclosure_mechanics, EXPECTED_DISCLOSURE)
  ) {
    failures.push(
      "source-policy private_reasoning.disclosure_mechanics does not match the approved disclosure inventory.",
    );
  }
  if (
    !sameStringSet(
      privateReasoning.disclosure_adoption_classes,
      PATCHED_CLASSES,
    )
  ) {
    failures.push(
      "source-policy disclosure adoption classes must be the patched classes only.",
    );
  }
  if (
    !sameStringSet(
      privateReasoning.disclosure_constraints,
      EXPECTED_DISCLOSURE_CONSTRAINTS,
    )
  ) {
    failures.push("source-policy disclosure constraints drifted.");
  }
  if (
    !sameStringSet(
      privateReasoning.forbidden_source_tokens,
      FORBIDDEN_SOURCE_TOKENS,
    )
  ) {
    failures.push("source-policy forbidden source tokens drifted.");
  }
  if (
    !sameStringSet(
      privateReasoning.forbidden_import_fragments,
      FORBIDDEN_IMPORT_FRAGMENTS,
    )
  ) {
    failures.push("source-policy forbidden import fragments drifted.");
  }

  const overlapPairs = [
    [
      "excluded",
      privateReasoning.excluded ?? [],
      "disclosure_mechanics",
      privateReasoning.disclosure_mechanics ?? [],
    ],
  ];
  for (const [aName, a, bName, b] of overlapPairs) {
    const dupes = overlaps(a, b);
    if (dupes.length) {
      failures.push(
        `source-policy groups ${aName}/${bName} overlap: ${dupes.join(", ")}.`,
      );
    }
  }

  // source-policy owns the complete private inventory; source-scope may omit
  // those paths from its compact boundary list.
  for (const path of privateReasoning.excluded ?? []) {
    const entry = scopeByPath.get(path);
    if (entry && entry.classification !== "EXCLUDED") {
      failures.push(
        `private reasoning excluded path must be EXCLUDED in source-scope: ${path}.`,
      );
    }
  }

  for (const path of privateReasoning.disclosure_mechanics ?? []) {
    const entry = scopeByPath.get(path);
    if (!entry || entry.classification !== "PARTIAL_SURGICAL") {
      failures.push(
        `reasoning disclosure path must be PARTIAL_SURGICAL: ${path}.`,
      );
      continue;
    }
    const constraints = entry.constraints ?? [];
    for (const required of EXPECTED_DISCLOSURE_CONSTRAINTS) {
      if (!constraints.includes(required)) {
        failures.push(
          `reasoning disclosure path missing ${required}: ${path}.`,
        );
      }
    }
  }

  const embedded = scope?.policy_sets ?? {};
  if (
    !sameStringSet(
      embedded.private_reasoning_excluded,
      privateReasoning.excluded ?? [],
    )
  ) {
    failures.push(
      "source-scope private_reasoning_excluded policy set must match source-policy.",
    );
  }
  if (
    !sameStringSet(
      embedded.public_reasoning_disclosure,
      privateReasoning.disclosure_mechanics ?? [],
    )
  ) {
    failures.push(
      "source-scope public_reasoning_disclosure policy set must match source-policy.",
    );
  }
}

function validateLockAndSchema(lock, provenanceSchema, failures) {
  validateExactIdentity(lock, failures, "upstream-lock");

  if (lock?.source_policy_file !== POLICY_FILE) {
    failures.push(`upstream-lock.source_policy_file must be ${POLICY_FILE}.`);
  }
  if (
    !Array.isArray(lock?.manifest_files) ||
    !lock.manifest_files.includes(POLICY_FILE)
  ) {
    failures.push(`upstream-lock.manifest_files must include ${POLICY_FILE}.`);
  }

  const sourceVerification = lock?.source_verification ?? {};
  const sourceVerificationChecks = [
    ["repository", EXACT_REPOSITORY],
    ["tag", EXACT_TAG],
    ["commit", EXACT_COMMIT],
    ["on_mismatch", "reject"],
  ];
  for (const [key, expected] of sourceVerificationChecks) {
    if (sourceVerification[key] !== expected) {
      failures.push(
        `upstream-lock.source_verification.${key} must be ${JSON.stringify(expected)}.`,
      );
    }
  }

  if (
    !sameStringSet(lock?.vendored_file_adoption_classes, SAFE_VENDORED_CLASSES)
  ) {
    failures.push(
      "upstream-lock vendored_file_adoption_classes must match the safe vendored classes exactly.",
    );
  }
  if (!sameStringSet(lock?.adoption_class_forbidden, FORBIDDEN_CLASSES)) {
    failures.push(
      "upstream-lock adoption_class_forbidden must match the forbidden classes exactly.",
    );
  }

  if (provenanceSchema?.policy_file !== POLICY_FILE) {
    failures.push(`provenance-schema.policy_file must be ${POLICY_FILE}.`);
  }
  if (
    !sameStringSet(
      provenanceSchema?.required_fields,
      REQUIRED_PROVENANCE_FIELDS,
    )
  ) {
    failures.push(
      "provenance-schema required_fields must match the fail-closed provenance contract.",
    );
  }
  if (
    !sameStringSet(
      provenanceSchema?.vendored_file_adoption_classes,
      SAFE_VENDORED_CLASSES,
    )
  ) {
    failures.push("provenance-schema vendored_file_adoption_classes drifted.");
  }
  if (
    !sameStringSet(
      provenanceSchema?.forbidden_adoption_classes,
      FORBIDDEN_CLASSES,
    )
  ) {
    failures.push("provenance-schema forbidden adoption classes drifted.");
  }
}

function validateVendoredSource(
  root,
  lock,
  policy,
  scopeByPath,
  failures,
  notes,
) {
  const srcDir = resolve(root, SRC_DIR);
  if (!existsSync(srcDir)) {
    notes.push("semantic source policy armed; no vendored source present");
    return;
  }

  const provenance = readJson(root, `${UPSTREAM_ROOT}/provenance.json`);
  if (!provenance) {
    failures.push(
      "semantic source policy requires provenance.json when vendored src/ exists.",
    );
    return;
  }
  const entries = provenance.entries;
  if (!Array.isArray(entries)) {
    failures.push("provenance.json must use the v2 manifest object contract.");
    return;
  }

  const byUpstreamPath = new Map();
  for (const entry of entries) {
    if (typeof entry?.upstream_path === "string") {
      if (byUpstreamPath.has(entry.upstream_path)) {
        failures.push(
          `semantic policy found duplicate provenance upstream_path: ${entry.upstream_path}.`,
        );
      }
      byUpstreamPath.set(entry.upstream_path, entry);
    }
  }

  const privateReasoning = policy.private_reasoning;
  for (const path of privateReasoning.excluded) {
    if (byUpstreamPath.has(path)) {
      failures.push(
        `private model reasoning path must never be vendored: ${path}.`,
      );
    }
  }

  const disclosurePaths = new Set(privateReasoning.disclosure_mechanics);
  for (const path of disclosurePaths) {
    const entry = byUpstreamPath.get(path);
    if (!entry) continue;
    if (entry.modified !== true) {
      failures.push(
        `private-reasoning/disclosure surgery path must be modified=true when vendored: ${path}.`,
      );
    }
    if (!PATCHED_CLASSES.includes(entry.adoption_class)) {
      failures.push(
        `private-reasoning/disclosure surgery path requires a patched adoption class: ${path}.`,
      );
    }
    if (
      typeof entry.modification_reason !== "string" ||
      !entry.modification_reason.trim()
    ) {
      failures.push(
        `private-reasoning/disclosure surgery path requires a modification reason: ${path}.`,
      );
    }
  }

  for (const file of walkFiles(srcDir)) {
    const content = readTextIfTextLike(file);
    if (content === null) continue;
    const rel = toPosix(relative(root, file));
    for (const token of privateReasoning.forbidden_source_tokens) {
      if (content.includes(token)) {
        failures.push(
          `vendored source retains forbidden private-reasoning token ${JSON.stringify(token)}: ${rel}.`,
        );
      }
    }
    for (const fragment of privateReasoning.forbidden_import_fragments) {
      if (content.includes(fragment)) {
        failures.push(
          `vendored source retains forbidden private-reasoning import/reference ${JSON.stringify(fragment)}: ${rel}.`,
        );
      }
    }
  }

  for (const entry of entries) {
    if (entry?.upstream_repository !== lock.repository) continue;
    const scopeEntry = scopeByPath.get(entry.upstream_path);
    if (!scopeEntry) continue;
    if (
      disclosurePaths.has(entry.upstream_path) &&
      entry.adoption_class === "KEEP_AS_IS"
    ) {
      failures.push(
        `source policy forbids KEEP_AS_IS for required semantic surgery: ${entry.upstream_path}.`,
      );
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
  const provenanceSchema = readJson(
    root,
    `${UPSTREAM_ROOT}/provenance-schema.json`,
  );

  if (!lock) failures.push("Missing upstream-lock.json.");
  if (!scope) failures.push("Missing source-scope.json.");
  if (!policy) failures.push(`Missing ${POLICY_FILE}.`);
  if (!provenanceSchema) failures.push("Missing provenance-schema.json.");
  if (failures.length) return { failures, notes };

  validateExactIdentity(scope, failures, "source-scope");
  const scopeByPath = validateSourceScope(scope, failures);
  validateLockAndSchema(lock, provenanceSchema, failures);
  validatePolicy(policy, scope, scopeByPath, failures);
  validateVendoredSource(root, lock, policy, scopeByPath, failures, notes);

  return { failures, notes };
}

function runCli() {
  const { failures, notes } = checkAgentUpstreamPolicy(process.cwd());
  if (failures.length) {
    console.error("Agent upstream semantic policy check FAILED:\n");
    for (const failure of failures) console.error(`- ${failure}`);
    if (notes.length) {
      console.error("\nNotes:");
      for (const note of notes) console.error(`  (note) ${note}`);
    }
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
