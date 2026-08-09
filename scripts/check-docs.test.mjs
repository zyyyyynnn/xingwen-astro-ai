import assert from "node:assert/strict";
import test from "node:test";

import { inspectMarkdown } from "./check-docs-rules.mjs";
import {
  containsProductionSchemaStatusWording,
  containsRepositoryPhaseIdentifier,
  containsRepositoryPhaseIdentifierPath,
  containsRepositoryProgressWording,
  containsRepositoryTaskCode,
  containsRepositoryTaskCodePath,
  containsRepositoryVersionLabel,
  containsRepositoryVersionLabelPath,
  isIssueOrPullRequestBodyTemplatePath,
  isRepositoryTextPath,
} from "./governance-identifiers.mjs";

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

test("counts an unescaped pipe inside a code span as a separator", () => {
  const source = "# Title\n\n## T\n\n| A | B |\n| --- | --- |\n| `x | y` | z |";
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /3 columns; expected 2/u,
  );
});

test("treats an escaped pipe inside a code span as cell content", () => {
  const source =
    "# Title\n\n## T\n\n| A | B |\n| --- | --- |\n| `x \\| y` | z |";
  assert.deepEqual(inspectMarkdown(source).errors, []);
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
    "| Status | Proposed |",
    "| Authority | X |",
    "| Scope | exoplanet_host_star |",
    "| Issue | #32 |",
    "| Superseded by | Data Model |",
    "| Authoring source | apps/api/src/app/schemas |",
    "| Time range | contract baseline |",
    "| Applies to | all Markdown |",
  ]);
  assert.deepEqual(inspectMarkdown(source).errors, []);
});

test("rejects Issue metadata for Accepted Authority", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "| Issue | #32 |",
  ]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /Issue metadata is not allowed in Accepted Authority/u,
  );
});

test("rejects task codes in every governed Markdown document", () => {
  for (const identifier of [
    ["C", "04"].join("-"),
    ["D", "xx"].join("-"),
    ["A", "NN"].join("-"),
    ["A", "1"].join("-"),
    ["A", "1000"].join("-"),
  ]) {
    assert.match(
      inspectMarkdown(`# Title\n\n${identifier}`).errors.join("\n"),
      /task code is not allowed in governed Markdown/u,
      identifier,
    );
  }
});

test("rejects task codes in repository prose surfaces", () => {
  const identifier = ["B", "19"].join("-");
  assert.equal(containsRepositoryTaskCode(`Contract from ${identifier}`), true);
});

test("rejects compact task codes in repository content and paths", () => {
  const upperIdentifier = ["D", "10"].join("");
  const lowerIdentifier = ["d", "10"].join("");
  assert.equal(containsRepositoryTaskCode(upperIdentifier), true);
  assert.equal(containsRepositoryTaskCode(`${lowerIdentifier}_contract`), true);
  assert.equal(
    containsRepositoryTaskCodePath(`scripts/check_${lowerIdentifier}.py`),
    true,
  );
});

test("rejects arbitrary compact task-code lengths and lowercase forms", () => {
  const compactLower = ["a", "22"].join("");
  const compactUpper = ["D", "100"].join("");
  assert.equal(
    containsRepositoryTaskCode(`${compactLower} ownership cleanup`),
    true,
  );
  assert.equal(
    containsRepositoryTaskCode(`${compactUpper} contract cleanup`),
    true,
  );
  assert.equal(
    containsRepositoryTaskCodePath(`tests/${compactLower}-contract.spec.ts`),
    true,
  );
});

test("does not treat platform architecture names as compact task codes", () => {
  assert.equal(containsRepositoryTaskCode("linux-x64-gnu"), false);
  assert.equal(containsRepositoryTaskCode("linux-x86_64"), false);
  assert.equal(containsRepositoryTaskCodePath("vendor/linux-x64-gnu"), false);
});

test("rejects lowercase hyphen task tokens embedded in prose", () => {
  assert.equal(containsRepositoryTaskCode("not-a-40-character hash"), true);
});

