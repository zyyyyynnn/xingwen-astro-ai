#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import process from "node:process";

function run(command, args, options = {}) {
  execFileSync(command, args, {
    cwd: process.cwd(),
    env: options.env ?? process.env,
    stdio: "inherit",
    shell: options.shell ?? false,
  });
}

function output(command, args) {
  return execFileSync(command, args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function requiredEnvironment(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for the Release Candidate gate.`);
  }
  return value;
}

const expectedCommit = requiredEnvironment("RELEASE_CANDIDATE_SOURCE_COMMIT");
if (!/^[0-9a-f]{40}$/u.test(expectedCommit)) {
  throw new Error(
    "RELEASE_CANDIDATE_SOURCE_COMMIT must be a full 40-character SHA.",
  );
}

const head = output("git", ["rev-parse", "HEAD"]);
if (head !== expectedCommit) {
  throw new Error(
    `Release Candidate source mismatch: expected ${expectedCommit}, current HEAD is ${head}.`,
  );
}

const dirty = output("git", ["status", "--porcelain", "--untracked-files=all"]);
if (dirty) {
  throw new Error(
    "Release Candidate requires a clean worktree so the tested source equals the exact commit.",
  );
}

if (!existsSync(".env")) {
  throw new Error(
    "Release Candidate requires a local .env file for the normal Compose runtime contract.",
  );
}

if (!existsSync("models")) {
  throw new Error(
    "Release Candidate requires the operator-managed PaddleOCR-VL model bundle under ./models; see docs/setup.md.",
  );
}

requiredEnvironment("DASHSCOPE_API_KEY");
const model = requiredEnvironment("DASHSCOPE_MODEL");
const explicitRevision = requiredEnvironment(
  "DASHSCOPE_EXPLICIT_MODEL_REVISION",
);
if (model !== explicitRevision) {
  throw new Error(
    "DASHSCOPE_MODEL and DASHSCOPE_EXPLICIT_MODEL_REVISION must identify the same qualifying Qwen revision.",
  );
}

run("docker", ["compose", "version"]);
const projectName = `xingwen-rc-${head.slice(0, 8)}-${process.pid}`;
const composeArgs = [
  "compose",
  "-f",
  "docker-compose.yml",
  "-f",
  "docker-compose.paddle-local.yml",
  "-p",
  projectName,
];
const runtimeEnvironment = {
  ...process.env,
  APP_ENV: "development",
  RELEASE_CANDIDATE_E2E: "1",
  RELEASE_CANDIDATE_QWEN_MODEL: model,
  REAL_INTEGRATION_API_ORIGIN: "http://127.0.0.1:8000",
  REAL_INTEGRATION_WORKSPACE_BASE_URL: "http://127.0.0.1:5173",
  VITE_API_BASE_URL: "http://127.0.0.1:8000",
};
const pnpmShell = process.platform === "win32";

console.log(`Release Candidate source: ${head}`);
console.log(`Release Candidate model: ${model}`);
console.log(`Release Candidate Compose project: ${projectName}`);

try {
  run("docker", [...composeArgs, "config", "--quiet"], {
    env: runtimeEnvironment,
  });
  run(
    "docker",
    [...composeArgs, "up", "--build", "--detach", "--wait", "--remove-orphans"],
    { env: runtimeEnvironment },
  );
  run("pnpm", ["exec", "playwright", "install", "chromium"], {
    env: runtimeEnvironment,
    shell: pnpmShell,
  });
  run(
    "pnpm",
    [
      "exec",
      "playwright",
      "test",
      "tests/e2e-integration/release-candidate-live.spec.ts",
      "--config",
      "playwright.integration.config.ts",
    ],
    { env: runtimeEnvironment, shell: pnpmShell },
  );
  console.log(`Release Candidate gate passed for ${head}.`);
} finally {
  // The RC project name is unique, so tearing down the isolated project also
  // removes its own ephemeral volumes without touching any existing
  // development/production project or its persisted volumes.
  try {
    run("docker", [...composeArgs, "down", "--volumes", "--remove-orphans"], {
      env: runtimeEnvironment,
    });
  } catch {
    console.error(
      `Release Candidate cleanup could not stop isolated project ${projectName}.`,
    );
  }
}
