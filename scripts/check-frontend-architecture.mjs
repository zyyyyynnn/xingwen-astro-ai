import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
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
  ["@xingwen/testing", "packages/testing"],
]);

const allowedLocalDependencies = new Map([
  ["@xingwen/site", new Set(["@xingwen/design-tokens", "@xingwen/ui"])],
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
  ["@xingwen/testing", new Set()],
]);

const boundaryRuntimeDependencyAllowlist = new Map([
  ["@xingwen/domain", new Set()],
  ["@xingwen/ui", new Set(["clsx", "lucide-react", "react"])],
]);

const approvedIconPackages = new Set(["lucide-react"]);
const knownIconPackages = new Set([
  "@fortawesome/react-fontawesome",
  "@heroicons/react",
  "@iconify/react",
  "@phosphor-icons/react",
  "@tabler/icons-react",
  "lucide-react",
  "react-icons",
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

  const declaredIconPackages = dependencyGroups
    .flatMap((group) => Object.keys(group))
    .filter((name) => knownIconPackages.has(name));

  for (const dependency of declaredIconPackages) {
    if (
      expectedName !== "@xingwen/ui" ||
      !approvedIconPackages.has(dependency)
    ) {
      failures.push(
        `${expectedName} must consume icons through @xingwen/ui/icons, not ${dependency}.`,
      );
    }
  }

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
  .map((file) => file.replaceAll("\\", "/"))
  .filter((file) => existsSync(resolve(root, file)));

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
const directIconImportPattern =
  /(?:from\s+|import\s*)["']([^"']*(?:lucide-react|react-icons|heroicons|tabler\/icons|fontawesome|iconify|phosphor)[^"']*)["']/gu;

for (const file of sourceFiles) {
  const content = readFileSync(resolve(root, file), "utf8");
  for (const match of content.matchAll(importPattern)) {
    const specifier = match[1];
    if (specifier && !exportedSpecifiers.has(specifier)) {
      failures.push(`${file} imports non-public package path ${specifier}.`);
    }
  }

  for (const match of content.matchAll(directIconImportPattern)) {
    const specifier = match[1];
    if (file !== "packages/ui/src/icons.ts" || specifier !== "lucide-react") {
      failures.push(
        `${file} imports icon package ${specifier} directly; use @xingwen/ui/icons.`,
      );
    }
  }
}

const uiSourceFiles = listedFiles.filter(
  (file) =>
    file.startsWith("packages/ui/src/") && /\.(?:css|ts|tsx)$/u.test(file),
);
const applicationPresentationSourceFiles = listedFiles.filter(
  (file) =>
    (file.startsWith("apps/site/src/") ||
      file.startsWith("apps/workspace/src/") ||
      file.startsWith("apps/workspace/upstream/openhands/src/")) &&
    /\.(?:astro|css|ts|tsx)$/u.test(file) &&
    !/\.(?:test|spec)\.(?:ts|tsx)$/u.test(file),
);
const rawColorPattern = /#[\da-f]{3,8}\b|\b(?:rgb|hsl|oklch)a?\s*\(/iu;

for (const file of [...uiSourceFiles, ...applicationPresentationSourceFiles]) {
  const content = readFileSync(resolve(root, file), "utf8");
  if (rawColorPattern.test(content)) {
    failures.push(`${file} hardcodes a raw color outside design tokens.`);
  }
}

for (const file of uiSourceFiles) {
  const content = readFileSync(resolve(root, file), "utf8");
  for (const forbiddenToken of ["--oh-", "--raw-", "--workspace-"]) {
    if (content.includes(forbiddenToken)) {
      failures.push(
        `${file} uses forbidden ${forbiddenToken} tokens; @xingwen/ui must consume core semantic tokens.`,
      );
    }
  }
}

const uiComponentsConfigPath = resolve(root, "packages/ui/components.json");
if (!existsSync(uiComponentsConfigPath)) {
  failures.push(
    "packages/ui/components.json must govern shadcn source adoption.",
  );
} else {
  const config = JSON.parse(readFileSync(uiComponentsConfigPath, "utf8"));
  if (config.iconLibrary !== "lucide") {
    failures.push(
      "packages/ui/components.json must select Lucide as iconLibrary.",
    );
  }
  if (config.rsc !== false || config.tsx !== true) {
    failures.push(
      "packages/ui/components.json must match the React client TypeScript package.",
    );
  }
  if (config.tailwind?.css !== "src/styles.css") {
    failures.push(
      "packages/ui/components.json must target the existing public UI stylesheet.",
    );
  }

  if (
    !config.aliases?.components ||
    typeof config.aliases.components !== "string"
  ) {
    failures.push(
      "packages/ui/components.json must declare required aliases.components for shadcn schema compliance.",
    );
  }
  if (!config.aliases?.utils || typeof config.aliases.utils !== "string") {
    failures.push(
      "packages/ui/components.json must declare required aliases.utils for shadcn schema compliance.",
    );
  }

  const uiManifest = JSON.parse(
    readFileSync(resolve(root, "packages/ui/package.json"), "utf8"),
  );
  const imports = uiManifest.imports ?? {};
  if (imports["#utils"] === "./src") {
    failures.push(
      "packages/ui/package.json #utils import must point to a specific utility module, not whole ./src.",
    );
  }
  if (
    !imports["#utils"] ||
    !existsSync(resolve(root, "packages/ui", imports["#utils"]))
  ) {
    failures.push(
      `packages/ui #utils import (${imports["#utils"]}) must resolve to an existing local module.`,
    );
  }
  if (!imports["#ui/*"] || !imports["#ui/*"].startsWith("./src/")) {
    failures.push(
      "packages/ui/package.json #ui/* import must use subpath pattern #ui/* -> ./src/*.tsx for component subpath resolution.",
    );
  }
  if (
    !imports["#components/*"] ||
    !imports["#components/*"].startsWith("./src/")
  ) {
    failures.push(
      "packages/ui/package.json #components/* import must use subpath pattern #components/* -> ./src/*.tsx for component resolution.",
    );
  }
}

const componentSourcesPath = resolve(
  root,
  "packages/ui/component-sources.json",
);

function collectPublicUiValueUsages(file, content) {
  const sourceFile = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKindFor(file),
  );
  const importedValuesByLocalName = new Map();

  for (const statement of sourceFile.statements) {
    if (
      !ts.isImportDeclaration(statement) ||
      !ts.isStringLiteral(statement.moduleSpecifier) ||
      statement.moduleSpecifier.text !== "@xingwen/ui" ||
      statement.importClause?.isTypeOnly ||
      !statement.importClause?.namedBindings ||
      !ts.isNamedImports(statement.importClause.namedBindings)
    ) {
      continue;
    }

    for (const element of statement.importClause.namedBindings.elements) {
      if (!element.isTypeOnly) {
        importedValuesByLocalName.set(
          element.name.text,
          element.propertyName?.text ?? element.name.text,
        );
      }
    }
  }

  const usages = new Set();
  function visit(node) {
    if (ts.isImportDeclaration(node)) return;
    if (ts.isIdentifier(node)) {
      const importedValue = importedValuesByLocalName.get(node.text);
      const isJsxTag =
        ((ts.isJsxOpeningElement(node.parent) ||
          ts.isJsxSelfClosingElement(node.parent)) &&
          node.parent.tagName === node) ||
        (ts.isJsxClosingElement(node.parent) && node.parent.tagName === node);
      const isDirectCall =
        ts.isCallExpression(node.parent) && node.parent.expression === node;
      if (importedValue && (isJsxTag || isDirectCall)) {
        usages.add(importedValue);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return usages;
}

const productionApplicationFiles = sourceFiles.filter(
  (file) =>
    file.startsWith("apps/") &&
    !/\.(?:test|spec)\.(?:ts|tsx)$/u.test(file) &&
    !/\.d\.ts$/u.test(file),
);
const productionUiUsagesByFile = new Map(
  productionApplicationFiles.map((file) => [
    file,
    collectPublicUiValueUsages(file, readFileSync(resolve(root, file), "utf8")),
  ]),
);

function collectPublicRuntimeExports(file, content) {
  const sourceFile = ts.createSourceFile(
    file,
    content,
    ts.ScriptTarget.Latest,
    true,
    scriptKindFor(file),
  );
  const runtimeExports = new Set();

  for (const statement of sourceFile.statements) {
    if (ts.isExportDeclaration(statement)) {
      if (statement.isTypeOnly) continue;
      if (statement.exportClause && ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          if (!element.isTypeOnly) {
            runtimeExports.add(element.name.text);
          }
        }
      }
    } else if (
      (ts.isFunctionDeclaration(statement) ||
        ts.isClassDeclaration(statement) ||
        ts.isVariableStatement(statement)) &&
      statement.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
    ) {
      if (ts.isVariableStatement(statement)) {
        for (const decl of statement.declarationList.declarations) {
          if (ts.isIdentifier(decl.name)) {
            runtimeExports.add(decl.name.text);
          }
        }
      } else if (statement.name && ts.isIdentifier(statement.name)) {
        runtimeExports.add(statement.name.text);
      }
    }
  }

  return runtimeExports;
}

const publicUiRuntimeExports = collectPublicRuntimeExports(
  "packages/ui/src/index.ts",
  readFileSync(resolve(root, "packages/ui/src/index.ts"), "utf8"),
);

if (!existsSync(componentSourcesPath)) {
  failures.push(
    "packages/ui/component-sources.json must record shadcn provenance.",
  );
} else {
  const sourceCatalog = JSON.parse(readFileSync(componentSourcesPath, "utf8"));
  const seenNames = new Set();
  const seenPaths = new Set();

  for (const component of sourceCatalog.components ?? []) {
    if (!component.name || typeof component.name !== "string") {
      failures.push(
        "UI component entry in component-sources.json is missing a valid name.",
      );
    } else if (seenNames.has(component.name)) {
      failures.push(
        `UI component name ${component.name} must be unique in component-sources.json.`,
      );
    } else {
      seenNames.add(component.name);
    }

    if (!publicUiRuntimeExports.has(component.name)) {
      failures.push(
        `UI component ${component.name ?? "unknown"} in component-sources.json must be a public runtime value export of @xingwen/ui.`,
      );
    }

    if (!component.local_path || typeof component.local_path !== "string") {
      failures.push(
        `UI component ${component.name ?? "unknown"} is missing local_path.`,
      );
    } else if (seenPaths.has(component.local_path)) {
      failures.push(
        `UI component local_path ${component.local_path} must be unique in component-sources.json.`,
      );
    } else {
      seenPaths.add(component.local_path);
      if (!existsSync(resolve(root, component.local_path))) {
        failures.push(
          `UI component ${component.name ?? "unknown"} local_path ${component.local_path} does not exist.`,
        );
      }
    }

    if (!component.source?.startsWith("@shadcn/")) {
      failures.push(
        `UI component ${component.name ?? "unknown"} has an unapproved shadcn source.`,
      );
    }

    if (
      !component.upstream_repository ||
      typeof component.upstream_repository !== "string"
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare upstream_repository.`,
      );
    }

    if (
      !component.upstream_revision ||
      typeof component.upstream_revision !== "string" ||
      /^(?:main|master|latest)$/i.test(component.upstream_revision)
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare an immutable upstream_revision (not main/master/latest).`,
      );
    }

    if (
      !component.upstream_commit ||
      typeof component.upstream_commit !== "string" ||
      !/^[0-9a-f]{40}$/.test(component.upstream_commit)
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare a valid 40-character hex upstream_commit.`,
      );
    }

    if (
      !component.registry_item ||
      typeof component.registry_item !== "string"
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare registry_item.`,
      );
    }

    if (!component.license || typeof component.license !== "string") {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare a license.`,
      );
    }

    if (
      !component.notice ||
      typeof component.notice !== "string" ||
      !existsSync(resolve(root, component.notice))
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} notice path (${component.notice}) must be a valid existing file.`,
      );
    }

    if (!component.adaptation || typeof component.adaptation !== "string") {
      failures.push(
        `UI component ${component.name ?? "unknown"} must declare adaptation details.`,
      );
    }

    if (
      !Array.isArray(component.production_consumers) ||
      component.production_consumers.length === 0
    ) {
      failures.push(
        `UI component ${component.name ?? "unknown"} must record a production consumer.`,
      );
    }

    for (const consumer of component.production_consumers ?? []) {
      const consumerPath = resolve(root, consumer);
      if (
        !existsSync(consumerPath) ||
        !productionUiUsagesByFile.get(consumer)?.has(component.name)
      ) {
        failures.push(
          `UI component ${component.name ?? "unknown"} consumer ${consumer} must import and use it in production code.`,
        );
      }
    }
  }
}

