# API Contract

Base URL: `/api/v1`

## 1. 通用响应

成功：

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {
    "request_id": "req_001",
    "cached": false
  }
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task not found",
    "detail": {}
  },
  "meta": {
    "request_id": "req_001",
    "cached": false
  }
}
```

`meta.cached=true` 表示本次响应使用真实运行缓存。缓存不是任务主状态，任务状态仍按 `task_status` 表达。

## 2. 枚举

| 字段 | 可选值 |
| --- | --- |
| `case_key` | `exoplanet_host_star` |
| `task_status` | `pending`, `planning`, `fetching_data`, `cleaning_data`, `searching_papers`, `summarizing_papers`, `reasoning_literature`, `building_graph`, `completed`, `revising`, `failed` |
| `step_status` | `pending`, `running`, `completed`, `failed`, `skipped` |
| `feedback_type` | `field_unit_error`, `field_mapping_error`, `source_error`, `paper_acquisition_error`, `paper_summary_error`, `literature_relation_error`, `graph_relation_error`, `other` |
| `source_type` | `database`, `paper_source`, `paper`, `cache`, `manual_review` |
| `paper_acquisition_status` | `pending`, `running`, `completed`, `failed`, `cached` |
| `claim_type` | `goal`, `method`, `dataset`, `finding`, `limitation`, `future_work` |
| `literature_relation_type` | `supports`, `extends`, `derived_from`, `limits`, `contradicts`, `uses_same_dataset`, `compares_method` |

## 3. 创建任务

`POST /api/v1/tasks`

请求：

```json
{
  "goal": "我想研究热木星候选体的轨道周期、半径、质量与宿主恒星温度之间的关系",
  "case_key": "exoplanet_host_star",
  "options": {
    "use_cache_if_failed": true,
    "max_rows": 200,
    "paper_search": {
      "max_candidates": 20,
      "max_selected": 8
    }
  }
}
```

响应：

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "status": "pending",
    "case_key": "exoplanet_host_star"
  },
  "error": null,
  "meta": { "request_id": "req_001", "cached": false }
}
```

## 4. 查询任务状态

