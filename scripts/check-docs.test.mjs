import assert from "node:assert/strict";
import test from "node:test";

import { inspectMarkdown } from "./check-docs-rules.mjs";

function metadataDoc(rows) {
  return ["# Title", "", "| 元数据 | 值 |", "| --- | --- |", ...rows].join(
    "\n",
  );
}

test("detects an unclosed fence", () => {
  assert.match(
    inspectMarkdown("# Title\n\n```text\nopen").errors.join("\n"),
    /fence/u,
  );
});

test("detects a heading level jump", () => {
  assert.match(
    inspectMarkdown("# Title\n\n### Skipped").errors.join("\n"),
    /H1 to H3/u,
  );
});

test("detects inconsistent table columns", () => {
  const source = "# Title\n\n| A | B |\n| --- | --- |\n| only |";
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /1 columns; expected 2/u,
  );
});

test("extracts local links and Mermaid blocks", () => {
  const source =
    "# Title\n\n[Docs](docs/README.md)\n\n```mermaid\nflowchart LR\n A-->B\n```";
  const result = inspectMarkdown(source);
  assert.deepEqual(result.links, [{ line: 3, target: "docs/README.md" }]);
  assert.deepEqual(result.mermaidBlocks[0].lines, ["flowchart LR", " A-->B"]);
});

test("rejects unrecognized Status values", () => {
  const source = metadataDoc(["| Status | Implemented |", "| Authority | X |"]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /Status is not recognized: Implemented/u,
  );
});

test("accepts the governed Status enumeration", () => {
  for (const status of [
    "Proposed",
    "Accepted",
    "Superseded",
    "Archived",
    "Reference",
  ]) {
    const source = metadataDoc([`| Status | ${status} |`, "| Authority | X |"]);
    assert.deepEqual(inspectMarkdown(source).errors, []);
  }
});

test("rejects Implementation as a metadata field", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "| Implementation | done |",
  ]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /forbidden progress field: Implementation/u,
  );
});

test("rejects Current runtime as a metadata field", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "| Current runtime | y |",
  ]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /forbidden progress field: Current runtime/u,
  );
});

test("rejects a metadata field that is not on the allowlist", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "| Source | somewhere |",
  ]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /not on the allowlist: Source/u,
  );
});

test("requires Status when metadata is mandatory", () => {
  const source = metadataDoc(["| Authority | X |"]);
  assert.match(
    inspectMarkdown(source, { requireMetadata: true }).errors.join("\n"),
    /missing Status metadata/u,
  );
});

test("requires Authority when metadata is mandatory", () => {
  const source = metadataDoc(["| Status | Accepted |"]);
  assert.match(
    inspectMarkdown(source, { requireMetadata: true }).errors.join("\n"),
    /missing Authority metadata/u,
  );
});

test("requires Status: Reference for reference documents", () => {
  const source = metadataDoc(["| Status | Accepted |", "| Authority | X |"]);
  assert.match(
    inspectMarkdown(source, { expectedStatus: "Reference" }).errors.join("\n"),
    /Status must be Reference/u,
  );
});

test("requires Status: Archived for archived documents", () => {
  const source = metadataDoc(["| Status | Accepted |", "| Authority | X |"]);
  assert.match(
    inspectMarkdown(source, { expectedStatus: "Archived" }).errors.join("\n"),
    /Status must be Archived/u,
  );
});

test("allows stable context metadata fields", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "| Scope | exoplanet_host_star |",
    "| Issue | #32 |",
    "| Superseded by | Data Model |",
    "| Authoring source | apps/api/src/app/schemas |",
    "| Time range | Phase 0 baseline |",
    "| Applies to | all Markdown |",
  ]);
  assert.deepEqual(inspectMarkdown(source).errors, []);
});
