import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

import * as prettier from "prettier";

const root = process.cwd();
const manifestPath = resolve(
  root,
  "apps/workspace/upstream/openhands/provenance.json",
);
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const modifiedPaths = manifest.entries
  .filter((entry) => entry.modified === true)
  .map((entry) => entry.local_path)
  .sort();
const write = process.argv.includes("--write");
const unformatted = [];

for (const path of modifiedPaths) {
  const absolutePath = resolve(root, path);
  const source = readFileSync(absolutePath, "utf8");
  const config = (await prettier.resolveConfig(absolutePath)) ?? {};
  const formatted = await prettier.format(source, {
    ...config,
    filepath: absolutePath,
  });
  if (source === formatted) continue;
  if (write) writeFileSync(absolutePath, formatted, "utf8");
  else unformatted.push(path);
}

if (unformatted.length > 0) {
  console.error("Modified OpenHands source files need formatting:");
  for (const path of unformatted) console.error(`- ${path}`);
  process.exit(1);
}

console.log(
  write
    ? `Formatted ${modifiedPaths.length} modified OpenHands source files.`
    : `Formatting check passed for ${modifiedPaths.length} modified OpenHands source files.`,
);
