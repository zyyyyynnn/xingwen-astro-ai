import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";
import ts from "typescript";

const root = process.cwd();
const packageLocations = new Map([
  ["@xingwen/site", "apps/site"],
  ["@xingwen/workspace", "apps/workspace"],
  ["@xingwen/design-tokens", "packages/design-tokens"],
  ["@xingwen/ui", "packages/ui"],
  ["@xingwen/domain", "packages/domain"],
  ["@xingwen/contracts", "packages/contracts"],
  ["@xingwen/data-access", "packages/data-access"],
  ["@xingwen/workspace-core", "packages/workspace-core"],
  ["@xingwen/visual-engine", "packages/visual-engine"],
  ["@xingwen/testing", "packages/testing"],
]);

const allowedLocalDependencies = new Map([
  [
    "@xingwen/site",
    new Set([
      "@xingwen/design-tokens",
      "@xingwen/ui",
      "@xingwen/visual-engine",
    ]),
  ],
  [
    "@xingwen/workspace",
    new Set([
      "@xingwen/design-tokens",
      "@xingwen/ui",
      "@xingwen/workspace-core",
      "@xingwen/data-access",
    ]),
  ],
  ["@xingwen/design-tokens", new Set()],
  ["@xingwen/ui", new Set()],
  ["@xingwen/domain", new Set()],
  ["@xingwen/contracts", new Set()],
  ["@xingwen/data-access", new Set(["@xingwen/domain", "@xingwen/contracts"])],
  ["@xingwen/workspace-core", new Set(["@xingwen/domain"])],
  ["@xingwen/visual-engine", new Set()],
  ["@xingwen/testing", new Set()],
]);

const boundaryRuntimeDependencyAllowlist = new Map([
  ["@xingwen/domain", new Set()],
  ["@xingwen/ui", new Set(["react"])],
  // visual-engine is a framework-agnostic boundary: scene model, palette
  // contract, glyph atlas, GLSL source and Poster data only. Three.js is
  // owned by the Site Visual Adapter, never imported here.
  ["@xingwen/visual-engine", new Set()],
]);

const failures = [];
const manifests = new Map();