const productionUiUsages = new Set(
  [...productionUiUsagesByFile.values()].flatMap((usages) => [...usages]),
);

for (const exportedValue of publicUiRuntimeExports) {
  if (!productionUiUsages.has(exportedValue)) {
    failures.push(
      `@xingwen/ui public value ${exportedValue} has no production consumer.`,
    );
  }
}

const publicUiUsageFixtures = [
  ['/* import { Button } from "@xingwen/ui"; <Button /> */', "Button", false],
  ['import { Button } from "@xingwen/ui";', "Button", false],
  [
    'import { Button } from "@xingwen/ui"; type T = typeof Button;',
    "Button",
    false,
  ],
  ['import { Button } from "@xingwen/ui"; <Button />;', "Button", true],
  [
    'import { buttonClassName as styles } from "@xingwen/ui"; styles({});',
    "buttonClassName",
    true,
  ],
];
for (const [content, exportedValue, expected] of publicUiUsageFixtures) {
  const actual = collectPublicUiValueUsages(
    "ui-consumer-fixture.tsx",
    content,
  ).has(exportedValue);
  if (actual !== expected) {
    failures.push(
      `Architecture production-consumer self-test failed for ${exportedValue}.`,
    );
  }
}

if (
  productionApplicationFiles.some((file) =>
    /\.(?:test|spec)\.(?:ts|tsx)$/u.test(file),
  )
) {
  failures.push(
    "Architecture production-consumer self-test included an application test file.",
  );
}

