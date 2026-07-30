import assert from "node:assert/strict";
import test from "node:test";

import { inspectMarkdown } from "./check-docs-rules.mjs";

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

test("rejects progress-style Status values", () => {
  const source =
    "# Title\n\n| 元数据 | 值 |\n| --- | --- |\n| Status | Implemented |\n| Authority | X |";
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
    const source = `# Title\n\n| 元数据 | 值 |\n| --- | --- |\n| Status | ${status} |\n| Authority | X |`;
    assert.deepEqual(inspectMarkdown(source).errors, []);
  }
});