test("allows URLs and page-size identifiers that resemble task codes", () => {
  assert.equal(
    containsRepositoryTaskCode("https://example.test/d51/report"),
    false,
  );
  assert.equal(containsRepositoryTaskCode("A4 paper"), false);
  assert.equal(containsRepositoryTaskCode("A4 @ 72 dpi"), false);
});

test("rejects phase identifiers in repository prose surfaces", () => {
  const identifier = ["Stage", "2"].join(" ");
  assert.equal(containsRepositoryPhaseIdentifier(identifier), true);
});

test("rejects multi-digit milestone identifiers", () => {
  assert.equal(
    containsRepositoryPhaseIdentifier(`${["M", "10"].join("")} delivery`),
    true,
  );
});

test("rejects priority-shaped phase identifiers", () => {
  assert.equal(containsRepositoryPhaseIdentifier(["P", "0"].join("")), true);
});

test("allows domain failure-stage descriptions", () => {
  assert.equal(
    containsRepositoryPhaseIdentifier("Parser failure Stage 2"),
    false,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier("failure_stage: schema"),
    false,
  );
  assert.equal(containsRepositoryPhaseIdentifier("解析失败阶段 2"), false);
});

test("rejects compact phase identifiers in repository content and paths", () => {
  const compactPhase = ["phase", "0"].join("");
  assert.equal(containsRepositoryPhaseIdentifier(compactPhase), true);
  assert.equal(
    containsRepositoryPhaseIdentifierPath(
      `generated/${compactPhase}/manifest.json`,
    ),
    true,
  );
});

test("rejects single-segment version labels in content and paths", () => {
  const versionLabel = ["v", "1"].join("");
  assert.equal(containsRepositoryVersionLabel(versionLabel), true);
  assert.equal(containsRepositoryVersionLabel(`fixture-${versionLabel}`), true);
  assert.equal(
    containsRepositoryVersionLabel(`graph_${versionLabel}_contract`),
    true,
  );
  assert.equal(
    containsRepositoryVersionLabelPath(`fixtures/data.${versionLabel}.json`),
    true,
  );
  assert.equal(
    containsRepositoryVersionLabelPath(
      `contracts/graph_${versionLabel}_contract.json`,
    ),
    true,
  );
});

test("allows technical versions and API paths", () => {
  assert.equal(containsRepositoryVersionLabel("Pydantic v2"), false);
  assert.equal(containsRepositoryVersionLabel('tag: "v1.10.0"'), false);
  assert.equal(containsRepositoryVersionLabel("call_model_v3_2"), false);
  assert.equal(
    containsRepositoryVersionLabelPath("models/call_model_v3_2.json"),
    false,
  );
  assert.equal(containsRepositoryVersionLabelPath("api/v1/projects.ts"), false);
  const versionedApiPath = ["/api/", "v", "1", "/projects"].join("");
  assert.equal(containsRepositoryVersionLabel(versionedApiPath), false);
  assert.equal(containsRepositoryVersionLabel("actions/checkout@v4"), false);
});

test("rejects progress references in Accepted Authority", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "",
    "当前实现不得写入规范。",
  ]).replace("| Authority | X |\n\n", "| Authority | X |\n\n## Rules\n\n");
  const errors = inspectMarkdown(source).errors.join("\n");
  assert.match(errors, /implementation-progress wording is not allowed/u);
});

