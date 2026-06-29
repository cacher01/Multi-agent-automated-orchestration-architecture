from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AgentPrivateContext:
    agent_id: str
    subtask_input: str
    output: str | None = None
    tool_results: list[Mapping[str, Any]] = field(default_factory=list)
    temporary_memory: dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedContext:
    task_summary: str
    plan_summary: str | None = None
    constraints: list[str] = field(default_factory=list)
    upstream_artifacts: dict[str, Any] = field(default_factory=dict)
    handoff_summary: str | None = None
    allowed_information: dict[str, Any] = field(default_factory=dict)

    def to_prompt_data(self) -> dict[str, Any]:
        return {
            "task_summary": self.task_summary,
            "plan_summary": self.plan_summary,
            "constraints": list(self.constraints),
            "upstream_artifacts": dict(self.upstream_artifacts),
            "handoff_summary": self.handoff_summary,
            "allowed_information": dict(self.allowed_information),
        }


@dataclass
class TaskContext:
    task_id: str
    original_input: str
    user_constraints: list[str] = field(default_factory=list)
    execution_plan: Mapping[str, Any] | None = None
    global_state: dict[str, Any] = field(default_factory=dict)
    shared_results: dict[str, Any] = field(default_factory=dict)
    decision_records: list[Mapping[str, Any]] = field(default_factory=list)
    agent_private_contexts: dict[str, AgentPrivateContext] = field(default_factory=dict)
    intermediate_results: list[Mapping[str, Any]] = field(default_factory=list)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    tool_invocations: list[Mapping[str, Any]] = field(default_factory=list)
    model_invocations: list[Mapping[str, Any]] = field(default_factory=list)
    errors: list[Mapping[str, Any]] = field(default_factory=list)
    final_result: Any | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ContextManager:
    def __init__(self) -> None:
        self._contexts: dict[str, TaskContext] = {}

    def create_task_context(
        self,
        task_id: str,
        original_input: str,
        user_constraints: list[str] | None = None,
    ) -> TaskContext:
        context = TaskContext(
            task_id=task_id,
            original_input=original_input,
            user_constraints=list(user_constraints or []),
        )
        self._contexts[task_id] = context
        return context

    def get_task_context(self, task_id: str) -> TaskContext:
        return self._contexts[task_id]

    def create_private_context(
        self,
        task_id: str,
        agent_id: str,
        subtask_input: str,
    ) -> AgentPrivateContext:
        context = self.get_task_context(task_id)
        private = AgentPrivateContext(agent_id=agent_id, subtask_input=subtask_input)
        context.agent_private_contexts[agent_id] = private
        self._touch(context)
        return private

    def get_private_context(self, task_id: str, requester_agent_id: str, target_agent_id: str) -> AgentPrivateContext:
        if requester_agent_id != target_agent_id:
            raise PermissionError("Agent private context is isolated")
        return self.get_task_context(task_id).agent_private_contexts[target_agent_id]

    def build_shared_context(
        self,
        task_id: str,
        *,
        task_summary: str | None = None,
        plan_summary: str | None = None,
        include_result_keys: list[str] | None = None,
        handoff_summary: str | None = None,
        allowed_information: Mapping[str, Any] | None = None,
    ) -> SharedContext:
        context = self.get_task_context(task_id)
        keys = include_result_keys or []
        upstream_artifacts = {key: context.shared_results[key] for key in keys if key in context.shared_results}
        return SharedContext(
            task_summary=task_summary or context.original_input,
            plan_summary=plan_summary,
            constraints=list(context.user_constraints),
            upstream_artifacts=upstream_artifacts,
            handoff_summary=handoff_summary,
            allowed_information=dict(allowed_information or {}),
        )

    def add_intermediate_result(self, task_id: str, key: str, value: Any, *, share: bool = False) -> None:
        context = self.get_task_context(task_id)
        record = {"key": key, "value": value}
        context.intermediate_results.append(record)
        if share:
            context.shared_results[key] = value
        self._touch(context)

    def record_agent_output(self, task_id: str, agent_id: str, output: Any, *, share: bool = False) -> None:
        context = self.get_task_context(task_id)
        context.agent_outputs[agent_id] = output
        if agent_id in context.agent_private_contexts:
            context.agent_private_contexts[agent_id].output = str(output)
        if share:
            context.shared_results[agent_id] = output
        self._touch(context)

    def cleanup_task_context(self, task_id: str, *, persist_intermediate_results: bool) -> TaskContext:
        context = self.get_task_context(task_id)
        context.agent_private_contexts.clear()
        context.model_invocations.clear()
        context.tool_invocations.clear()
        if not persist_intermediate_results:
            context.intermediate_results.clear()
            context.shared_results.clear()
            context.agent_outputs.clear()
        self._touch(context)
        return context

    def _touch(self, context: TaskContext) -> None:
        context.updated_at = datetime.now(timezone.utc)
