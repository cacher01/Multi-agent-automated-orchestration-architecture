from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.tools.base import ToolInvocationResult
from app.tools.policy import ToolPolicy, load_tool_policy
from app.tools.registry import ToolRegistry


class FakeToolStore:
    def __init__(self) -> None:
        self.saved: list[ToolInvocationResult] = []

    def save_tool_invocation(self, invocation: ToolInvocationResult) -> None:
        self.saved.append(invocation)


class FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, Mapping[str, Any]]] = []

    def log_event(self, task_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        self.events.append((task_id, event_type, payload))


def test_authorized_tool_returns_not_implemented_and_records_intent() -> None:
    store = FakeToolStore()
    logger = FakeLogger()
    registry = ToolRegistry(store=store, logger=logger)

    result = registry.record_intent(
        tool_name="web_search",
        requested_by="researcher",
        input={"query": "status"},
        task_id="task-1",
    )

    assert result.permission_status == "allowed"
    assert result.execution_status == "not_implemented"
    assert result.message == "Tool is planned but not implemented in MVP."
    assert store.saved == [result]
    assert logger.events[0][0] == "task-1"
    assert logger.events[0][1] == "tool_requested"


def test_unauthorized_tool_returns_denied_and_is_still_visible() -> None:
    store = FakeToolStore()
    logger = FakeLogger()
    registry = ToolRegistry(store=store, logger=logger)

    result = registry.record_intent(
        tool_name="file_writer",
        requested_by="researcher",
        input={"path": "x"},
        task_id="task-2",
    )

    assert result.permission_status == "denied"
    assert result.execution_status == "denied"
    assert "not allowed" in result.message
    assert store.saved == [result]
    assert logger.events[0][1] == "tool_requested"


def test_unknown_tool_is_denied_without_execution() -> None:
    registry = ToolRegistry()

    result = registry.record_intent(tool_name="unknown", requested_by="tool_user")

    assert result.permission_status == "denied"
    assert result.execution_status == "denied"
    assert "Unsupported tool" in result.message


def test_registry_includes_confirmed_tool_placeholders() -> None:
    registry = ToolRegistry()

    assert set(registry.list_tools()) == {
        "web_search",
        "web_fetch",
        "weather_query",
        "time_lookup",
        "file_reader",
        "file_writer",
        "code_executor",
        "database_query",
        "calculator",
        "api_caller",
    }
    weather = registry.get_tool("weather_query")
    assert weather is not None
    assert weather.category == "information"


def test_new_simple_tools_are_permission_checked_and_not_implemented() -> None:
    registry = ToolRegistry()

    result = registry.record_intent(tool_name="weather_query", requested_by="orchestrator")

    assert result.permission_status == "allowed"
    assert result.execution_status == "not_implemented"


def test_tool_policy_loads_runtime_policy_file(tmp_path) -> None:
    policy_file = tmp_path / "tool_policy.yaml"
    policy_file.write_text(
        """
web_search:
  provider: tavily
filesystem:
  workspace_roots:
    - "."
  extra_allowed_directories:
    - "D:/data"
  denied_paths:
    - ".env"
code_executor:
  timeout_seconds: 30
  output_max_chars: 1000
  blacklist:
    exact_commands:
      - "danger"
    patterns:
      - "rm -rf"
api_caller:
  allowed_domains:
    - "api.example.com"
""".strip(),
        encoding="utf-8",
    )

    policy = load_tool_policy(policy_file)

    assert isinstance(policy, ToolPolicy)
    assert policy.web_search.provider == "tavily"
    assert policy.filesystem.extra_allowed_directories == ("D:/data",)
    assert policy.code_executor.timeout_seconds == 30
    assert policy.code_executor.exact_commands == ("danger",)
    assert policy.api_caller.allowed_domains == ("api.example.com",)
