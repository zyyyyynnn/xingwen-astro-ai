import assert from "node:assert/strict";
import test from "node:test";
import {
  validateCommitSubject,
  validatePrTitle,
} from "./check-title-governance.mjs";

test("validatePrTitle accepts the governed grammar", () => {
  for (const title of [
    "feat(a-21): freeze OpenHands upstream agent source baseline",
    "fix(backend): resolve Research Input URL ingestion race condition",
    "docs(repo): consolidate active project specifications",
    "ci(repo): enforce pull request and commit title grammar",
    "refactor(a-20)!: retire legacy workspace product layer",
  ]) {
    assert.equal(validatePrTitle(title).valid, true, title);
  }
});

test("validatePrTitle rejects legacy or ungoverned metadata", () => {
  for (const title of [
    "[A] A-21 Freeze OpenHands upstream Agent source baseline",
    "feat(a21): freeze OpenHands upstream agent source baseline",
    "fix(C-01): align manifest metadata contract",
    "feat(a-21): freeze OpenHands upstream agent source baseline (#197)",
    "feat(a-21): freeze OpenHands upstream agent source baseline #197",
    "feat(a-21): freeze OpenHands upstream agent source baseline (A-21)",
    "feat(repo): finish governance PR-1/5",
    "feat(repo): WIP title governance",
    "feat(repo): 修复标题治理",
    "feat(repo): remove E:\\xingwen-astro-ai\\scratch.txt",
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
      "feat(b-19): implement research input attachment and URL ingestion contract (#187)",
    ).valid,
    true,
  );
  assert.equal(
    validateCommitSubject(
      "chore(sync): merge main into d-01 paper pipeline branch",
    ).valid,
    true,
  );
});

test("validateCommitSubject rejects references in PR branch commits", () => {
  assert.equal(
    validateCommitSubject(
      "feat(b-19): implement research input attachment contract (#187)",
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
    "feat(a-21): freeze OpenHands (#187) upstream agent source",
    "feat(a-21): freeze OpenHands source (#187) (#198)",
    "fix(b-08): close publication review [agent-fixed-pr166]",
    "fix(repo): CI PASS after title repair",
    "fix(repo): resolve Review 4882344932 blocker",
    "Merge pull request #166 from zyyyyynnn/feat/b-08-claim-relation-trace-api",
    "feat(a-21): freeze OpenHands upstream agent source baseline.",
  ]) {
    assert.equal(validateCommitSubject(title).valid, false, title);
  }
});
