"""Task schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .enums import CaseKey, StepStatus, TaskStatus


class PaperSearchOptions(BaseModel):
    max_candidates: int = Field(default=20, ge=1, le=100)
    max_selected: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def selected_must_not_exceed_candidates(self) -> PaperSearchOptions:
        if self.max_selected > self.max_candidates:
            raise ValueError("max_selected must not exceed max_candidates")
        return self


class TaskOptions(BaseModel):
    use_cache_if_failed: bool = True
    max_rows: int = Field(default=200, ge=1, le=1000)
    paper_search: PaperSearchOptions = Field(default_factory=PaperSearchOptions)


class TaskCreateRequest(BaseModel):
    goal: str = Field(min_length=4, max_length=500)
    case_key: CaseKey = CaseKey.exoplanet_host_star
    options: TaskOptions = Field(default_factory=TaskOptions)


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    case_key: CaseKey


class StepInfo(BaseModel):
    key: str
    label: str
    status: StepStatus
    message: str = ""


class TaskStatusResponse(BaseModel):
    task_id: str
    goal: str
    case_key: CaseKey
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    used_cache: bool = False
    created_at: datetime
    updated_at: datetime
    steps: list[StepInfo]

    @model_validator(mode="after")
    def status_snapshot_must_be_consistent(self) -> TaskStatusResponse:
        if (
            self.status == TaskStatus.pending
            and any(step.status == StepStatus.running for step in self.steps)
        ):
            raise ValueError("task with a running step must not be pending")
        if (
            self.status == TaskStatus.pending
            and any(step.status != StepStatus.pending for step in self.steps)
        ):
            raise ValueError("pending task must not contain started steps")
        if self.status == TaskStatus.completed and self.progress != 100:
            raise ValueError("completed task must have progress 100")
        return self
