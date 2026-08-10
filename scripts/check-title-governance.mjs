import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import {
  containsPhaseIdentifier,
  containsTaskCode,
} from "./governance-identifiers.mjs";

const ALLOWED_TYPES = new Set([
  "feat",
  "fix",
  "refactor",
  "docs",
  "test",
  "ci",
  "build",
  "chore",
  "perf",
  "style",
  "revert",
]);

const ALLOWED_SYSTEM_SCOPES = new Set([
  "repo",
  "frontend",
  "backend",
  "contracts",
  "data",
  "security",
  "docs",
  "ci",
  "deps",
  "release",
  "sync",
]);

const TITLE_REGEX = /^([a-z]+)\(([^()\s]+)\)(!)?: (.+)$/u;
const FULL_SHA_REGEX = /^[0-9a-f]{40}$/u;
const REFERENCE_REGEX = /#\d+/gu;
const ISSUE_PR_ID_REGEX = /\b(?:Issue|PR)\s*#?\d+\b/iu;
const TRAILING_PR_BACKLINK_REGEX = /\s\(#\d+\)$/u;
const COMMIT_SHA_TOKEN_REGEX = /\b[0-9a-f]{7,40}\b/giu;
const CJK_REGEX =
  /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;
const CONTROL_CHARACTER_REGEX = /[\u0000-\u001f\u007f]/u;
const LOCAL_PATH_REGEX =
  /(?:\b[A-Za-z]:[\\/]|(?:^|\s)\/(?:home|Users|mnt|tmp)\/)/u;
const DATE_REGEX = /\b\d{4}-\d{2}-\d{2}\b/u;
const AGENT_MARKER_REGEX = /\[agent-fixed-[^\]]+\]/iu;
const PROCESS_STATUS_REGEX = /\b(?:WIP|Draft|Ready|Merged|PASS|BLOCKED)\b/iu;
const REVIEW_ID_REGEX = /\breview(?:\s+id)?\s*#?\d+\b/iu;
const CI_STATUS_REGEX =
  /\bCI\s*[:=-]?\s*(?:PASS|FAIL(?:ED)?|GREEN|RED|SUCCESS)\b/iu;

function containsCommitSha(summary) {
  for (const match of summary.matchAll(COMMIT_SHA_TOKEN_REGEX)) {
    const token = match[0];
    const hasDigit = /\d/u.test(token);
    const hasHexLetter = /[a-f]/iu.test(token);
    if (token.length === 40 || (hasDigit && hasHexLetter)) {
      return true;
    }
  }
  return false;
}

function addSummaryPolicyErrors(summary, errors) {
  if (CJK_REGEX.test(summary)) {
    errors.push("Summary must use English and must not contain CJK text");
  }
  if (LOCAL_PATH_REGEX.test(summary)) {
    errors.push("Summary must not contain a local absolute path");
  }
  if (containsCommitSha(summary)) {
    errors.push("Summary must not contain a commit SHA");
  }
  if (DATE_REGEX.test(summary)) {
    errors.push("Summary must not contain an execution date");
  }
  if (ISSUE_PR_ID_REGEX.test(summary)) {
    errors.push("Summary must not contain an Issue or PR identifier");
  }
  if (containsTaskCode(summary)) {
    errors.push("Summary must not contain a task code");
  }
  if (containsPhaseIdentifier(summary)) {
    errors.push("Summary must not contain a work-stage identifier");
  }
  if (AGENT_MARKER_REGEX.test(summary)) {
    errors.push("Summary must not contain an agent/process marker");
  }
  if (PROCESS_STATUS_REGEX.test(summary)) {
    errors.push("Summary must not contain workflow status markers");
  }
  if (REVIEW_ID_REGEX.test(summary)) {
    errors.push("Summary must not contain a Review identifier");
  }
  if (CI_STATUS_REGEX.test(summary)) {
    errors.push("Summary must not contain CI execution status");
  }
  if (summary.endsWith(".")) {
    errors.push("Summary must not end with a period");
  }
}

