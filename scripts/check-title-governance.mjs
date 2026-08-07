import { execSync } from 'node:child_process';

const ALLOWED_TYPES = new Set([
  'feat', 'fix', 'refactor', 'docs', 'test', 'ci', 'build', 'chore', 'perf', 'style', 'revert'
]);

const ALLOWED_SYSTEM_SCOPES = new Set([
  'repo', 'frontend', 'backend', 'contracts', 'data', 'security', 'docs', 'ci', 'deps', 'release', 'sync'
]);

const TASK_SCOPE_REGEX = /^[a-dx]-[0-9]{2,3}$/;
const LEGACY_PREFIX_REGEX = /^\[[A-ZXa-zx]\]|^\[agent-fixed-[^\]]+\]|^\bWIP\b|^\bDraft\b/i;

export function validateTitleGrammar(title, { isPr = false } = {}) {
  const errors = [];

  if (!title || typeof title !== 'string') {
    errors.push('Title must be a non-empty string');
    return { valid: false, errors };
  }

  const trimmed = title.trim();
  if (trimmed.includes('\n') || trimmed.includes('\r')) {
    errors.push('Title must be a single line');
  }

  if (LEGACY_PREFIX_REGEX.test(trimmed)) {
    errors.push('Title contains forbidden legacy prefix (e.g. [A], [B], WIP, Draft)');
  }

  const match = /^([a-z]+)\(([^)]+)\)(!)?:\s*(.+)$/.exec(trimmed);
  if (!match) {
    errors.push('Title must conform to Conventional Commit format: <type>(<scope>): <summary>');
    return { valid: false, errors };
  }

  const [, type, scope, , summary] = match;

  if (!ALLOWED_TYPES.has(type)) {
    errors.push(`Type '${type}' is not allowed. Allowed types: ${Array.from(ALLOWED_TYPES).join(', ')}`);
  }

  const isTaskScope = TASK_SCOPE_REGEX.test(scope);
  const isSystemScope = ALLOWED_SYSTEM_SCOPES.has(scope);
  if (!isTaskScope && !isSystemScope) {
    errors.push(`Scope '${scope}' is invalid. Must match ^[a-dx]-[0-9]{2,3}$ or be one of: ${Array.from(ALLOWED_SYSTEM_SCOPES).join(', ')}`);
  }

  const prSuffixMatches = summary.match(/\(#\d+\)/g);
  if (isPr) {
    if (prSuffixMatches) {
      errors.push('PR title must not contain PR backlink suffix (#123)');
    }
  } else {
    if (prSuffixMatches && prSuffixMatches.length > 1) {
      errors.push('Commit subject must not contain multiple PR backlink suffixes');
    } else if (prSuffixMatches && prSuffixMatches.length === 1) {
      if (!summary.endsWith(prSuffixMatches[0])) {
        errors.push('PR backlink suffix (#123) must be at the end of commit subject');
      }
    }
  }

  const cleanSummary = summary.replace(/\s*\(#\d+\)$/, '').trim();
  if (!cleanSummary) {
    errors.push('Summary section cannot be empty');
  }

  if (cleanSummary.endsWith('.')) {
    errors.push('Summary must not end with a period');
  }

  return {
    valid: errors.length === 0,
    errors,
    parsed: { type, scope, summary: cleanSummary }
  };
}

export function validatePrTitle(title) {
  return validateTitleGrammar(title, { isPr: true });
}

export function validateCommitSubject(subject) {
  return validateTitleGrammar(subject, { isPr: false });
}

if (process.argv[1] && process.argv[1].endsWith('check-title-governance.mjs')) {
  const prTitle = process.env.PR_TITLE;
  const baseSha = process.env.BASE_SHA;
  const headSha = process.env.HEAD_SHA;

  let failed = false;

  if (prTitle) {
    console.log(`Checking PR Title: "${prTitle}"`);
    const res = validatePrTitle(prTitle);
    if (!res.valid) {
      console.error(`❌ PR Title Error: ${res.errors.join('; ')}`);
      failed = true;
    } else {
      console.log('✅ PR Title PASS');
    }
  }

  if (baseSha && headSha) {
    console.log(`Checking commit subjects between ${baseSha}...${headSha}`);
    try {
      const output = execSync(`git log ${baseSha}..${headSha} --format="%H%x09%s"`, { encoding: 'utf-8' });
      const lines = output.trim().split('\n').filter(Boolean);
      for (const line of lines) {
        const [sha, subject] = line.split('\t');
        const res = validateCommitSubject(subject);
        if (!res.valid) {
          console.error(`❌ Commit ${sha.substring(0, 8)} Subject Error: "${subject}" -> ${res.errors.join('; ')}`);
          failed = true;
        }
      }
      if (!failed) {
        console.log(`✅ Checked ${lines.length} commit subjects: ALL PASS`);
      }
    } catch (err) {
      console.error('Failed to retrieve commit list:', err.message);
      failed = true;
    }
  }

  if (failed) {
    process.exit(1);
  }
}
