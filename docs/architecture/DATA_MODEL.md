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
| `Paper` | 文献信息 | 文献页、图谱 |
| `PaperSummary` | 文献结构化总结 | 文献页 |
| `Evidence` | 数据/文献/图谱证据 | 图谱、溯源详情 |
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
  "key": "fetching_data",
  "label": "获取天文数据",
  "status": "running",
  "message": "正在查询主数据源",
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

## 7. Paper

```json
{
  "id": "paper_001",
  "title": "string",
  "authors": ["string"],
  "year": 2024,
  "doi": "string",
  "url": "string",
  "source_ids": ["source_arxiv_001"]
}
```

## 8. PaperSummary

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

## 9. Evidence

```json
{
  "id": "evidence_001",
  "task_id": "task_001",
  "type": "database_query",
  "source_id": "source_nasa_exoplanet_archive",
  "paper_id": null,
  "target_type": "field",
  "target_id": "pl_orbper",
  "content": "Field pl_orbper retrieved from source query result.",
  "locator": {
    "kind": "column",
    "value": "pl_orbper"
  },
  "quote_or_value": "pl_orbper returned by TAP query",
  "extraction_method": "rule_based_mapping",
  "source_snapshot": {
    "retrieved_at": "2026-07-04T10:01:00Z",
    "query_hash": "sha256:example"
  },
  "confidence": 0.95,
  "created_at": "2026-07-04T10:03:00Z"
}
```

`Evidence.type` 可选：`database_query`、`paper_text`、`model_extraction`、`user_feedback`、`cache_record`。

增强字段说明：

| 字段 | 用途 |
| --- | --- |
| `locator` | 指向证据在来源中的位置，如字段名、表格列、段落、页码、URL 片段 |
| `quote_or_value` | 保留可核验的短文本、字段值或查询返回依据 |
| `extraction_method` | 说明证据来自规则映射、模型抽取、人工反馈或缓存记录 |
| `source_snapshot` | 记录查询时间、查询 hash、缓存版本或文献版本，便于复现 |

## 10. GraphNode

```json
{
  "id": "field_pl_orbper",
  "task_id": "task_001",
  "type": "field",
  "label": "Orbital Period",
  "ref_id": "pl_orbper",
  "metadata": {
    "unit": "day"
  }
}
```

`GraphNode.type` 可选：`research_goal`、`dataset`、`field`、`source`、`paper`、`finding`、`evidence`。

## 11. GraphEdge

```json
{
  "id": "edge_001",
  "task_id": "task_001",
  "source": "source_nasa_exoplanet_archive",
  "target": "field_pl_orbper",
  "type": "provides_field",
  "evidence_ids": ["evidence_001"],
  "confidence": 0.95
}
```

`GraphEdge.type` 可选：`uses_dataset`、`provides_field`、`supports_finding`、`cites`、`derived_from`、`corrected_by_feedback`。

MVP 图谱优先实现少量强证据关系：`provides_field`、`supports_finding`、`derived_from`。不追求大图规模。

## 12. QualityScore

```json
{
  "task_id": "task_001",
  "field_coverage": 0.86,
  "missing_rate": 0.14,
  "source_completeness": 1.0,
  "unit_consistency": 1.0,
  "paper_summary_completeness": 0.85,
  "graph_evidence_completeness": 0.92,
  "reproducibility": 0.9
}
```

## 13. UserFeedback

```json
{
  "id": "fb_001",
  "task_id": "task_001",
  "type": "field_unit_error",
  "target_type": "field",
  "target_id": "pl_orbper",
  "message": "需要明确轨道周期单位",
  "status": "accepted",
  "resolution": "unit set to day based on source metadata",
  "created_at": "2026-07-04T10:10:00Z",
  "resolved_at": "2026-07-04T10:12:00Z"
}
```

## 14. 证据链最低要求

任何展示结果至少满足：

```text
result_id -> evidence_id -> source_id / paper_id -> url/query/retrieved_at
```

缺少证据链的内容只能作为“候选结果”展示，不能作为最终结论。
