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

## 2. 枚举

| 字段 | 可选值 |
| --- | --- |
| `case_key` | `exoplanet_host_star` |
| `task_status` | `pending`, `planning`, `fetching_data`, `cleaning_data`, `summarizing_papers`, `building_graph`, `using_cache`, `completed`, `revising`, `failed` |
| `step_status` | `pending`, `running`, `completed`, `failed`, `skipped` |
| `feedback_type` | `field_unit_error`, `field_mapping_error`, `source_error`, `paper_summary_error`, `graph_relation_error`, `other` |
| `source_type` | `database`, `paper`, `cache`, `manual_review` |

## 3. 创建任务

`POST /api/v1/tasks`

请求：

```json
{
  "goal": "我想研究热木星候选体的轨道周期、半径、质量与宿主恒星温度之间的关系",
  "case_key": "exoplanet_host_star",
  "options": {
    "use_cache_if_failed": true,
    "max_rows": 200
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
    "status": "cleaning_data",
    "progress": 45,
    "created_at": "2026-07-04T10:00:00Z",
    "updated_at": "2026-07-04T10:02:30Z",
    "steps": [
      {
        "key": "planning",
        "label": "解析科研目标",
        "status": "completed",
        "message": "已生成任务计划"
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
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_004", "cached": false }
}
```

## 7. 获取文献总结

`GET /api/v1/tasks/{task_id}/papers`

```json
{
  "success": true,
  "data": {
    "papers": [
      {
        "paper_id": "paper_001",
        "title": "string",
        "year": 2024,
        "url": "string",
        "summary": {
          "research_goal": "string",
          "method": "string",
          "dataset": "string",
          "findings": ["string"],
          "limitations": ["string"]
        },
        "evidence_ids": ["evidence_001"]
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_005", "cached": false }
}
```

## 8. 获取学术图谱

`GET /api/v1/tasks/{task_id}/graph`

```json
{
  "success": true,
  "data": {
    "nodes": [
      {
        "id": "field_pl_orbper",
        "type": "field",
        "label": "Orbital Period",
        "ref_id": "pl_orbper"
      }
    ],
    "edges": [
      {
        "id": "edge_001",
        "source": "source_nasa_exoplanet_archive",
        "target": "field_pl_orbper",
        "type": "provides_field",
        "evidence_ids": ["evidence_001"]
      }
    ]
  },
  "error": null,
  "meta": { "request_id": "req_006", "cached": false }
}
```

## 9. 获取证据详情

`GET /api/v1/tasks/{task_id}/evidence/{evidence_id}`

```json
{
  "success": true,
  "data": {
    "id": "evidence_001",
    "type": "database_query",
    "source_id": "source_nasa_exoplanet_archive",
    "content": "Field pl_orbper retrieved from NASA Exoplanet Archive query result.",
    "confidence": 0.95
  },
  "error": null,
  "meta": { "request_id": "req_007", "cached": false }
}
```

## 10. 提交反馈

`POST /api/v1/tasks/{task_id}/feedback`

请求：

```json
{
  "type": "field_unit_error",
  "target_type": "field",
  "target_id": "pl_orbper",
  "message": "需要明确轨道周期单位"
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
  "meta": { "request_id": "req_008", "cached": false }
}
```

## 11. 导出

| 接口 | 输出 |
| --- | --- |
| `GET /api/v1/tasks/{task_id}/export/csv` | 标准化数据集 CSV |
| `GET /api/v1/tasks/{task_id}/export/data-dictionary` | 字段字典 JSON/CSV |
| `GET /api/v1/tasks/{task_id}/export/provenance-report` | 溯源报告 Markdown/JSON |

## 12. 错误码

| code | 含义 |
| --- | --- |
| `INVALID_REQUEST` | 请求参数无效 |
| `TASK_NOT_FOUND` | 任务不存在 |
| `TASK_NOT_READY` | 结果尚未生成 |
| `MODEL_CALL_FAILED` | 模型调用失败 |
| `DATA_SOURCE_FAILED` | 外部数据源失败 |
| `CACHE_NOT_AVAILABLE` | 无可用缓存 |
| `SCHEMA_VALIDATION_FAILED` | 模型或模块输出不符合 schema |
