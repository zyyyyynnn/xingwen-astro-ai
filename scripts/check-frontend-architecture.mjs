import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import process from "node:process";

const root = process.cwd();
const packageLocations = new Map([
  ["@xingwen/site", "apps/site"],
  ["@xingwen/workspace", "apps/workspace"],
  ["@xingwen/design-tokens", "packages/design-tokens"],
  ["@xingwen/ui", "packages/ui"],
  ["@xingwen/domain", "packages/domain"],
  ["@xingwen/contracts", "packages/contracts"],
  ["@xingwen/data-access", "packages/data-access"],
  ["@xingwen/workspace-core", "packages/workspace-core"],
  ["@xingwen/visual-engine", "packages/visual-engine"],
  ["@xingwen/testing", "packages/testing"],
]);

const allowedLocalDependencies = new Map([
  [
    "@xingwen/site",
    new Set([
      "@xingwen/design-tokens",
      "@xingwen/ui",
      "@xingwen/visual-engine",
    ]),
  ],
  [
    "@xingwen/workspace",
    new Set([
      "@xingwen/design-tokens",
      "@xingwen/ui",
      "@xingwen/workspace-core",
      "@xingwen/data-access",
    ]),
  ],
  ["@xingwen/design-tokens", new Set()],
  ["@xingwen/ui", new Set()],
  ["@xingwen/domain", new Set()],
  ["@xingwen/contracts", new Set()],
  ["@xingwen/data-access", new Set(["@xingwen/domain", "@xingwen/contracts"])],
  ["@xingwen/workspace-core", new Set(["@xingwen/domain"])],
  ["@xingwen/visual-engine", new Set()],
  ["@xingwen/testing", new Set()],
]);

const failures = [];
const manifests = new Map();

for (const [expectedName, location] of packageLocations) {
  const manifestPath = resolve(root, location, "package.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  manifests.set(expectedName, { location, manifest });

  if (manifest.name !== expectedName) {
    failures.push(`${location}/package.json must declare ${expectedName}.`);
  }

  const dependencyGroups = [
    manifest.dependencies ?? {},
    manifest.devDependencies ?? {},
    manifest.peerDependencies ?? {},
    manifest.optionalDependencies ?? {},
  ];
  const localDependencies = dependencyGroups
    .flatMap((group) => Object.keys(group))
    .filter((name) => name.startsWith("@xingwen/"));
  const allowed = allowedLocalDependencies.get(expectedName);

  for (const dependency of localDependencies) {
    if (!allowed?.has(dependency)) {
      failures.push(`${expectedName} must not depend on ${dependency}.`);
    }
  }

  if (location.startsWith("packages/")) {
    for (const dependency of localDependencies) {
      if (
        dependency === "@xingwen/site" ||
        dependency === "@xingwen/workspace"
      ) {
        failures.push(
          `${expectedName} must not depend on an application package.`,
        );
      }
    }
  }
}

const listedFiles = execFileSync(
  "git",
  ["ls-files", "-co", "--exclude-standard"],
  {
    cwd: root,
    encoding: "utf8",
  },
)
  .split(/\r?\n/u)
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"));

const lockfiles = listedFiles.filter((file) => file.endsWith("pnpm-lock.yaml"));
if (lockfiles.length !== 1 || lockfiles[0] !== "pnpm-lock.yaml") {
  failures.push(
    `Expected one root dependency lock; found: ${lockfiles.join(", ") || "none"}.`,
  );
}

const exportedSpecifiers = new Set();
for (const [name, { manifest }] of manifests) {
  const exportsField = manifest.exports ?? {};
  for (const exportKey of Object.keys(exportsField)) {
    exportedSpecifiers.add(
      exportKey === "." ? name : `${name}${exportKey.slice(1)}`,
    );
  }
}

const sourceFiles = listedFiles.filter((file) =>
  /\.(?:astro|mjs|ts|tsx)$/u.test(file),
);
const importPattern = /(?:from\s+|import\s*)["'](@xingwen\/[^"']+)["']/gu;

for (const file of sourceFiles) {
  const content = readFileSync(resolve(root, file), "utf8");
  for (const match of content.matchAll(importPattern)) {
    const specifier = match[1];
    if (specifier && !exportedSpecifiers.has(specifier)) {
      failures.push(`${file} imports non-public package path ${specifier}.`);
    }
  }
}

for (const file of listedFiles.filter((entry) =>
  /(?:^|\/)tsconfig[^/]*\.json$/u.test(entry),
)) {
  const content = readFileSync(resolve(root, file), "utf8");
  const config = JSON.parse(content);
  if (config.compilerOptions?.paths) {
    failures.push(`${file} must not define package-bypassing path aliases.`);
  }
}

function checkSourceBoundary(location, forbiddenPatterns, description) {
  for (const file of sourceFiles.filter((entry) =>
    entry.startsWith(`${location}/src/`),
  )) {
    const content = readFileSync(resolve(root, file), "utf8").toLowerCase();
    for (const pattern of forbiddenPatterns) {
      if (content.includes(pattern)) {
        failures.push(
          `${relative(root, resolve(root, file))} violates ${description}: ${pattern}.`,
        );
      }
    }
  }
}

checkSourceBoundary(
  "packages/domain",
  [
    "react",
    "astro",
    "vite",
    "fetch(",
    "xmlhttprequest",
    "window.",
    "document.",
  ],
  "the framework-free domain boundary",
);
checkSourceBoundary(
  "packages/ui",
  ["fetch(", "repository"],
  "the presentation-only UI boundary",
);
checkSourceBoundary(
  "packages/visual-engine",
  ["fetch(", "repository"],
  "the presentation-only visual boundary",
);

if (failures.length > 0) {
  console.error("Frontend architecture check failed:\n");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Frontend architecture check passed.");
