import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import process from "node:process";

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
const SKIP_PATH_PREFIXES = ["apps/api/migrations"];

/**
 * Files intentionally allowed to contain `/api/vN` literals:
 * - the frontend architecture check owns self-test fixtures that assert the
 *   `forbidApiVersionPaths` rule detects violations;
 * - this guard itself documents the pattern it forbids.
 */
const ALLOWLIST = new Set([
  "scripts/check-frontend-architecture.mjs",
  "scripts/check-versionless-api.mjs",
  "CONTRIBUTING.md", // past GitHub issue titles quoted verbatim
]);

const VERSION_PATH_PATTERN = /\/api\/v[0-9](?=[/\W]|$)/u;

/**
 * Collect scannable files under the tracked source tree.
 *
 * `git ls-files -co --exclude-standard` lists tracked and untracked files while
 * honouring `.gitignore`, so ignored trees (`node_modules`, `dist`, `.turbo`,
 * Python `.venv`, …) never leak in as false positives. Results are then
 * filtered to the versioned source directories and inspected extensions.
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
  const existing = listed.filter((file) => existsSync(join(root, file)));

  return existing.filter((file) => {
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
  });
}

const failures = [];

for (const file of collectFiles()) {
  if (ALLOWLIST.has(file)) {
    continue;
  }
  const contents = readFileSync(join(root, file), "utf8");
  const lines = contents.split(/\r?\n/u);
  for (let index = 0; index < lines.length; index += 1) {
    if (VERSION_PATH_PATTERN.test(lines[index])) {
      failures.push(`${file}:${index + 1}: ${lines[index].trim()}`);
    }
  }
}

if (failures.length > 0) {
  console.error(
    "Versionless API check failed — version-prefixed paths found:\n",
  );
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Versionless API check passed.");
