from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_FOR_CLARIFICATION = "waiting_for_clarification"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    PERMISSION_DENIED = "permission_denied"


class FailureResult(BaseModel):
    task_id: str
    reason: str
    error_message: str
    completed_parts: list[str] = Field(default_factory=list)
    incomplete_parts: list[str] = Field(default_factory=list)
    retry_count: int = 0
    last_status: TaskStatus = TaskStatus.FAILED


class Task(BaseModel):
    task_id: str
    user_input: str
    status: TaskStatus = TaskStatus.CREATED
    execution_mode: str | None = None
    result: str | None = None
    error: str | None = None
    persist_logs: bool = False
    persist_intermediate_results: bool = False
    retry_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskCreateRequest(BaseModel):
    input: str = Field(min_length=1)
    persist_logs: bool = False
    persist_intermediate_results: bool = False


class TaskSubmitResponse(BaseModel):
    task_id: str
    status: TaskStatus
    mode: str
    result: str | None = None
    tool_required: bool = False
    tool_message: str | None = None
    clarification_question: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    execution_mode: str | None = None
    created_at: datetime
    updated_at: datetime
    retry_count: int = 0
    error: str | None = None


class TaskResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    result: str | None = None
    failure: FailureResult | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

