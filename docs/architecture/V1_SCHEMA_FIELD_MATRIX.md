# `/api` Phase 0 Schema Field Matrix

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Authority | `/api` Phase 0 Schema field mapping and drift decisions |

This matrix compares the frozen [`DATA_MODEL_V1.md`](DATA_MODEL_V1.md) with the
Pydantic authoring source. `required` refers to JSON Schema requiredness. A dash
means that no default exists.

## Data results and provenance

| Model | Domain field | v1 wire field | Type / enum | Required | Default | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| DatasetResponse | `id` | `dataset_id` | string | yes | — | Alias preserves v1 wire |
| DatasetResponse | `task_id` | same | string | yes | — | Aligned |
| DatasetResponse | `name` | same | string | yes | — | Aligned |
| DatasetResponse | `case_key` | same | `exoplanet_host_star` | yes | — | Aligned |
| DatasetResponse | `row_count` | same | integer >= 0 | yes | — | Aligned |
| DatasetResponse | `field_count` | same | integer >= 0 | yes | — | Aligned |
| DatasetResponse | `created_at` | same | datetime | yes | — | Aligned |
| DatasetResponse | transport `columns` | same | list[ColumnInfo] | yes | — | Existing v1 response extension |
| DatasetResponse | transport `rows` | same | list[object] | yes | — | Existing v1 response extension |
| DatasetResponse | transport `quality_score` | same | QualityScore/null | no | null | Existing v1 response extension |
| ColumnInfo | `name` | same | string | yes | — | FieldDefinition transport name |
| ColumnInfo | `label` | same | string | yes | — | Aligned |
| ColumnInfo | `unit` | same | string | yes | — | Aligned |
| ColumnInfo | `description` | same | string | yes | — | Aligned |
| ColumnInfo | `data_type` | same | string | yes | — | Aligned |
| ColumnInfo | `required` | same | boolean | yes | — | Aligned |
| ColumnInfo | `source_ids` | same | non-empty list[string] | yes | — | Aligned |
| ColumnInfo | `missing_rate` | same | number 0..1 | yes | — | Aligned |
| ColumnInfo | `mapping_rule` | same | string | yes | — | Aligned |
| SourceRecordItem | `id` | same | string | yes | — | SourceRecord transport name |
| SourceRecordItem | `task_id` | same | string | yes | — | Aligned |
| SourceRecordItem | `type` | same | `database \| paper_source \| paper \| cache \| manual_review` | yes | — | Aligned |
| SourceRecordItem | `name` | same | string | yes | — | Aligned |
| SourceRecordItem | `url` | same | string | yes | — | Aligned |
| SourceRecordItem | `query` | same | string | yes | — | Aligned |
| SourceRecordItem | `retrieved_at` | same | datetime | yes | — | Aligned |
| SourceRecordItem | `cached` | same | boolean | no | false | Aligned |
| SourceRecordItem | `license_note` | same | string/null | no | null | Aligned |
| QualityScore | `task_id` | same | string | yes | — | Aligned |
| QualityScore | `field_coverage` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `missing_rate` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `source_completeness` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `unit_consistency` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `paper_acquisition_reproducibility` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `paper_summary_completeness` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `literature_relation_evidence_rate` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `graph_evidence_completeness` | same | number 0..1 | yes | — | Aligned |
| QualityScore | `reproducibility` | same | number 0..1 | yes | — | Aligned |

## Paper acquisition