export function validateTitleGrammar(
  title,
  { isPr = false, allowPrBacklink = true } = {},
) {
  const errors = [];

  if (!title || typeof title !== "string") {
    errors.push("Title must be a non-empty string");
    return { valid: false, errors };
  }

  if (title !== title.trim()) {
    errors.push("Title must not have leading or trailing whitespace");
  }
  if (CONTROL_CHARACTER_REGEX.test(title)) {
    errors.push(
      "Title must be a single line and contain no control characters",
    );
  }

  const candidate = title.trim();
  const match = TITLE_REGEX.exec(candidate);
  if (!match) {
    errors.push("Title must conform exactly to: <type>(<scope>)[!]: <summary>");
    return { valid: false, errors };
  }

  const [, type, scope, , rawSummary] = match;

  if (!ALLOWED_TYPES.has(type)) {
    errors.push(
      `Type '${type}' is not allowed. Allowed types: ${Array.from(ALLOWED_TYPES).join(", ")}`,
    );
  }

  const isSystemScope = ALLOWED_SYSTEM_SCOPES.has(scope);
  if (!isSystemScope) {
    errors.push(
      `Scope '${scope}' is invalid. Use one of: ${Array.from(ALLOWED_SYSTEM_SCOPES).join(", ")}`,
    );
  }

  const references = rawSummary.match(REFERENCE_REGEX) ?? [];
  const trailingBacklink = TRAILING_PR_BACKLINK_REGEX.exec(rawSummary)?.[0];

  if (isPr) {
    if (references.length > 0) {
      errors.push("PR title must not contain an Issue or PR number");
    }
  } else if (references.length > 0) {
    if (!allowPrBacklink) {
      errors.push(
        "PR branch commit subject must not contain an Issue or PR number",
      );
    } else if (references.length !== 1 || trailingBacklink === undefined) {
      errors.push(
        "Commit subject may contain only one trailing PR backlink formatted as (#123)",
      );
    }
  }

  const cleanSummary =
    !isPr && allowPrBacklink && trailingBacklink !== undefined
      ? rawSummary.slice(0, -trailingBacklink.length).trimEnd()
      : rawSummary;

  if (!cleanSummary) {
    errors.push("Summary section cannot be empty");
  } else {
    addSummaryPolicyErrors(cleanSummary, errors);
  }

  return {
    valid: errors.length === 0,
    errors,
    parsed: { type, scope, summary: cleanSummary },
  };
}

export function validatePrTitle(title) {
  return validateTitleGrammar(title, { isPr: true, allowPrBacklink: false });
}

export function validateCommitSubject(
  subject,
  { allowPrBacklink = true } = {},
) {
  return validateTitleGrammar(subject, { allowPrBacklink });
}

function requireFullSha(name, value) {
  if (!value || !FULL_SHA_REGEX.test(value)) {
    throw new Error(`${name} must be a 40-character lowercase hexadecimal SHA`);
  }
  return value;
}

function assertCommitAvailable(sha) {
  try {
    execFileSync("git", ["cat-file", "-e", `${sha}^{commit}`], {
      stdio: "ignore",
    });
  } catch {
    throw new Error(
      `Commit ${sha} is not available in the checkout. Configure actions/checkout with fetch-depth: 0.`,
    );
  }
}

function readCommitSubject(sha, envName) {
  const commit = requireFullSha(envName, sha);
  assertCommitAvailable(commit);
  return execFileSync("git", ["show", "-s", "--format=%s", commit], {
    encoding: "utf8",
  }).trimEnd();
}

export function readCommitSubjects(baseSha, headSha) {
  const base = requireFullSha("BASE_SHA", baseSha);
  const head = requireFullSha("HEAD_SHA", headSha);
  assertCommitAvailable(base);
  assertCommitAvailable(head);

  const output = execFileSync(
    "git",
    ["log", `${base}..${head}`, "--format=%H%x09%s"],
    {
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    },
  );

  return output
    .split(/\r?\n/u)
    .filter(Boolean)
    .map((line) => {
      const separator = line.indexOf("\t");
      if (separator <= 0) {
        throw new Error(`Unexpected git log record: ${line}`);
      }
      return {
        sha: line.slice(0, separator),
        subject: line.slice(separator + 1),
      };
    });
}

function runIntegrationMode(integrationSha) {
  try {
    const subject = readCommitSubject(integrationSha, "INTEGRATION_SHA");
    console.log(`Checking integration commit subject: "${subject}"`);
    const result = validateCommitSubject(subject, { allowPrBacklink: true });
    if (!result.valid) {
      console.error(
        `Integration commit subject error: ${result.errors.join("; ")}`,
      );
      return 1;
    }
    console.log("Integration commit subject PASS");
    return 0;
  } catch (error) {
    console.error(`Integration commit subject check failed: ${error.message}`);
    return 1;
  }
}

