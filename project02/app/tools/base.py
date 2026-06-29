from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4


class ToolName(str, Enum):
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    WEATHER_QUERY = "weather_query"
    TIME_LOOKUP = "time_lookup"
    FILE_READER = "file_reader"
    FILE_WRITER = "file_writer"
    CODE_EXECUTOR = "code_executor"
    DATABASE_QUERY = "database_query"
    CALCULATOR = "calculator"
    API_CALLER = "api_caller"


SUPPORTED_TOOL_NAMES: tuple[str, ...] = tuple(tool.value for tool in ToolName)


class PermissionStatus(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class ToolExecutionStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    DENIED = "denied"
    PLANNED = "planned"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class ToolInvocationRequest:
    tool_name: str
    requested_by: str
    input: Mapping[str, Any] = field(default_factory=dict)
    task_id: str | None = None


@dataclass(frozen=True)
class ToolInvocationResult:
    tool_name: str
    requested_by: str
    input: Mapping[str, Any]
    permission_status: str
    execution_status: str
    message: str
    invocation_id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    output: Mapping[str, Any] | None = None
    error: Mapping[str, Any] | None = None
    finished_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "requested_by": self.requested_by,
            "input": dict(self.input),
            "permission_status": self.permission_status,
            "execution_status": self.execution_status,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "output": dict(self.output) if self.output is not None else None,
            "error": dict(self.error) if self.error is not None else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at is not None else None,
        }


class ToolInvocationStore(Protocol):
    def save_tool_invocation(self, invocation: ToolInvocationResult) -> None:
        ...


class ToolEventLogger(Protocol):
    def log_event(self, task_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        ...