| Model | Domain field | v1 wire field | Type | Required | Default | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| PaperSearchQuery | `id` | `query_id` | string | yes | — | Alias preserves v1 wire |
| PaperSearchQuery | `task_id` | same | string | yes | — | Aligned |
| PaperSearchQuery | `case_key` | same | string | yes | — | Aligned |
| PaperSearchQuery | `keywords` | same | list[string] | yes | — | Aligned |
| PaperSearchQuery | `source_types` | same | list[string] | yes | — | Aligned |
| PaperSearchQuery | `filters` | same | object | yes | — | Aligned |
| PaperSearchQuery | `query_string` | same | string | yes | — | Aligned |
| PaperSearchQuery | `created_at` | same | datetime | yes | — | Aligned |
| PaperAcquisitionRun | `id` | `run_id` | string | yes | — | Alias preserves v1 wire |
| PaperAcquisitionRun | `task_id` | same | string | yes | — | Aligned |
| PaperAcquisitionRun | `query_id` | same | string | yes | — | Aligned |
| PaperAcquisitionRun | `status` | same | `pending \| running \| completed \| failed \| cached` | yes | — | Aligned |
| PaperAcquisitionRun | `candidate_count` | same | integer >= 0 | yes | — | Aligned |
| PaperAcquisitionRun | `selected_count` | same | integer >= 0 | yes | — | Aligned |
| PaperAcquisitionRun | `dedupe_rule` | same | string | yes | — | Aligned |
| PaperAcquisitionRun | `used_cache` | same | boolean | yes | — | Aligned |
| PaperAcquisitionRun | `started_at` | same | datetime | yes | — | Aligned |
| PaperAcquisitionRun | `finished_at` | same | datetime/null | no | null | Aligned |
| PaperCandidate | `id` | `candidate_id` | string | yes | — | Alias preserves v1 wire |
| PaperCandidate | `task_id` | same | string | yes | — | Aligned |
| PaperCandidate | `run_id` | same | string | yes | — | Aligned |
| PaperCandidate | `source_record_id` | same | string | yes | — | Aligned |
| PaperCandidate | `external_id` | same | string/null | no | null | Aligned |
| PaperCandidate | `title` | same | string | yes | — | Aligned |
| PaperCandidate | `authors` | same | list[string] | yes | — | Aligned |
| PaperCandidate | `year` | same | integer/null | no | null | Aligned |
| PaperCandidate | `doi` | same | string/null | no | null | Aligned |
| PaperCandidate | `arxiv_id` | same | string/null | no | null | Aligned |
| PaperCandidate | `url` | same | string/null | no | null | Aligned |
| PaperCandidate | `abstract` | same | string/null | no | null | Aligned |
| PaperCandidate | `relevance_score` | same | number 0..1 | yes | — | Aligned |
| PaperCandidate | `dedupe_key` | same | string | yes | — | Aligned |
| PaperCandidate | `selected` | same | boolean | yes | — | Aligned |
| PaperCandidate | `selection_reason` | same | string/null | no | null | Aligned |

## Paper and summary

| Model | Domain field | v1 wire field | Type | Required | Default | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| PaperItem | `id` | `paper_id` | string | yes | — | Alias preserves v1 wire |
| PaperItem | `candidate_id` | same | string | yes | — | Aligned |
| PaperItem | `task_id` | same | string | yes | — | Aligned |
| PaperItem | `title` | same | string | yes | — | Aligned |
| PaperItem | `authors` | same | list[string] | yes | — | Aligned |
| PaperItem | `year` | same | integer/null | no | null | Aligned |
| PaperItem | `doi` | absent | — | — | — | Deliberate: retained on candidate in v1 |
| PaperItem | `arxiv_id` | absent | — | — | — | Deliberate: retained on candidate in v1 |
| PaperItem | `url` | same | string/null | no | null | Aligned |
| PaperItem | `source_ids` | same | non-empty list[string] | yes | — | Aligned |
| PaperItem | transport `summary` | same | PaperSummary/null | no | null | Existing v1 response extension |
| PaperItem | transport `evidence_ids` | same | list[string] | no | empty | Existing v1 response extension |
| PaperSummary | `id` | same | string | yes | — | Aligned |
| PaperSummary | `paper_id` | same | string | yes | — | Aligned |
| PaperSummary | `research_goal` | same | string | yes | — | Aligned |
| PaperSummary | `method` | same | string | yes | — | Aligned |
| PaperSummary | `dataset` | same | string | yes | — | Aligned |
| PaperSummary | `findings` | same | list[string] | yes | — | Aligned |
| PaperSummary | `limitations` | same | list[string] | yes | — | Aligned |
| PaperSummary | `future_work` | same | list[string] | yes | — | Aligned |
| PaperSummary | `evidence_ids` | same | non-empty list[string] | yes | — | Aligned |
| PaperSummary | `model_name` | same | string | yes | — | Aligned |
| PaperSummary | `prompt_version` | same | string | yes | — | Aligned |

## Literature reasoning

