from __future__ import annotations

import sys

from app.tools.gateway import ToolGateway
from app.tools.policy import CodeExecutorPolicy, FilesystemPolicy, ToolPolicy, WebSearchPolicy


def test_gateway_executes_calculator() -> None:
    result = ToolGateway().request_tool(
        tool_name="calculator",
        requested_by="orchestrator",
        input={"expression": "2 + 3 * 4"},
    )

    assert result.execution_status == "succeeded"
    assert result.output == {"result": "14", "steps": ["2 + 3 * 4"]}


def test_gateway_executes_time_lookup() -> None:
    result = ToolGateway().request_tool(
        tool_name="time_lookup",
        requested_by="orchestrator",
        input={"timezone": "UTC"},
    )

    assert result.execution_status == "succeeded"
    assert result.output is not None
    assert result.output["timezone"] == "UTC"


def test_gateway_reads_and_writes_authorized_files(tmp_path) -> None:
    policy = ToolPolicy(
        filesystem=FilesystemPolicy(workspace_roots=(str(tmp_path),)),
    )
    gateway = ToolGateway(policy=policy)
    target = tmp_path / "note.txt"

    written = gateway.request_tool(
        tool_name="file_writer",
        requested_by="tool_user",
        input={"path": str(target), "operation": "create", "content": "hello"},
    )
    read = gateway.request_tool(
        tool_name="file_reader",
        requested_by="tool_user",
        input={"path": str(target)},
    )

    assert written.execution_status == "succeeded"
    assert read.execution_status == "succeeded"
    assert read.output is not None
    assert read.output["content"] == "hello"


def test_gateway_denies_unauthorized_file_path(tmp_path) -> None:
    gateway = ToolGateway(policy=ToolPolicy(filesystem=FilesystemPolicy(workspace_roots=(str(tmp_path),))))
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = gateway.request_tool(
        tool_name="file_reader",
        requested_by="tool_user",
        input={"path": str(outside)},
    )

    assert result.execution_status == "failed"
    assert result.error is not None
    assert result.error["code"] == "path_not_allowed"


def test_gateway_executes_safe_command(tmp_path) -> None:
    policy = ToolPolicy(
        filesystem=FilesystemPolicy(workspace_roots=(str(tmp_path),)),
        code_executor=CodeExecutorPolicy(patterns=("Remove-Item .* -Recurse",)),
    )
    gateway = ToolGateway(policy=policy)

    result = gateway.request_tool(
        tool_name="code_executor",
        requested_by="tool_user",
        input={"command": [sys.executable, "-c", "print('ok')"], "cwd": str(tmp_path)},
    )

    assert result.execution_status == "succeeded"
    assert result.output is not None
    assert result.output["exit_code"] == 0
    assert "ok" in result.output["stdout"]


def test_gateway_sanitizes_unexpected_adapter_errors() -> None:
    class BrokenAdapter:
        name = "web_search"

        def execute(self, tool_input):
            raise RuntimeError("403 Client Error for url: https://example.com/?q=%E7%89%B9%E6%96%AF%E6%8B%89")

    result = ToolGateway(adapters={"web_search": BrokenAdapter()}).request_tool(
        tool_name="web_search",
        requested_by="researcher",
        input={"query": "\u7279\u65af\u62c9"},
        task_id="task-1",
    )

    assert result.execution_status == "failed"
    assert result.message == "Tool adapter failed."
    assert result.error is not None
    assert "%E7%89%B9" not in result.error["message"]


def test_gateway_denies_blacklisted_command(tmp_path) -> None:
    policy = ToolPolicy(
        filesystem=FilesystemPolicy(workspace_roots=(str(tmp_path),)),
        code_executor=CodeExecutorPolicy(patterns=("git reset --hard",)),
    )
    gateway = ToolGateway(policy=policy)

    result = gateway.request_tool(
        tool_name="code_executor",
        requested_by="tool_user",
        input={"command": ["git", "reset", "--hard"], "cwd": str(tmp_path)},
    )

    assert result.execution_status == "failed"
    assert result.error is not None
    assert result.error["code"] == "command_denied"


def test_gateway_denies_api_domain_not_in_allowlist() -> None:
    result = ToolGateway().request_tool(
        tool_name="api_caller",
        requested_by="orchestrator",
        input={"method": "GET", "url": "https://api.example.com/data"},
    )

    assert result.execution_status == "failed"
    assert result.error is not None
    assert result.error["code"] == "domain_not_allowed"


def test_gateway_returns_structured_tavily_provider_failure(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = ToolGateway(policy=ToolPolicy(web_search=WebSearchPolicy(provider="tavily"))).request_tool(
        tool_name="web_search",
        requested_by="researcher",
        input={"query": "test"},
    )

    assert result.execution_status == "failed"
    assert result.error is not None
    assert result.error["code"] == "provider_not_configured"


def test_gateway_uses_duckduckgo_fallback_without_tavily(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    class FakeResponse:
        text = '<a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com">Example</a><a class="result__snippet">Snippet text</a>'

        def raise_for_status(self) -> None:
            return None

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.tools.adapters.web_search.httpx.get", fake_get)
    result = ToolGateway().request_tool(
        tool_name="web_search",
        requested_by="researcher",
        input={"query": "test"},
    )

    assert result.execution_status == "succeeded"
    assert result.output is not None
    assert result.output["results"][0]["url"] == "https://example.com"
