# Data Model

本文档定义 MVP 核心实体。实现时可映射为 PostgreSQL 表、Pydantic Model 和前端 TypeScript 类型。

## 1. Entity Overview

| 实体 | 用途 | 主要消费者 |
| --- | --- | --- |
| `ResearchTask` | 记录一次科研任务 | 前端、后端 |
| `TaskStep` | 记录任务步骤状态 | 前端时间线 |
| `Dataset` | 标准化数据集 | 数据页、导出 |
| `FieldDefinition` | 字段字典 | 数据页、质量评分 |
| `SourceRecord` | 来源记录 | 溯源报告、图谱 |
| `PaperSearchQuery` | 记录论文检索条件 | 论文获取页、复现 |
| `PaperAcquisitionRun` | 记录一次论文获取过程 | 论文获取页、缓存 |
| `PaperCandidate` | 自动获取的论文候选 | 论文获取页、文献总结 |
| `Paper` | 入选文献信息 | 文献页、图谱 |
| `PaperSummary` | 文献结构化总结 | 文献页 |
| `LiteratureClaim` | 从论文中抽取的研究主张 | 推理页、图谱 |
| `LiteratureRelation` | 跨文献逻辑关系 | 推理页、图谱 |
| `ReasoningTrace` | 跨文献推理链路 | 推理页、证据详情 |
| `Evidence` | 数据/文献/推理/图谱证据 | 图谱、溯源详情 |
| `GraphNode` | 图谱节点 | 图谱页 |
| `GraphEdge` | 图谱边 | 图谱页 |
| `QualityScore` | 质量评分 | 数据页、验收 |
| `UserFeedback` | 用户反馈与修正记录 | 反馈页、后端 |

## 2. ResearchTask

```json
{
  "id": "task_001",
  "goal": "string",
  "case_key": "exoplanet_host_star",
  "status": "pending",
  "progress": 0,
  "used_cache": false,
  "created_at": "2026-07-04T10:00:00Z",
  "updated_at": "2026-07-04T10:00:00Z"
}
```

`used_cache` 是结果来源标记，不是任务状态。任务实时运行失败但成功使用缓存兜底时，状态仍应进入 `completed`，并由 `used_cache`、`SourceRecord.cached` 和响应 `meta.cached` 表达缓存命中。

## 3. TaskStep

```json
{
  "id": "step_001",
  "task_id": "task_001",
  "key": "searching_papers",
  "label": "获取主案例论文",
  "status": "running",
  "message": "正在检索主案例相关论文候选",
  "started_at": "2026-07-04T10:01:00Z",
  "finished_at": null
}
```

## 4. Dataset

```json
{
  "id": "dataset_001",
  "task_id": "task_001",
  "name": "exoplanet_host_star_dataset",
  "case_key": "exoplanet_host_star",
  "row_count": 120,
  "field_count": 12,
  "created_at": "2026-07-04T10:03:00Z"
}
```

数据行存储建议：MVP 可先用 JSONB 保存 `rows`，稳定后再拆成规范化表。

## 5. FieldDefinition

```json
{
  "name": "pl_orbper",
  "label": "Orbital Period",
  "unit": "day",
  "description": "Planet orbital period",
  "data_type": "number",
  "required": true,
  "source_ids": ["source_nasa_exoplanet_archive"],
  "missing_rate": 0.08,
  "mapping_rule": "NASA Exoplanet Archive: pl_orbper -> pl_orbper"
}
```

## 6. SourceRecord

```json
{
  "id": "source_nasa_exoplanet_archive",
  "task_id": "task_001",
  "type": "database",
  "name": "NASA Exoplanet Archive",
  "url": "https://exoplanetarchive.ipac.caltech.edu/",
  "query": "string",
  "retrieved_at": "2026-07-04T10:01:00Z",
  "cached": false,
  "license_note": "public archive"
}
```

`SourceRecord.type` 可选：`database`、`paper_source`、`paper`、`cache`、`manual_review`。

## 7. PaperSearchQuery

