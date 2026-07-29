# Phase 0 `/api` Data Model

| Metadata | Value |
| --- | --- |
| Status | Accepted |
| Authority | `/api` Phase 0 DTO contract |
| Historical source | `DATA_MODEL.md` at `9dddef0754443e8645e506d705c0f52ef7a165ca` |
| Authoring source | `apps/api/src/app/schemas` |
| Scope | Fixture-backed Phase 0 `/api`; not the `DATA_MODEL.md` target model |

This document freezes the Phase 0 contract used by Issue #26. The current
[`DATA_MODEL.md`](DATA_MODEL.md) remains the `/api` target model and must not
be used to change these v1 DTOs implicitly. A deliberate v1 deviation must be
recorded in [`V1_SCHEMA_FIELD_MATRIX.md`](V1_SCHEMA_FIELD_MATRIX.md) and covered
by contract tests.

All timestamps are timezone-aware ISO 8601 values. Fields listed below are
required unless marked `optional` or assigned an explicit default.

## Data results and provenance

### Dataset

The v1 transport class is `DatasetResponse` and keeps `dataset_id` as the wire
alias for domain `id`.

| Field | Type |
| --- | --- |
| `dataset_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `name` | string |
| `case_key` | `exoplanet_host_star` |
| `row_count` | integer, `>= 0` |
| `field_count` | integer, `>= 0` |
| `created_at` | datetime |
| `columns` | list[ColumnInfo] |
| `rows` | list[object] |
| `quality_score` | QualityScore or null; default null |

### FieldDefinition

The historical entity is represented by the v1 transport class `ColumnInfo`.

| Field | Type |
| --- | --- |
| `name` | string |
| `label` | string |
| `unit` | string |
| `description` | string |
| `data_type` | string |
| `required` | boolean |
| `source_ids` | non-empty list[string] |
| `missing_rate` | number, `0..1` |
| `mapping_rule` | string |

### SourceRecord

The v1 transport class is `SourceRecordItem`.

| Field | Type |
| --- | --- |
| `id` | string |
| `task_id` | string |
| `type` | `database | paper_source | paper | cache | manual_review` |
| `name` | string |
| `url` | string |
| `query` | string |
| `retrieved_at` | datetime |
| `cached` | boolean; default false |
| `license_note` | string or null; default null |

### QualityScore

| Field | Type |
| --- | --- |
| `task_id` | string |
| `field_coverage` | number, `0..1` |
| `missing_rate` | number, `0..1` |
| `source_completeness` | number, `0..1` |
| `unit_consistency` | number, `0..1` |
| `paper_acquisition_reproducibility` | number, `0..1` |
| `paper_summary_completeness` | number, `0..1` |
| `literature_relation_evidence_rate` | number, `0..1` |
| `graph_evidence_completeness` | number, `0..1` |
| `reproducibility` | number, `0..1` |

## Paper acquisition

### PaperSearchQuery

| Field | Type |
| --- | --- |
| `query_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `case_key` | `exoplanet_host_star` |
| `keywords` | list[string] |
| `source_types` | list[string] |
| `filters` | object |
| `query_string` | string |
| `created_at` | datetime |

### PaperAcquisitionRun

| Field | Type |
| --- | --- |
| `run_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `query_id` | string |
| `status` | `pending | running | completed | failed | cached` |
| `candidate_count` | integer, `>= 0` |
| `selected_count` | integer, `>= 0` |
| `dedupe_rule` | string |
| `used_cache` | boolean |
| `started_at` | datetime |
| `finished_at` | datetime or null; default null |

### PaperCandidate

| Field | Type |
| --- | --- |
| `candidate_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `run_id` | string |
| `source_record_id` | string |
| `external_id` | string or null; default null |
| `title` | string |
| `authors` | list[string] |
| `year` | integer or null; default null |
| `doi` | string or null; default null |
| `arxiv_id` | string or null; default null |
| `url` | string or null; default null |
| `abstract` | string or null; default null |
| `relevance_score` | number, `0..1` |
| `dedupe_key` | string |
| `selected` | boolean |
| `selection_reason` | string or null; default null |