for (const file of sourceFiles.filter(
  (entry) =>
    entry.startsWith("apps/") &&
    !entry.startsWith("apps/workspace/upstream/openhands/src/") &&
    !/\.(?:test|spec)\.(?:ts|tsx)$/u.test(entry),
)) {
  const content = readFileSync(resolve(root, file), "utf8");
  if (/<(?:button|input|select|textarea)\b/u.test(content)) {
    failures.push(
      `${file} declares an app-private form primitive; use @xingwen/ui public exports.`,
    );
  }
  if (/packages\/ui\/src|@xingwen\/ui\/src/u.test(content)) {
    failures.push(`${file} deep-imports private @xingwen/ui source.`);
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
        "clsx",
        "lucide-react",
        "react",
        "react/jsx-runtime",
        "react/jsx-dev-runtime",
      ]),
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
  return (
    specifier.startsWith("./") ||
    specifier.startsWith("../") ||
    specifier.startsWith("#")
  );
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

const workspaceRuntimeCompositionFiles = new Set([
  "apps/workspace/src/main.tsx",
  "apps/workspace/src/runtime.ts",
  "apps/workspace/src/boundaries.ts",
]);

const workspaceProductionFiles = sourceFiles.filter(
  (entry) =>
    entry.startsWith("apps/workspace/src/") &&
    !/\.(?:test|spec)\.(?:ts|tsx)$/u.test(entry) &&
    !/\.d\.ts$/u.test(entry) &&
    !workspaceRuntimeCompositionFiles.has(entry),
);