| Model | Domain field | v1 wire field | Type | Required | Default | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| LiteratureClaim | `id` | `claim_id` | string | yes | — | Alias preserves v1 wire |
| LiteratureClaim | `task_id` | same | string | yes | — | Aligned |
| LiteratureClaim | `paper_id` | same | string | yes | — | Aligned |
| LiteratureClaim | `claim_type` | same | `goal \| method \| dataset \| finding \| limitation \| future_work` | yes | — | Aligned |
| LiteratureClaim | `text` | same | string | yes | — | Aligned |
| LiteratureClaim | `normalized_text` | same | string | yes | — | Aligned |
| LiteratureClaim | `evidence_ids` | same | non-empty list[string] | yes | — | Aligned |
| LiteratureClaim | `confidence` | same | number 0..1 | yes | — | Aligned |
| LiteratureRelation | `id` | `relation_id` | string | yes | — | Alias preserves v1 wire |
| LiteratureRelation | `task_id` | same | string | yes | — | Aligned |
| LiteratureRelation | `source_claim_id` | same | string | yes | — | Aligned |
| LiteratureRelation | `target_claim_id` | same | string | yes | — | Aligned |
| LiteratureRelation | `relation_type` | same | `supports \| extends \| derived_from \| limits \| contradicts \| uses_same_dataset \| compares_method` | yes | — | Aligned |
| LiteratureRelation | `reasoning_trace_id` | same | string | yes | — | Required for accepted v1 relations |
| LiteratureRelation | `evidence_ids` | same | non-empty list[string] | yes | — | Aligned |
| LiteratureRelation | `confidence` | same | number 0..1 | yes | — | Aligned |
| ReasoningTrace | `id` | `trace_id` | string | yes | — | Alias preserves v1 wire |
| ReasoningTrace | `task_id` | same | string | yes | — | Aligned |
| ReasoningTrace | `relation_id` | same | string | yes | — | Aligned |
| ReasoningTrace | `steps` | same | list[TraceStep] | yes | — | Aligned |
| ReasoningTrace | `evidence_ids` | same | non-empty list[string] | yes | — | Aligned |
| ReasoningTrace | `model_name` | same | string | yes | — | Aligned |
| ReasoningTrace | `prompt_version` | same | string | yes | — | Aligned |

## Evidence and embedded snapshot

| Model | Domain field | v1 wire field | Type | Required | Default | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| EvidenceResponse | `id` | same | string | yes | — | Aligned |
| EvidenceResponse | `task_id` | same | string | yes | — | Aligned |
| EvidenceResponse | `type` | same | `database_query \| paper_search \| paper_metadata \| paper_text \| model_extraction \| reasoning_trace \| user_feedback \| cache_record` | yes | — | Aligned |
| EvidenceResponse | `source_id` | same | string/null | no | null | Conditional by evidence type |
| EvidenceResponse | `paper_id` | same | string/null | no | null | Conditional by evidence type |
| EvidenceResponse | `target_type` | same | string | yes | — | Aligned |
| EvidenceResponse | `target_id` | same | string | yes | — | Aligned |
| EvidenceResponse | `content` | same | string/null | no | null | Conditional by evidence type |
| EvidenceResponse | `locator` | same | Locator/null | no | null | Conditional by evidence type |
| EvidenceResponse | `quote_or_value` | same | string/null | no | null | Conditional by evidence type |
| EvidenceResponse | `extraction_method` | same | string | yes | — | Aligned |
| EvidenceResponse | `source_snapshot` | same | SourceSnapshot | yes | — | Aligned |
| EvidenceResponse | `confidence` | same | number 0..1 | yes | — | Aligned |
| EvidenceResponse | `created_at` | same | datetime | yes | — | Aligned |
| SourceSnapshot | `retrieved_at` | same | datetime | yes | — | Aligned |
| SourceSnapshot | `query_hash` | same | string/null | no | null | Aligned |
| SourceSnapshot | expanded v2 fields | absent | — | — | — | Deliberate reduced embedded v1 DTO |

Exact field sets, required arrays, aliases, defaults, and enum values are
enforced in `apps/api/tests/test_pipeline_contract.py`. Generated manifest
coverage and stale output are enforced by the committed generated contracts and
CI `--check`. Any change above requires updating the frozen v1 document and the
corresponding exact assertion in the same change.
