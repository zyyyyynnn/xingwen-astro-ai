# Scientific Document Parsing — Review Checklist (D-10 / #190)

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Scientific Document Parsing 人工审查清单：reference-after-rewrite、vendor 边界与采用完整性 |

This checklist is the **human** counterpart to the machine-enforced gate
`scripts/check_d10_governance.py`. The machine gate can detect *strings*; it
cannot detect *intent*. A reviewer must verify the items below on every PR that
touches `apps/api/src/app/services/scientific_document/**` or
`apps/api/src/app/schemas/scientific_document*.py`.

## 1. Reference-after-rewrite (HIGHEST PRIORITY)

The D-10 red line: **do not read a third-party parser's source and hand-rewrite
a similar engine inside Xingwen.** Adoption is only allowed via an official
stable package / documented API / separately approved minimal vendored source.

Reviewer must confirm NONE of the following exist:

- [ ] No hand-written OCR engine (e.g. glyph matching, Tesseract-like loop).
- [ ] No hand-written layout engine (region proposals, reading-order heuristics).
- [ ] No hand-written table recognition (cell merging, ruling-line detection).
- [ ] No hand-written formula recognition / LaTeX reconstruction from pixels.
- [ ] No hand-written PDF glyph parser or reading-order engine.
- [ ] No copied third-party prompt, schema, or orchestration (renamed or not).
- [ ] No "avoid the dependency, so reimplement the capability" pattern.

If ANY of the above exists, the PR is **BLOCKED** and must be reverted to
adoption-only. This is non-negotiable regardless of test pass.

## 2. Vendor boundary (Domain vs Adapter)

- [ ] `app/schemas/scientific_document*.py` imports **zero** vendor packages
      (`paddleocr`, `docling`, `mineru`, `grobid`, `pp_structure`, …).
- [ ] Vendor package names/types do NOT appear as field names or type hints in
      the Canonical schema — only as `str` provenance values
      (`native_engine`, `visual_model_id`, …).
- [ ] A D-11 adapter (when built) lives under `services/scientific_document/*`
      and maps vendor output INTO the Canonical contract; the contract never
      imports the vendor.

## 3. Upstream adoption integrity

- [ ] Every adopted capability has an `approved` entry in
      `services/scientific_document/upstream_adoption.json`.
- [ ] Exact `package` + `package_version` (no `latest`/`main`/`master`).
- [ ] Exact `model_id` + `model_revision` for any model (no floating alias).
- [ ] `license` present; `model_weight_license` present when a model exists.
- [ ] `official_interface_used`, `network_behavior`, `cache_behavior`,
      `upgrade_strategy`, `explicitly_unused_scope` all filled from FIRST-PARTY
      sources (official repo / docs / release / registry), not blogs or memory.
- [ ] No production parser depends on an `evaluated_not_adopted` /
      `deferred` / `blocked` entry.

## 4. Quality semantics (anti-hallucination)

- [ ] `partial` keeps `unparsed != absent`; missing recognition is never
      treated as "does not exist in the paper".
- [ ] `unsupported` emits NO fabricated full text; no downstream model is
      allowed to auto-complete the gap.
- [ ] `accepted` is NOT interpreted as "scientific fact verified".
- [ ] `ScientificDataExtractionCandidate` carries NO canonical mapping / unit
      normalization / scientific admission fields.

## 5. Evidence / provenance chain

- [ ] Every `DocumentLocator` has an explicit coordinate system
      (top-left origin, points, inclusive, page-relative, normalized 0..1,
      empty/`None` semantics defined).
- [ ] A future `DocumentParse` can be traced back to
      `ResearchInput` content hash via `SourceSnapshot`.

## 6. Scope discipline

- [ ] No PostgreSQL `DocumentParse` tables / migrations (B-20 owns those).
- [ ] No `SourceSnapshot` DB materialization (B-20 owns those).
- [ ] No `PaperSummary` projection or Claim/Relation changes (D-12 / C-09).
- [ ] No HTTP endpoint or frontend component.
- [ ] No production Paddle / hybrid router / page router / model loader.
- [ ] Golden Set restricted PDFs are **local-only**; their full text is NOT
      committed to the repo.
