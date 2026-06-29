from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    DIRECT = "direct"
    SUPERVISOR = "supervisor"
    DAG = "dag"
    DISCUSSION = "discussion"
    HANDOFF = "handoff"


class Complexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class DecisionResult(BaseModel):
    complexity: Complexity
    execution_mode: ExecutionMode
    requires_tools: bool = False
    requires_clarification: bool = False
    required_capabilities: list[str] = Field(default_factory=list)
    reason: str = ""


class ExecutionStep(BaseModel):
    step_id: str
    description: str
    capability: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    plan_id: str
    task_id: str
    execution_mode: ExecutionMode
    steps: list[ExecutionStep] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    budget: dict[str, int] = Field(default_factory=dict)
    timeout: int | None = None