for (const file of workspaceProductionFiles) {
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
  `fetch("${["/api", ["v", "2"].join(""), "research", "projects"].join("/")}");`,
  "new XMLHttpRequest();",
  'new EventSource("/events");',
  'new WebSocket("wss://example.test/events");',
  'import schema from "@xingwen/contracts";',
  `const apiPath = "${["/api", ["v", "1"].join(""), "tasks"].join("/")}";`,
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

const workspaceNewFileFixtures = [
  ["apps/workspace/src/features/example.tsx", 'fetch("/api/projects");'],
  ["apps/workspace/src/components/example.tsx", "new XMLHttpRequest();"],
  ["apps/workspace/src/pages/example.tsx", 'new EventSource("/events");'],
  [
    "apps/workspace/src/pages/example.tsx",
    'import schema from "@xingwen/contracts";',
  ],
  [
    "apps/workspace/src/features/example.tsx",
    `const path = "${["/api", ["v", "1"].join(""), "projects"].join("/")}";`,
  ],
];

for (const [file, content] of workspaceNewFileFixtures) {
  if (
    collectBoundaryViolations(file, content, workspacePresentationRule)
      .length === 0
  ) {
    failures.push(
      `Architecture boundary self-test failed for new Workspace file ${file}.`,
    );
  }
}

if (
  !workspaceRuntimeCompositionFiles.has("apps/workspace/src/runtime.ts") ||
  workspaceProductionFiles.includes("apps/workspace/src/runtime.ts")
) {
  failures.push(
    "Architecture boundary self-test: runtime.ts must be excluded from Workspace presentation checks.",
  );
}

const workspaceShellRoots = listedFiles.filter(
  (entry) => entry === "apps/workspace/upstream/openhands/src/root.tsx",
);
if (workspaceShellRoots.length !== 1) {
  failures.push(
    "Workspace must have exactly one source-adopted OpenHands product root.",
  );
}

const workspaceHostPath = "apps/workspace/src/workspace-host.tsx";
if (!listedFiles.includes(workspaceHostPath)) {
  failures.push("Workspace host composition file is missing.");
} else {
  const workspaceHost = readFileSync(resolve(root, workspaceHostPath), "utf8");
  if (!workspaceHost.includes("OpenHandsWorkspaceRoot")) {
    failures.push(
      "Workspace host must mount the single source-adopted OpenHands root.",
    );
  }
}

const forbiddenPathMarkers = [
  '"/tour"',
  "localStorage route shadow",
  "Workspace route shim",
  "parallel Workspace route",
];
for (const file of workspaceProductionFiles) {
  const content = readFileSync(resolve(root, file), "utf8");
  for (const marker of forbiddenPathMarkers) {
    if (content.includes(marker)) {
      failures.push(`${file} contains a forbidden parallel path: ${marker}.`);
    }
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
