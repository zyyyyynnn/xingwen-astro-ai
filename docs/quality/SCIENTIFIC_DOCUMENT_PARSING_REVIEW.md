# Scientific Document Parsing — Review Checklist (D-10 / #190)

| 元数据 | 值 |
| --- | --- |
| Status | Accepted |
| Authority | Scientific Document Parsing 人工审查清单：reference-after-rewrite、vendor 边界与采用完整性 |

This checklist is the human counterpart to
`scripts/check_d10_governance.py`. Machine gates can validate imports, versions,
manifests and tracked files; they cannot determine whether a developer read an
upstream implementation and rewrote the same engine by hand.

## 1. Reference-after-rewrite — highest priority

The D-10 red line: third-party parser capability is adopted through an official
stable package/documented API (or a separately approved minimal vendored source),
not reconstructed inside Xingwen.

Reviewer must confirm:

- [ ] No hand-written OCR engine.
- [ ] No hand-written layout/reading-order engine.
- [ ] No hand-written table recognition or ruling/cell reconstruction engine.
- [ ] No hand-written formula recognition/LaTeX reconstruction from pixels.
- [ ] No hand-written PDF glyph parser.
- [ ] No copied/renamed third-party prompt, schema or orchestration.
- [ ] No “avoid the dependency, therefore reimplement it” path.
- [ ] `docs/references/**` is used only for understanding/benchmark/risk, never as
      production source Authority.

Any violation is `verdict: BLOCKED` regardless of CI status.

## 2. Canonical Domain vs Adapter

- [ ] `app/schemas/scientific_document.py` imports no parser vendor package/type.
- [ ] Canonical field/type names are Xingwen-owned, not vendor raw objects.
- [ ] There is exactly one parser Port input (`DocumentParseInput`) and one
      output (`DocumentParseCandidate`).
- [ ] `source_type`/`mime_type` are explicit facts; no output→input reconstruction
      or default provenance exists.
- [ ] A D-11 adapter maps upstream output **into** the Canonical Contract and does
      not leak raw vendor objects across the Port.

## 3. Canonical integrity

- [ ] Page/block/table identities are unique and references are not dangling.
- [ ] Every block appears exactly once in its owning page membership.
- [ ] Table/formula/figure objects reference a block of the correct kind/page.
- [ ] Block/table-cell/formula/figure geometry stays within owning page bounds.
- [ ] Table spans do not exceed/overlap the logical grid; merged cells do not
      require fabricated placeholder cells.
- [ ] `DocumentLocator` is the only locator representation; cell locator requires
      table identity and text span requires block identity.
- [ ] Candidate config/native/visual/model provenance is internally consistent
      with its parser profile.

## 4. Upstream adoption integrity

- [ ] Every consumable capability has `adoption_status=approved` in
      `services/scientific_document/upstream_adoption.json`.
- [ ] Approved package has exact `package_version`; no ranges/floating aliases.
- [ ] Approved Python `import_roots` are declared explicitly in the manifest;
      the governance gate does not guess package→module mappings.
- [ ] Model capability has exact model id/resolved id and immutable revision;
      Hugging Face revisions are pinned to a commit, not `main`/`latest`.
- [ ] Code and model licenses are recorded separately where applicable.
- [ ] Official interface, unused scope, CPU/GPU, network/download/cache/offline
      behavior, risks and upgrade strategy come from first-party evidence.
- [ ] Production code does not consume deferred/blocked/evaluated-not-adopted
      entries.

## 5. Quality semantics

- [ ] `accepted` is parser admission, not scientific verification.
- [ ] `partial` preserves `unparsed != absent`.
- [ ] Whole-document `unsupported` does not contain accepted blocks.
- [ ] Unsupported structured table/formula/figure output is not fabricated.
- [ ] `ScientificDataExtractionCandidate` contains no canonical mapping, unit
      normalization, scientific acceptance or publication state.

## 6. Evidence / provenance

- [ ] Coordinates are top-left origin, absolute PDF points, page-relative and
      **not normalized**; unknown bbox is `None`.
- [ ] A future persisted locator can trace through DocumentParse →
      SourceSnapshot → ResearchInput/content hash.
- [ ] Restricted/full-text content is not copied into public/logging surfaces.

## 7. Golden Set / Benchmark truthfulness

- [ ] Fixture, Golden, Recorded and Live classifications are not conflated.
- [ ] Restricted real PDFs remain local-only; repository entries use real
      identifiers/provenance rather than placeholders.
- [ ] Committed fixture bytes match manifest hashes; missing/tampered fixtures
      fail closed.
- [ ] Raster/scanned fixture genuinely has no text layer.
- [ ] Golden content hash covers entry provenance/license/content/annotations,
      excluding only explicitly volatile metadata.
- [ ] Benchmark metrics are measured against declared annotations when possible;
      unmeasured capabilities are `not_run`/`unsupported`/`not_applicable`, not
      silently reported as zero accuracy.
- [ ] Report hash self-verifies and remains deterministic across run time.
- [ ] Required real native baseline tests execute in CI and do not skip when the
      benchmark dependency group is missing.

## 8. Scope discipline

- [ ] No production Paddle/hybrid/page router/model loader in D-10.
- [ ] No DocumentParse PostgreSQL tables/migrations or SourceSnapshot DB
      materialization (B-20).
- [ ] No PaperSummary/Claim/Relation/C mapping changes (D-12/C-09 and existing
      downstream tasks own those).
- [ ] No HTTP endpoint, frontend, HTML parser or plot digitizer.
- [ ] No model weights committed to Git.

## 9. Merge gate

Before merge, reviewer must bind the verdict to the exact PR HEAD and verify:

- [ ] `origin/main` has not drifted from the task's locked base unexpectedly.
- [ ] Foundation, Backend, Frontend and X-01 integration jobs are green.
- [ ] D-10 native benchmark step installed the locked benchmark dependency group,
      ran real native tests, produced a report and validated it inside the same
      locked uv environment.
- [ ] No unresolved review blocker/thread remains.
- [ ] PR description and Authority reflect the exact final HEAD and actual test
      evidence.

Only then may the formal technical conclusion be `verdict: PASS`.
