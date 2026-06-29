from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.task_service import TaskService
from app.storage.sqlite import SQLiteStorage


def make_client(tmp_path: Path) -> TestClient:
    storage = SQLiteStorage(f"sqlite:///{tmp_path / 'test.db'}")
    return TestClient(create_app(TaskService(storage=storage)))


def test_app_startup_and_health(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_simple_direct_task_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    created = client.post("/tasks", json={"input": "Say hello"}).json()

    assert created["status"] == "succeeded"
    assert created["mode"] == "direct"
    assert "MVP direct response" in created["result"]

    result = client.get(f"/tasks/{created['task_id']}/result")
    assert result.status_code == 200
    assert result.json()["result"] == created["result"]


def test_single_simple_tool_intent_task_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/tasks", json={"input": "lookup weather in Shanghai"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["tool_required"] is True
    assert body["tool_message"] == "Tool is planned but not implemented in MVP."


def test_complex_async_task_result_query_and_logs(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/tasks", json={"input": "Design and implement a multi-step plan"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    task_id = body["task_id"]

    status_response = client.get(f"/tasks/{task_id}")
    assert status_response.status_code == 200
    assert status_response.json()["execution_mode"] == "dag"

    result_response = client.get(f"/tasks/{task_id}/result")
    assert result_response.status_code == 200
    result = result_response.json()
    assert result["status"] == "succeeded"
    assert "Complex task processed" in result["result"]

    logs_response = client.get(f"/tasks/{task_id}/logs")
    assert logs_response.status_code == 200
    event_types = {event["event_type"] for event in logs_response.json()["events"]}
    assert {"task_created", "decision_made", "task_succeeded"}.issubset(event_types)


def test_clarification_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/tasks", json={"input": "do it"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_for_clarification"
    assert "clarification_question" in body


def test_budget_exceeded_path(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/tasks", json={"input": "please exceed budget"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "budget_exceeded"
    assert body["failure"]["reason"] == "budget_exceeded"


def test_permission_denied_path_for_tool_intent(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/tasks", json={"input": "permission search external API"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "permission_denied"
    assert body["failure"]["reason"] == "permission_denied"


def test_candidate_memory_approval_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    created = client.post("/tasks", json={"input": "Design and implement a plan"}).json()
    task_id = created["task_id"]
    result = client.get(f"/tasks/{task_id}/result").json()
    memory_id = result["candidate_memories"][0]["memory_id"]

    listed = client.get("/memories")
    assert listed.status_code == 200
    assert listed.json()["memories"][0]["status"] == "pending"

    approved = client.post(f"/memories/{memory_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    deleted = client.delete(f"/memories/{memory_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"


def test_capabilities_and_secret_safety(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["tool_execution_enabled"] is True
    assert "api_key" not in response.text.lower()
    assert "deepseek" not in response.text.lower()


def test_frontend_is_served(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "Orchestrator" in response.text
