from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_task_then_read_pending_task() -> None:
    response = client.post(
        "/api/v1/tasks",
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
    status_response = client.get(f"/api/v1/tasks/{task_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["data"]["status"] == "pending"
    assert status_payload["data"]["used_cache"] is False
    assert status_payload["meta"]["cached"] is False


def test_core_result_endpoints_use_envelope_and_request_id() -> None:
    paths = [
        "/api/v1/tasks/task_001/dataset",
        "/api/v1/tasks/task_001/sources",
        "/api/v1/tasks/task_001/paper-acquisition",
        "/api/v1/tasks/task_001/papers",
        "/api/v1/tasks/task_001/literature-reasoning",
        "/api/v1/tasks/task_001/graph",
        "/api/v1/tasks/task_001/evidence/evidence_001",
    ]
    for path in paths:
        response = client.get(path, headers={"X-Request-Id": "req_test"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["error"] is None
        assert payload["meta"]["request_id"] == "req_test"


def test_graph_edges_are_evidence_bound() -> None:
    response = client.get("/api/v1/tasks/task_001/graph")
    assert response.status_code == 200
    edges = response.json()["data"]["edges"]
    assert edges
    assert all(edge["evidence_ids"] for edge in edges)
    cross_doc_edges = [edge for edge in edges if edge.get("relation_id")]
    assert cross_doc_edges
    assert all(edge.get("reasoning_trace_id") for edge in cross_doc_edges)


def test_validation_error_uses_contract_envelope() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"goal": "", "case_key": "exoplanet_host_star"},
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert payload["meta"]["request_id"]


def test_missing_task_uses_contract_error_code() -> None:
    response = client.get("/api/v1/tasks/not_found")
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "TASK_NOT_FOUND"
