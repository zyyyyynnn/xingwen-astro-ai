#!/usr/bin/env node
/**
 * check-agent-upstream-adoption.mjs
 *
 * Machine gate enforcing OpenHands as the UNIQUE upstream Agent Product source,
 * a fail-closed provenance contract, and a private-reasoning boundary. Runs as
 * part of `pnpm check:architecture`.
 *
 * Gates:
 *   G1  Unique product          — only OpenHands is an upstream Agent product.
 *   G2  Exact ref               — OpenHands/OpenHands @ v1.10.0 @ 566386...
 *   G3  No other source        — repository allowlist + unique upstream root.
 *   G4  No second shell        — no competing Agent Product skeleton root.
 *   G5  Provenance             — if src/ present, provenance.json 1:1 + fail-closed.
 *   G6  No rewrite class       — adoption_class forbids REWRITE/RECREATE/REIMPLEMENT/INSPIRED_BY.
 *   G7  Coding surface         — excluded coding surfaces must not enter production graph.
 *   G8  Only OpenHands src     — no file sourced from a non-OpenHands repository.
 *   G9  Private reasoning boundary — policy_sets honored (excluded/disclosure).
 *   G10 Source closure         — every adopted-scope path has one final disposition.
 *
 * The check is injectable: `checkAgentUpstreamAdoption(root)` where root is any
 * repo root. The CLI entrypoint passes process.cwd().
 */

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { resolve, relative, sep } from "node:path";

import { analyzeVendoredImportGraph } from "./agent-upstream-graph.mjs";
import { computeSelectedTreeSha256 } from "./agent-upstream-provenance.mjs";
import { isForbiddenVendoredProductPath } from "./agent-upstream-boundary.mjs";

const UPSTREAM_ROOT = "apps/workspace/upstream/openhands";
const SRC_DIR = `${UPSTREAM_ROOT}/src`;
const ALLOWED_REPOSITORIES = new Set([
  "https://github.com/OpenHands/OpenHands.git",
]);
const FORBIDDEN_CLASSES = ["REWRITE", "RECREATE", "REIMPLEMENT", "INSPIRED_BY"];
const REQUIRED_META = [
  "upstream-lock.json",
  "source-scope.json",
  "source-policy.json",
  "vendor-blueprint.json",
  "provenance-schema.json",
  "LICENSE.upstream",
  "NOTICE.md",
];
const VALID_CLASSIFICATIONS = new Set([
  "REQUIRED_VENDOR",
  "REQUIRED_TRANSITIVE",
  "PARTIAL_SURGICAL",
  "EXCLUDED",
  "DEFERRED_NOT_VENDORED",
]);
const HASH_RE = /^[0-9a-f]{64}$/u;
const DISCLOSURE_CONSTRAINTS = [
  "preserve-disclosure-mechanics",
  "forbid-private-reasoning-input",
  "public-auditable-reasoning-only",
];

