import assert from "node:assert/strict";
import test from "node:test";

import {
  inspectTrackedFiles,
  versionlessApiViolations,
} from "./check-versionless-api.mjs";

for (const version of [1, 12]) {
  test(`rejects a tracked path with API version ${version}`, () => {
    const path = ["apps", "api", `v${version}`, "router.py"].join("/");

    assert.deepEqual(
      versionlessApiViolations(path, "print('neutral content')"),
      [`${path}: path contains a version-prefixed API segment`],
    );
  });
}

test("allows an unversioned tracked path with neutral content", () => {
  const path = ["apps", "api", "src", "app", "router.py"].join("/");

  assert.deepEqual(
    versionlessApiViolations(path, "print('neutral content')"),
    [],
  );
});

test("rejects a version-prefixed Xingwen API path in source content", () => {
  const path = "apps/api/src/app/router.py";
  const contents = 'route = "/api/v2/runs"';

  assert.deepEqual(versionlessApiViolations(path, contents), [
    `${path}:1: ${contents}`,
  ]);
});

test("allows only the exact file-scoped MAST provider version paths", () => {
  const path = "services/scientific_skills/astro_acquisition.py";
  const contents = [
    'endpoint = "https://mast.stsci.edu/api/v0.1/Download/file"',
    'provider_path = "/api/v0.1/Download/file"',
  ].join("\n");

  assert.deepEqual(versionlessApiViolations(path, contents), []);
  assert.deepEqual(
    versionlessApiViolations(path, `${contents}\nlocal = "/api/v2/runs"`),
    [`${path}:3: local = "/api/v2/runs"`],
  );
});

test("checks versioned paths even when their contents are not scannable", () => {
  const path = ["apps", "api", `v${12}`, "NOTICE"].join("/");
  let contentRead = false;

  assert.deepEqual(
    inspectTrackedFiles([path], () => {
      contentRead = true;
      return "neutral content";
    }),
    [`${path}: path contains a version-prefixed API segment`],
  );
  assert.equal(contentRead, false);
});