function runPrMode(prTitle, baseSha, headSha) {
  let failed = false;

  console.log(`Checking PR title: "${prTitle}"`);
  const prResult = validatePrTitle(prTitle);
  if (!prResult.valid) {
    console.error(`PR title error: ${prResult.errors.join("; ")}`);
    failed = true;
  } else {
    console.log("PR title PASS");
  }

  try {
    const commits = readCommitSubjects(baseSha, headSha);
    console.log(`Checking ${commits.length} PR branch commit subject(s)`);
    for (const { sha, subject } of commits) {
      const result = validateCommitSubject(subject, {
        allowPrBacklink: false,
      });
      if (!result.valid) {
        console.error(
          `Commit ${sha.slice(0, 8)} subject error: "${subject}" -> ${result.errors.join("; ")}`,
        );
        failed = true;
      }
    }
    if (!failed) {
      console.log("PR branch commit subjects PASS");
    }
  } catch (error) {
    console.error(`Commit subject check failed: ${error.message}`);
    failed = true;
  }

  return failed ? 1 : 0;
}

export function validateIssueTemplate(name, content) {
  const errors = [];
  if (!content || typeof content !== "string") {
    errors.push("Template content must be a non-empty string");
    return { valid: false, errors };
  }
  // Forbidden dynamic-state mirrors that create a second source of truth.
  const forbiddenSection = [
    "## Completed baseline",
    "## Planned handoff",
    "## 依赖",
    "## 边界与依赖",
    "## 状态",
    "## 当前 DAG",
    "## 当前主线",
    "## 当前批准",
  ];
  for (const sec of forbiddenSection) {
    if (content.includes(sec)) {
      errors.push(`Template must not contain the section "${sec}" (GitHub native metadata is the sole state source)`);
    }
  }
  // Forbidden child-task checklist that duplicates native Sub-issue relation.
  if (/-\s*\[\s*\]\s*#/.test(content)) {
    errors.push("Template must not contain a `- [ ] #` sub-task checklist (use GitHub native Sub-issue)");
  }
  // NOTE: [A/B/C/D/X]-NN responsibility taxonomy is an approved stable identifier
  // in GitHub Issue titles/bodies and must NOT be flagged here. Only live-state
  // mirrors (sections / checklists / "blocked-by #" guidance) are forbidden.
  // Forbidden guidance that tells users to copy live metadata into the body.
  const forbiddenGuidance = [
    "blocked-by #",
    "经 #",
    "已 consolidated",
    "已 merged",
    "当前 main 尚未",
  ];
  for (const g of forbiddenGuidance) {
    if (content.includes(g)) {
      errors.push(`Template must not instruct users to mirror live state ("${g}")`);
    }
  }
  return { valid: errors.length === 0, errors, name };
}

function runTemplateMode() {
  const dir = process.env.TEMPLATE_DIR;
  if (!dir) {
    console.error("Template governance check requires TEMPLATE_DIR");
    return 1;
  }
  const fs = require("node:fs");
  const path = require("node:path");
  const files = fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".md"));
  let failed = false;
  for (const f of files) {
    const content = fs.readFileSync(path.join(dir, f), "utf8");
    const result = validateIssueTemplate(f, content);
    if (!result.valid) {
      console.error(`Template ${f} error: ${result.errors.join("; ")}`);
      failed = true;
    } else {
      console.log(`Template ${f} PASS`);
    }
  }
  return failed ? 1 : 0;
}

function runCli() {
  const prTitle = process.env.PR_TITLE;
  const baseSha = process.env.BASE_SHA;
  const headSha = process.env.HEAD_SHA;
  const integrationSha = process.env.INTEGRATION_SHA;
  const templateDir = process.env.TEMPLATE_DIR;

  if (templateDir && !prTitle && !baseSha && !headSha && !integrationSha) {
    return runTemplateMode();
  }

  const hasPrContext = Boolean(prTitle || baseSha || headSha);

  if (integrationSha && hasPrContext) {
    console.error(
      "Title governance check accepts either PR context or INTEGRATION_SHA, not both",
    );
    return 1;
  }

  if (integrationSha) {
    return runIntegrationMode(integrationSha);
  }

  if (!prTitle || !baseSha || !headSha) {
    console.error(
      "PR title governance check requires PR_TITLE, BASE_SHA, and HEAD_SHA",
    );
    return 1;
  }

  return runPrMode(prTitle, baseSha, headSha);
}

const isMainModule =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));

if (isMainModule) {
  process.exitCode = runCli();
}
