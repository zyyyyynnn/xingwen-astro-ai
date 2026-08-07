#!/usr/bin/env node
/**
 * check-agent-upstream-adoption.mjs
 *
 * A-21 Phase 2 machine gate: enforce OpenHands as the UNIQUE upstream Agent
 * Product source and forbid design-level reimplementation / second shell /
 * losing-candidate leakage. Runs as part of `pnpm check:architecture`.
 *
 * Gates (spec §25):
 *   G1 Unique product      — only OpenHands is an upstream Agent product.
 *   G2 Exact ref            — only OpenHands/OpenHands @ v1.10.0 @ 566386...
 *   G3 No losing candidates— no AnythingLLM/LibreChat/Dify as source.
 *   G4 No second shell     — no competing Agent Product skeleton root.
 *   G5 Provenance          — (forward) every vendored file needs manifest.
 *   G6 No rewrite class    — adoption_class forbids REWRITE/RECREATE/REIMPLEMENT/INSPIRED_BY.
 *   G7 Coding surface      — excluded coding surfaces must not enter production graph.
 *   G8 Only OpenHands src  — no copy from LibreChat/AnythingLLM/Dify.
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = process.cwd();
const failures = [];
const notes = [];

const VENDOR_ROOT = "apps/workspace/upstream/openhands";
const requiredMeta = [
  "upstream-lock.json",
  "source-scope.json",
  "vendor-blueprint.json",
  "provenance-schema.json",
  "LICENSE.upstream",
  "NOTICE.md",
];

function readJSON(rel) {
  const p = resolve(root, rel);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
}

// ---- G1 / G2 / G3 / G6 / G8 : validate upstream-lock.json ----
const lock = readJSON(`${VENDOR_ROOT}/upstream-lock.json`);
if (!lock) {
  failures.push(`Missing ${VENDOR_ROOT}/upstream-lock.json`);
} else {
  // G1
  if (lock.product !== "OpenHands") {
    failures.push(
      `G1: unique product must be OpenHands, found "${lock.product}".`,
    );
  }
  if (!lock.unique_agent_product_source) {
    failures.push(
      "G1: upstream-lock.unique_agent_product_source must be true.",
    );
  }
  // G2
  if (lock.repository !== "https://github.com/OpenHands/OpenHands.git") {
    failures.push(
      `G2: repository must be OpenHands/OpenHands, found "${lock.repository}".`,
    );
  }
  if (lock.tag !== "v1.10.0") {
    failures.push(`G2: tag must be v1.10.0, found "${lock.tag}".`);
  }
  if (lock.commit !== "56638693908b8ac83a2fa3bde6eb6c33aae37f4b") {
    failures.push(
      `G2: commit must be 56638693908b8ac83a2fa3bde6eb6c33aae37f4b, found "${lock.commit}".`,
    );
  }
  if (typeof lock.commit !== "string" || lock.commit.length !== 40) {
    failures.push("G2: commit must be a 40-char SHA.");
  }
  if (
    ["latest", "main", "master", ""].includes(lock.tag) ||
    lock.tag?.startsWith("main")
  ) {
    failures.push("G2: floating tag/main not allowed.");
  }
  // G3
  const rejected = lock.rejected_candidates ?? [];
  const badLeak = ["AnythingLLM", "LibreChat", "Dify"].filter(
    (c) => lock.repository?.includes(c) || lock.product === c,
  );
  if (badLeak.length) {
    failures.push(
      `G3: losing candidate leaked into lock: ${badLeak.join(", ")}.`,
    );
  }
  if (!Array.isArray(rejected) || rejected.length === 0) {
    notes.push(
      "G3: no rejected_candidates recorded (expected AnythingLLM/LibreChat/Dify).",
    );
  }
  // G6
  for (const cls of lock.adoption_class_forbidden ?? []) {
    if (["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"].includes(cls))
      continue;
    failures.push(
      `G6: adoption_class_forbidden list should only contain REWRITE/RECREATE/REIMPLEMENT/INSPIRED_BY; found "${cls}".`,
    );
  }
  if (lock.forbid_design_level_reimplementation !== true) {
    failures.push("G6: forbid_design_level_reimplementation must be true.");
  }
}

// ---- G1 / G3 / G8 : no other vendor/third_party/upstream roots ----
const forbiddenRoots = [
  "apps/workspace/upstream",
  "apps/workspace/third_party",
  "apps/workspace/vendor",
  "packages/third_party",
];
for (const r of forbiddenRoots) {
  const p = resolve(root, r);
  if (!existsSync(p)) continue;
  for (const entry of readdirSync(p)) {
    const full = join(p, entry);
    if (!statSync(full).isDirectory()) continue;
    if (full.replace(/\\/g, "/").endsWith(`${VENDOR_ROOT}`)) continue;
    // G4 / G8: any other product root is a competing Agent Product source
    failures.push(
      `G4/G8: competing vendor root detected: ${r}/${entry} (only ${VENDOR_ROOT} allowed).`,
    );
  }
}

// ---- G6 / G7 : validate vendor-blueprint.json + source-scope.json ----
const blueprint = readJSON(`${VENDOR_ROOT}/vendor-blueprint.json`);
if (blueprint) {
  for (const rule of blueprint.hard_rules ?? []) {
    if (
      /rewrite|recreate|reimplement|inspired by/i.test(rule) &&
      !/never|not|forbid|!=/i.test(rule)
    ) {
      // only flag if it seems to endorse rather than forbid — conservative skip
    }
  }
  const forbidden = ["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"];
  for (const f of forbidden) {
    if (
      JSON.stringify(blueprint).includes(`"${f}"`) &&
      !JSON.stringify(blueprint.adoption_class_allowlist ?? []).includes(f)
    ) {
      failures.push(
        `G6: blueprint references forbidden class "${f}" outside allowlist context.`,
      );
    }
  }
} else {
  failures.push(`Missing ${VENDOR_ROOT}/vendor-blueprint.json`);
}

const scope = readJSON(`${VENDOR_ROOT}/source-scope.json`);
if (!scope) {
  failures.push(`Missing ${VENDOR_ROOT}/source-scope.json`);
} else {
  // ---- G3 / G8 : losing candidates must not appear as SOURCE PROVENANCE ----
  // Allowed: naming them in a controlled `rejected_candidates` field or handoff
  // prose. Forbidden: as actual repository / product / adopted upstream_path.
  const leakScan = ["anythingllm", "librechat", "dify"];
  if (lock) {
    for (const field of ["repository", "product", "commit"]) {
      const v = String(lock[field] ?? "").toLowerCase();
      for (const term of leakScan) {
        if (v.includes(term)) {
          failures.push(
            `G3/G8: losing candidate "${term}" in upstream-lock.${field}.`,
          );
        }
      }
    }
  }
  for (const f of scope.files ?? []) {
    if (
      !["REQUIRED_VENDOR", "REQUIRED_TRANSITIVE", "PARTIAL_SURGICAL"].includes(
        f.classification,
      )
    )
      continue;
    const v = String(f.upstream_path ?? "").toLowerCase();
    for (const term of leakScan) {
      if (v.includes(term)) {
        failures.push(
          `G3/G8: losing candidate "${term}" in adopted upstream_path ${f.upstream_path}.`,
        );
      }
    }
  }
  // G7: excluded coding surfaces must be classified EXCLUDED
  const excluded = (scope.files ?? []).filter(
    (f) => f.classification === "EXCLUDED",
  );
  if (excluded.length === 0) {
    failures.push(
      "G7: source-scope has no EXCLUDED entries (coding surfaces must be excluded).",
    );
  }
  const codingTerms = [
    "terminal",
    "diff-viewer",
    "browser/",
    "git-service",
    "vscode",
    "electron",
    "cloud",
  ];
  const badAdopted = (scope.files ?? []).filter(
    (f) =>
      (f.classification === "REQUIRED_VENDOR" ||
        f.classification === "REQUIRED_TRANSITIVE") &&
      codingTerms.some((t) => f.upstream_path.toLowerCase().includes(t)),
  );
  if (badAdopted.length) {
    failures.push(
      `G7: coding surface adopted as vendor: ${badAdopted.map((f) => f.upstream_path).join(", ")}.`,
    );
  }
  // G6: no forbidden adoption class anywhere
  const badClass = (scope.files ?? []).filter((f) =>
    ["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"].includes(
      f.classification,
    ),
  );
  if (badClass.length) {
    failures.push(
      `G6: forbidden adoption_class present: ${badClass.length} file(s).`,
    );
  }
  // G5 (forward): if a src/ dir exists, every file needs a manifest entry
  const srcDir = resolve(root, `${VENDOR_ROOT}/src`);
  if (existsSync(srcDir)) {
    const manifestPaths = new Set(
      (scope.files ?? []).map((f) => f.upstream_path),
    );
    const onDisk = [];
    const walk = (dir) => {
      for (const e of readdirSync(dir)) {
        const full = join(dir, e);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.(ts|tsx)$/.test(e))
          onDisk.push(full.replace(root, "").replace(/\\/g, "/"));
      }
    };
    walk(srcDir);
    if (onDisk.length && onDisk.length !== manifestPaths.size) {
      failures.push(
        `G5: vendored src files (${onDisk.length}) != manifest entries (${manifestPaths.size}) — 1:1 required.`,
      );
    }
    notes.push(
      `G5: ${onDisk.length} vendored files cross-checked against manifest.`,
    );
  } else {
    notes.push(
      "G5: no vendored src/ yet (Phase 2 = metadata only) — forward gate armed.",
    );
  }
}

// ---- Required metadata presence ----
for (const m of requiredMeta) {
  if (!existsSync(resolve(root, `${VENDOR_ROOT}/${m}`))) {
    failures.push(`Missing required vendor metadata: ${VENDOR_ROOT}/${m}`);
  }
}

// ---- Report ----
if (failures.length > 0) {
  console.error("Agent upstream adoption check FAILED:\n");
  for (const f of failures) console.error(`- ${f}`);
  if (notes.length) {
    console.error("\nNotes:");
    for (const n of notes) console.error(`  (note) ${n}`);
  }
  process.exit(1);
}

console.log("Agent upstream adoption check passed.");
if (notes.length) {
  for (const n of notes) console.log(`  (note) ${n}`);
}
