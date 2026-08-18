import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

/**
 * Guards against reintroduction of version-prefixed API paths. The whole product now
 * speaks a single versionless `/api/*` surface; a stray version segment in
 * source, config, or docs signals an accidental regression.
 *
 * Node built-ins only; mirrors the style of the other `scripts/check-*.mjs`
 * gates. Exits 1 with a `file:line` listing on any hit.
 */

const root = resolve(process.cwd());

/** Top-level directories that are scanned recursively. */
const SCAN_DIRS = ["apps", "packages", "services", "tests", "scripts"];

/** File extensions inspected for version-prefixed API paths. */
const SCANNED_EXTENSIONS = new Set([
  ".py",
  ".ts",
  ".tsx",
  ".js",
  ".mjs",
  ".cjs",
  ".json",
  ".yml",
  ".yaml",
]);

/** Directory names skipped anywhere in the tree. */
const SKIP_DIR_NAMES = new Set(["node_modules", "dist", ".turbo"]);

/** Path prefixes (relative, forward-slash) skipped wholesale. */
const SKIP_PATH_PREFIXES = [];

/**
 * Files intentionally allowed to contain `/api/vN` literals:
 * - the frontend architecture check owns self-test fixtures that assert the
 *   `forbidApiVersionPaths` rule detects violations;
 * - this guard itself documents the pattern it forbids.
 */
const ALLOWLIST = new Set([
  "scripts/check-frontend-architecture.mjs",
  "scripts/check-versionless-api.mjs",
  "scripts/check-versionless-api.test.mjs",
]);

/**
 * Official provider routes whose upstream API version is part of the provider
 * contract, not the Xingwen product API. Keep this exact and file-scoped so a
 * new local `/api/vN` path in the same module still fails the gate.
 */
const EXTERNAL_PROVIDER_API_PATHS = new Map([
  [
    "services/scientific_skills/astro_acquisition.py",
    new Set([
      "https://mast.stsci.edu/api/v0.1/Download/file",
      "/api/v0.1/Download/file",
    ]),
  ],
]);

const VERSION_PATH_PATTERN = /\/api\/v[0-9]+(?=[/\W]|$)/u;
const VERSIONED_API_TRACKED_PATH_PATTERN = /(?:^|\/)api\/v[0-9]+(?=\/|$)/u;

/**
 * Collect existing tracked and untracked files under the repository root.
 *
 * `git ls-files -co --exclude-standard` lists tracked and untracked files while
 * honouring `.gitignore`, so ignored trees (`node_modules`, `dist`, `.turbo`,
 * Python `.venv`, …) never leak in as false positives. Results are then
 * checked for path violations before content-specific filtering.
 */
function collectFiles() {
  const listed = execFileSync(
    "git",
    ["ls-files", "-co", "--exclude-standard"],
    {
      cwd: root,
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
    },
  )
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((file) => file.replaceAll("\\", "/"));

  // A generated Contract may be intentionally removed in the working tree;
  // do not attempt to read deleted tracked paths before the next commit.
  return listed.filter((file) => existsSync(join(root, file)));
}

function shouldScanContents(file) {
  if (file.split("/").some((segment) => SKIP_DIR_NAMES.has(segment))) {
    return false;
  }
  if (SKIP_PATH_PREFIXES.some((prefix) => file.startsWith(prefix))) {
    return false;
  }
  const dot = file.lastIndexOf(".");
  const extension = dot === -1 ? "" : file.slice(dot);
  // Markdown is policed repo-wide (docs live under docs/ and the repo root);
  // code/config files are policed only within the versioned source dirs.
  if (extension === ".md") {
    return true;
  }
  if (!SCAN_DIRS.some((dir) => file === dir || file.startsWith(`${dir}/`))) {
    return false;
  }
  return SCANNED_EXTENSIONS.has(extension);
}

export function versionlessApiViolations(file, contents = null) {
  const failures = [];
  if (VERSIONED_API_TRACKED_PATH_PATTERN.test(file)) {
    failures.push(`${file}: path contains a version-prefixed API segment`);
  }
  if (contents === null || ALLOWLIST.has(file)) {
    return failures;
  }
  const lines = contents.split(/\r?\n/u);
  for (let index = 0; index < lines.length; index += 1) {
    let inspectedLine = lines[index];
    for (const providerPath of EXTERNAL_PROVIDER_API_PATHS.get(file) ?? []) {
      inspectedLine = inspectedLine.replaceAll(providerPath, "");
    }
    if (VERSION_PATH_PATTERN.test(inspectedLine)) {
      failures.push(`${file}:${index + 1}: ${lines[index].trim()}`);
    }
  }
  return failures;
}

export function inspectTrackedFiles(files, readContents) {
  const failures = [];
  for (const file of files) {
    const contents = shouldScanContents(file) ? readContents(file) : null;
    failures.push(...versionlessApiViolations(file, contents));
  }
  return failures;
}

export function main() {
  const failures = inspectTrackedFiles(collectFiles(), (file) =>
    readFileSync(join(root, file), "utf8"),
  );

  if (failures.length > 0) {
    console.error(
      "Versionless API check failed — version-prefixed paths found:\n",
    );
    for (const failure of failures) {
      console.error(`- ${failure}`);
    }
    return 1;
  }

  console.log("Versionless API check passed.");
  return 0;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  process.exitCode = main();
}
