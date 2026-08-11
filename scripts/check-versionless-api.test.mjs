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
