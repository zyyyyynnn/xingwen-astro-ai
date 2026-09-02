import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
  rmSync,
} from "node:fs";
import path from "node:path";
import test from "node:test";

test("handoff binds real results to clean exact source and leaves missing proof unverified", () => {
  const root = process.cwd();
  const parent = path.join(root, ".artifacts", "handoff-tests");
  mkdirSync(parent, { recursive: true });
  const directory = mkdtempSync(path.join(parent, "manifest-"));
  const git = (...args) =>
    execFileSync("git", args, {
      cwd: directory,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  try {
    writeFileSync(path.join(directory, ".gitignore"), ".artifacts/\n", "utf8");
    writeFileSync(
      path.join(directory, "handoff-manifest.json"),
      readFileSync(path.join(root, "handoff-manifest.json")),
    );
    git("init", "--quiet");
    git("add", ".gitignore", "handoff-manifest.json");
    git(
      "-c",
      "user.name=Manifest Test",
      "-c",
      "user.email=manifest@example.invalid",
      "commit",
      "--quiet",
      "-m",
      "test: declare handoff catalog",
    );
    const head = git("rev-parse", "HEAD");
    const evidence = path.join(directory, ".artifacts", "evidence");
    mkdirSync(evidence, { recursive: true });
    const report = (sourceCommit, result) =>
      writeFileSync(
        path.join(evidence, "release-candidate-real-data-report.json"),
        JSON.stringify({
          source_commit: sourceCommit,
          generated_at: new Date().toISOString(),
          result,
        }),
        "utf8",
      );
    const generate = () =>
      execFileSync(
        process.execPath,
        [path.join(root, "scripts", "build-handoff-manifest.mjs")],
        {
          cwd: directory,
          env: {
            ...process.env,
            RELEASE_CANDIDATE_SOURCE_COMMIT: head,
            RELEASE_CANDIDATE_EVIDENCE_DIR: evidence,
          },
          stdio: "pipe",
        },
      );
    report(head, "passed");
    generate();
    const manifest = JSON.parse(
      readFileSync(path.join(evidence, "handoff-manifest.json"), "utf8"),
    );
    assert.equal(manifest.source_commit, head);
    assert.ok(manifest.generated_at);
    assert.equal(manifest.verification.real_data.verified, true);
    assert.equal(manifest.verification.real_qwen.verified, false);
    report(head, "failed");
    generate();
    assert.equal(
      JSON.parse(
        readFileSync(path.join(evidence, "handoff-manifest.json"), "utf8"),
      ).verification.real_data.verified,
      false,
    );
    report("0".repeat(40), "passed");
    assert.throws(generate, /Evidence source mismatch/);
    report(head, "passed");
    writeFileSync(
      path.join(directory, "uncommitted.txt"),
      "source changed",
      "utf8",
    );
    assert.throws(generate, /clean worktree/);
  } finally {
    rmSync(directory, { recursive: true });
  }
});