```json
{
  "id": "paper_query_001",
  "task_id": "task_001",
  "case_key": "exoplanet_host_star",
  "keywords": ["exoplanet candidate", "host star", "orbital period"],
  "source_types": ["paper_source"],
  "filters": {
    "year_from": 2015,
    "max_results": 20
  },
  "query_string": "exoplanet candidate host star orbital period",
  "created_at": "2026-07-04T10:04:00Z"
}
```

## 8. PaperAcquisitionRun

```json
{
  "id": "paper_run_001",
  "task_id": "task_001",
  "query_id": "paper_query_001",
  "status": "completed",
  "candidate_count": 12,
  "selected_count": 6,
  "dedupe_rule": "doi_or_title_year",
  "used_cache": false,
  "started_at": "2026-07-04T10:04:00Z",
  "finished_at": "2026-07-04T10:05:30Z"
}
```

## 9. PaperCandidate

```json
{
  "id": "paper_candidate_001",
  "task_id": "task_001",
  "run_id": "paper_run_001",
  "source_record_id": "source_ads_or_arxiv",
  "external_id": "string",
  "title": "string",
  "authors": ["string"],
  "year": 2024,
  "doi": "string",
  "arxiv_id": "string",
  "url": "string",
  "abstract": "string",
  "relevance_score": 0.86,
  "dedupe_key": "doi:string",
  "selected": true,
  "selection_reason": "Matches host-star parameter integration case"
}
```

`PaperCandidate` 来自自动检索或真实运行缓存。手写 seed list 只能作为评测基准、fallback 或人工校验，不得冒充自动获取结果。

## 10. Paper

```json
{
  "id": "paper_001",
  "candidate_id": "paper_candidate_001",
  "task_id": "task_001",
  "title": "string",
  "authors": ["string"],
  "year": 2024,
  "doi": "string",
  "arxiv_id": "string",
  "url": "string",
  "source_ids": ["source_ads_or_arxiv"]
}
```

## 11. PaperSummary

```json
{
  "id": "summary_001",
  "paper_id": "paper_001",
  "research_goal": "string",
  "method": "string",
  "dataset": "string",
  "findings": ["string"],
  "limitations": ["string"],
  "future_work": ["string"],
  "evidence_ids": ["evidence_001"],
  "model_name": "qwen-plus",
  "prompt_version": "paper-summary-v1"
}
```

## 12. LiteratureClaim

```json
{
  "id": "claim_001",
  "task_id": "task_001",
  "paper_id": "paper_001",
  "claim_type": "finding",
  "text": "string",
  "normalized_text": "string",
  "evidence_ids": ["evidence_001"],
  "confidence": 0.82
}
```

`claim_type` 可选：`goal`、`method`、`dataset`、`finding`、`limitation`、`future_work`。

## 13. LiteratureRelation

```json
{
  "id": "relation_001",
  "task_id": "task_001",
  "source_claim_id": "claim_001",
  "target_claim_id": "claim_002",
  "relation_type": "supports",
  "reasoning_trace_id": "trace_001",
  "evidence_ids": ["evidence_001", "evidence_002"],
  "confidence": 0.78
}
```

`relation_type` 可选：`supports`、`extends`、`derived_from`、`limits`、`contradicts`、`uses_same_dataset`、`compares_method`。

## 14. ReasoningTrace

```json
{
  "id": "trace_001",
  "task_id": "task_001",
  "relation_id": "relation_001",
  "steps": [
    {
      "order": 1,
      "claim_id": "claim_001",
      "rationale": "Paper A reports the same host-star parameter dependency."
    },
    {
      "order": 2,
      "claim_id": "claim_002",
      "rationale": "Paper B extends the analysis to a newer candidate set."
    }
  ],
  "evidence_ids": ["evidence_001", "evidence_002"],
  "model_name": "qwen-plus",
  "prompt_version": "literature-reasoning-v1"
}
```

`ReasoningTrace` 是跨文献逻辑推理的可审查记录。没有 `evidence_ids` 的推理只能作为候选，不进入最终图谱。

