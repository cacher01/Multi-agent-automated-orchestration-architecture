from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.tools.base import (
    PermissionStatus,
    ToolEventLogger,
    ToolExecutionStatus,
    ToolInvocationRequest,
    ToolInvocationResult,
    ToolInvocationStore,
)
from app.tools.catalog import DEFAULT_TOOLS, ToolDefinition
from app.tools.permissions import PermissionManager
from app.tools.policy import ToolPolicy, load_tool_policy


@dataclass
class ToolRegistry:
    permission_manager: PermissionManager = field(default_factory=PermissionManager)
    policy: ToolPolicy = field(default_factory=load_tool_policy)
    store: ToolInvocationStore | None = None
    logger: ToolEventLogger | None = None
    tools: dict[str, ToolDefinition] = field(default_factory=lambda: dict(DEFAULT_TOOLS))

    def list_tools(self) -> list[str]:
        return sorted(self.tools)

    def describe_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "category": tool.category,
                "description": tool.description,
                "input_schema": dict(tool.input_schema),
                "output_schema": dict(tool.output_schema),
            }
            for tool in sorted(self.tools.values(), key=lambda item: item.name)
        ]

    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        return self.tools.get(tool_name)

    def record_intent(
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
        decision = self.permission_manager.check(requested_by, tool_name)
        if decision.allowed and tool_name not in self.tools:
            decision = self.permission_manager.check(requested_by, "__unsupported__")
        result = ToolInvocationResult(
            tool_name=request.tool_name,
            requested_by=request.requested_by,
            input=request.input,
            permission_status=PermissionStatus.ALLOWED.value if decision.allowed else PermissionStatus.DENIED.value,
            execution_status=(
                ToolExecutionStatus.NOT_IMPLEMENTED.value
                if decision.allowed
                else ToolExecutionStatus.DENIED.value
            ),
            message=(
                "Tool is planned but not implemented in MVP."
                if decision.allowed
                else decision.reason
            ),
            task_id=task_id,
        )
        self._persist(result)
        self._log(result)
        return result

    def _persist(self, result: ToolInvocationResult) -> None:
        if self.store is not None:
            self.store.save_tool_invocation(result)

    def _log(self, result: ToolInvocationResult) -> None:
        if self.logger is not None and result.task_id is not None:
            self.logger.log_event(result.task_id, "tool_requested", result.to_record())
