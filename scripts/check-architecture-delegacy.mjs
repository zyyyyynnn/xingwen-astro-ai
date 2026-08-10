import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

import {
  isIssueOrPullRequestBodyTemplatePath,
  isRepositoryTextPath,
} from "./governance-identifiers.mjs";

const FORBIDDEN_SURFACES = [
  ["retired task API", /\/api\/tasks(?:\/|\b)/u],
  ["retired Task service", /\bTaskService\b/u],
  ["retired task create request", /\bTaskCreateRequest\b/u],
  ["retired task status response", /\bTaskStatusResponse\b/u],
  ["retired workflow executor", /\bWorkflowExecutor\b/u],
  ["retired workflow context", /\bWorkflowContext\b/u],
  ["retired workflow hooks", /\bWorkflowHooks\b/u],
  ["retired task status enum", /\bTaskStatus\b/u],
  ["retired task-read projection", /\btask-read\b/iu],
  ["retired task schema module", /\bapp\.schemas\.task\b/u],
  ["retired workflow executor module", /\bapp\.workflow\.executor\b/u],
  ["retired task state-machine module", /\bapp\.workflow\.state_machine\b/u],
];

const FORBIDDEN_PATHS = new Set([
  "apps/api/src/app/services/task_service.py",
  "apps/api/src/app/routers/tasks.py",
  "apps/api/src/app/schemas/task.py",
  "apps/api/src/app/workflow/executor.py",
  "apps/api/src/app/workflow/state_machine.py",
  "apps/api/src/app/workflow/types.py",
]);

export function inspectArchitectureText(value) {
  return FORBIDDEN_SURFACES.filter(([, pattern]) => pattern.test(value)).map(
    ([name]) => name,
  );
}

export function inspectArchitecturePath(path) {
  return FORBIDDEN_PATHS.has(path.replaceAll("\\", "/"));
}

function trackedFiles(root) {
  return execFileSync("git", ["-c", "core.quotepath=false", "ls-files", "-z"], {
    cwd: root,
    encoding: "utf8",
  })
    .split("\0")
    .filter(Boolean)
    .map((file) => file.replaceAll("\\", "/"));
}

export function runArchitectureDelegacyCheck(root = process.cwd()) {
  const errors = [];
  for (const file of trackedFiles(root)) {
    if (!existsSync(resolve(root, file))) continue;
    if (inspectArchitecturePath(file)) {
      errors.push(`${file}: retired architecture path is tracked`);
      continue;
    }
    if (
      !isRepositoryTextPath(file) ||
      file.startsWith("apps/workspace/upstream/") ||
      isIssueOrPullRequestBodyTemplatePath(file) ||
      [
        "apps/api/uv.lock",
        "pnpm-lock.yaml",
        "scripts/check-architecture-delegacy.mjs",
        "scripts/check-architecture-delegacy.test.mjs",
      ].includes(file)
    ) {
      continue;
    }
    const lines = readFileSync(resolve(root, file), "utf8").split(/\r?\n/u);
    for (const [index, line] of lines.entries()) {
      for (const surface of inspectArchitectureText(line)) {
        errors.push(`${file}: line ${index + 1}: ${surface} is not allowed`);
      }
    }
  }
  return errors;
}

if (import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  const errors = runArchitectureDelegacyCheck();
  if (errors.length > 0) {
    console.error("Architecture de-legacy check failed:\n");
    for (const error of errors) console.error(`- ${error}`);
    process.exit(1);
  }
  console.log("Architecture de-legacy check passed.");
}