## 15. Evidence

```json
{
  "id": "evidence_001",
  "task_id": "task_001",
  "type": "paper_text",
  "source_id": "source_ads_or_arxiv",
  "paper_id": "paper_001",
  "target_type": "claim",
  "target_id": "claim_001",
  "content": "Claim extracted from paper abstract or accessible text.",
  "locator": {
    "kind": "abstract",
    "value": "abstract"
  },
  "quote_or_value": "short verifiable quote or value",
  "extraction_method": "model_extraction",
  "source_snapshot": {
    "retrieved_at": "2026-07-04T10:05:00Z",
    "query_hash": "sha256:example"
  },
  "confidence": 0.95,
  "created_at": "2026-07-04T10:06:00Z"
}
```

`Evidence.type` 可选：`database_query`、`paper_search`、`paper_metadata`、`paper_text`、`model_extraction`、`reasoning_trace`、`user_feedback`、`cache_record`。

增强字段说明：

| 字段 | 用途 |
| --- | --- |
| `locator` | 指向证据在来源中的位置，如字段名、表格列、摘要、段落、页码、URL 片段 |
| `quote_or_value` | 保留可核验的短文本、字段值或查询返回依据 |
| `extraction_method` | 说明证据来自规则映射、自动检索、模型抽取、人工反馈或缓存记录 |
| `source_snapshot` | 记录查询时间、查询 hash、缓存版本或文献版本，便于复现 |

## 16. GraphNode

```json
{
  "id": "claim_001",
  "task_id": "task_001",
  "type": "claim",
  "label": "Host-star parameter finding",
  "ref_id": "claim_001",
  "metadata": {
    "paper_id": "paper_001"
  }
}
```

`GraphNode.type` 可选：`research_goal`、`dataset`、`field`、`source`、`paper`、`finding`、`claim`、`relation`、`reasoning_trace`、`evidence`。

## 17. GraphEdge

```json
{
  "id": "edge_001",
  "task_id": "task_001",
  "source": "claim_001",
  "target": "claim_002",
  "type": "supports",
  "relation_id": "relation_001",
  "reasoning_trace_id": "trace_001",
  "evidence_ids": ["evidence_001", "evidence_002"],
  "confidence": 0.95
}
```

`GraphEdge.type` 可选：`uses_dataset`、`provides_field`、`supports_finding`、`cites`、`derived_from`、`supports`、`extends`、`limits`、`contradicts`、`corrected_by_feedback`。

MVP 图谱优先实现少量强证据关系：`provides_field`、`supports_finding`、`derived_from`、`supports`、`extends`、`limits`。跨文献关系必须绑定 `LiteratureRelation`、`ReasoningTrace` 和 `evidence_ids`。

## 18. QualityScore

```json
{
  "task_id": "task_001",
  "field_coverage": 0.86,
  "missing_rate": 0.14,
  "source_completeness": 1.0,
  "unit_consistency": 1.0,
  "paper_acquisition_reproducibility": 1.0,
  "paper_summary_completeness": 0.85,
  "literature_relation_evidence_rate": 1.0,
  "graph_evidence_completeness": 0.92,
  "reproducibility": 0.9
}
```

## 19. UserFeedback

```json
{
  "id": "fb_001",
  "task_id": "task_001",
  "type": "graph_relation_error",
  "target_type": "literature_relation",
  "target_id": "relation_001",
  "message": "该关系更像 limits 而不是 supports",
  "status": "accepted",
  "resolution": "relation_type updated after evidence review",
  "created_at": "2026-07-04T10:10:00Z",
  "resolved_at": "2026-07-04T10:12:00Z"
}
```

## 20. 证据链最低要求

任何展示结果至少满足：

```text
result_id -> evidence_id -> source_id / paper_id -> url/query/retrieved_at
```

跨文献推理结果还必须满足：

```text
literature_relation_id -> reasoning_trace_id -> claim_ids -> evidence_ids -> paper_ids
```

缺少证据链的内容只能作为“候选结果”展示，不能作为最终结论。
