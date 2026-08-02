import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import process from "node:process";

import {
  findRetiredLockfileDependencies,
  findRetiredManifestDependencies,
  findRetiredResolvedDependencies,
  findRetiredTextTerms,
  isRetiredPath,
} from "./check-frontend-legacy-rules.mjs";

const root = process.cwd();
const forbiddenLockNames = new Set([
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb",
]);
const textFilePattern =
  /(?:^|\/)(?:[^/]+\.(?:astro|css|html|js|json|jsx|md|mjs|toml|ts|tsx|txt|yaml|yml)|Dockerfile)$/u;
const files = execFileSync("git", ["ls-files", "-co", "--exclude-standard"], {
  cwd: root,
  encoding: "utf8",
})
  .split(/\r?\n/u)
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"))
  .filter((file) => existsSync(resolve(root, file)));
const failures = [];

for (const file of files) {
  if (isRetiredPath(file)) {
    failures.push(`${file}: retired application path or component remains.`);
  }
  if (forbiddenLockNames.has(basename(file))) {
    failures.push(`${file}: unsupported dependency lock remains.`);
  }

  const path = resolve(root, file);
  if (basename(file) === "package.json") {
    const manifest = JSON.parse(readFileSync(path, "utf8"));
    for (const dependency of findRetiredManifestDependencies(manifest)) {
      failures.push(`${file}: retired dependency ${dependency}.`);
    }
    continue;
  }
  if (file === "pnpm-lock.yaml") {
    for (const dependency of findRetiredLockfileDependencies(
      readFileSync(path, "utf8"),
    )) {
      failures.push(`${file}: retired resolved dependency ${dependency}.`);
    }
    continue;
  }
  if (!textFilePattern.test(file)) {
    continue;
  }

  for (const term of findRetiredTextTerms(readFileSync(path, "utf8"))) {
    failures.push(
      `${file}: contains retired runtime term ${JSON.stringify(term)}.`,
    );
  }
}

try {
  const executable = process.platform === "win32" ? "pwsh" : "pnpm";
  const args =
    process.platform === "win32"
      ? [
          "-NoLogo",
          "-NoProfile",
          "-NonInteractive",
          "-Command",
          "pnpm list -r --json --depth Infinity",
        ]
      : ["list", "-r", "--json", "--depth", "Infinity"];
  const tree = JSON.parse(
    execFileSync(executable, args, {
      cwd: root,
      encoding: "utf8",
      env: { ...process.env, FORCE_COLOR: "0", NO_COLOR: "1" },
    }),
  );
  for (const dependency of findRetiredResolvedDependencies(tree)) {
    failures.push(
      `resolved dependency tree: retired dependency ${dependency}.`,
    );
  }
} catch (error) {
  failures.push(
    `could not inspect the resolved dependency tree: ${error.message}`,
  );
}

if (failures.length > 0) {
  console.error("Frontend retirement check failed:\n");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Frontend retirement check passed.");
