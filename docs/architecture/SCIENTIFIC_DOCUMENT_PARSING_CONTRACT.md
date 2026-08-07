# Scientific Document Parsing Contract (D-10 / #190)

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Scientific Document Parsing 冻结契约、Parser Port、Golden Set、Benchmark 与上游采用边界 |

Frozen Canonical Contract, Parser Port, Golden Set, Benchmark and Upstream
Adoption for the Scientific Document Parsing boundary. This document is the
authoritative design record for **#190 D-10** and the handoff source for
**#191 D-11** (Hybrid Parser) and **#192 B-20** (DocumentParse persistence).

Scope is **exoplanet_host_star** only. Everything below is MVP-fixed; do not
generalize to universal Document AI, web parsing, FITS analysis, plot
digitization, or a second Evidence/Workflow/Version system.

## 1. Ownership boundary

| Xingwen owns | Upstream owns |
|---|---|
| Contract (this schema) | PDF parsing |
| Evidence / locator semantics | OCR |
| Quality semantics | layout |
| Version / hash | table recognition |
| Benchmark | formula recognition |
| Workflow boundary | visual document understanding |

We **adopt, adapt, normalize, validate, benchmark, govern** — never
**read-then-rewrite** a third-party engine.

## 2. Canonical Contract (single source)

`apps/api/src/app/schemas/scientific_document.py` is the ONLY authoritative
schema source. `compute_scientific_document_schema_hash()` yields a stable
`sha256:` hash of the JSON schemas (Pydantic `json_schema(mode="serialization")`,
sorted, so declaration order cannot change the hash). Version
`SCIENTIFIC_DOCUMENT_SCHEMA_VERSION = "1.0.0"`.

Exposed models: `DocumentParseInput`, `DocumentParseCandidate`, `DocumentPage`,
`DocumentBlock`, `DocumentTable`, `DocumentTableCell`, `DocumentFormula`,
`DocumentFigure`, `DocumentLocator`, `DocumentParseQuality`, `DocumentBBox`,
`TextSpan`, `ScientificDataExtractionCandidate`, `DocumentParseProfile`.

Benchmark models live in `scientific_document_benchmark.py`: `GoldenSetManifest`,
`GoldenSetEntry`, `BenchmarkReport`, `BenchmarkCaseResult`, `BenchmarkMetricValue`.

**No vendor type enters the Canonical schema.** Vendor identity is carried only
as `str` provenance (`native_engine`, `visual_model_id`, `parser_profile_id`).

## 3. Parser Port (vendor-neutral)

`apps/api/src/app/services/scientific_document/ports.py` defines
`DocumentParserPort` (Protocol) with `parse_document(input: DocumentParseInput)
-> DocumentParseCandidate`. It expresses Xingwen's needed capability, never a
vendor object. D-11 implements this port; D-10 ships only the interface.

## 4. Quality semantics (anti-hallucination)

- **accepted** — current parser/profile reached admission conditions for the
  usable region; may become downstream Evidence / input. NOT "scientific fact
  verified".
- **partial** — only part parsed. Downstream may use the clearly valid part, but
  MUST keep `unparsed != absent`. A missing recognition is NEVER "does not exist
  in the paper".
- **unsupported** — current parser/profile cannot reliably process. No fabricated
  full text; no downstream model may auto-complete the gap.

## 5. Block model

`DocumentBlockKind`: `heading, paragraph, list, table, formula, figure, caption,
reference, footnote`. Every block has stable identity (`block_id`),
`page_index`, `reading_order`, `bbox`, kind, `quality`, and `parser_backend` /
`parser_profile_id` provenance. Third-party raw schema is never the Domain.

## 6. Locator contract

`DocumentLocator`: `page_index`, `block_id`, `bbox` (top-left origin, absolute
PDF points, inclusive, page-relative, NOT normalized), `reading_order`, optional
`text_span`, `table_id`, `cell_id`. `bbox` is `None` when unknown (never a
zero-rect pretending to be unknown). Coordinates are absolute points in the page's
own width/height space — there is no normalized 0..1 representation anywhere in
the contract. Empty / unknown semantics are explicit.

