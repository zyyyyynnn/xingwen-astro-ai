import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";
import process from "node:process";

import { JSDOM } from "jsdom";

import { inspectMarkdown } from "./check-docs-rules.mjs";

const root = process.cwd();
const documentWindow = new JSDOM("<!doctype html><html><body></body></html>")
  .window;
globalThis.window = documentWindow;
globalThis.document = documentWindow.document;
const { default: mermaid } = await import("mermaid");
const files = execFileSync(
  "git",
  ["-c", "core.quotepath=false", "ls-files", "*.md", "**/*.md"],
  { cwd: root, encoding: "utf8" },
)
  .split(/\r?\n/u)
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"))
  .filter((file) => existsSync(resolve(root, file)));
const results = new Map();
const errors = [];
const authorities = new Map();

function requiresMetadata(file) {
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
    file.startsWith("docs/references/") ||
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

for (const file of files) {
  const expectedStatus = file.startsWith("docs/references/")
    ? "Reference"
    : null;
  const result = inspectMarkdown(readFileSync(resolve(root, file), "utf8"), {
    requireSingleH1:
      !file.startsWith(".github/") &&
      !/^packages\/prompts\/[^/]+\/v\d+\.md$/u.test(file),
    expectedStatus,
    requireMetadata: requiresMetadata(file),
  });
  results.set(file, result);
  for (const error of result.errors) errors.push(`${file}: ${error}`);

  if (
    result.metadata.Authority &&
    !["Reference", "Archived"].includes(result.metadata.Status)
  ) {
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

const indexFile = "docs/README.md";
const indexTargets = new Set();
for (const link of results.get(indexFile)?.links ?? []) {
  const target = localTarget(link.target);
  if (!target) continue;
  const absolute = resolve(root, dirname(indexFile), target);
  if (existsSync(absolute) && statSync(absolute).isFile()) {
    indexTargets.add(relative(root, absolute).replaceAll("\\", "/"));
  }
}
for (const [file, result] of results) {
  if (
    requiresMetadata(file) &&
    file !== indexFile &&
    !["Reference", "Archived"].includes(result.metadata.Status) &&
    !indexTargets.has(file)
  ) {
    errors.push(`${file}: normative document is missing from ${indexFile}`);
  }
}

if (errors.length > 0) {
  console.error("Documentation check failed:\n");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}

console.log(`Documentation check passed for ${files.length} Markdown files.`);
