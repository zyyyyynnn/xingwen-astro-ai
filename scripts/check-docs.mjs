import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import process from "node:process";

import { JSDOM } from "jsdom";

import { inspectMarkdown } from "./check-docs-rules.mjs";
import {
  containsProductionSchemaStatusWording,
  containsRepositoryPhaseIdentifier,
  containsRepositoryPhaseIdentifierPath,
  containsRepositoryProgressWording,
  containsRepositoryTaskCode,
  containsRepositoryTaskCodePath,
  containsRepositoryVersionLabel,
  containsRepositoryVersionLabelPath,
  isIssueOrPullRequestBodyTemplatePath,
  isRepositoryTextPath,
} from "./governance-identifiers.mjs";

const root = process.cwd();
const documentWindow = new JSDOM("<!doctype html><html><body></body></html>")
  .window;
globalThis.window = documentWindow;
globalThis.document = documentWindow.document;
const { default: mermaid } = await import("mermaid");

const trackedFiles = execFileSync(
  "git",
  ["-c", "core.quotepath=false", "ls-files", "-z"],
  { cwd: root, encoding: "utf8" },
)
  .split("\0")
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"))
  .filter((file) => existsSync(resolve(root, file)));

const files = trackedFiles.filter((file) => file.endsWith(".md"));
const repositoryTextFiles = trackedFiles.filter(
  (file) =>
    isRepositoryTextPath(file) &&
    !file.startsWith("apps/workspace/upstream/") &&
    !file.startsWith("tests/evidence/") &&
    !["apps/api/uv.lock", "pnpm-lock.yaml"].includes(file) &&
    file !== "scripts/governance-identifiers.mjs" &&
    file !== "scripts/check-title-governance.mjs",
);

const results = new Map();
const errors = [];
const authorities = new Map();

function isReference(file) {
  return file.startsWith("docs/references/");
}

function requiresAuthority(file) {
  if (isReference(file)) return false;
  return (
    [
      "CONTRIBUTING.md",
      "DEPLOYMENT.md",
      "DESIGN.md",
      "PRD.md",
      "SECURITY.md",
    ].includes(file) ||
    file === "docs/README.md" ||
    file === "docs/setup.md" ||
    /^docs\/(?:ai|architecture|design|engineering|product|quality)\/[^/]+\.md$/u.test(
      file,
    ) ||
    file === "packages/prompts/README.md" ||
    file === "packages/schemas/README.md"
  );
}

function localTarget(rawTarget) {
  let target = rawTarget;
  if (target.startsWith("<") && target.endsWith(">")) {
    target = target.slice(1, -1);
  } else {
    target = target.replace(/\s+["'][^"']*["']\s*$/u, "");
  }
  if (/^(?:[a-z][a-z0-9+.-]*:|#)/iu.test(target)) return null;
  target = target.split("#", 1)[0].split("?", 1)[0];
  if (!target) return null;
  try {
    return decodeURIComponent(target);
  } catch {
    return target;
  }
}

for (const file of trackedFiles) {
  if (containsRepositoryTaskCodePath(file)) {
    errors.push(`${file}: task code is not allowed in tracked file paths`);
  }
  if (containsRepositoryPhaseIdentifierPath(file)) {
    errors.push(
      `${file}: phase identifier is not allowed in tracked file paths`,
    );
  }
  if (containsRepositoryVersionLabelPath(file)) {
    errors.push(
      `${file}: pseudo-version label is not allowed in tracked file paths`,
    );
  }
}

for (const file of files) {
  const result = inspectMarkdown(readFileSync(resolve(root, file), "utf8"), {
    requireSingleH1: !file.startsWith(".github/"),
    requireAuthority: requiresAuthority(file),
  });
  results.set(file, result);
  for (const error of result.errors) errors.push(`${file}: ${error}`);

  if (isReference(file) && result.metadata.Authority) {
    errors.push(
      `${file}: Reference material must not declare normative Authority`,
    );
  }
  if (!isReference(file) && result.metadata.Authority) {
    const previous = authorities.get(result.metadata.Authority);
    if (previous) {
      errors.push(`${file}: duplicates Authority from ${previous}`);
    } else {
      authorities.set(result.metadata.Authority, file);
    }
  }

  for (const link of result.links) {
    const target = localTarget(link.target);
    if (!target) continue;
    const absolute = target.startsWith("/")
      ? resolve(root, target.slice(1))
      : resolve(root, dirname(file), target);
    const withinRoot =
      absolute === root || absolute.startsWith(`${root}${sep}`);
    if (!withinRoot || !existsSync(absolute)) {
      errors.push(
        `${file}: line ${link.line}: local link does not exist: ${link.target}`,
      );
    }
  }

  for (const block of result.mermaidBlocks) {
    try {
      await mermaid.parse(block.lines.join("\n"));
    } catch (error) {
      errors.push(
        `${file}: line ${block.line}: invalid Mermaid: ${error.message}`,
      );
    }
  }
}

for (const file of repositoryTextFiles) {
  const lines = readFileSync(resolve(root, file), "utf8").split(/\r?\n/u);
  for (const [index, line] of lines.entries()) {
    if (containsRepositoryTaskCode(line)) {
      errors.push(
        `${file}: line ${index + 1}: task code is not allowed in repository prose`,
      );
    }
    if (containsRepositoryPhaseIdentifier(line)) {
      errors.push(
        `${file}: line ${index + 1}: phase identifier is not allowed in repository prose`,
      );
    }
    if (containsRepositoryVersionLabel(line)) {
      errors.push(
        `${file}: line ${index + 1}: pseudo-version label is not allowed in repository prose`,
      );
    }
    if (
      !isIssueOrPullRequestBodyTemplatePath(file) &&
      containsRepositoryProgressWording(line)
    ) {
      errors.push(
        `${file}: line ${index + 1}: implementation-progress wording is not allowed in repository prose`,
      );
    }
    if (containsProductionSchemaStatusWording(line, file)) {
      errors.push(
        `${file}: line ${index + 1}: stub status is not allowed in production schemas`,
      );
    }
  }
}

const indexFile = "docs/README.md";
const indexTargets = new Set();
const indexContent = readFileSync(resolve(root, indexFile), "utf8");
const indexLines = indexContent.split(/\r?\n/u);
for (const link of inspectMarkdown(indexContent, {
  requireSingleH1: false,
}).links) {
  if (!indexLines[link.line - 1]?.trimStart().startsWith("|")) continue;
  const target = localTarget(link.target);
  if (!target) continue;
  const absolute = resolve(root, dirname(indexFile), target);
  if (existsSync(absolute) && statSync(absolute).isFile()) {
    indexTargets.add(relative(root, absolute).replaceAll("\\", "/"));
  }
}

for (const file of files) {
  if (
    requiresAuthority(file) &&
    file !== indexFile &&
    !indexTargets.has(file)
  ) {
    errors.push(`${file}: normative Authority is missing from ${indexFile}`);
  }
}
for (const file of indexTargets) {
  if (isReference(file)) {
    errors.push(
      `${indexFile}: Reference material cannot appear in the Authority map: ${file}`,
    );
  }
}

if (errors.length > 0) {
  console.error("Documentation check failed:\n");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`Documentation check passed for ${files.length} Markdown files.`);
