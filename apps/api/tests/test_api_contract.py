from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.task import StepInfo, TaskStatusResponse


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task_then_read_pending_task() -> None:
    response = client.post(
        "/api/tasks",
        json={
            "goal": "研究热木星候选体与宿主恒星参数之间的关系",
            "case_key": "exoplanet_host_star",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "pending"

    task_id = payload["data"]["task_id"]
    status_response = client.get(
        f"/api/tasks/{task_id}", headers={"X-Request-Id": "req_pending_task"}
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["data"]["status"] == "pending"
    assert status_payload["data"]["progress"] == 0
    assert status_payload["data"]["steps"] == []
    assert status_payload["data"]["used_cache"] is False
    assert status_payload["meta"]["cached"] is False
    assert status_payload["meta"]["request_id"] == "req_pending_task"


def test_task_status_snapshot_invariants() -> None:
    base = {
        "task_id": "task_invariant",
        "goal": "验证任务状态快照内部一致性",
        "case_key": "exoplanet_host_star",
        "used_cache": False,
        "created_at": "2026-07-19T00:00:00Z",
        "updated_at": "2026-07-19T00:00:00Z",
    }

    with pytest.raises(
        ValidationError, match="pending task must not contain started steps"
    ):
        TaskStatusResponse(
            **base,
            status="pending",
            progress=0,
            steps=[StepInfo(key="fetching_data", label="获取数据", status="completed")],
        )

    with pytest.raises(ValidationError, match="completed task must have progress 100"):
        TaskStatusResponse(**base, status="completed", progress=99, steps=[])

    with pytest.raises(
        ValidationError, match="task with a running step must not be pending"
    ):
        TaskStatusResponse(
            **base,
            status="pending",
            progress=0,
            steps=[StepInfo(key="fetching_data", label="获取数据", status="running")],
        )


def test_fixed_demo_task_keeps_running_state_and_results() -> None:
    status_response = client.get("/api/tasks/task_001")
    assert status_response.status_code == 200
    status = status_response.json()["data"]
    assert status["status"] == "searching_papers"
    assert status["progress"] == 55
    assert any(step["status"] == "running" for step in status["steps"])

    dataset_response = client.get("/api/tasks/task_001/dataset")
    assert dataset_response.status_code == 200
    assert dataset_response.json()["data"]["dataset_id"] == "dataset_001"


def test_core_result_endpoints_use_envelope_and_request_id() -> None:
    paths = [
        "/api/tasks/task_001/dataset",
        "/api/tasks/task_001/sources",
        "/api/tasks/task_001/paper-acquisition",
        "/api/tasks/task_001/papers",
        "/api/tasks/task_001/literature-reasoning",
        "/api/tasks/task_001/graph",
        "/api/tasks/task_001/evidence/evidence_001",
    ]
    for path in paths:
        response = client.get(path, headers={"X-Request-Id": "req_test"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["error"] is None
        assert payload["meta"]["request_id"] == "req_test"


def test_graph_edges_are_evidence_bound() -> None:
    response = client.get("/api/tasks/task_001/graph")
    assert response.status_code == 200
    edges = response.json()["data"]["edges"]
    assert edges
    assert all(edge["evidence_ids"] for edge in edges)
    cross_doc_edges = [edge for edge in edges if edge.get("relation_id")]
    assert cross_doc_edges
    assert all(edge.get("reasoning_trace_id") for edge in cross_doc_edges)


def test_validation_error_uses_contract_envelope() -> None:
    response = client.post(
        "/api/tasks",
        json={"goal": "", "case_key": "exoplanet_host_star"},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["meta"]["request_id"]


def test_missing_task_uses_contract_error_code() -> None:
    response = client.get("/api/tasks/not_found")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "TASK_NOT_FOUND"
