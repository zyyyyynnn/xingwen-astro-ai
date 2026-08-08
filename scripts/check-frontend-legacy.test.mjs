import assert from "node:assert/strict";
import test from "node:test";

import {
  findRetiredLockfileDependencies,
  findRetiredManifestDependencies,
  findRetiredResolvedDependencies,
  findRetiredTextTerms,
  findRetiredWorkspaceCssTerms,
  findRetiredWorkspaceManifestDependencies,
  findRetiredWorkspaceIdentifiers,
  findFakeWorkspaceCapabilityPhrases,
  frameworkName,
  isRetiredPackageName,
  isRetiredPath,
  retiredWorkspacePackageNames,
  retiredWorkspacePaths,
  retiredWorkspaceIdentifierNames,
  fakeWorkspaceCapabilityPhrases,
  retiredWorkspaceCssTermsExport,
} from "./check-frontend-legacy-rules.mjs";

test("rejects the bare retired runtime in a manifest", () => {
  assert.deepEqual(
    findRetiredManifestDependencies({ dependencies: { [frameworkName]: "1" } }),
    [`dependencies.${frameworkName}`],
  );
});

test("rejects case variants in documentation", () => {
  const titleCase = frameworkName[0].toUpperCase() + frameworkName.slice(1);
  assert.deepEqual(findRetiredTextTerms(`${titleCase} migration`), [
    frameworkName,
  ]);
});

test("rejects retired terms in ordinary JSON configuration", () => {
  const config = JSON.stringify({ framework: frameworkName });
  assert.deepEqual(findRetiredTextTerms(config), [frameworkName]);
});

test("rejects the retired bridge package", () => {
  const name = `${frameworkName}-demi`;
  assert.deepEqual(
    findRetiredManifestDependencies({ optionalDependencies: { [name]: "1" } }),
    [`optionalDependencies.${name}`],
  );
});

test("rejects an indirect lockfile dependency", () => {
  const lockfile = `lockfileVersion: '9.0'\n\npackages:\n\n  '${frameworkName}@3.5.0':\n    resolution: {}\n`;
  assert.deepEqual(findRetiredLockfileDependencies(lockfile), [frameworkName]);
});

test("rejects the retired application directory", () => {
  assert.equal(
    isRetiredPath(["apps", "web", "src", "main.ts"].join("/")),
    true,
  );
});

test("rejects retired component files", () => {
  assert.equal(isRetiredPath(`src/Component.${frameworkName}`), true);
});

test("rejects namespace packages in the resolved dependency tree", () => {
  const name = `@${frameworkName}/compiler-core`;
  assert.deepEqual(
    findRetiredResolvedDependencies([{ dependencies: { [name]: { name } } }]),
    [name],
  );
});

test("rejects retired Workspace application paths", () => {
  for (const path of retiredWorkspacePaths) {
    assert.equal(isRetiredPath(path), true, path);
  }
});

test("allows legitimate current Workspace paths", () => {
  assert.equal(
    isRetiredPath("apps/workspace/src/pages/new-workspace-page.tsx"),
    false,
  );
  assert.equal(
    isRetiredPath("apps/workspace/src/components/new-navigation.tsx"),
    false,
  );
  assert.equal(
    isRetiredPath("apps/workspace/src/features/research-adapter/index.ts"),
    false,
  );
  assert.equal(
    isRetiredPath("apps/workspace/src/hooks/use-agent-runtime.ts"),
    false,
  );
});

test("does not permanently ban Tailwind from the Workspace", () => {
  assert.equal(isRetiredPackageName("tailwindcss"), false);
  assert.equal(isRetiredPackageName("@tailwindcss/vite"), false);
});

test("accepts an empty retired Workspace dependency list", () => {
  assert.deepEqual(retiredWorkspacePackageNames, []);
  const manifest = { dependencies: { tailwindcss: "4" } };
  assert.deepEqual(findRetiredWorkspaceManifestDependencies(manifest), []);
});

test("rejects exact retired Workspace identifiers", () => {
  assert.deepEqual(findRetiredWorkspaceIdentifiers("WorkspacePage"), [
    "WorkspacePage",
  ]);
  assert.deepEqual(
    findRetiredWorkspaceIdentifiers("const page = WorkspacePage;"),
    ["WorkspacePage"],
  );
  assert.deepEqual(
    findRetiredWorkspaceIdentifiers("function ResearchShell() {}"),
    ["ResearchShell"],
  );
});

test("allows legitimate compound Workspace identifiers", () => {
  const compoundIdentifiers = [
    "NewWorkspacePage",
    "AgentWorkspacePage",
    "WorkspacePageModel",
    "ResearchShellAdapter",
    "ArtifactCanvasState",
    "ArtifactPreview",
    "PreviewPane",
    "previewState",
    "workspacePage",
  ];
  for (const name of compoundIdentifiers) {
    assert.deepEqual(
      findRetiredWorkspaceIdentifiers(`export function ${name}() {}`),
      [],
      `Expected ${name} to be allowed as an identifier`,
    );
  }
});

test("rejects explicit placeholder and fake capability phrases", () => {
  assert.ok(
    findFakeWorkspaceCapabilityPhrases("科研工作台将在此提供研究画布。")
      .length > 0,
  );
  assert.ok(
    findFakeWorkspaceCapabilityPhrases("功能开发中").includes("功能开发中"),
  );
  assert.ok(
    findFakeWorkspaceCapabilityPhrases("Coming soon").includes("Coming soon"),
  );
  assert.ok(
    findFakeWorkspaceCapabilityPhrases("coming soon").includes("Coming soon"),
  );
});

test("allows stable Workspace content and legitimate preview text", () => {
  const allowedTexts = [
    "研究工作台",
    "请使用桌面设备",
    "研究工作台需要更宽的浏览器窗口。",
    "Artifact preview is available from the completed renderer.",
  ];
  for (const text of allowedTexts) {
    assert.deepEqual(
      findFakeWorkspaceCapabilityPhrases(text),
      [],
      `Expected "${text}" to contain no fake capability phrases`,
    );
  }
});

test("rejects retired Workspace stylesheet rules", () => {
  const rule = retiredWorkspaceCssTermsExport[1];
  assert.deepEqual(findRetiredWorkspaceCssTerms(rule), [rule]);
});