for (const [expectedName, location] of packageLocations) {
  const manifestPath = resolve(root, location, "package.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  manifests.set(expectedName, { location, manifest });

  if (manifest.name !== expectedName) {
    failures.push(`${location}/package.json must declare ${expectedName}.`);
  }

  const dependencyGroups = [
    manifest.dependencies ?? {},
    manifest.devDependencies ?? {},
    manifest.peerDependencies ?? {},
    manifest.optionalDependencies ?? {},
  ];
  const localDependencies = dependencyGroups
    .flatMap((group) => Object.keys(group))
    .filter((name) => name.startsWith("@xingwen/"));
  const allowed = allowedLocalDependencies.get(expectedName);

  for (const dependency of localDependencies) {
    if (!allowed?.has(dependency)) {
      failures.push(`${expectedName} must not depend on ${dependency}.`);
    }
  }

  const allowedRuntimeDependencies =
    boundaryRuntimeDependencyAllowlist.get(expectedName);
  if (allowedRuntimeDependencies) {
    const runtimeDependencies = [
      manifest.dependencies ?? {},
      manifest.peerDependencies ?? {},
      manifest.optionalDependencies ?? {},
    ]
      .flatMap((group) => Object.keys(group))
      .filter((name) => !name.startsWith("@xingwen/"));

    for (const dependency of runtimeDependencies) {
      if (!allowedRuntimeDependencies.has(dependency)) {
        failures.push(
          `${expectedName} must not add presentation or transport dependency ${dependency}.`,
        );
      }
    }
  }

  if (location.startsWith("packages/")) {
    for (const dependency of localDependencies) {
      if (
        dependency === "@xingwen/site" ||
        dependency === "@xingwen/workspace"
      ) {
        failures.push(
          `${expectedName} must not depend on an application package.`,
        );
      }
    }
  }
}

const listedFiles = execFileSync(
  "git",
  ["ls-files", "-co", "--exclude-standard"],
  {
    cwd: root,
    encoding: "utf8",
  },
)
  .split(/\r?\n/u)
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"));

const lockfiles = listedFiles.filter((file) => file.endsWith("pnpm-lock.yaml"));
if (lockfiles.length !== 1 || lockfiles[0] !== "pnpm-lock.yaml") {
  failures.push(
    `Expected one root dependency lock; found: ${lockfiles.join(", ") || "none"}.`,
  );
}

const exportedSpecifiers = new Set();
for (const [name, { manifest }] of manifests) {
  const exportsField = manifest.exports ?? {};
  for (const exportKey of Object.keys(exportsField)) {
    exportedSpecifiers.add(
      exportKey === "." ? name : `${name}${exportKey.slice(1)}`,
    );
  }
}

const sourceFiles = listedFiles.filter((file) =>
  /\.(?:astro|mjs|ts|tsx)$/u.test(file),
);
const importPattern = /(?:from\s+|import\s*)["'](@xingwen\/[^"']+)["']/gu;

for (const file of sourceFiles) {
  const content = readFileSync(resolve(root, file), "utf8");
  for (const match of content.matchAll(importPattern)) {
    const specifier = match[1];
    if (specifier && !exportedSpecifiers.has(specifier)) {
      failures.push(`${file} imports non-public package path ${specifier}.`);
    }
  }
}

for (const file of listedFiles.filter((entry) =>
  /(?:^|\/)tsconfig[^/]*\.json$/u.test(entry),
)) {
  const content = readFileSync(resolve(root, file), "utf8");
  const config = JSON.parse(content);
  if (config.compilerOptions?.paths) {
    failures.push(`${file} must not define package-bypassing path aliases.`);
  }
}

const networkAndStorageGlobals = new Set([
  "EventSource",
  "WebSocket",
  "XMLHttpRequest",
  "fetch",
  "indexedDB",
  "localStorage",
  "sessionStorage",
]);
const boundaryRules = new Map([
  [
    "packages/domain",
    {
      description: "the framework-free domain boundary",
      allowedBareImports: new Set(),
      forbiddenIdentifiers: new Set([
        ...networkAndStorageGlobals,
        "document",
        "globalThis",
        "location",
        "navigator",
        "window",
      ]),
      forbidRepositorySymbols: false,
    },
  ],
  [
    "packages/ui",
    {
      description: "the presentation-only UI boundary",
      allowedBareImports: new Set([
        "react",
        "react/jsx-runtime",
        "react/jsx-dev-runtime",
      ]),
      forbiddenIdentifiers: networkAndStorageGlobals,
      forbidRepositorySymbols: true,
    },
  ],
  [
    "packages/visual-engine",
    {
      description: "the framework-agnostic visual boundary",
      allowedBareImports: new Set(),
      forbiddenIdentifiers: networkAndStorageGlobals,
      forbidRepositorySymbols: true,
    },
  ],
]);

const workspacePresentationRule = {
  description: "the Workspace presentation boundary",
  forbiddenBareImports: new Set(["@xingwen/contracts"]),
  forbiddenIdentifiers: new Set([
    "EventSource",
    "WebSocket",
    "XMLHttpRequest",
    "fetch",
  ]),
  forbidApiVersionPaths: true,
  forbidRepositorySymbols: false,
};

function isRelativeImport(specifier) {
  return specifier.startsWith("./") || specifier.startsWith("../");
}

function scriptKindFor(file) {
  if (file.endsWith(".tsx")) return ts.ScriptKind.TSX;
  if (file.endsWith(".mjs")) return ts.ScriptKind.JS;
  return ts.ScriptKind.TS;
}

function collectBoundaryViolations(file, content, rule) {
  const violations = new Set();
  const sourceFile = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKindFor(file),
  );

  function checkModuleSpecifier(specifier) {
    if (
      rule.allowedBareImports &&
      !isRelativeImport(specifier) &&
      !rule.allowedBareImports.has(specifier)
    ) {
      violations.add(`forbidden runtime import ${specifier}`);
    }

    for (const forbidden of rule.forbiddenBareImports ?? []) {
      if (specifier === forbidden || specifier.startsWith(`${forbidden}/`)) {
        violations.add(`forbidden transport import ${specifier}`);
      }
    }
  }

  function visit(node) {
    if (
      (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
      node.moduleSpecifier &&
      ts.isStringLiteral(node.moduleSpecifier)
    ) {
      checkModuleSpecifier(node.moduleSpecifier.text);
    }

    if (
      ts.isCallExpression(node) &&
      (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
        (ts.isIdentifier(node.expression) &&
          node.expression.text === "require"))
    ) {
      const [argument] = node.arguments;
      if (argument && ts.isStringLiteral(argument)) {
        checkModuleSpecifier(argument.text);
      } else {
        violations.add("non-static runtime import");
      }
    }

    if (ts.isIdentifier(node) && rule.forbiddenIdentifiers.has(node.text)) {
      violations.add(`forbidden browser or transport global ${node.text}`);
    }

    if (
      ts.isElementAccessExpression(node) &&
      node.argumentExpression &&
      ts.isStringLiteral(node.argumentExpression) &&
      rule.forbiddenIdentifiers.has(node.argumentExpression.text)
    ) {
      violations.add(
        `forbidden browser or transport member ${node.argumentExpression.text}`,
      );
    }

    if (
      rule.forbidRepositorySymbols &&
      ts.isIdentifier(node) &&
      /repository/iu.test(node.text)
    ) {
      violations.add(`forbidden Repository symbol ${node.text}`);
    }

    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  if (rule.forbidApiVersionPaths && /\/api\/v[12](?=\/|["'`])/u.test(content)) {
    violations.add("hardcoded API version path");
  }
  return [...violations].map(
    (violation) => `${file} violates ${rule.description}: ${violation}.`,
  );
}

for (const [location, rule] of boundaryRules) {
  for (const file of sourceFiles.filter((entry) =>
    entry.startsWith(`${location}/src/`),
  )) {
    failures.push(
      ...collectBoundaryViolations(
        file,
        readFileSync(resolve(root, file), "utf8"),
        rule,
      ),
    );
  }
}

for (const file of sourceFiles.filter(
  (entry) =>
    entry.startsWith("apps/workspace/src/pages/") ||
    entry.startsWith("apps/workspace/src/components/"),
)) {
  failures.push(
    ...collectBoundaryViolations(
      file,
      readFileSync(resolve(root, file), "utf8"),
      workspacePresentationRule,
    ),
  );
}

const boundaryRuleFixtures = [
  ["packages/domain", 'import http from "node:http";'],
  ["packages/domain", 'localStorage.getItem("token");'],
  ["packages/ui", 'import axios from "axios";'],
  ["packages/visual-engine", 'globalThis["fetch"]("/api");'],
  ["packages/visual-engine", 'import * as THREE from "three";'],
];

for (const [location, content] of boundaryRuleFixtures) {
  const rule = boundaryRules.get(location);
  if (
    !rule ||
    collectBoundaryViolations("boundary-fixture.ts", content, rule).length === 0
  ) {
    failures.push(`Architecture boundary self-test failed for ${location}.`);
  }
}

const workspacePresentationRuleFixtures = [
  'fetch("/api/v2/research/projects");',
  "new XMLHttpRequest();",
  'new EventSource("/events");',
  'new WebSocket("wss://example.test/events");',
  'import schema from "@xingwen/contracts";',
  'const apiPath = "/api/v1/tasks";',
];

for (const content of workspacePresentationRuleFixtures) {
  if (
    collectBoundaryViolations(
      "workspace-presentation-fixture.tsx",
      content,
      workspacePresentationRule,
    ).length === 0
  ) {
    failures.push(
      "Architecture boundary self-test failed for Workspace pages.",
    );
  }
}

if (failures.length > 0) {
  console.error("Frontend architecture check failed:\n");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Frontend architecture check passed.");