## 7. Table / Formula / Figure

- **Table**: `table_id`, page/block identity, `rows` (rectangular
  `tuple[tuple[DocumentTableCell, ...], ...]`), header semantics, `row_span` /
  `column_span`, per-cell `bbox` / indices / `raw text` / `quality`. Cross-page
  tables cannot be reliably merged → `partial`. No cell guessing.
- **Formula**: `block_id`, `page_index`, `bbox`, `raw_text` where available,
  `latex` where upstream provides it. raw AND normalized may coexist. Recognition
  failure must NOT be LLM-completed.
- **Figure** (Phase 1): block identity, `bbox`, `caption`, `title`, axis/legend/
  visible OCR labels, `quality`/`provenance`. **Explicitly forbidden**: plot
  digitization, curve recovery, scatter-point recovery, scientific pixel
  measurement.

## 8. ScientificDataExtractionCandidate boundary

Describes ONLY a candidate: `candidate_id`, `raw_value`, `raw_unit`,
`raw_text`/`context`, `field_hint`, `object_hint`, `research_input_id`,
`source_snapshot_id?`, `document_parse_id?`, locator fields, `parse_quality`,
`evidence`/`provenance locator`. It MUST NOT carry `canonical_field`,
`canonical_unit`, `normalized_value`, `accepted_scientific_value`,
`quality_score_as_scientific_truth`, or `dataset_publication_status` — those
belong to the existing C Pipeline. Correct chain:

```
ScientificDataExtractionCandidate
  → existing Field Manifest → mapping → unit normalization
  → quality/admission → Dataset candidate → Publisher
```

**OCR → final Dataset is forbidden.**

## 9. DocumentParse logical identity (for B-20)

A parse is deterministically identified by:
`research_input/content hash` + `parser_profile_id` + `parser_profile_version`
+ `native_engine` + `native_engine_version` + `visual_model_id` + `visual_model_revision`
+ `config_hash` → `canonical_output_hash`. Same input + same parser/model/config
reuses the parse; different config/revision yields a different identity. B-20
owns the DB schema.

## 10. Native upstream (approved)

- **Package**: `docling-parse` **7.11.0** (PyPI, MIT).
- **Official API**: `DoclingPdfParser` → `load(path_or_stream=BytesIO(bytes))`
  with `ContentConfig(word/line=COMPUTE_AND_MATERIALIZE)`, iterate
  `pdf_doc.iterate_pages()` → `page.dimension.{width,height}` (points, A4 =
  595.28×841.89), `page.iterate_cells(unit_type="word")` → `word.rect`
  (`BoundingRectangle`, **bottom-left** origin in PDF space).
- **License**: MIT (code). No model weights. CPU-capable. No network, no model
  download, no extra binary at runtime.
- **Capability**: born-digital text layer + per-word geometry. Sufficient for
  the D-11 **native born-digital PDF path**.
- **Cannot provide**: scanned/OCR pages, layout/table/formula recognition,
  visual understanding → those need the visual backend.

The D-10 `native_baseline.py` is a **benchmark-only** harness (not a production
adapter): it maps docling-parse output into the Canonical contract and records
input/config/output hashes. It is gated behind an optional dependency so it
never enters API startup.

## 11. Visual upstream (approved)

- **Repository**: `PaddlePaddle/PaddleOCR` (Apache 2.0).
- **Package**: `paddleocr` **3.6.0** (PyPI, Apache 2.0) — installed with extras
  `pip install "paddleocr[doc-parser]==3.6.0"`. The D-10 manifest pins the exact
  version (`package_version = "3.6.0"`); no range/ floating version is permitted.
- **Model**: `PaddleOCR-VL-1.6` (id `PaddleOCR-VL-1.6-0.9B`, `pipeline_version="v1.6"`),
  HF `PaddlePaddle/PaddleOCR-VL-1.6` (Apache 2.0 model weights), immutable revision
  `cdc88f5feff0e4079e75863205053a68358e52f7`.
