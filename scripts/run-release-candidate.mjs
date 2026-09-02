#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
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

const visualBaseUrl = process.env.PADDLEOCR_VL_BASE_URL?.trim();
const visualRevision = process.env.PADDLEOCR_VL_MODEL_REVISION?.trim();
if (Boolean(visualBaseUrl) !== Boolean(visualRevision)) {
  throw new Error(
    "The HTTP visual backend requires both PADDLEOCR_VL_BASE_URL and PADDLEOCR_VL_MODEL_REVISION.",
  );
}
if (visualBaseUrl && process.env.PADDLEOCR_VL_LOCAL_BUNDLE?.trim()) {
  throw new Error("Select either the HTTP visual backend or the local bundle.");
}
if (!visualBaseUrl && !existsSync("models")) {
  throw new Error(
    "Release Candidate requires an explicit HTTP visual backend or the operator-managed model bundle under ./models; see docs/setup.md.",
  );
}

requiredEnvironment("DASHSCOPE_API_KEY");
const model = requiredEnvironment("DASHSCOPE_MODEL");
const inputHosts = requiredEnvironment("URL_FETCH_ALLOWED_HOSTS");
if (
  !inputHosts
    .split(",")
    .some((host) => host.trim().toLowerCase() === "arxiv.org")
) {
  throw new Error(
    "Release Candidate full-text ingestion requires arxiv.org in URL_FETCH_ALLOWED_HOSTS.",
  );
}
const explicitRevision = process.env.DASHSCOPE_EXPLICIT_MODEL_REVISION?.trim();
if (explicitRevision && model !== explicitRevision) {
  throw new Error(
    "DASHSCOPE_EXPLICIT_MODEL_REVISION must match the explicit DASHSCOPE_MODEL identity when supplied.",
  );
}

const checks = JSON.parse(
  output("gh", [
    "run",
    "list",
    "--commit",
    head,
    "--limit",
    "30",
    "--json",
    "workflowName,headSha,conclusion,status,url,createdAt",
  ]),
);
const requiredChecks = ["CI", "CodeQL"].map((name) => {
  const check = checks.find(
    (item) => item.workflowName === name && item.headSha === head,
  );
  if (check?.status !== "completed" || check.conclusion !== "success") {
    throw new Error(`Release Candidate requires ${name} PASS on ${head}.`);
  }
  return check;
});
const evidenceDirectory = path.resolve(
  ".artifacts",
  "release-candidate",
  head,
  new Date().toISOString().replaceAll(":", "-"),
);
mkdirSync(evidenceDirectory, { recursive: true });
writeFileSync(
  path.join(evidenceDirectory, "continuous-integration.json"),
  JSON.stringify(
    {
      source_commit: head,
      generated_at: new Date().toISOString(),
      checks: requiredChecks,
      result: "passed",
    },
    null,
    2,
  ) + "\n",
  "utf8",
);

run("docker", ["compose", "version"]);
const projectName = `xingwen-rc-${head.slice(0, 8)}-${process.pid}`;
const composeArgs = [
  "compose",
  "-f",
  "docker-compose.yml",
  ...(visualBaseUrl ? [] : ["-f", "docker-compose.paddle-local.yml"]),
  "-p",
  projectName,
];
function parseTcpPort(name, fallback) {
  const value = (process.env[name] ?? fallback)?.toString().trim();
  if (!value || !/^\d+$/u.test(value)) {
    throw new Error(
      `${name} must be a valid numeric TCP port, received "${value}".`,
    );
  }
  const port = Number.parseInt(value, 10);
  if (port < 1 || port > 65535) {
    throw new Error(`${name} must be between 1 and 65535, received ${port}.`);
  }
  return port;
}

const rcPostgresPort = parseTcpPort("RELEASE_CANDIDATE_POSTGRES_PORT", "55432");
const rcApiPort = parseTcpPort("RELEASE_CANDIDATE_API_PORT", "58000");
const rcSitePort = parseTcpPort("RELEASE_CANDIDATE_SITE_PORT", "54321");
const rcWorkspacePort = parseTcpPort(
  "RELEASE_CANDIDATE_WORKSPACE_PORT",
  "55173",
);

