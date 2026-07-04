# Data Model

## ResearchTask

```json
{
  "id": "task_001",
  "goal": "string",
  "case_key": "exoplanet_host_star",
  "status": "pending",
  "created_at": "string",
  "updated_at": "string"
}
```

## Dataset

```json
{
  "id": "dataset_001",
  "task_id": "task_001",
  "name": "exoplanet_host_star_dataset",
  "columns": [],
  "rows": [],
  "created_at": "string"
}
```

## Field

```json
{
  "name": "pl_orbper",
  "label": "Orbital Period",
  "unit": "day",
  "description": "Planet orbital period",
  "source_ids": ["source_001"],
  "missing_rate": 0.12
}
```

## Source

```json
{
  "id": "source_001",
  "type": "database",
  "name": "NASA Exoplanet Archive",
  "url": "string",
  "query": "string",
  "retrieved_at": "string"
}
```

## Paper

```json
{
  "id": "paper_001",
  "title": "string",
  "authors": [],
  "year": 2026,
  "doi": "string",
  "url": "string"
}
```

## PaperSummary

```json
{
  "paper_id": "paper_001",
  "background": "string",
  "research_goal": "string",
  "method": "string",
  "dataset": "string",
  "findings": [],
  "limitations": [],
  "future_work": []
}
```

## Evidence

```json
{
  "id": "evidence_001",
  "type": "paper_text",
  "source_id": "paper_001",
  "target_type": "Field",
  "target_id": "pl_orbper",
  "content": "string",
  "confidence": 0.85
}
```

## GraphNode

```json
{
  "id": "node_001",
  "type": "Paper",
  "label": "string",
  "ref_id": "paper_001"
}
```

## GraphEdge

```json
{
  "id": "edge_001",
  "source": "node_001",
  "target": "node_002",
  "type": "uses_dataset",
  "evidence_ids": ["evidence_001"]
}
```

## QualityScore

```json
{
  "task_id": "task_001",
  "field_coverage": 0.9,
  "missing_rate": 0.15,
  "source_completeness": 0.95,
  "unit_consistency": 0.9,
  "reproducibility": 0.85
}
```

## UserFeedback

```json
{
  "id": "fb_001",
  "task_id": "task_001",
  "type": "field_unit_error",
  "target": "pl_orbper",
  "message": "这个字段需要明确单位",
  "status": "accepted",
  "created_at": "string"
}
```