function readJSON(root, rel) {
  const p = resolve(root, rel);
  if (!existsSync(p)) return null;
  return JSON.parse(readFileSync(p, "utf8"));
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
  if (!blueprint)
    failures.push(`Missing ${UPSTREAM_ROOT}/vendor-blueprint.json`);
  const scope = readJSON(root, `${UPSTREAM_ROOT}/source-scope.json`);
  if (!scope) {
    failures.push(`Missing ${UPSTREAM_ROOT}/source-scope.json`);
    return { failures, notes };
  }

  // ---- Scope metadata integrity (G-scoped, §14) ----
  const scopeChecks = [
    ["product", lock.product],
    ["repository", lock.repository],
    ["tag", lock.tag],
    ["commit", lock.commit],
    ["license", lock.license],
  ];
  for (const [k, v] of scopeChecks) {
    if (scope[k] !== v) {
      failures.push(
        `Scope metadata mismatch: scope.${k} ("${scope[k]}") != lock.${k} ("${v}").`,
      );
    }
  }
  // unique upstream_path (no silent map overwrite)
  const seenPaths = new Map();
  for (const f of scope.files ?? []) {
    if (seenPaths.has(f.upstream_path)) {
      failures.push(`Scope duplicate upstream_path: ${f.upstream_path}.`);
    }
    seenPaths.set(f.upstream_path, true);
    if (!VALID_CLASSIFICATIONS.has(f.classification)) {
      failures.push(
        `Scope invalid classification "${f.classification}" for ${f.upstream_path}.`,
      );
    }
  }
  // summary / total recomputation
  const recomputed = {
    REQUIRED_VENDOR: 0,
    REQUIRED_TRANSITIVE: 0,
    PARTIAL_SURGICAL: 0,
    EXCLUDED: 0,
    DEFERRED_NOT_VENDORED: 0,
  };
  for (const f of scope.files ?? []) recomputed[f.classification]++;
  if (JSON.stringify(recomputed) !== JSON.stringify(scope.summary)) {
    failures.push(
      `Scope summary mismatch: ${JSON.stringify(scope.summary)} != ${JSON.stringify(recomputed)}.`,
    );
  }
  if (scope.total_scoped_files !== scope.files.length) {
    failures.push(
      `Scope total_scoped_files (${scope.total_scoped_files}) != files.length (${scope.files.length}).`,
    );
  }
  const files = scope.files ?? [];

  // The approved mechanics list is the human architecture boundary. The
  // inventory below may describe every frozen upstream path, but it cannot
  // silently expand or shrink the adopted product surface.
  const approvedMechanicsPaths = new Set();
  const transitiveMechanicsPaths = new Set();
  if (
    !Array.isArray(scope.approved_mechanics) ||
    scope.approved_mechanics.length === 0
  ) {
    failures.push(
      "Approved mechanics scope must contain at least one surface.",
    );
  } else {
    for (const surface of scope.approved_mechanics) {
      if (
        !surface ||
        typeof surface !== "object" ||
        !Array.isArray(surface.upstream_paths)
      ) {
        failures.push("Approved mechanics scope contains an invalid surface.");
        continue;
      }
      for (const upstreamPath of surface.upstream_paths) {
        if (approvedMechanicsPaths.has(upstreamPath)) {
          failures.push(`Approved mechanics scope duplicates ${upstreamPath}.`);
          continue;
        }
        approvedMechanicsPaths.add(upstreamPath);
        const entry = seenPaths.has(upstreamPath)
          ? files.find((candidate) => candidate.upstream_path === upstreamPath)
          : null;
        if (!entry) {
          failures.push(
            `Approved mechanics path is missing from source-scope: ${upstreamPath}.`,
          );
        } else if (
          ![
            "REQUIRED_VENDOR",
            "REQUIRED_TRANSITIVE",
            "PARTIAL_SURGICAL",
          ].includes(entry.classification)
        ) {
          failures.push(
            `Approved mechanics path ${upstreamPath} must be adopted, found ${entry.classification}.`,
          );
        }
      }
    }
  }
  if (
    scope.transitive_mechanics !== undefined &&
    !Array.isArray(scope.transitive_mechanics)
  ) {
    failures.push("Transitive mechanics scope must be an array when present.");
  } else {
    for (const surface of scope.transitive_mechanics ?? []) {
      if (
        !surface ||
        typeof surface !== "object" ||
        !Array.isArray(surface.upstream_paths)
      ) {
        failures.push(
          "Transitive mechanics scope contains an invalid surface.",
        );
        continue;
      }
      for (const upstreamPath of surface.upstream_paths) {
        if (
          approvedMechanicsPaths.has(upstreamPath) ||
          transitiveMechanicsPaths.has(upstreamPath)
        ) {
          failures.push(`Mechanics scope duplicates ${upstreamPath}.`);
          continue;
        }
        transitiveMechanicsPaths.add(upstreamPath);
        const entry = seenPaths.has(upstreamPath)
          ? files.find((candidate) => candidate.upstream_path === upstreamPath)
          : null;
        if (!entry) {
          failures.push(
            `Transitive mechanics path is missing from source-scope: ${upstreamPath}.`,
          );
        } else if (
          !["REQUIRED_TRANSITIVE", "PARTIAL_SURGICAL"].includes(
            entry.classification,
          )
        ) {
          failures.push(
            `Transitive mechanics path ${upstreamPath} must be REQUIRED_TRANSITIVE or PARTIAL_SURGICAL, found ${entry.classification}.`,
          );
        }
      }
    }
  }
  const adoptedMechanicsPaths = new Set([
    ...approvedMechanicsPaths,
    ...transitiveMechanicsPaths,
  ]);
  for (const entry of files) {
    if (
      ["REQUIRED_VENDOR", "REQUIRED_TRANSITIVE", "PARTIAL_SURGICAL"].includes(
        entry.classification,
      ) &&
      !adoptedMechanicsPaths.has(entry.upstream_path)
    ) {
      failures.push(
        `Adopted source-scope path is not in the approved or transitive mechanics scope: ${entry.upstream_path}.`,
      );
    }
  }

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
  const excluded = files.filter((f) => f.classification === "EXCLUDED");
  if (excluded.length === 0) {
    failures.push(
      "G7: source-scope has no EXCLUDED entries (coding surfaces must be excluded).",
    );
  }
  const badAdopted = files.filter(
    (f) =>
      (f.classification === "REQUIRED_VENDOR" ||
        f.classification === "REQUIRED_TRANSITIVE") &&
      isForbiddenVendoredProductPath(f.upstream_path),
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

  // ---- G9 : private reasoning boundary (policy_sets) ----
  // source-policy is the complete inventory; compact source-scope files only
  // need to reject a private path when it is explicitly represented there.
  const policySets = scope.policy_sets ?? {};
  if (policySets.private_reasoning_excluded) {
    for (const p of policySets.private_reasoning_excluded) {
      const sf = seenPaths.has(p)
        ? files.find((f) => f.upstream_path === p)
        : null;
      if (sf && sf.classification !== "EXCLUDED") {
        failures.push(
          `G9: private_reasoning_excluded path not classified EXCLUDED: ${p}.`,
        );
      }
    }
  }
  if (policySets.public_reasoning_disclosure) {
    for (const p of policySets.public_reasoning_disclosure) {
      const sf = files.find((f) => f.upstream_path === p);
      if (!sf || sf.classification !== "PARTIAL_SURGICAL") {
        failures.push(
          `G9: public_reasoning_disclosure path not classified PARTIAL_SURGICAL: ${p}.`,
        );
        continue;
      }
      const cs = sf.constraints ?? [];
      for (const req of DISCLOSURE_CONSTRAINTS) {
        if (!cs.includes(req)) {
          failures.push(
            `G9: disclosure path missing constraint "${req}": ${p}.`,
          );
        }
      }
    }
  }

  // ---- G5 : provenance (disk <-> provenance exact 1:1, fail-closed) ----
  const srcDir = resolve(root, SRC_DIR);
  let provenanceEntries = [];
  let diskLocalPaths = new Set();
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
      const entries = manifest?.entries;
      const entryList = Array.isArray(entries) ? entries : [];
      if (
        Array.isArray(manifest) ||
        manifest?.schema !== "xingwen.agent-upstream.provenance/v2" ||
        !Array.isArray(entries)
      ) {
        failures.push(
          "G5: provenance.json must use the v2 manifest object contract.",
        );
      }
      provenanceEntries = entryList;
      const schema =
        readJSON(root, `${UPSTREAM_ROOT}/provenance-schema.json`) ?? {};
      const requiredFields = schema.required_fields ?? [];
      const vendoredClasses = lock.vendored_file_adoption_classes ?? [];
      const scopeByPath = new Map(files.map((f) => [f.upstream_path, f]));
      const classCompat = schema.class_compatibility ?? {};

      const sourceChecks = [
        ["repository", lock.repository],
        ["tag", lock.tag],
        ["commit", lock.commit],
        ["license", lock.license],
      ];
      for (const [field, expected] of sourceChecks) {
        if (manifest?.source?.[field] !== expected) {
          failures.push(`G5: provenance source ${field} mismatch.`);
        }
      }
      if (!HASH_RE.test(lock.keep_as_is_tree_sha256 ?? "")) {
        failures.push(
          "G5: upstream-lock keep_as_is_tree_sha256 must be 64 lowercase hex.",
        );
      }
      if (manifest?.keep_as_is_tree_sha256 !== lock.keep_as_is_tree_sha256) {
        failures.push(
          "G5: provenance KEEP_AS_IS aggregate digest differs from upstream-lock.",
        );
      }

      // Disk -> Provenance : every on-disk file has exactly one manifest entry
      const diskFiles = walkFiles(srcDir);
      diskLocalPaths = new Set(
        diskFiles.map((f) => toPosix(relative(root, f))),
      );
      const provByLocal = new Map();
      for (const e of entryList) {
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
      for (const e of entryList) {
        if (!diskLocalPaths.has(e.local_path)) {
          failures.push(
            `G5: dangling provenance entry (file missing): ${e.local_path}.`,
          );
        }
      }
      // Per-entry mapping and adoption validation
      for (const e of entryList) {
        const where = e.local_path ?? "<unknown local_path>";
        // required fields present
        for (const rf of requiredFields) {
          if (!(rf in e))
            failures.push(
              `G5: provenance entry missing required field "${rf}" (${where}).`,
            );
        }
        if (!("modified" in e)) {
          failures.push(`G5: provenance entry missing "modified" (${where}).`);
        } else if (typeof e.modified !== "boolean") {
          failures.push(
            `G5: provenance "modified" must be boolean (${where}).`,
          );
        }
        if (e.modified === true && !e.modification_reason) {
          failures.push(
            `G5: modified=true requires non-empty modification_reason (${where}).`,
          );
        }
        // path safety (skip if already flagged missing by required-field check)
        if (
          typeof e.upstream_path !== "string" ||
          !e.upstream_path.startsWith("src/") ||
          e.upstream_path.includes("..") ||
          e.upstream_path.includes("\\")
        ) {
          failures.push(`G5: unsafe upstream_path (${where}).`);
        }
        if (
          typeof e.local_path !== "string" ||
          !e.local_path.startsWith(`${SRC_DIR}/`) ||
          e.local_path.includes("..")
        ) {
          failures.push(`G5: local_path escapes upstream src root (${where}).`);
        } else if (
          typeof e.upstream_path === "string" &&
          e.local_path !== `${UPSTREAM_ROOT}/${e.upstream_path}`
        ) {
          failures.push(
            `G5: local_path must preserve the upstream relative path (${where}).`,
          );
        }
        // adoption class validity for actual files
        if (e.adoption_class && !vendoredClasses.includes(e.adoption_class)) {
          failures.push(
            `G5: adoption_class not allowed for vendored file: ${e.adoption_class} (${where}).`,
          );
        }
        // Provenance -> Scope membership
        const sc = scopeByPath.get(e.upstream_path);
        if (!sc) {
          failures.push(
            `G5: provenance upstream_path not in source-scope: ${e.upstream_path} (${where}).`,
          );
        } else if (
          ![
            "REQUIRED_VENDOR",
            "REQUIRED_TRANSITIVE",
            "PARTIAL_SURGICAL",
          ].includes(sc.classification)
        ) {
          failures.push(
            `G5: provenance upstream_path classified ${sc.classification} (must be REQUIRED_VENDOR/TRANSITIVE/PARTIAL_SURGICAL): ${e.upstream_path} (${where}).`,
          );
        } else if (
          e.adoption_class &&
          !(classCompat[sc.classification] ?? []).includes(e.adoption_class)
        ) {
          failures.push(
            `G5: adoption_class ${e.adoption_class} incompatible with scope classification ${sc.classification} (${where}).`,
          );
        }
        if (e.modified === false && e.adoption_class !== "KEEP_AS_IS") {
          failures.push(`G5: modified=false requires KEEP_AS_IS (${where}).`);
        }
        if (
          e.modified === true &&
          ![
            "KEEP_WITH_MINIMAL_PATCH",
            "KEEP_STRUCTURE_REPLACE_DOMAIN_CONTENT",
          ].includes(e.adoption_class)
        ) {
          failures.push(
            `G5: modified=true requires a patched adoption class (${where}).`,
          );
        }
      }

      const keepAsIsEntries = entryList.filter(
        (entry) => entry.adoption_class === "KEEP_AS_IS",
      );
      if (
        HASH_RE.test(lock.keep_as_is_tree_sha256 ?? "") &&
        keepAsIsEntries.every(
          (entry) =>
            typeof entry.upstream_path === "string" &&
            entry.upstream_path.startsWith("src/") &&
            entry.local_path === `${UPSTREAM_ROOT}/${entry.upstream_path}` &&
            diskLocalPaths.has(entry.local_path),
        )
      ) {
        const keepAsIsPaths = keepAsIsEntries.map((entry) =>
          entry.upstream_path.slice("src/".length),
        );
        if (
          computeSelectedTreeSha256(srcDir, keepAsIsPaths) !==
          lock.keep_as_is_tree_sha256
        ) {
          failures.push(
            "G5: KEEP_AS_IS source differs from the frozen upstream aggregate digest.",
          );
        }
      }
    }
  }

  // ---- G10 : frozen adopted-scope closure + local import reachability ----
  if (existsSync(srcDir)) {
    const schema =
      readJSON(root, `${UPSTREAM_ROOT}/provenance-schema.json`) ?? {};
    const resolutionFile = schema.resolution_file ?? "source-resolution.json";
    const resolution = readJSON(root, `${UPSTREAM_ROOT}/${resolutionFile}`);
    if (!resolution) {
      failures.push(
        `G10: vendored src/ present but ${UPSTREAM_ROOT}/${resolutionFile} missing.`,
      );
    } else {
      if (resolution.repository !== lock.repository) {
        failures.push("G10: source-resolution repository mismatch.");
      }
      if (resolution.tag !== lock.tag) {
        failures.push("G10: source-resolution tag mismatch.");
      }
      if (resolution.commit !== lock.commit) {
        failures.push("G10: source-resolution commit mismatch.");
      }
      if (resolution.entrypoint !== "src/root.tsx") {
        failures.push(
          "G10: source-resolution entrypoint must be src/root.tsx.",
        );
      }

      const requiredClassifications = new Set([
        "REQUIRED_VENDOR",
        "REQUIRED_TRANSITIVE",
        "PARTIAL_SURGICAL",
      ]);
      const requiredPaths = new Set(adoptedMechanicsPaths);
      const requiredScopeEntries = [...requiredPaths]
        .map((upstreamPath) =>
          files.find((entry) => entry.upstream_path === upstreamPath),
        )
        .filter(
          (entry) => entry && requiredClassifications.has(entry.classification),
        );
      const statuses = new Set(schema.resolution_statuses ?? []);
      const requiredFields = schema.resolution_required_fields ?? [];
      const resolutionEntries = resolution.entries ?? [];
      const resolutionByPath = new Map();
      const provenanceByPath = new Map(
        provenanceEntries.map((entry) => [entry.upstream_path, entry]),
      );
      const importGraph = analyzeVendoredImportGraph({
        root,
        sourceRoot: SRC_DIR,
        diskPaths: diskLocalPaths,
      });
      if (importGraph.unresolved.length > 0) {
        failures.push(
          `G10: vendored source has unresolved local imports: ${importGraph.unresolved
            .map(({ from, specifier }) => `${from} -> ${specifier}`)
            .join(", ")}.`,
        );
      }
      if (importGraph.unreachable.length > 0) {
        failures.push(
          `G10: vendored source is outside the src/root.tsx dependency closure: ${importGraph.unreachable.join(", ")}.`,
        );
      }

      for (const entry of resolutionEntries) {
        const where = entry.upstream_path ?? "<unknown upstream_path>";
        for (const field of requiredFields) {
          if (!(field in entry)) {
            failures.push(
              `G10: source-resolution entry missing "${field}" (${where}).`,
            );
          }
        }
        if (resolutionByPath.has(entry.upstream_path)) {
          failures.push(
            `G10: duplicate source-resolution upstream_path: ${entry.upstream_path}.`,
          );
        }
        resolutionByPath.set(entry.upstream_path, entry);
        if (!requiredPaths.has(entry.upstream_path)) {
          failures.push(
            `G10: source-resolution path is outside adopted scope: ${where}.`,
          );
        }
        if (!statuses.has(entry.status)) {
          failures.push(
            `G10: invalid source-resolution status "${entry.status}" (${where}).`,
          );
        }
        if (typeof entry.reason !== "string" || !entry.reason.trim()) {
          failures.push(`G10: source-resolution reason is empty (${where}).`);
        }
        if (typeof entry.proof !== "string" || !entry.proof.trim()) {
          failures.push(`G10: source-resolution proof is empty (${where}).`);
        }

        const provenance = provenanceByPath.get(entry.upstream_path);
        if (provenance) {
          const expectedStatus = provenance.modified
            ? "SURGICALLY_ADAPTED"
            : "VENDORED";
          if (entry.status !== expectedStatus) {
            failures.push(
              `G10: ${where} must resolve as ${expectedStatus}, found ${entry.status}.`,
            );
          }
        } else {
          failures.push(
            `G10: adopted-scope path has no vendored source: ${where}.`,
          );
        }
      }

      for (const upstreamPath of requiredPaths) {
        if (!resolutionByPath.has(upstreamPath)) {
          failures.push(
            `G10: adopted-scope path has no final resolution: ${upstreamPath}.`,
          );
        }
      }

      const recomputedResolutionSummary = {
        VENDORED: 0,
        SURGICALLY_ADAPTED: 0,
      };
      for (const entry of resolutionEntries) {
        if (entry.status in recomputedResolutionSummary) {
          recomputedResolutionSummary[entry.status] += 1;
        }
      }
      if (
        JSON.stringify(resolution.summary) !==
        JSON.stringify(recomputedResolutionSummary)
      ) {
        failures.push("G10: source-resolution summary mismatch.");
      }
      if (resolution.total !== requiredScopeEntries.length) {
        failures.push(
          `G10: source-resolution total (${resolution.total}) != adopted scope (${requiredScopeEntries.length}).`,
        );
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
