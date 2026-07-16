import assert from "node:assert/strict";
import test from "node:test";

import {
  findRetiredLockfileDependencies,
  findRetiredManifestDependencies,
  findRetiredResolvedDependencies,
  findRetiredTextTerms,
  frameworkName,
  isRetiredPath,
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
