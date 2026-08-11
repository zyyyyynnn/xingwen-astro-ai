import assert from "node:assert/strict";
import test from "node:test";

import {
  inspectArchitecturePath,
  inspectArchitectureText,
} from "./check-architecture-delegacy.mjs";

function parts(...values) {
  return values.join("");
}

test("rejects retired product and workflow semantics", () => {
  const samples = [
    parts("/api/", "tasks"),
    parts("Task", "Service"),
    parts("Task", "Create", "Request"),
    parts("Task", "Status", "Response"),
    parts("Workflow", "Executor"),
    parts("Workflow", "Context"),
    parts("Workflow", "Hooks"),
    parts("Task", "Status"),
    parts("task", "-", "read"),
  ];
  for (const sample of samples) {
    assert.notDeepEqual(inspectArchitectureText(sample), [], sample);
  }
});

test("does not reject current persistent workflow names", () => {
  assert.deepEqual(inspectArchitectureText("PersistentWorkflowExecutor"), []);
  assert.deepEqual(inspectArchitectureText("PersistentWorkflowStore"), []);
  assert.deepEqual(inspectArchitectureText("ResearchRun status"), []);
});

test("rejects retired module paths", () => {
  assert.equal(
    inspectArchitecturePath(
      parts("apps/api/src/app/workflow/", "state", "_machine.py"),
    ),
    true,
  );
  assert.equal(
    inspectArchitecturePath("apps/api/src/app/workflow/persistent_executor.py"),
    false,
  );
});
