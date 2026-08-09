# Cross-source Entity Alignment

| Field     | Value                                                         |
| --------- | ------------------------------------------------------------- |
| Status    | Accepted                                                      |
| Scope     | Deterministic TOI/PS entity alignment                         |
| Authority | Runtime behavior, Evidence, review input, and benchmark rules |

## 1. Scope and boundaries

The alignment engine consumes the immutable outputs of the primary and supplemental
acquisition adapters. The primary source is
`nasa_exoplanet_archive.toi`; the supplemental source is
`nasa_exoplanet_archive.ps`. Each side retains its own `SourceSnapshotRecord`,
query hash, content hash, source mode, data level, completion status, cursor,
raw row key, and raw-record content hash.

The public data-layer entry point is:

```python
align_cross_source_records(input: CrossmatchInput) -> CrossmatchResult
```

The function is deterministic and has no HTTP, database, cache, Run, Router, or
Artifact side effects. It never invokes either source Adapter. Canonical field
mapping, quality scoring, unit conversion, Dataset construction,
Artifact publication, and runtime orchestration are owned by their respective
responsibility boundaries.

## 2. Versioned inputs

The Pydantic authoring source is
`apps/api/src/app/schemas/crossmatch.py`. All contracts are immutable and reject
extra fields. The pipeline pins:

- Case and Field Manifest versions and content hashes;
- the versioned Crossmatch RuleSet and its content hash;
- producer name and version;
- the versioned entity-alias catalog;
- the complete frozen acquisition SourcePolicy and its version/content hash;
- both complete `SourceSnapshotRecord` values;
- both completion scopes and canonical raw-record references;
- optional explicit `ManualReviewDecision` hashes.

Crossmatch source fields are discovered through Field Manifest `SourceAlias`
entries only when the canonical field is declared as a `crossmatch_key`.
`SourceAlias` maps a source column to a canonical field; it is not a value-level
name alias registry. Value aliases live only in the versioned entity-alias
catalog.

## 3. Input invariants and completion scope

`CrossmatchSourceInput` is a typed projection of one acquisition result. It
rejects:

- a record `source_id` that differs from its Snapshot;
- duplicate row keys or record hashes;
- Snapshot request metadata that contradicts the declared origin.

`CrossmatchInput` validates both typed source origins against the versioned
`source-policy.v1.json` carried by the input and pinned by the RuleSet. The
frozen SourcePolicy is the only allowlist; neither the Schema nor the engine
keeps a second hard-coded source-mode/data-level matrix.

The engine also rejects reversed or unauthorized sources and any source absent
from the frozen Manifest bundle. It first checks `max_left_records` and
`max_right_records`, then normalizes candidates and computes
`left_hosts × right_hosts + left_planets × right_assertions` before entering
any matching loop. That eligible comparison count is checked against
`max_candidate_pairs`. Capacity overflow fails with
`CROSSMATCH_CAPACITY_EXCEEDED`; records and candidates are never silently
truncated.

With a complete opposite source, a candidate without an edge is `unmatched`.
With a `truncated` or `unknown` opposite source, it is `inconclusive`. The result
retains both completion objects, so coverage always means the observed
Snapshot scope and never proves that an object is absent upstream.

## 4. Normalization and matching policy

Normalization is conservative and versioned:

- TIC and Gaia DR3 identifiers accept only positive catalog integers and known
  prefixes; catalog identifiers are bounded to 19 digits.
- TOI accepts the primary acquisition numeric form plus `TOI 1243.01` and `TOI-1243.01`, while
  retaining the numeric candidate suffix. It never infers a lettered planet
  name.
- Names use Unicode NFKC, trimmed/collapsed whitespace, and `casefold`.
- ICRS degree coordinates require finite RA in `[0, 360)` (with `360`
  normalized to `0`) and Dec in `[-90, 90]`.
- Angular separation uses a stable spherical haversine calculation and handles
  RA wrap-around and poles.

Closed automatic methods are `exact_identifier`, `curated_entity_alias`,
`coordinate`, and `compound`. `manual_review` is deliberately not an automatic
method. Coordinate-only edges are never automatically accepted. The frozen
RuleSet records the strict and manual-review thresholds, method priority,
confidence values, conflict policy versions, and capacity limits.

Equal TIC values confirm host-star identity only; they do not infer planet
identity. Distinct PS `pl_refname` rows remain distinct planet assertions.
Curated planet aliases require independent host corroboration for automatic
acceptance. Conflicting identifiers, identifier/coordinate disagreement, and
competing aliases remain explicit conflict groups.

## 5. Evidence and review

Every candidate retains a `SourceRecordReference` with Snapshot/query/content
hashes, source-specific row key, raw-record hash, object type, and source entity
key. Each normalized identity value retains its Manifest-derived raw-field
locator and normalization-rule version.

Every edge has deterministic conditions and `CrossmatchEvidence` tied to both
candidate sides, both Snapshot/query boundaries, raw fields, RuleSet identity,
confidence, confidence band, and automatic decision. Coordinate Evidence
records separation plus both strict and manual-review thresholds. The
`CrossmatchResult` validator cross-checks Candidate, Edge, Evidence, Record,
metrics, Snapshot, RuleSet, and producer references even if a caller recomputes
hashes. Each Evidence locator must identify the referenced candidate's source
row and the exact normalized identity raw field required by its condition.
Condition IDs are derived from their complete payload; coordinate separation,
operator, thresholds, and rule reference are checked against the candidate
coordinates and frozen RuleSet. Conflict codes are derived from the admitted
Edge/Evidence component instead of trusted as caller metadata.

