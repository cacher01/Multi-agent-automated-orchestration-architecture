from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.tools.adapters.api_caller import ApiCallerAdapter
from app.tools.adapters.base import ToolAdapter, ToolAdapterError
from app.tools.adapters.calculator import CalculatorAdapter
from app.tools.adapters.code_executor import CodeExecutorAdapter
from app.tools.adapters.database_query import DatabaseQueryAdapter
from app.tools.adapters.filesystem import FileReaderAdapter, FileWriterAdapter
from app.tools.adapters.time_lookup import TimeLookupAdapter
from app.tools.adapters.weather_query import WeatherQueryAdapter
from app.tools.adapters.web_fetch import WebFetchAdapter
from app.tools.adapters.web_search import WebSearchAdapter
from app.tools.base import (
    PermissionStatus,
    ToolEventLogger,
    ToolExecutionStatus,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvocationStore,
)
from app.tools.permissions import PermissionManager
from app.tools.policy import ToolPolicy, load_tool_policy
from app.tools.registry import ToolRegistry


@dataclass
class ToolGateway:
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    permission_manager: PermissionManager = field(default_factory=PermissionManager)
    policy: ToolPolicy = field(default_factory=load_tool_policy)
    store: ToolInvocationStore | None = None
    logger: ToolEventLogger | None = None
    storage: Any | None = None
    adapters: dict[str, ToolAdapter] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.adapters:
            self.adapters = self._default_adapters()

    def request_tool(
        self,
        *,
        tool_name: str,
        requested_by: str,
        input: Mapping[str, Any] | None = None,
        task_id: str | None = None,
    ) -> ToolInvocationResult:
        request = ToolInvocationRequest(
            tool_name=tool_name,
            requested_by=requested_by,
            input=input or {},
            task_id=task_id,
        )
        definition = self.registry.get_tool(request.tool_name)
        if definition is None:
            result = self._result(
                request,
                PermissionStatus.DENIED.value,
                ToolExecutionStatus.DENIED.value,
                f"Unsupported tool: {request.tool_name}",
            )
            self._persist_and_log(result)
            return result

        permission = self.permission_manager.check(request.requested_by, request.tool_name)
        if not permission.allowed:
            result = self._result(
                request,
                PermissionStatus.DENIED.value,
                ToolExecutionStatus.DENIED.value,
                permission.reason,
            )
            self._persist_and_log(result)
            return result

        adapter = self.adapters.get(request.tool_name)
        if adapter is None:
            result = self._result(
                request,
                PermissionStatus.ALLOWED.value,
                ToolExecutionStatus.NOT_IMPLEMENTED.value,
                "Tool is registered but no adapter is implemented.",
            )
            self._persist_and_log(result)
            return result

        try:
            adapter_result = adapter.execute(request.input)
            result = self._result(
                request,
                PermissionStatus.ALLOWED.value,
                ToolExecutionStatus.SUCCEEDED.value,
                adapter_result.message,
                output=adapter_result.output,
                finished_at=datetime.now(timezone.utc),
            )
        except ToolAdapterError as exc:
            result = self._result(
                request,
                PermissionStatus.ALLOWED.value,
                ToolExecutionStatus.FAILED.value,
                exc.message,
                error=exc.to_error(),
                finished_at=datetime.now(timezone.utc),
            )
        except TimeoutError as exc:
            result = self._result(
                request,
                PermissionStatus.ALLOWED.value,
                ToolExecutionStatus.TIMEOUT.value,
                str(exc),
                error={"code": "tool_timeout", "message": str(exc), "details": {}},
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            result = self._result(
                request,
                PermissionStatus.ALLOWED.value,
                ToolExecutionStatus.FAILED.value,
                "Tool adapter failed.",
                error={"code": "tool_error", "message": self._sanitize_error_message(str(exc)), "details": {}},
                finished_at=datetime.now(timezone.utc),
            )
        self._persist_and_log(result)
        return result

    def record_intent(
        self,
        *,
        tool_name: str,
        requested_by: str,
        input: Mapping[str, Any] | None = None,
        task_id: str | None = None,
    ) -> ToolInvocationResult:
        return self.request_tool(
            tool_name=tool_name,
            requested_by=requested_by,
            input=input,
            task_id=task_id,
        )

    def _default_adapters(self) -> dict[str, ToolAdapter]:
        return {
            "web_search": WebSearchAdapter(self.policy.web_search),
            "web_fetch": WebFetchAdapter(),
            "weather_query": WeatherQueryAdapter(),
            "time_lookup": TimeLookupAdapter(),
            "file_reader": FileReaderAdapter(self.policy.filesystem),
            "file_writer": FileWriterAdapter(self.policy.filesystem),
            "code_executor": CodeExecutorAdapter(self.policy.code_executor, self.policy.filesystem),
            "database_query": DatabaseQueryAdapter(self.storage),
            "calculator": CalculatorAdapter(),
            "api_caller": ApiCallerAdapter(self.policy.api_caller),
        }

    def _result(
        self,
        request: ToolInvocationRequest,
        permission_status: str,
        execution_status: str,
        message: str,
        output: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
        finished_at: datetime | None = None,
    ) -> ToolInvocationResult:
        return ToolInvocationResult(
            tool_name=request.tool_name,
            requested_by=request.requested_by,
            input=request.input,
            permission_status=permission_status,
            execution_status=execution_status,
            message=message,
            task_id=request.task_id,
            output=output,
            error=error,
            finished_at=finished_at,
        )

    def _persist_and_log(self, result: ToolInvocationResult) -> None:
        if self.store is not None:
            self.store.save_tool_invocation(result)
        if self.logger is not None and result.task_id is not None:
            self.logger.log_event(result.task_id, "tool_requested", result.to_record())
            if result.execution_status == ToolExecutionStatus.SUCCEEDED.value:
                self.logger.log_event(result.task_id, "tool_completed", result.to_record())
            elif result.execution_status in {ToolExecutionStatus.FAILED.value, ToolExecutionStatus.TIMEOUT.value}:
                self.logger.log_event(result.task_id, "tool_failed", result.to_record())

    def _sanitize_error_message(self, message: str) -> str:
        sanitized = re.sub(r"https?://\S+", "[url omitted]", message)
        sanitized = re.sub(r"%[0-9A-Fa-f]{2}(?:%[0-9A-Fa-f]{2})+", "[encoded text omitted]", sanitized)
        return sanitized[:240]
