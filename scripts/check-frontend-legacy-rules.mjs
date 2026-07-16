import { readFileSync } from "node:fs";

const ruleSource = JSON.parse(
  readFileSync(
    new URL("./frontend-retirement-rules.json", import.meta.url),
    "utf8",
  ),
);

export const frameworkName = String.fromCharCode(
  ...ruleSource.frameworkCodePoints,
);
const expandRuleParts = (parts) =>
  parts.join("").replaceAll("{framework}", frameworkName);
const retiredApp = ruleSource.retiredAppParts.join("/");

const dependencyFields = ruleSource.dependencyFields;
const retiredExactPackages = new Set(
  ruleSource.exactPackageParts
    .map(expandRuleParts)
    .map((name) => name.toLowerCase()),
);
const retiredPackagePrefixes =
  ruleSource.packagePrefixParts.map(expandRuleParts);
const retiredTextTerms = [
  frameworkName,
  retiredApp,
  ...ruleSource.retiredTextCodePoints.map((codes) =>
    String.fromCharCode(...codes),
  ),
  ...ruleSource.retiredTextParts.map((parts) => parts.join("")),
];

export function isRetiredPackageName(name) {
  const normalized = name.toLowerCase();
  return (
    retiredExactPackages.has(normalized) ||
    retiredPackagePrefixes.some((prefix) => normalized.startsWith(prefix))
  );
}

export function findRetiredManifestDependencies(manifest) {
  const failures = [];
  for (const field of dependencyFields) {
    for (const name of Object.keys(manifest[field] ?? {})) {
      if (isRetiredPackageName(name)) {
        failures.push(`${field}.${name}`);
      }
    }
  }
  return failures;
}

export function findRetiredTextTerms(content) {
  const normalized = content.toLowerCase();
  return retiredTextTerms.filter((term) =>
    normalized.includes(term.toLowerCase()),
  );
}

export function isRetiredPath(file) {
  const normalized = file.replaceAll("\\", "/").toLowerCase();
  return (
    normalized === retiredApp ||
    normalized.startsWith(`${retiredApp}/`) ||
    normalized.endsWith(`.${frameworkName}`)
  );
}

function packageNameFromLockKey(key) {
  const unquoted = key.replace(/^['"]|['"]$/gu, "").replace(/^\//u, "");
  const separator = unquoted.startsWith("@")
    ? unquoted.indexOf("@", unquoted.indexOf("/") + 1)
    : unquoted.indexOf("@");
  return separator > 0 ? unquoted.slice(0, separator) : unquoted;
}

export function findRetiredLockfileDependencies(content) {
  const failures = new Set();
  let inResolutionSection = false;

  for (const line of content.split(/\r?\n/u)) {
    const topLevel = /^([a-z][a-zA-Z]*):\s*$/u.exec(line);
    if (topLevel) {
      inResolutionSection = ["packages", "snapshots"].includes(topLevel[1]);
      continue;
    }
    if (!inResolutionSection) {
      continue;
    }

    const entry = /^  (.+):\s*$/u.exec(line);
    if (!entry) {
      continue;
    }
    const name = packageNameFromLockKey(entry[1]);
    if (isRetiredPackageName(name)) {
      failures.add(name);
    }
  }

  return [...failures];
}

export function findRetiredResolvedDependencies(value) {
  const failures = new Set();
  const seen = new Set();

  function visit(node) {
    if (!node || typeof node !== "object" || seen.has(node)) {
      return;
    }
    seen.add(node);

    if (Array.isArray(node)) {
      for (const child of node) {
        visit(child);
      }
      return;
    }

    if (typeof node.name === "string" && isRetiredPackageName(node.name)) {
      failures.add(node.name);
    }
    for (const field of dependencyFields) {
      const dependencies = node[field];
      if (!dependencies || typeof dependencies !== "object") {
        continue;
      }
      for (const [name, dependency] of Object.entries(dependencies)) {
        if (isRetiredPackageName(name)) {
          failures.add(name);
        }
        visit(dependency);
      }
    }
  }

  visit(value);
  return [...failures];
}
