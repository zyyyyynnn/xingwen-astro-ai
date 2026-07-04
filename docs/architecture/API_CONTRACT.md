# API Contract

## 1. 通用响应格式

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

错误响应：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task not found"
  }
}
```

## 2. 创建科研任务

`POST /api/tasks`

请求：

```json
{
  "goal": "我想研究热木星候选体的轨道周期、半径、质量与宿主恒星温度之间的关系",
  "case_key": "exoplanet_host_star"
}
```

响应：

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "status": "pending"
  },
  "error": null
}
```

## 3. 查询任务状态

`GET /api/tasks/{task_id}`

响应：

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "status": "cleaning",
    "goal": "...",
    "progress": 55,
    "steps": [
      {
        "key": "parsing",
        "label": "解析科研目标",
        "status": "completed"
      },
      {
        "key": "cleaning",
        "label": "清洗和对齐字段",
        "status": "running"
      }
    ]
  },
  "error": null
}
```

## 4. 获取数据集

`GET /api/tasks/{task_id}/dataset`

响应：

```json
{
  "success": true,
  "data": {
    "columns": [],
    "rows": [],
    "field_dictionary": [],
    "quality_score": {}
  },
  "error": null
}
```

## 5. 获取来源信息

`GET /api/tasks/{task_id}/sources`

响应：

```json
{
  "success": true,
  "data": {
    "sources": []
  },
  "error": null
}
```

## 6. 获取文献总结

`GET /api/tasks/{task_id}/papers`

响应：

```json
{
  "success": true,
  "data": {
    "papers": []
  },
  "error": null
}
```

## 7. 获取图谱

`GET /api/tasks/{task_id}/graph`

响应：

```json
{
  "success": true,
  "data": {
    "nodes": [],
    "edges": []
  },
  "error": null
}
```

## 8. 提交反馈

`POST /api/tasks/{task_id}/feedback`

请求：

```json
{
  "type": "field_unit_error",
  "target": "pl_orbper",
  "message": "这个字段需要明确单位"
}
```

响应：

```json
{
  "success": true,
  "data": {
    "feedback_id": "fb_001",
    "status": "accepted"
  },
  "error": null
}
```

## 9. 导出

- `GET /api/tasks/{task_id}/export/csv`
- `GET /api/tasks/{task_id}/export/report`