## Selected paper and summary

### Paper

The v1 transport class is `PaperItem`.

| Field | Type |
| --- | --- |
| `paper_id` | string; legacy wire name for domain `id` |
| `candidate_id` | string |
| `task_id` | string |
| `title` | string |
| `authors` | list[string] |
| `year` | integer or null; default null |
| `url` | string or null; default null |
| `source_ids` | non-empty list[string] |
| `summary` | PaperSummary or null; default null |
| `evidence_ids` | list[string]; default empty |

`doi` and `arxiv_id` remain represented by PaperCandidate in the v1 response.
This is a deliberate transport difference from the historical entity example.

### PaperSummary

| Field | Type |
| --- | --- |
| `id` | string |
| `paper_id` | string |
| `research_goal` | string |
| `method` | string |
| `dataset` | string |
| `findings` | list[string] |
| `limitations` | list[string] |
| `future_work` | list[string] |
| `evidence_ids` | non-empty list[string] |
| `model_name` | string |
| `prompt_version` | string |

## Literature reasoning

### LiteratureClaim

| Field | Type |
| --- | --- |
| `claim_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `paper_id` | string |
| `claim_type` | `goal | method | dataset | finding | limitation | future_work` |
| `text` | string |
| `normalized_text` | string |
| `evidence_ids` | non-empty list[string] |
| `confidence` | number, `0..1` |

### LiteratureRelation

| Field | Type |
| --- | --- |
| `relation_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `source_claim_id` | string |
| `target_claim_id` | string |
| `relation_type` | `supports | extends | derived_from | limits | contradicts | uses_same_dataset | compares_method` |
| `reasoning_trace_id` | string |
| `evidence_ids` | non-empty list[string] |
| `confidence` | number, `0..1` |

### ReasoningTrace

| Field | Type |
| --- | --- |
| `trace_id` | string; legacy wire name for domain `id` |
| `task_id` | string |
| `relation_id` | string |
| `steps` | list[TraceStep] |
| `evidence_ids` | non-empty list[string] |
| `model_name` | string |
| `prompt_version` | string |

`TraceStep` requires `order`, `claim_id`, and `rationale`.

## Evidence

### Evidence

The v1 transport class remains `EvidenceResponse` to preserve imports.

| Field | Type |
| --- | --- |
| `id` | string |
| `task_id` | string |
| `type` | `database_query | paper_search | paper_metadata | paper_text | model_extraction | reasoning_trace | user_feedback | cache_record` |
| `source_id` | string or null; default null |
| `paper_id` | string or null; default null |
| `target_type` | string |
| `target_id` | string |
| `content` | string or null; default null |
| `locator` | Locator or null; default null |
| `quote_or_value` | string or null; default null |
| `extraction_method` | string |
| `source_snapshot` | SourceSnapshot |
| `confidence` | number, `0..1` |
| `created_at` | datetime |

`source_id`, `paper_id`, `content`, `locator`, and `quote_or_value` are nullable
because database, paper, model, feedback, and cache evidence do not share the
same locator. `target_*`, extraction metadata, snapshot, confidence, and time
remain required so an accepted result is auditable.

### SourceSnapshot

The historical v1 Evidence response embeds only:

| Field | Type |
| --- | --- |
| `retrieved_at` | datetime |
| `query_hash` | string or null; default null |

This intentionally reduced embedded snapshot is frozen for v1 compatibility.
The expanded SourceSnapshot defined by the target `DATA_MODEL.md` belongs to
the target `/api` model and must not be backported by silently changing the v1
wire response.

## Evidence invariants

- PaperSummary, LiteratureClaim, LiteratureRelation, and ReasoningTrace require
  at least one Evidence id.
- LiteratureRelation requires a ReasoningTrace id.
- Graph-edge invariants remain defined by the existing v1 graph DTO tests.
- Fixture data is identified as Fixture and is not represented as a live or
  cached scientific result.