Identifier and alias conditions carry only field/left/right values; coordinate
conditions carry only separation plus both thresholds. `source_scope` remains a
reserved v1 operator value and is rejected as an executable condition because
v1 defines no dedicated payload for it.

An optional `ManualReviewDecision` is a separate, hashed input. It binds the
pre-adjudication source-input hash, full RuleSet identity, logical match key,
left/right candidate IDs, Evidence IDs, reviewer kind, rationale, and
timezone-aware timestamp. Stale or mismatched bindings fail closed. Applying a
review records the adjudication audit fields but preserves the automatic
`review_required` or `conflict` decision. Benchmark decisions use
`reviewer_kind=benchmark_fixture` and are not represented as human or
scientific approval.

Every result carries a typed `admission_context` containing the frozen RuleSet,
AliasCatalog, SourcePolicy, source-input hash, both source origins/completion
scopes, and complete manual-decision inputs required for admission. The result
validator binds curated-alias conditions to an actual catalog entry, binds
source mode/data level to Snapshot metadata, and binds every projected
adjudication field to its typed decision and `input_hash`; a caller cannot
substitute a same-row field, false-live origin, completion scope, fabricated
alias ID, conflict code, or reviewer while retaining the admitted provenance
hashes. The externally trusted `input_hash`/`source_input_hash` remains the
authenticity anchor; the embedded context provides a complete typed consistency
check and does not replace trust in that upstream hash.

A record logical match key is derived from the record type, entity level, and
both candidate-id sets, so paired and conflict-group records over the same
candidates stay in separate namespaces and manual-review bindings resolve
unambiguously.

`MatchDecision.rejected` is a reserved Contract value: a structured record may
carry it and still passes candidate, Evidence, RuleSet, and reference
validation, but the automatic engine does not emit it. `manual_review` is not a
method, and a human `AdjudicationDecision.rejected` is a separate audit input
that records the adjudication without overriding the automatic decision; it is
never presented as an automatic `MatchDecision.rejected` engine output.

## 6. Stable identity and metrics

`source_input_hash` covers manifests, rules, aliases, snapshots, completion
scope, origin, and canonically sorted raw records. `input_hash` additionally
binds sorted manual-decision hashes. `output_hash` covers the stable result and
equals the canonical result `content_hash`. All hashes exclude wall-clock
latency, logs, branch names, output paths, and the hash field itself.

Logical match keys are based on source identities and row keys; they are
separate from mutable result content hashes. Input record order and JSON object
key order do not affect output ordering or hashes.

Metrics report record/candidate counts, paired/matched/ambiguous/conflict and
side-specific unmatched counts, inconclusive and manual-review-required counts,
topology counts, confidence and method distributions, deterministic error
references, and numerator/denominator/value triples for coverage and rates.
Metrics are recomputed during admission from Candidate, Edge, Evidence, and
Record members. `left_record_count` and `right_record_count` count distinct
source-row references represented by admitted candidates rather than trusting
caller-provided totals.
`candidate_pair_count` is the number of materialized `CandidateEdge` records,
not the eligible comparison count used by the capacity preflight.
They describe processing coverage and traceability, not scientific correctness
or final data quality.

## 7. Frozen benchmark and limitations

`services/data_pipeline/benchmarks/exoplanet_host_star/crossmatch-benchmark.v1.json`
contains 28 machine-executable synthetic scenarios. It covers exact identifier
topologies (including many-to-many), host-only TIC semantics, reference-row
preservation, the absent TOI Gaia mapping, strict/manual coordinate bands, RA
wrap and poles, multiple candidates, aliases and conflicts, completion scope,
duplicate record and Snapshot/source failures, invalid coordinates, and
valid/stale manual-review bindings. Its capacity scenario expands four raw
record pairs into eight eligible entity-level comparisons and verifies fail-fast
rejection. Parameterized pipeline tests additionally cover `unknown` scope.

The benchmark and alias entries are synthetic fixtures, not scientific ground
truth. The frozen TOI Manifest does not expose Gaia DR3, so the alignment result retains PS Gaia
values but does not fabricate a TOI Gaia field merely to claim an exact Gaia
cross-source case. Existing recorded TOI and PS fixtures also do not share a
verified entity identity; they are acquisition evidence and are not presented
as a real successful crossmatch.

## 8. Validation

Relevant checks are:

```powershell
uv run --project apps/api pytest apps/api/tests/test_crossmatch_contract.py `
  apps/api/tests/test_crossmatch_identity.py `
  apps/api/tests/test_crossmatch_policy.py `
  apps/api/tests/test_crossmatch_pipeline.py `
  apps/api/tests/test_crossmatch_benchmark.py
uv run --project apps/api python scripts/export_schemas.py `
  --output packages/schemas/generated/phase0 `
  --include DatasetResponse --include ColumnInfo --include QualityScore `
  --include SourceRecordItem --include PaperSearchQuery `
  --include PaperAcquisitionRun --include PaperCandidate --include PaperSummary `
  --include LiteratureClaim --include LiteratureRelation `
  --include ReasoningTrace --include EvidenceResponse --include SourceSnapshot `
  --include DataSourceCompletion --include CrossmatchInput `
  --include CrossmatchResult --include CrossmatchBenchmarkManifest `
  --include CrossmatchBenchmarkReport --check
python scripts/check_foundation.py
node scripts/check-docs.mjs
git diff --check
```

The JSON Schema export includes the public alignment input, output, completion,
benchmark-manifest, and benchmark-report contracts. No HTTP route or duplicate
transport DTO is introduced.