const configuredPorts = [
  { name: "RELEASE_CANDIDATE_POSTGRES_PORT", port: rcPostgresPort },
  { name: "RELEASE_CANDIDATE_API_PORT", port: rcApiPort },
  { name: "RELEASE_CANDIDATE_SITE_PORT", port: rcSitePort },
  { name: "RELEASE_CANDIDATE_WORKSPACE_PORT", port: rcWorkspacePort },
];
const distinctPorts = new Set(configuredPorts.map((item) => item.port));
if (distinctPorts.size !== configuredPorts.length) {
  throw new Error(
    `Release Candidate host ports must be mutually distinct: ${configuredPorts
      .map((item) => `${item.name}=${item.port}`)
      .join(", ")}.`,
  );
}

const runtimeEnvironment = {
  ...process.env,
  APP_ENV: "development",
  RELEASE_CANDIDATE_E2E: "1",
  RELEASE_CANDIDATE_QWEN_MODEL: model,
  DASHSCOPE_MODEL: model,
  DASHSCOPE_EXPLICIT_MODEL_REVISION: explicitRevision ?? "",
  PADDLEOCR_VL_BASE_URL: visualBaseUrl ?? "",
  PADDLEOCR_VL_MODEL_REVISION: visualRevision ?? "",
  PADDLEOCR_VL_LOCAL_BUNDLE: "",
  RELEASE_CANDIDATE_COMPOSE_PROJECT: projectName,
  RELEASE_CANDIDATE_EVIDENCE_DIR: evidenceDirectory,
  RELEASE_CANDIDATE_POSTGRES_PORT: String(rcPostgresPort),
  RELEASE_CANDIDATE_API_PORT: String(rcApiPort),
  RELEASE_CANDIDATE_SITE_PORT: String(rcSitePort),
  RELEASE_CANDIDATE_WORKSPACE_PORT: String(rcWorkspacePort),
  POSTGRES_PORT: String(rcPostgresPort),
  API_PORT: String(rcApiPort),
  SITE_PORT: String(rcSitePort),
  WORKSPACE_PORT: String(rcWorkspacePort),
  CORS_ORIGINS: `http://localhost:${rcWorkspacePort},http://127.0.0.1:${rcWorkspacePort}`,
  PUBLIC_WORKSPACE_URL: `http://localhost:${rcWorkspacePort}/workspace`,
  VITE_API_BASE_URL: `http://127.0.0.1:${rcApiPort}`,
  VITE_SITE_URL: `http://127.0.0.1:${rcSitePort}`,
  REAL_INTEGRATION_API_ORIGIN: `http://127.0.0.1:${rcApiPort}`,
  REAL_INTEGRATION_WORKSPACE_BASE_URL: `http://127.0.0.1:${rcWorkspacePort}`,
  PLAYWRIGHT_BROWSERS_PATH: path.resolve(
    ".artifacts",
    "tooling",
    "playwright-browsers",
  ),
  TEMP: path.resolve(".artifacts", "tooling", "temp"),
  TMP: path.resolve(".artifacts", "tooling", "temp"),
};
const pnpmShell = process.platform === "win32";
mkdirSync(runtimeEnvironment.TEMP, { recursive: true });

console.log(`Release Candidate source: ${head}`);
console.log(`Release Candidate model: ${model}`);
console.log(`Release Candidate Compose project: ${projectName}`);
console.log(
  `Release Candidate host ports: postgres=${rcPostgresPort}, api=${rcApiPort}, site=${rcSitePort}, workspace=${rcWorkspacePort}`,
);
console.log(`Release Candidate evidence: ${evidenceDirectory}`);

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
      "--retries",
      "0",
      "--output",
      path.join(evidenceDirectory, "browser-results"),
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
  run(process.execPath, ["scripts/build-handoff-manifest.mjs"], {
    env: runtimeEnvironment,
  });
}
