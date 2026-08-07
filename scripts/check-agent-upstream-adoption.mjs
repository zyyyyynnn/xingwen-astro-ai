#!/usr/bin/env node
/**
 * check-agent-upstream-adoption.mjs
 *
 * Machine gate enforcing OpenHands as the UNIQUE upstream Agent Product source
 * and forbidding design-level reimplementation / second shell / alternate
 * upstream root. Runs as part of `pnpm check:architecture`.
 *
 * Gates:
 *   G1 Unique product      — only OpenHands is an upstream Agent product.
 *   G2 Exact ref            — only OpenHands/OpenHands @ v1.10.0 @ 566386...
 *   G3 No other source     — repository allowlist + unique upstream root.
 *   G4 No second shell     — no competing Agent Product skeleton root.
 *   G5 Provenance          — if src/ present, provenance.json 1:1 + hashes.
 *   G6 No rewrite class    — adoption_class forbids REWRITE/RECREATE/REIMPLEMENT/INSPIRED_BY.
 *   G7 Coding surface      — excluded coding surfaces must not enter production graph.
 *   G8 Only OpenHands src  — no file sourced from a non-OpenHands repository.
 *
 * The check is injectable: `checkAgentUpstreamAdoption(root)` where root is any
 * repo root. The CLI entrypoint passes process.cwd().
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { resolve, relative, sep } from "node:path";
import { createHash } from "node:crypto";

const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const SRC_DIR = `${UPSTREAM_ROOT}/src`;
const ALLOWED_REPOSITORIES = new Set([
  "https://github.com/OpenHands/OpenHands.git",
]);
const FORBIDDEN_CLASSES = ["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"];
const REQUIRED_META = [
  "upstream-lock.json",
  "source-scope.json",
  "vendor-blueprint.json",
  "provenance-schema.json",
  "LICENSE.upstream",
  "NOTICE.md",
];

function readJSON(root, rel) {
  const p = resolve(root, rel);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
}

function sha256OfFile(absPath) {
  const h = createHash("sha256");
  h.update(readFileSync(absPath));
  return h.digest("hex");
}

function walkFiles(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const full = resolve(dir, e);
    if (statSync(full).isDirectory()) out.push(...walkFiles(full));
    else if (statSync(full).isFile()) out.push(full);
  }
  return out;
}

function toPosix(p) {
  return p.split(sep).join("/");
}

/** @returns {{ failures: string[], notes: string[] }} */
export function checkAgentUpstreamAdoption(root) {
  const failures = [];
  const notes = [];

  // ---- G1 / G2 / G3 / G6 : validate upstream-lock.json ----
  const lock = readJSON(root, `${UPSTREAM_ROOT}/upstream-lock.json`);
  if (!lock) {
    failures.push(`Missing ${UPSTREAM_ROOT}/upstream-lock.json`);
    return { failures, notes };
  }
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
  // G3 — repository allowlist (no second upstream source)
  if (!ALLOWED_REPOSITORIES.has(lock.repository)) {
    failures.push(`G3: repository not on allowlist: "${lock.repository}".`);
  }
  // G6
  for (const cls of lock.adoption_class_forbidden ?? []) {
    if (!FORBIDDEN_CLASSES.includes(cls))
      failures.push(
        `G6: adoption_class_forbidden contains unexpected "${cls}".`,
      );
  }
  if (lock.forbid_design_level_reimplementation !== true) {
    failures.push("G6: forbid_design_level_reimplementation must be true.");
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
      const full = resolve(p, entry);
      if (!statSync(full).isDirectory()) continue;
      if (toPosix(full).endsWith(UPSTREAM_ROOT)) continue;
      failures.push(
        `G4/G8: competing vendor root detected: ${r}/${entry} (only ${UPSTREAM_ROOT} allowed).`,
      );
    }
  }

  // ---- G6 / G7 : validate blueprint + scope ----
  const blueprint = readJSON(root, `${UPSTREAM_ROOT}/vendor-blueprint.json`);
  if (!blueprint) {
    failures.push(`Missing ${UPSTREAM_ROOT}/vendor-blueprint.json`);
  }
  const scope = readJSON(root, `${UPSTREAM_ROOT}/source-scope.json`);
  if (!scope) {
    failures.push(`Missing ${UPSTREAM_ROOT}/source-scope.json`);
    return { failures, notes };
  }
  // G6: no forbidden class referenced outside allowlist context
  if (blueprint) {
    for (const f of FORBIDDEN_CLASSES) {
      if (
        JSON.stringify(blueprint).includes(`"${f}"`) &&
        !JSON.stringify(blueprint.adoption_class_allowlist ?? []).includes(f)
      ) {
        failures.push(
          `G6: blueprint references forbidden class "${f}" outside allowlist context.`,
        );
      }
    }
  }
  // G7: excluded coding surfaces classified EXCLUDED
  const files = scope.files ?? [];
  const excluded = files.filter((f) => f.classification === "EXCLUDED");
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
  const badAdopted = files.filter(
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
  // G6: no forbidden adoption class in scope
  const badClass = files.filter((f) =>
    FORBIDDEN_CLASSES.includes(f.classification),
  );
  if (badClass.length) {
    failures.push(
      `G6: forbidden adoption_class present: ${badClass.length} file(s).`,
    );
  }

  // ---- G5 : provenance (disk <-> manifest <-> scope, hash integrity) ----
  const srcDir = resolve(root, SRC_DIR);
  if (!existsSync(srcDir)) {
    notes.push(
      "source provenance enforcement armed; no vendored source present",
    );
  } else {
    const manifestPath = resolve(root, `${UPSTREAM_ROOT}/provenance.json`);
    if (!existsSync(manifestPath)) {
      failures.push(
        `G5: vendored src/ present but ${UPSTREAM_ROOT}/provenance.json missing.`,
      );
    } else {
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
      const entries = Array.isArray(manifest)
        ? manifest
        : (manifest.entries ?? []);
      const scopeByPath = new Map(files.map((f) => [f.upstream_path, f]));

      // Disk -> Provenance : every on-disk file has exactly one manifest entry
      const diskFiles = walkFiles(srcDir);
      const diskLocalPaths = new Set(
        diskFiles.map((f) => toPosix(relative(root, f))),
      );
      const provByLocal = new Map();
      for (const e of entries) {
        if (provByLocal.has(e.local_path)) {
          failures.push(
            `G5: duplicate local_path in provenance: ${e.local_path}.`,
          );
        }
        provByLocal.set(e.local_path, e);
      }
      for (const lp of diskLocalPaths) {
        if (!provByLocal.has(lp)) {
          failures.push(`G5: on-disk file has no provenance entry: ${lp}.`);
        }
      }
      // Provenance -> Disk : every manifest entry maps to a real file
      for (const e of entries) {
        if (!diskLocalPaths.has(e.local_path)) {
          failures.push(
            `G5: dangling provenance entry (file missing): ${e.local_path}.`,
          );
        }
      }
      // Provenance -> Source Scope : upstream_path exists exactly once, allowed class
      for (const e of entries) {
        const sc = scopeByPath.get(e.upstream_path);
        if (!sc) {
          failures.push(
            `G5: provenance upstream_path not in source-scope: ${e.upstream_path}.`,
          );
          continue;
        }
        if (
          ![
            "REQUIRED_VENDOR",
            "REQUIRED_TRANSITIVE",
            "PARTIAL_SURGICAL",
          ].includes(sc.classification)
        ) {
          failures.push(
            `G5: provenance upstream_path classified ${sc.classification} (must be REQUIRED_VENDOR/TRANSITIVE/PARTIAL_SURGICAL): ${e.upstream_path}.`,
          );
        }
        // G8 : repository must match lock
        if (
          e.upstream_repository &&
          e.upstream_repository !== lock.repository
        ) {
          failures.push(
            `G8: provenance sourced from non-OpenHands repo: ${e.upstream_repository}.`,
          );
        }
        // Hash integrity
        const diskFile = resolve(root, e.local_path);
        if (existsSync(diskFile)) {
          const fileHash = sha256OfFile(diskFile);
          if (e.vendored_sha256 && e.vendored_sha256 !== fileHash) {
            failures.push(`G5: vendored_sha256 mismatch for ${e.local_path}.`);
          }
          if (
            sc.source_sha256 &&
            e.upstream_source_sha256 &&
            e.upstream_source_sha256 !== sc.source_sha256
          ) {
            failures.push(
              `G5: upstream_source_sha256 mismatch vs source-scope for ${e.upstream_path}.`,
            );
          }
          if (e.modified === false) {
            if (
              e.vendored_sha256 &&
              e.upstream_source_sha256 &&
              e.vendored_sha256 !== e.upstream_source_sha256
            ) {
              failures.push(
                `G5: modified=false but vendored_sha256 != upstream_source_sha256 for ${e.local_path}.`,
              );
            }
          } else if (e.modified === true) {
            if (!e.modification_reason) {
              failures.push(
                `G5: modified=true requires non-empty modification_reason for ${e.local_path}.`,
              );
            }
            if (e.vendored_sha256 && e.vendored_sha256 !== fileHash) {
              failures.push(
                `G5: modified=true but vendored_sha256 != actual file hash for ${e.local_path}.`,
              );
            }
          }
        }
      }
    }
  }

  // ---- Required metadata presence ----
  for (const m of REQUIRED_META) {
    if (!existsSync(resolve(root, `${UPSTREAM_ROOT}/${m}`))) {
      failures.push(`Missing required vendor metadata: ${UPSTREAM_ROOT}/${m}`);
    }
  }

  return { failures, notes };
}

// ---- CLI ----
if (import.meta.main) {
  const { failures, notes } = checkAgentUpstreamAdoption(process.cwd());
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
}
