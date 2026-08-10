# Scientific Document Parsing Contract

| 元数据    | 值                                                                                      |
| --------- | --------------------------------------------------------------------------------------- |
| Authority | Scientific Document Parsing Canonical Contract、Parser Port、Native/Visual provenance、Golden Set 与 Benchmark |

This document defines the scientific-document parsing boundary for the fixed
`exoplanet_host_star` case. It is not a universal Document AI, Web parser, FITS
pipeline, plot digitizer, or second Evidence/Workflow/Version system.

## 1. Ownership boundary

| Xingwen owns                 | Upstream owns                                |
| ---------------------------- | -------------------------------------------- |
| Canonical Contract           | Born-digital PDF text layer and word geometry |
| Evidence / locator semantics | Visual OCR/layout/table/formula recognition  |
| Parse quality semantics      | PDF decoding and model inference             |
| Identity / hashes            |                                              |
| Golden Set / Benchmark       |                                              |

The implementation rule is **adopt → adapt → normalize → validate → benchmark →
govern**. `docs/references/**` is never production implementation Authority;
reading third-party source and hand-rewriting an equivalent parser is forbidden.

## 2. Canonical Contract

Single authoring source:
`apps/api/src/app/schemas/scientific_document.py`.

- `SCIENTIFIC_DOCUMENT_SCHEMA_VERSION = "1.2.0"`.
- `compute_scientific_document_schema_hash()` fingerprints the exported Pydantic
  JSON Schemas deterministically.
- Canonical models contain no vendor types/imports. Native and visual engine
  identities are plain provenance data.
- `DocumentParseCandidate` validates aggregate referential integrity before it
  can cross the Port boundary.

Core models: `DocumentParseInput`, `DocumentParseCandidate`, `DocumentPage`,
`DocumentBlock`, `DocumentTable`, `DocumentTableCell`, `DocumentFormula`,
`DocumentFigure`, `DocumentLocator`, `DocumentBBox`, `TextSpan`,
`DocumentParseProfile`, `ScientificDataExtractionCandidate`.

`DocumentParseProfile.routing_policy_id` 与 `resource_policy_id` 保存策略 identity；`parser_profile_version` 只表示独立 parser profile 的技术版本。

## 3. Parser Port

`apps/api/src/app/services/scientific_document/ports.py` exposes exactly one
vendor-neutral capability:

```text
DocumentParserPort.parse_document(
    input: DocumentParseInput
) -> DocumentParseCandidate
```

There is no parallel `ParseRequest`/`ParseResult` DTO and no output→input
reconstruction. `source_type` and `mime_type` are caller-supplied facts; they are
never guessed. Any native or visual adapter maps upstream output into this Contract.
The source tree includes a native benchmark adapter; no HTTP route invokes a
visual adapter, so requests must not claim visual execution without one.

## 4. Quality semantics

- `accepted`: current parser/profile produced a usable admitted region. It does
  **not** mean a scientific fact is verified.
- `partial`: valid regions may be used, but `unparsed != absent` must propagate.
- `unsupported`: the parser/profile cannot reliably process the region; no
  fabricated text/structure may be emitted or auto-completed downstream.

Whole-document `unsupported` cannot contain accepted blocks. Unsupported tables
cannot carry structured rows; unsupported formula/figure objects cannot carry
recognized textual payload.

## 5. Locator and geometry

`DocumentLocator` is the single locator representation:
`page_index`, optional `block_id`, `bbox`, `reading_order`, `text_span`,
`table_id`, `cell_id`.

Coordinate system is fixed:

- origin: page top-left;
- x rightward, y downward;
- absolute PDF points, page-relative;
- **not normalized** (no 0..1 representation);
- unknown geometry is `None`, never a zero rectangle.

`cell_id` requires `table_id`; `text_span` requires `block_id`. The persistence
layer is responsible for validating persisted locators against the immutable parse.

## 6. Aggregate integrity

`DocumentParseCandidate` fails closed on:

- duplicate page/block/table identities;
- block missing from its page or appearing more than once in page membership;
- cross-page/dangling references;
- duplicate per-page reading order;
- block/table-cell/formula/figure bbox escaping page geometry;
- table/formula/figure references to the wrong block kind;
- parser-profile/config/native/visual provenance inconsistencies.

Every canonical block must appear exactly once in its owning
`DocumentPage.block_ids`.

## 7. Table / Formula / Figure

### Table

`DocumentTable` has `row_count`, `column_count` and rows of **anchor cells**.
Each cell has stable `cell_id`, `row_index`, `column_index`, spans,
`is_header`, bbox/text/quality. A spanning cell occupies its logical grid
rectangle; placeholder cells are not invented for covered positions. Validators
reject duplicate cell ids, unordered/invalid anchors, out-of-bounds spans and
overlapping occupied coordinates. A table must reference a canonical block of
kind `table` when included in a parse candidate. Unreliable cross-page merging is
`partial`, not guessed completion.

### Formula

Stores raw visible text and/or upstream-provided LaTeX plus block/page/bbox,
backend/profile and quality. `unsupported` carries no recognized formula text.

### Figure

