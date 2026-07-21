"""Dataset schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import CaseKey


class ColumnInfo(BaseModel):
    name: str
    label: str
    unit: str
    description: str
    data_type: str
    required: bool
    source_ids: list[str] = Field(min_length=1)
    missing_rate: float = Field(ge=0.0, le=1.0)
    mapping_rule: str


class QualityScore(BaseModel):
    task_id: str
    field_coverage: float = Field(ge=0.0, le=1.0)
    missing_rate: float = Field(ge=0.0, le=1.0)
    source_completeness: float = Field(ge=0.0, le=1.0)
    unit_consistency: float = Field(ge=0.0, le=1.0)
    paper_acquisition_reproducibility: float = Field(ge=0.0, le=1.0)
    paper_summary_completeness: float = Field(ge=0.0, le=1.0)
    literature_relation_evidence_rate: float = Field(ge=0.0, le=1.0)
    graph_evidence_completeness: float = Field(ge=0.0, le=1.0)
    reproducibility: float = Field(ge=0.0, le=1.0)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(alias="dataset_id")
    task_id: str
    name: str
    case_key: CaseKey
    row_count: int = Field(ge=0)
    field_count: int = Field(ge=0)
    created_at: datetime
    columns: list[ColumnInfo]
    rows: list[dict]
    quality_score: QualityScore | None = None
