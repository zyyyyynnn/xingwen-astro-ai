"""Dataset schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    label: str
    unit: str
    source_ids: list[str]
    missing_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class QualityScore(BaseModel):
    field_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    source_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    unit_consistency: float = Field(default=0.0, ge=0.0, le=1.0)


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    columns: list[ColumnInfo]
    rows: list[dict]
    quality_score: QualityScore | None = None