`GET /api/v1/tasks/{task_id}`

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "goal": "...",
    "case_key": "exoplanet_host_star",
    "status": "searching_papers",
    "progress": 55,
    "used_cache": false,
    "created_at": "2026-07-04T10:00:00Z",
    "updated_at": "2026-07-04T10:02:30Z",
    "steps": [
      {
        "key": "searching_papers",
        "label": "获取主案例论文",
        "status": "running",
        "message": "正在检索主案例相关论文候选"
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_002", "cached": false }
}
```

## 5. 获取数据集

`GET /api/v1/tasks/{task_id}/dataset`

```json
{
  "success": true,
  "data": {
    "dataset_id": "dataset_001",
    "name": "exoplanet_host_star_dataset",
    "columns": [
      {
        "name": "pl_orbper",
        "label": "Orbital Period",
        "unit": "day",
        "source_ids": ["source_nasa_exoplanet_archive"],
        "missing_rate": 0.08
      }
    ],
    "rows": [
      {
        "object_id": "toi_001",
        "pl_orbper": 3.52,
        "hostname": "Host Star A"
      }
    ],
    "quality_score": {
      "field_coverage": 0.86,
      "source_completeness": 1.0,
      "unit_consistency": 1.0
    }
  },
  "error": null,
  "meta": { "request_id": "req_003", "cached": false }
}
```

## 6. 获取来源记录

`GET /api/v1/tasks/{task_id}/sources`

```json
{
  "success": true,
  "data": {
    "sources": [
      {
        "id": "source_nasa_exoplanet_archive",
        "type": "database",
        "name": "NASA Exoplanet Archive",
        "url": "https://exoplanetarchive.ipac.caltech.edu/",
        "query": "...",
        "retrieved_at": "2026-07-04T10:01:00Z",
        "cached": false
      },
      {
        "id": "source_ads_or_arxiv",
        "type": "paper_source",
        "name": "paper source",
        "url": "string",
        "query": "exoplanet candidate host star orbital period",
        "retrieved_at": "2026-07-04T10:05:00Z",
        "cached": false
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_004", "cached": false }
}
```

## 7. 获取论文获取结果

`GET /api/v1/tasks/{task_id}/paper-acquisition`

```json
{
  "success": true,
  "data": {
    "query": {
      "query_id": "paper_query_001",
      "keywords": ["exoplanet candidate", "host star", "orbital period"],
      "query_string": "exoplanet candidate host star orbital period",
      "filters": {
        "year_from": 2015,
        "max_results": 20
      }
    },
    "run": {
      "run_id": "paper_run_001",
      "status": "completed",
      "candidate_count": 12,
      "selected_count": 6,
      "dedupe_rule": "doi_or_title_year",
      "used_cache": false
    },
    "candidates": [
      {
        "candidate_id": "paper_candidate_001",
        "title": "string",
        "authors": ["string"],
        "year": 2024,
        "doi": "string",
        "arxiv_id": "string",
        "url": "string",
        "abstract": "string",
        "source_record_id": "source_ads_or_arxiv",
        "relevance_score": 0.86,
        "selected": true,
        "selection_reason": "Matches host-star parameter integration case"
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_005", "cached": false }
}
```

## 8. 获取文献总结

`GET /api/v1/tasks/{task_id}/papers`

```json
{
  "success": true,
  "data": {
    "papers": [
      {
        "paper_id": "paper_001",
        "candidate_id": "paper_candidate_001",
        "title": "string",
        "year": 2024,
        "url": "string",
        "summary": {
          "research_goal": "string",
          "method": "string",
          "dataset": "string",
          "findings": ["string"],
          "limitations": ["string"],
          "future_work": ["string"]
        },
        "evidence_ids": ["evidence_001"]
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_006", "cached": false }
}
```

## 9. 获取跨文献推理结果

`GET /api/v1/tasks/{task_id}/literature-reasoning`

```json
{
  "success": true,
  "data": {
    "claims": [
      {
        "claim_id": "claim_001",
        "paper_id": "paper_001",
        "claim_type": "finding",
        "text": "string",
        "evidence_ids": ["evidence_001"],
        "confidence": 0.82
      }
    ],
    "relations": [
      {
        "relation_id": "relation_001",
        "source_claim_id": "claim_001",
        "target_claim_id": "claim_002",
        "relation_type": "supports",
        "reasoning_trace_id": "trace_001",
        "evidence_ids": ["evidence_001", "evidence_002"],
        "confidence": 0.78
      }
    ],
    "traces": [
      {
        "trace_id": "trace_001",
        "relation_id": "relation_001",
        "steps": [
          {
            "order": 1,
            "claim_id": "claim_001",
            "rationale": "string"
          }
        ],
        "evidence_ids": ["evidence_001", "evidence_002"]
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_007", "cached": false }
}
```

## 10. 获取学术图谱

`GET /api/v1/tasks/{task_id}/graph`

```json
{
  "success": true,
  "data": {
    "nodes": [
      {
        "id": "claim_001",
        "type": "claim",
        "label": "Host-star parameter finding",
        "ref_id": "claim_001"
      }
    ],
    "edges": [
      {
        "id": "edge_001",
        "source": "claim_001",
        "target": "claim_002",
        "type": "supports",
        "relation_id": "relation_001",
        "reasoning_trace_id": "trace_001",
        "evidence_ids": ["evidence_001", "evidence_002"]
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_008", "cached": false }
}
```

## 11. 获取证据详情

`GET /api/v1/tasks/{task_id}/evidence/{evidence_id}`

```json
{
  "success": true,
  "data": {
    "id": "evidence_001",
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
    "confidence": 0.95
  },
  "error": null,
  "meta": { "request_id": "req_009", "cached": false }
}
```

## 12. 提交反馈

`POST /api/v1/tasks/{task_id}/feedback`

请求：

```json
{
  "type": "literature_relation_error",
  "target_type": "literature_relation",
  "target_id": "relation_001",
  "message": "该关系更像 limits 而不是 supports"
}
```

响应：

```json
{
  "success": true,
  "data": {
    "feedback_id": "fb_001",
    "status": "accepted",
    "next_status": "revising"
  },
  "error": null,
  "meta": { "request_id": "req_010", "cached": false }
}
```

## 13. 导出

| 接口 | 输出 |
| --- | --- |
| `GET /api/v1/tasks/{task_id}/export/csv` | 标准化数据集 CSV |
| `GET /api/v1/tasks/{task_id}/export/data-dictionary` | 字段字典 JSON/CSV |
| `GET /api/v1/tasks/{task_id}/export/provenance-report` | 溯源报告 Markdown/JSON |
| `GET /api/v1/tasks/{task_id}/export/papers` | 论文候选、入选论文和总结 JSON |
| `GET /api/v1/tasks/{task_id}/export/literature-reasoning` | Claim、Relation、ReasoningTrace JSON |

## 14. 错误码

| code | 含义 |
| --- | --- |
| `INVALID_REQUEST` | 请求参数无效 |
| `TASK_NOT_FOUND` | 任务不存在 |
| `TASK_NOT_READY` | 结果尚未生成 |
| `MODEL_CALL_FAILED` | 模型调用失败 |
| `DATA_SOURCE_FAILED` | 外部数据源失败 |
| `PAPER_SOURCE_FAILED` | 论文来源失败 |
| `REASONING_TRACE_INVALID` | 推理链缺少证据或结构不合法 |
| `CACHE_NOT_AVAILABLE` | 无可用缓存 |
| `SCHEMA_VALIDATION_FAILED` | 模型或模块输出不符合 schema |
