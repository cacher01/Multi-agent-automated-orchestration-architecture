from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from app.memory.context import SharedContext


class AgentCapability(str, Enum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    TOOL_USER = "tool_user"
    WRITER = "writer"
    REVIEWER = "reviewer"
    ANALYST = "analyst"
    EXPLORER = "explorer"


BUILT_IN_CAPABILITIES: tuple[str, ...] = tuple(capability.value for capability in AgentCapability)


@dataclass(frozen=True)
class AgentDefinition:
    capability: str
    description: str


@dataclass(frozen=True)
class AgentInvocationRequest:
    task_id: str
    capability: str
    subtask: str
    shared_context: SharedContext
    agent_id: str | None = None
    model_options: Mapping[str, Any] | None = None


@dataclass
class AgentInvocation:
    task_id: str
    agent_id: str
    capability: str
    input: Mapping[str, Any]
    output: str | None = None
    status: str = "created"
    token_usage: int = 0
    error: str | None = None
    invocation_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "capability": self.capability,
            "input": dict(self.input),
            "output": self.output,
            "status": self.status,
            "token_usage": self.token_usage,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
