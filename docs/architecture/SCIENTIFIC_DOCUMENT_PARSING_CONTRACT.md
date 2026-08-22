# Scientific Document Parsing Contract

| 元数据    | 值                                                                                      |
| --------- | --------------------------------------------------------------------------------------- |
| Authority | Scientific Document Parsing Canonical Contract、Parser Port、Native/Visual provenance、Golden Set 与 Benchmark |

This document defines the scientific-document parsing boundary for the fixed
`exoplanet_host_star` case. It is not a universal Document AI, Web parser, FITS
pipeline, plot digitizer, or second Evidence/Workflow/Version system.

## 1. Ownership boundary

| Xingwen owns                 | Upstream owns                                      |
| ---------------------------- | -------------------------------------------------- |
| Canonical Contract           | Born-digital PDF text layer and word geometry       |
| Evidence / locator semantics | Visual OCR/layout/table/formula/figure recognition |
| Parse quality semantics      | PDF/image decoding and model inference              |
| Identity / hashes            |                                                    |
| Golden Set / Benchmark       |                                                    |

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
never guessed. The production hybrid adapter maps both native and visual upstream
output into this Contract. It accepts PDF plus JPEG/PNG/TIFF/WebP document images;
image documents require the configured visual service and fail closed when it is
absent or fails.

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

### 8.1 Handoff to data admission

The raw candidate enters the existing Dataset chain through one deterministic
document observation pipeline:

- Field labels resolve only via exact canonical field ids or exact normalized
  registered `DocumentFieldAlias` entries owned by the Field Manifest
  (NFKC + trim + whitespace collapse + casefold; no fuzzy matching, no LLM
  mapping, no dynamically learned aliases).
- Entities bind only through exact unique matches against the frozen
  crossmatch identity rows. Documents are never a third crossmatch side and
  no canonical object is created.
- Scalar semantics (symmetric/asymmetric uncertainty, upper/lower limits,
  explicit nulls) are parsed exactly once into the typed admitted observation;
  Dataset projection never re-reads the free text.
- Admission outcomes are `accepted`, `review_required`, or `rejected` with
  stable reason codes; `review_required` never auto-selects a value.
- Authorization requires all of: Contract `document_source_policy =
  research_input`, Case Manifest `document_source_classes` capability, bound
  ResearchInput, persisted DocumentParse, its persisted SourceSnapshot, and a
  valid locator.
- Provenance reuses the persisted DocumentParse SourceSnapshot row through the
  Publisher binding map; a second snapshot row is never created.

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

`hybrid_parser.py` is the production parser adapter. For PDF it runs native
parsing first, then routes every page containing bitmap/vector structure or an
insufficient text layer to the configured PaddleOCR-VL service. This preserves
tables, formulas and figures that a sufficiently long text layer alone cannot
represent. Document images go directly through the same visual boundary.
Unresolved pages remain explicitly `partial` or `unsupported`.

The same manifest records the accepted visual adapter boundary:

- `paddleocr[doc-parser]==3.6.0` and `paddlex[genai-client,ocr]==3.6.0`
  (the exact extras pinned by the `paddleocr[doc-parser]` requirement), with
  explicit `paddleocr`, `paddlex` and `paddle` import roots;
- the pipeline component graph contains `PP-DocLayoutV3` and
  `PaddleOCR-VL-1.6-0.9B`; every required file is size/SHA-256 pinned in
  `visual_model_assets.json`, including the immutable Hugging Face revision;
- `upstream_adoption.json` owns package identity and every pipeline/runtime
  semantic: pipeline version, runtime backend, component execution policy,
  the component-role to vendor-constructor-parameter directory bindings,
  directory binding, network and implicit-download policy, and runtime
  profiles;
- `visual_model_assets.json` owns only the immutable model asset identity:
  the component role, model identity, official source, immutable revision,
  license provenance, exact file inventory, per-component asset digests and
  the bundle digest; the adoption manifest references it through the bundle
  digest;
- the bundle digest binds only the component graph, model/source/revision
  identity and asset digests; it never binds manifest_id, manifest
  schema_version, runtime directory parameters, runtime policy, parser
  packages, device, Python probe version or local paths;
- the adoption `component_directory_bindings` must cover exactly the asset
  component roles with distinct vendor parameters; the component graph has
  one owner (the asset manifest) and the runtime mapping has one owner (the
  adoption manifest);
- model directories are operator-provided and must pass full verification
  before any Paddle import or initialization; a cache name or local path is not
  model identity;
- `paddlepaddle==3.2.1`, `device=cpu` is approved by a network-isolated Live
  initialization and real `predict` over the committed `gs-formula` fixture;
  the profile `fixture_id` references the golden set entry and its
  `fixture_sha256` must equal that entry's `content_hash`, which is computed
  from the committed fixture bytes, so live evidence is machine-bound to the
  golden set;
- `paddlepaddle-gpu==3.2.1` remains deferred with `probe_evidence=not_run`;
  CPU evidence cannot approve the GPU profile;
- chart, seal, document orientation, unwarping, image-block OCR and plot
  digitization remain disabled or excluded;
- license provenance has one owner per fact: the adoption manifest records
  the code/package adoption license, and the asset manifest records each
  component/model license.

Each runtime profile has a deterministic `configuration_hash` composed at the
single composition point `runtime_provenance.py` over the asset bundle
digest, the adoption-owned pipeline version, runtime backend, component
execution policy, component directory bindings and
directory/network/implicit-download policies, the exact adopted parser
package identity (`paddleocr` package/extra/version and `paddlex`
package/extras/version), and the exact Paddle distribution/version/device.
The configuration hash covers the frozen execution configuration only; the
Python version is live probe evidence on the runtime profile and is excluded
until it becomes a frozen runtime contract. Local model/cache paths,
usernames, hostnames, timestamps and review metadata are excluded. A
production hybrid-parser consumer may select only an approved profile; the
current approved profile is CPU.

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
- distinguishes independently admitted CPU/GPU profiles and rejects CPU
  evidence presented as GPU approval;
- rejects machine-local absolute paths in tracked Scientific Document
  contracts/evidence;
- rejects model weight files and unapproved vendored parser source;
- rejects vendor imports from the Canonical schema.

Machine detection is necessary but not sufficient. Formal review must
additionally confirm the reference-after-rewrite red line by judgment, because
no machine gate can determine whether a developer read an upstream
implementation and hand-rewrote the same engine: no hand-written OCR,
layout/reading-order, table recognition, formula recognition or PDF glyph
parser, and no copied/renamed third-party prompt, schema or orchestration.
`docs/references/**` is used only for understanding, benchmark design and risk
identification, never as production source Authority. Any violation is a merge
blocker regardless of CI status.

## 14. Runtime boundary

The API composition owns one `HybridScientificDocumentParser`: native
`docling-parse` is always available for PDF text/geometry, while a configured
PaddleOCR-VL endpoint supplies visual page parsing. The parser result enters the
single DocumentParse persistence and paper-summary path; it does not introduce a
second workflow, Publisher or Evidence model. Missing visual configuration or a
failed visual request fails closed for image documents and remains explicit on
routed PDF pages. The single asynchronous paper-summary read boundary reloads
the canonical candidate from CAS, checks the persisted SourceSnapshot and
frozen parser identity, and validates every locator and quoted text span before
any summary, export, downstream Literature/Graph projection, Feedback target or
document-source result is returned. The document-source endpoint only resolves
the ResearchInput after that shared read succeeds. HTML parsing and plot
digitization remain outside this contract.
