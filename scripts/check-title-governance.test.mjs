import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  validateCommitSubject,
  validateIssueTemplate,
  validatePrTitle,
} from "./check-title-governance.mjs";

const forbiddenTaskScope = ["a", "21"].join("-");
const compactTaskScope = ["a", "21"].join("");
const forbiddenBackendScope = ["b", "08"].join("-");
const forbiddenTaskCode = ["A", "1"].join("-");
const forbiddenPhase = ["Phase", "II"].join(" ");
const forbiddenMilestone = ["Mile", "stone"].join("");
const forbiddenBatch = ["PR", "1/5"].join("-");
const forbiddenWip = ["W", "IP"].join("");
const messierOne = ["M", "1"].join("");

test("validatePrTitle accepts the governed grammar", () => {
  for (const title of [
    "feat(frontend): freeze OpenHands upstream agent source baseline",
    "fix(backend): resolve Research Input URL ingestion race condition",
    "feat(api): compose the complete transport contract",
    "fix(api): align runtime operation parity",
    "test(api): cover contract composition",
    "docs(repo): consolidate active project specifications",
    "ci(repo): enforce pull request and commit title grammar",
    "refactor(frontend)!: consolidate workspace product layer",
    "fix(repo): remove defaced fixture",
    `docs(repo): document Messier ${messierOne} Cygnus X-1 and carbon isotope C-14`,
  ]) {
    assert.equal(validatePrTitle(title).valid, true, title);
  }
});

test("validatePrTitle rejects task-like and ungoverned api scopes", () => {
  const versionedApiScope = ["api-v", "1"].join("");
  const taskLikeScopes = [["a", "24"].join("-"), ["b", "23"].join("-")];
  for (const scope of [
    ...taskLikeScopes,
    versionedApiScope,
    "random-api",
    "backend_api",
  ]) {
    assert.equal(
      validatePrTitle(`fix(${scope}): align transport contract`).valid,
      false,
      scope,
    );
  }
});

test("validateIssueTemplate accepts current repository templates", async () => {
  const { readFile } = await import("node:fs/promises");
  for (const name of ["bug.md", "chore.md", "feature.md", "gate.md"]) {
    const content = await readFile(
      join(".github", "ISSUE_TEMPLATE", name),
      "utf8",
    );
    assert.deepEqual(validateIssueTemplate(name, content).errors, [], name);
  }
});

test("validateIssueTemplate rejects native metadata mirrors", () => {
  const forbidden = [
    ["## 状", "态"].join(""),
    ["## Completed", " baseline"].join(""),
    ["## Planned", " handoff"].join(""),
    ["## 依", "赖"].join(""),
    ["## 边界与", "依赖"].join(""),
    ["blocked", "-by #123"].join(""),
    "- [ ] #123",
    ["## 当前 ", "DAG"].join(""),
    ["已 ", "merged"].join(""),
  ];
  for (const marker of forbidden) {
    assert.equal(
      validateIssueTemplate("invalid.md", marker).valid,
      false,
      marker,
    );
  }
  assert.equal(
    validateIssueTemplate("valid.md", "## Acceptance\n\n- [ ] test passes")
      .valid,
    true,
  );
  assert.equal(
    validateIssueTemplate("valid.md", "running failed partial completed").valid,
    true,
  );
});

test("template CLI validates an explicit template directory", () => {
  const directory = mkdtempSync(join(tmpdir(), "template-governance-"));
  try {
    writeFileSync(
      join(directory, "valid.md"),
      "## Acceptance\n\n- [ ] test passes\n",
      "utf8",
    );
    const result = spawnSync(
      process.execPath,
      ["scripts/check-title-governance.mjs"],
      {
        cwd: process.cwd(),
        env: { ...process.env, TEMPLATE_DIR: directory },
        encoding: "utf8",
      },
    );
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.match(result.stdout, /Template valid\.md PASS/u);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("validatePrTitle rejects forbidden or ungoverned metadata", () => {
  for (const title of [
    "[A] OpenHands Upstream Baseline Freeze OpenHands upstream Agent source baseline",
    "feat(upstream_baseline): freeze OpenHands upstream agent source baseline",
    `feat(${compactTaskScope}): freeze OpenHands upstream agent source baseline`,
    "fix(Case and Field Manifest): align manifest metadata contract",
    `feat(${forbiddenTaskScope}): freeze OpenHands upstream agent source baseline (#197)`,
    `feat(${forbiddenTaskScope}): freeze OpenHands upstream agent source baseline #197`,
    `feat(${forbiddenTaskScope}): resolve PR 197 title governance`,
    `feat(${forbiddenTaskScope}): resolve Issue 190 title governance`,
    `feat(${forbiddenTaskScope}): freeze OpenHands upstream agent source baseline (OpenHands Upstream Baseline)`,
    `feat(repo): finish governance ${forbiddenBatch}`,
    `docs(repo): update ${forbiddenTaskCode} authority`,
    `docs(repo): publish ${forbiddenPhase} authority`,
    `docs(repo): assign governance ${forbiddenMilestone}`,
    `feat(repo): ${forbiddenWip} title governance`,
    "feat(repo): 修复标题治理",
    "feat(repo): remove E:\\xingwen-astro-ai\\scratch.txt",
    "feat(repo): remove /tmp/title-governance.log",
    "feat(repo): align title governance at a9b8f7f",
    "feat(repo): align title governance on 2026-08-08",
    " feat(repo): leading whitespace",
    "feat(repo):missing separator space",
    "feat(invalid_scope): test title governance",
  ]) {
    assert.equal(validatePrTitle(title).valid, false, title);
  }
});

test("validateCommitSubject allows a single integration backlink when requested", () => {
  assert.equal(
    validateCommitSubject(
      "feat(backend): implement research input attachment and URL ingestion contract (#187)",
    ).valid,
    true,
  );
  assert.equal(
    validateCommitSubject("chore(sync): merge main into paper pipeline branch")
      .valid,
    true,
  );
});

test("validateCommitSubject rejects references in PR branch commits", () => {
  assert.equal(
    validateCommitSubject(
      "feat(backend): implement research input attachment contract (#187)",
      { allowPrBacklink: false },
    ).valid,
    false,
  );
  assert.equal(
    validateCommitSubject("fix(repo): close #187 review gap", {
      allowPrBacklink: false,
    }).valid,
    false,
  );
});

test("validateCommitSubject rejects malformed backlinks and process noise", () => {
  for (const title of [
    `feat(${forbiddenTaskScope}): freeze OpenHands (#187) upstream agent source`,
    `feat(${forbiddenTaskScope}): freeze OpenHands source (#187) (#198)`,
    "fix(repo): resolve PR 198 title gate",
    "fix(repo): resolve Issue 190 title gate",
    `fix(${forbiddenBackendScope}): close publication review [agent-fixed-pr166]`,
    "fix(repo): CI PASS after title repair",
    "fix(repo): resolve Review 4882344932 blocker",
    `Merge pull request #166 from zyyyyynnn/feat/${forbiddenBackendScope}-claim-relation-trace-api`,
    `feat(${forbiddenTaskScope}): freeze OpenHands upstream agent source baseline.`,
  ]) {
    assert.equal(validateCommitSubject(title).valid, false, title);
  }
});
