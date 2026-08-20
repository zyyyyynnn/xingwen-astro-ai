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

test("validates basic Markdown structure", () => {
  assert.match(
    inspectMarkdown("# Title\n\n```text\nopen").errors.join("\n"),
    /fence/u,
  );
  assert.match(
    inspectMarkdown("# Title\n\n### Skipped").errors.join("\n"),
    /H1 to H3/u,
  );
  assert.match(
    inspectMarkdown(
      "# Title\n\n| A | B |\n| --- | --- |\n| only |",
    ).errors.join("\n"),
    /1 columns; expected 2/u,
  );
});

test("extracts links and Mermaid blocks", () => {
  const source =
    "# Title\n\n[Docs](docs/README.md)\n\n```mermaid\nflowchart LR\n A-->B\n```";
  const result = inspectMarkdown(source);
  assert.deepEqual(result.links, [{ line: 3, target: "docs/README.md" }]);
  assert.deepEqual(result.mermaidBlocks[0].lines, ["flowchart LR", " A-->B"]);
});

test("requires Authority only for normative documents", () => {
  assert.match(
    inspectMarkdown("# Title", { requireAuthority: true }).errors.join("\n"),
    /missing Authority metadata/u,
  );
  assert.deepEqual(
    inspectMarkdown(metadataDoc(["| Authority | Stable contract |"]), {
      requireAuthority: true,
    }).errors,
    [],
  );
});

test("allows only stable metadata fields", () => {
  const source = metadataDoc([
    "| Authority | Stable contract |",
    "| Scope | exoplanet_host_star |",
    "| Authoring source | apps/api/src/app/schemas |",
    "| Applies to | all current consumers |",
  ]);
  assert.deepEqual(inspectMarkdown(source).errors, []);
});

test("rejects lifecycle and work-state metadata", () => {
  for (const key of [
    "Status",
    "Issue",
    "Superseded by",
    "Time range",
    "Progress",
  ]) {
    const source = metadataDoc([
      "| Authority | Stable contract |",
      `| ${key} | value |`,
    ]);
    assert.match(
      inspectMarkdown(source).errors.join("\n"),
      /history or status/u,
      key,
    );
  }
});

test("rejects unknown metadata fields", () => {
  const source = metadataDoc([
    "| Authority | Stable contract |",
    "| Source | somewhere |",
  ]);
  assert.match(
    inspectMarkdown(source).errors.join("\n"),
    /not on the stable allowlist/u,
  );
});

test("rejects PR and Issue work-state references in governed Markdown", () => {
  const issueReference = ["Issue #", "32"].join("");
  assert.match(
    inspectMarkdown(`# Title\n\n${issueReference}`).errors.join("\n"),
    /work-state reference/u,
  );
});

test("rejects task codes in content and paths", () => {
  const hyphenated = ["D", "10"].join("-");
  const compact = ["a", "22"].join("");
  assert.equal(containsRepositoryTaskCode(`cleanup ${hyphenated}`), true);
  assert.equal(containsRepositoryTaskCode(`${compact} cleanup`), true);
  assert.equal(
    containsRepositoryTaskCodePath(`tests/${compact}-contract.spec.ts`),
    true,
  );
  assert.match(
    inspectMarkdown(`# Title\n\n${hyphenated}`).errors.join("\n"),
    /task code is not allowed/u,
  );
});

test("does not confuse platform architecture tokens with task codes", () => {
  assert.equal(containsRepositoryTaskCode("linux-x64-gnu"), false);
  assert.equal(containsRepositoryTaskCode("linux-x86_64"), false);
  assert.equal(containsRepositoryTaskCodePath("vendor/linux-x64-gnu"), false);
});

test("rejects work phase identities but allows failure-stage semantics", () => {
  const phase = ["Phase", "2"].join(" ");
  const compact = ["phase", "_", "1"].join("");
  const workMarker = ["M", "2"].join("");
  assert.equal(containsRepositoryPhaseIdentifier(phase), true);
  assert.equal(containsRepositoryPhaseIdentifier(compact), true);
  assert.equal(containsRepositoryPhaseIdentifier(workMarker), true);
  assert.equal(
    containsRepositoryPhaseIdentifierPath(`generated/${compact}/manifest.json`),
    true,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier("failure_stage: schema"),
    false,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier(["Parser failure Sta", "ge 2"].join("")),
    false,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier(["phase: ", "0.45,"].join("")),
    false,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier(["phase: ", "1}"].join("")),
    false,
  );
  assert.equal(
    containsRepositoryPhaseIdentifier(["Phase: ", "2 is ongoing"].join("")),
    true,
  );
});

test("rejects repository pseudo-version identities", () => {
  const short = ["v", "1"].join("");
  const underscored = ["_", "v", "3", "_", "2"].join("");
  const dotted = [".", "v", "1"].join("");
  const hyphenated = ["-", "v", "2"].join("");
  const camel = ["Graph", "V", "1"].join("");
  assert.equal(containsRepositoryVersionLabel(short), true);
  assert.equal(containsRepositoryVersionLabel(`name${underscored}`), true);
  assert.equal(containsRepositoryVersionLabel(`name${dotted}`), true);
  assert.equal(containsRepositoryVersionLabel(`name${hyphenated}`), true);
  assert.equal(containsRepositoryVersionLabel(camel), true);
  assert.equal(
    containsRepositoryVersionLabel(["Ver", "sioned Data Artifact"].join("")),
    true,
  );
  assert.equal(
    containsRepositoryVersionLabelPath(`fixtures/data${dotted}.json`),
    true,
  );
});

test("retains legitimate technical and external versions", () => {
  assert.equal(containsRepositoryVersionLabel("Pydantic v2"), false);
  const externalIdentity = ["call_deepseek_v", "3_2"].join("");
  assert.equal(containsRepositoryVersionLabel(externalIdentity), true);
  assert.equal(containsRepositoryVersionLabel('tag: "v1.10.0"'), false);
  assert.equal(containsRepositoryVersionLabel("schema_version: 2.0.0"), false);
  assert.equal(containsRepositoryVersionLabel("actions/checkout@v4"), false);
  const upstreamLayoutModel = ["PP-DocLayout", "V", "3"].join("");
  assert.equal(containsRepositoryVersionLabel(upstreamLayoutModel), false);
  assert.equal(
    containsRepositoryVersionLabel(
      `${upstreamLayoutModel} and PaddleOCR-VL-1.6-0.9B`,
    ),
    false,
  );
  assert.equal(
    containsRepositoryVersionLabelPath(
      ["api", ["v", "1"].join(""), "projects.ts"].join("/"),
    ),
    false,
  );
});

test("detects repository progress wording", () => {
  const futureAdapter = ["future", "production adapter"].join(" ");
  const placeholder = ["cache boundary", "placeholder"].join(" ");
  assert.equal(containsRepositoryProgressWording(futureAdapter), true);
  assert.equal(containsRepositoryProgressWording(placeholder), true);
  assert.equal(
    containsRepositoryProgressWording("placeholder cells are not invented"),
    false,
  );
});

test("recognizes repository text and template exemptions", () => {
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

test("rejects stub wording only in production schemas", () => {
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
