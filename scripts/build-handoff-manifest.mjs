#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const directory = process.env.RELEASE_CANDIDATE_EVIDENCE_DIR;
const sourceCommit = process.env.RELEASE_CANDIDATE_SOURCE_COMMIT;
if (!directory || !sourceCommit) {
  throw new Error(
    "Handoff requires the release source commit and evidence directory.",
  );
}
const git = (...args) => execFileSync("git", args, { encoding: "utf8" }).trim();
if (
  git("rev-parse", "HEAD") !== sourceCommit ||
  git("status", "--porcelain", "--untracked-files=all")
) {
  throw new Error(
    "Handoff requires a clean worktree at the declared source commit.",
  );
}
// A generated manifest belongs beside its run evidence, never in tracked source.
git("check-ignore", path.join(directory, "handoff-manifest.json"));
const manifest = JSON.parse(readFileSync("handoff-manifest.json", "utf8"));
manifest.source_commit = sourceCommit;
manifest.generated_at = new Date().toISOString();
for (const verification of Object.values(manifest.verification)) {
  if (!verification.evidence) continue;
  const file = path.join(directory, verification.evidence);
  if (!existsSync(file)) continue;
  const report = JSON.parse(readFileSync(file, "utf8"));
  if (report.source_commit !== sourceCommit) {
    throw new Error(`Evidence source mismatch: ${verification.evidence}`);
  }
  verification.verified = report.result === "passed";
  verification.generated_at = report.generated_at;
}
const destination = path.join(directory, "handoff-manifest.json");
writeFileSync(destination, JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log(`Handoff manifest: ${destination}`);