Figure blocks store bbox, caption/title, axis/legend text and visible labels only.
Plot digitization, curve/scatter recovery and scientific pixel measurement are
out of scope. `unsupported` carries no recognized textual payload.

## 8. ScientificDataExtractionCandidate

This is a raw observation candidate only:

- raw value/unit/text;
- field/object hints;
- ResearchInput/SourceSnapshot/DocumentParse references;
- parse quality;
- one `DocumentLocator`.

It does **not** carry canonical field mapping, normalized units/values,
scientific acceptance or publication state. Correct chain:

```text
ScientificDataExtractionCandidate
→ existing Field Manifest
→ existing mapping
→ unit normalization
→ quality/admission
→ Dataset candidate
→ Publisher
```

`OCR → final Dataset` is forbidden.

## 9. DocumentParse logical identity

The logical identity supplied to the persistence layer binds the ResearchInput
content hash, parser profile/version, native engine revision, optional visual
engine/model revision, configuration hash and canonical output hash. Candidate
`config_hash` must equal the profile configuration hash and engine identities
must agree with the profile. Different
parser/config revisions produce different immutable parse identities. The persistence layer
owns the database schema.

## 10. Upstream adoption

Manifest authority:
`services/scientific_document/upstream_adoption.json`.

- distribution: `docling-parse==7.11.0`;
- approved Python import root: `docling_parse`;
- license: MIT; no model weights;
- official interface used by the benchmark probe:
  `DoclingPdfParser.load(...)`, `iterate_pages()`,
  `page.iterate_cells(unit_type="word")`;
- CPU-capable, no parse-time network/model download;
- intended scope: born-digital text layer + word geometry;
- excluded: scanned OCR, semantic layout/table/formula/figure recognition.

`native_baseline.py` is benchmark-only and does not enter API startup.

The same manifest records the accepted visual adapter boundary:

- `paddleocr==3.6.0` with explicit `paddleocr` and `paddle` import roots;
- `PaddlePaddle/PaddleOCR-VL-1.6` pinned to immutable model revision
  `cdc88f5feff0e4079e75863205053a68358e52f7`;
- Apache-2.0 code and model-weight licenses recorded separately;
- chart recognition and plot digitization excluded;
- model download, cache, offline, CPU/GPU and attribution requirements fixed in
  the manifest.

Adoption approval authorizes an adapter to consume the pinned upstream; it is
not execution evidence. A visual result exists only when a DocumentParserPort
adapter actually runs and records complete engine/model provenance.

## 11. Golden Set

`services/scientific_document/golden_set.json`, version `1.1.0`, contains 16
main-case documents:

- 10 legal committed synthetic fixtures for deterministic CI;
- 6 real, local-only publication records identified by genuine arXiv ids.

Restricted PDFs are never committed or fetched by CI. Their local content hash
remains absent when the exact bytes were not locally verified. Expected
annotations record selected headings/values/structures rather than pretending
full-document character-level ground truth.

The scanned fixture is raster-only with no text layer; native-only parsing must
return no accepted blocks for it.

The derived `golden_set_content_hash` used by Benchmark covers the complete
manifest except volatile `generated_at`, including every entry's provenance,
license, content hash, coverage and expected annotation.

## 12. Benchmark

`services/scientific_document/benchmark_runner.py`:

- strongly validates the Golden manifest;
- fails on missing committed fixture or content-hash mismatch;
- executes the real pinned native parser over committed fixtures;
- records case-local quality counts;
- computes textual `block_recovery` only where manually selected critical text
  anchors exist;
- computes native routing coverage and geometry locator validity;
- reports visual routing coverage as `not_applicable` for native-only runs;
- explicitly reports unsupported/not-run/not-applicable metrics rather than
  representing unmeasured capabilities as zero;
- includes Golden/config/schema/upstream identity in deterministic `input_hash`;
- produces a self-verifying `output_hash` that excludes the hash field itself
  and volatile `created_at`.

For native-only, structural table/formula/figure recovery is `unsupported`, and
reading-order error and resource measurements are `not_run`.

`check_scientific_document_benchmark_report.py` reloads the produced artifact through the
Pydantic report contract and therefore verifies its hash and non-empty execution.

## 13. Governance gate

`scripts/check_scientific_document_governance.py` is stdlib-only and runs in Foundation CI. It:

- AST-detects both `import docs.references...` and
  `from docs.references...` in production code;
- authorizes parser imports only through explicit `import_roots` on an
  `adoption_status=approved` manifest entry;
- rejects floating/range adoption versions;
- validates critical manifest fields before runtime adapters can rely on them;
- rejects model weight files and unapproved vendored parser source;
- rejects vendor imports from the Canonical schema.

Machine detection is necessary but not sufficient. The human checklist in
`docs/quality/SCIENTIFIC_DOCUMENT_PARSING_REVIEW.md` remains mandatory.

## 14. Runtime boundary

This contract defines scanned-page and visual provenance without claiming an
executing visual adapter. It does not define DocumentParse PostgreSQL
persistence, SourceSnapshot materialization, paper-summary or data-pipeline
integration, HTTP endpoints, frontend behavior, HTML parsing, or plot
digitization. Missing adapters fail closed and cannot emit accepted visual
content, ArtifactVersion, benchmark measurements or model-call proof.
