import assert from 'node:assert/strict';
import test from 'node:test';
import { validatePrTitle, validateCommitSubject } from './check-title-governance.mjs';

test('validatePrTitle accepts valid Conventional Commit titles', () => {
  assert.equal(validatePrTitle('feat(a-21): freeze OpenHands upstream agent source baseline').valid, true);
  assert.equal(validatePrTitle('fix(backend): resolve Research Input URL ingestion race condition').valid, true);
  assert.equal(validatePrTitle('docs(repo): consolidate active project specifications').valid, true);
  assert.equal(validatePrTitle('ci(repo): enforce pull request and commit title grammar').valid, true);
});

test('validatePrTitle rejects legacy prefixes, PR backlinks, and invalid scopes', () => {
  assert.equal(validatePrTitle('[A] A-21 Freeze OpenHands upstream Agent source baseline').valid, false);
  assert.equal(validatePrTitle('feat(a21): freeze OpenHands upstream agent source baseline').valid, false);
  assert.equal(validatePrTitle('feat(a-21): freeze OpenHands upstream agent source baseline (#197)').valid, false);
  assert.equal(validatePrTitle('WIP: feat(repo): initial draft').valid, false);
  assert.equal(validatePrTitle('feat(invalid_scope): test').valid, false);
});

test('validateCommitSubject accepts valid commit subjects and PR integration backlinks', () => {
  assert.equal(validateCommitSubject('feat(a-21): freeze OpenHands upstream agent source baseline').valid, true);
  assert.equal(validateCommitSubject('feat(b-19): implement research input attachment and URL ingestion contract (#187)').valid, true);
  assert.equal(validateCommitSubject('chore(sync): merge main into d-01 paper pipeline branch').valid, true);
});

test('validateCommitSubject rejects forbidden patterns and trailing periods', () => {
  assert.equal(validateCommitSubject('feat(a-21): freeze OpenHands upstream agent source baseline.').valid, false);
  assert.equal(validateCommitSubject('feat(a-21): freeze OpenHands (#187) upstream agent').valid, false);
  assert.equal(validateCommitSubject('Merge pull request #166 from zyyyyynnn/feat/b-08-claim-relation-trace-api').valid, false);
});