- **Official interface**: `from paddleocr import PaddleOCRVL;
  PaddleOCRVL(pipeline_version="v1.6").predict(image)` → `save_to_json` /
  `save_to_markdown`. Element-level also loadable via `transformers>=5.0.0`.
- **License**: code Apache 2.0; model weights Apache 2.0 (redistribution
  permitted; keep attribution / NOTICE).
- **Device**: `paddlepaddle-gpu==3.2.1` + CUDA, with CPU fallback
  (`DEVICE = cuda if available else cpu`). GPU is NOT a core-path requirement.
- **Download/cache/network**: first run downloads weights from BCE Bos /
  HuggingFace and caches; offline requires pre-seeded cache. Paddle must NOT be
  a core startup dependency (no `import app → import Paddle → download model`).
- **Scope (Phase 1)**: text / table / formula / figure-caption; chart
  recognition stays OFF (no plot digitization).

## 12. Hybrid rationale

Native-only covers born-digital text + geometry. Scanned pages, complex
layout, tables, formulas and figure text need the visual backend. D-11 wires a
hybrid router behind `DocumentParserPort`, mapping PaddleOCR-VL output INTO the
Canonical contract without polluting the Domain. D-10 freezes the Port and the
hybrid result structure (`BenchmarkParserMode.hybrid` reserved); the real hybrid
run belongs to D-11.

## 13. Evidence chain

```
PaperSummary statement
  → Evidence
  → DocumentParse locator (page/block/bbox/table-cell)
  → SourceSnapshot
  → ResearchInput
  → immutable content hash
```

D-10 freezes the logical contract only. The DB materialization of
ResearchInput-backed SourceSnapshot is **B-20**.

## 14. Golden Set

16 entries (10 committed synthetic fixtures + 6 local-only restricted
real-paper manifests) around `exoplanet_host_star`. Fixtures cover born-digital,
two-column, reading order, simple/complex/cross-page tables, formula,
figure+caption, mixed, scanned-like, low-quality. Manifest:
`services/scientific_document/golden_set.json`. Restricted PDFs are NOT committed
(repo keeps source/DOI/license/provenance/hash/expected annotations + local
acquisition notes). CI never downloads restricted papers.

## 15. Benchmark

`services/scientific_document/benchmark_runner.py` runs the native-only baseline
over committed fixtures and emits a versioned, hashed `BenchmarkReport`. Metrics
(versioned, deterministic, clear denominators, empty-sample safe):
`native_routing_coverage`, `visual_routing_coverage` (reserved), `block_recovery`,
`reading_order_error`, `table_structure_recovery`, `formula_recovery`,
`figure_caption_linkage`, `evidence_locator_validity`, `accepted_rate`,
`partial_rate`, `unsupported_rate`, `latency`, `peak_memory`, `cpu_result`,
`gpu_result_if_available`, `failure_category`. Native-only is real (docling-parse
run, not mock); hybrid result structure is reserved for D-11.

## 16. Governance gate

`scripts/check_d10_governance.py` (machine) blocks: production `docs.references`
imports, unapproved vendor imports in the parser area (docling allowed only in
`native_baseline.py`), floating model/revision tokens, model weight files in
git, canonical schema vendor-type leakage. `docs/quality/
SCIENTIFIC_DOCUMENT_PARSING_REVIEW.md` is the human counterpart (reference-after-
rewrite, vendor boundary, adoption integrity). Machine detection is necessary
but NOT sufficient; the human review is mandatory.

## 17. Non-goals (this PR only)

No production Paddle adapter, no hybrid router, no model loader, no PostgreSQL
`DocumentParse` tables/migrations, no `SourceSnapshot` persistence, no
`PaperSummary` projection, no Claim/Relation change, no C mapping/unit/quality
algorithm, no HTTP endpoint, no frontend, no HTML parser, no plot digitizer.
