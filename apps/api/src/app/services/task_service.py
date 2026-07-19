"""P0 task orchestration for mock API integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.errors import task_not_found, task_not_ready
from app.mock.data import (
    mock_dataset,
    mock_evidence,
    mock_graph,
    mock_literature_reasoning,
    mock_paper_acquisition,
    mock_papers,
    mock_sources,
    mock_task_status,
)
from app.schemas.dataset import DatasetResponse
from app.schemas.enums import CaseKey, TaskStatus
from app.schemas.evidence import EvidenceResponse
from app.schemas.graph import GraphResponse
from app.schemas.paper import PaperAcquisitionResponse, PapersResponse
from app.schemas.reasoning import LiteratureReasoningResponse
from app.schemas.source import SourcesResponse
from app.schemas.task import TaskCreateRequest, TaskCreateResponse, TaskStatusResponse


@dataclass
class TaskRecord:
    task_id: str
    goal: str
    case_key: CaseKey
    status: TaskStatus
    created_at: datetime
    updated_at: datetime


class TaskService:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {
            "task_001": TaskRecord(
                task_id="task_001",
                goal=mock_task_status().goal,
                case_key=CaseKey.exoplanet_host_star,
                status=TaskStatus.searching_papers,
                created_at=mock_task_status().created_at,
                updated_at=mock_task_status().updated_at,
            )
        }

    def create_task(self, req: TaskCreateRequest) -> TaskCreateResponse:
        now = datetime.now(timezone.utc)
        task_id = f"task_{uuid4().hex[:12]}"
        self._tasks[task_id] = TaskRecord(
            task_id=task_id,
            goal=req.goal,
            case_key=req.case_key,
            status=TaskStatus.pending,
            created_at=now,
            updated_at=now,
        )
        return TaskCreateResponse(task_id=task_id, status=TaskStatus.pending, case_key=req.case_key)

    def get_task(self, task_id: str) -> TaskStatusResponse:
        record = self._require_task(task_id)
        if task_id == "task_001":
            return mock_task_status()
        return TaskStatusResponse(
            task_id=record.task_id,
            goal=record.goal,
            case_key=record.case_key,
            status=record.status,
            progress=0,
            used_cache=False,
            created_at=record.created_at,
            updated_at=record.updated_at,
            steps=[],
        )

    def get_dataset(self, task_id: str) -> DatasetResponse:
        self._require_mock_ready(task_id)
        return mock_dataset()

    def get_sources(self, task_id: str) -> SourcesResponse:
        self._require_mock_ready(task_id)
        return mock_sources()

    def get_paper_acquisition(self, task_id: str) -> PaperAcquisitionResponse:
        self._require_mock_ready(task_id)
        return mock_paper_acquisition()

    def get_papers(self, task_id: str) -> PapersResponse:
        self._require_mock_ready(task_id)
        return mock_papers()

    def get_literature_reasoning(self, task_id: str) -> LiteratureReasoningResponse:
        self._require_mock_ready(task_id)
        return mock_literature_reasoning()

    def get_graph(self, task_id: str) -> GraphResponse:
        self._require_mock_ready(task_id)
        return mock_graph()

    def get_evidence(self, task_id: str, evidence_id: str) -> EvidenceResponse:
        self._require_mock_ready(task_id)
        evidence = mock_evidence(evidence_id)
        if evidence is None:
            raise task_not_found(evidence_id)
        return evidence

    def _require_task(self, task_id: str) -> TaskRecord:
        record = self._tasks.get(task_id)
        if record is None:
            raise task_not_found(task_id)
        return record

    def _require_mock_ready(self, task_id: str) -> None:
        record = self._require_task(task_id)
        if record.status == TaskStatus.pending:
            raise task_not_ready(task_id, record.status)


task_service = TaskService()
