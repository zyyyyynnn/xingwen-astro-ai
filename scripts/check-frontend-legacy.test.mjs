import assert from "node:assert/strict";
import test from "node:test";

import {
  findRetiredLockfileDependencies,
  findRetiredManifestDependencies,
  findRetiredResolvedDependencies,
  findRetiredTextTerms,
  findRetiredWorkspaceCssTerms,
  findRetiredWorkspaceManifestDependencies,
  findRetiredWorkspaceTextTerms,
  findTourRouteRefs,
  frameworkName,
  isRetiredPackageName,
  isRetiredPath,
  retiredWorkspacePackageNames,
  retiredWorkspacePaths,
  retiredWorkspaceSymbolAndPlaceholderTerms,
  retiredWorkspaceCssTermsExport,
  tourRouteAllowlist,
  tourRouteTermsExport,
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

test("rejects the retired compatibility package", () => {
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

test("allows legitimate new Workspace paths not retired by A-20", () => {
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

test("rejects retired Workspace symbols and placeholder copy in Workspace source", () => {
  const symbol = retiredWorkspaceSymbolAndPlaceholderTerms[0];
  assert.deepEqual(findRetiredWorkspaceTextTerms(`export function ${symbol}`), [
    symbol,
  ]);
  const placeholder = retiredWorkspaceSymbolAndPlaceholderTerms.at(-1);
  assert.deepEqual(findRetiredWorkspaceTextTerms(placeholder), [placeholder]);
});

test("rejects fake capability text in Workspace source", () => {
  const terms = findRetiredWorkspaceTextTerms(
    "科研工作台将在此提供研究画布。",
  );
  assert.ok(terms.length > 0, "将在此提供 should be caught");
});

test("rejects retired Workspace stylesheet rules", () => {
  const rule = retiredWorkspaceCssTermsExport[1];
  assert.deepEqual(findRetiredWorkspaceCssTerms(rule), [rule]);
});

test("rejects the retired route term outside the compatibility allowlist", () => {
  const term = tourRouteTermsExport[0];
  assert.deepEqual(findTourRouteRefs(`link to ${term} here`), [term]);
  assert.equal(tourRouteAllowlist.has("apps/workspace/src/router.tsx"), true);
  assert.equal(
    tourRouteAllowlist.has("apps/site/src/pages/index.astro"),
    false,
  );
});