test("rejects implementation-progress wording across repository text", () => {
  const laterTask = ["later", "task"].join(" ");
  const modulePlaceholder = ["cache boundary", "placeholder"].join(" ");
  const futureIntegration = ["future", "integration"].join(" ");
  const moduleLabel = ["C", "module"].join("-");
  const contractFreeze = ["contract", "freeze change"].join("-");
  const mappingChange = ["C", "mapping changes"].join(" ");
  const futureApi = ["future", "PaperCollection API publisher"].join(" ");
  const futureAdapter = ["future", "production benchmark adapter"].join(" ");
  const laterHttpAdapter = ["later,", "the HTTP adapter"].join(" ");
  const chineseFutureConsumer = ["未来", "Graph 消费端"].join(" ");
  const chineseLaterBoundary = ["后续", "持久化边界"].join(" ");
  assert.equal(containsRepositoryProgressWording(laterTask), true);
  assert.equal(containsRepositoryProgressWording(modulePlaceholder), true);
  assert.equal(containsRepositoryProgressWording(futureIntegration), true);
  assert.equal(containsRepositoryProgressWording(moduleLabel), true);
  assert.equal(containsRepositoryProgressWording(contractFreeze), true);
  assert.equal(containsRepositoryProgressWording(mappingChange), true);
  assert.equal(containsRepositoryProgressWording(futureApi), true);
  assert.equal(containsRepositoryProgressWording(futureAdapter), true);
  assert.equal(containsRepositoryProgressWording(laterHttpAdapter), true);
  assert.equal(containsRepositoryProgressWording(chineseFutureConsumer), true);
  assert.equal(containsRepositoryProgressWording(chineseLaterBoundary), true);
  assert.equal(isRepositoryTextPath("docs/authority.md"), true);
  assert.equal(
    isIssueOrPullRequestBodyTemplatePath(".github/ISSUE_TEMPLATE/chore.md"),
    true,
  );
  assert.equal(
    isIssueOrPullRequestBodyTemplatePath("docs/authority.md"),
    false,
  );
});

test("rejects stub status in production schemas only", () => {
  const statusWord = ["extraction", "stub"].join(" ");
  assert.equal(
    containsProductionSchemaStatusWording(
      statusWord,
      "apps/api/src/app/schemas/scientific_document.py",
    ),
    true,
  );
  assert.equal(
    containsProductionSchemaStatusWording(
      statusWord,
      "apps/api/tests/test_scientific_document_contract.py",
    ),
    false,
  );
});

test("allows domain placeholders and stable non-goals", () => {
  assert.equal(
    containsRepositoryProgressWording("placeholder cells are not invented"),
    false,
  );
  assert.equal(
    containsRepositoryProgressWording("This package exports no cache runtime"),
    false,
  );
});

test("rejects each forbidden progress phrase in Accepted Authority", () => {
  for (const phrase of [
    "Current Progress",
    "Current PR",
    "Pending Tasks",
    "Implementation Status",
  ]) {
    const source = metadataDoc([
      "| Status | Accepted |",
      "| Authority | X |",
      "",
      phrase,
    ]).replace("| Authority | X |\n\n", "| Authority | X |\n\n## Rules\n\n");
    assert.match(
      inspectMarkdown(source).errors.join("\n"),
      /implementation-progress wording is not allowed/u,
      phrase,
    );
  }
});

test("rejects phase identifiers in every governed Markdown document", () => {
  for (const identifier of [
    ["Phase", "0"].join(" "),
    ["Phase", "II"].join(" "),
    ["Stage", "1"].join(" "),
    ["Stage", "A"].join(" "),
    ["M", "2"].join(""),
    ["PR", "1/5"].join("-"),
    ["第", "一", "阶段"].join(""),
    ["阶段", "一"].join(""),
    ["第", "一", "期"].join(""),
    ["期", "一"].join(" "),
    ["Mile", "stone"].join(""),
  ]) {
    const source = `# Title\n\n${identifier}`;
    assert.match(
      inspectMarkdown(source).errors.join("\n"),
      /phase identifier is not allowed in governed Markdown/u,
      identifier,
    );
  }
});

test("allows stable astronomy identifiers that are not work stages", () => {
  const messierOne = ["M", "1"].join("");
  const messierThirtyOne = ["M", "31"].join("");
  assert.deepEqual(
    inspectMarkdown(
      `# Title\n\nMessier ${messierOne}、Messier ${messierThirtyOne}、Cygnus X-1 和 carbon isotope C-14 均在范围内。会话过期 401。`,
    ).errors,
    [],
  );
});

test("rejects merge-conflict markers in Accepted Authority", () => {
  const source = metadataDoc([
    "| Status | Accepted |",
    "| Authority | X |",
    "",
    "=======",
  ]).replace("| Authority | X |\n\n", "| Authority | X |\n\n## Rules\n\n");
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /merge-conflict marker/u,
  );
});
