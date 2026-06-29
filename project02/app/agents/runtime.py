from __future__ import annotations

import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.agents.registry import AgentRegistry
from app.agents.schemas import AgentInvocation, AgentInvocationRequest
from app.llm.base import LLMMessage, LLMProvider


class AgentInvocationStore(Protocol):
    def save_agent_invocation(self, invocation: AgentInvocation) -> None:
        ...


class AgentEventLogger(Protocol):
    def log_event(self, task_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        ...


@dataclass
class AgentRuntime:
    llm_provider: LLMProvider
    registry: AgentRegistry = field(default_factory=AgentRegistry)
    store: AgentInvocationStore | None = None
    logger: AgentEventLogger | None = None
    timeout_seconds: float = 60.0

    def invoke(self, request: AgentInvocationRequest) -> AgentInvocation:
        definition = self.registry.get(request.capability)
        agent_id = request.agent_id or f"{request.capability}:{request.task_id}"
        agent_input = self._build_agent_input(request, definition.description)
        invocation = AgentInvocation(
            task_id=request.task_id,
            agent_id=agent_id,
            capability=request.capability,
            input=agent_input,
            status="running",
        )
        try:
            response = self._generate_with_timeout(
                [
                    LLMMessage(role="system", content=definition.description),
                    LLMMessage(role="user", content=self._render_prompt(agent_input)),
                ],
                self._model_options_for(request.capability, request.model_options),
            )
            invocation.output = response.content
            invocation.token_usage = response.total_tokens
            invocation.status = "succeeded"
        except Exception as exc:
            fallback = self._fallback_output(agent_input, str(exc))
            if fallback is not None:
                invocation.output = fallback
                invocation.error = str(exc)
                invocation.status = "succeeded"
            else:
                invocation.error = str(exc)
                invocation.status = "failed"
        invocation.finished_at = datetime.now(timezone.utc)
        self._persist(invocation)
        self._log(invocation)
        return invocation

    def _generate_with_timeout(
        self,
        messages: list[LLMMessage],
        model_options: Mapping[str, Any] | None,
    ) -> Any:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.llm_provider.generate, messages, model_options)
        try:
            return future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError as exc:
            if future.done():
                raise
            future.cancel()
            raise TimeoutError(f"Agent LLM call exceeded {self.timeout_seconds:.0f} seconds.") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _build_agent_input(self, request: AgentInvocationRequest, description: str) -> dict[str, Any]:
        return {
            "subtask": request.subtask,
            "shared_context": request.shared_context.to_prompt_data(),
            "capability": request.capability,
            "capability_description": description,
        }

    def _model_options_for(self, capability: str, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        max_tokens_by_capability = {
            "researcher": 1200,
            "planner": 900,
            "analyst": 1200,
            "writer": 1800,
            "reviewer": 700,
            "explorer": 1000,
            "tool_user": 900,
        }
        options: dict[str, Any] = {
            "temperature": 0.2,
            "max_tokens": max_tokens_by_capability.get(capability, 1000),
        }
        options.update(dict(overrides or {}))
        return options

    def _render_prompt(self, agent_input: Mapping[str, Any]) -> str:
        compact_context = self._compact_value(agent_input["shared_context"], max_chars=7000)
        return (
            f"Subtask:\n{agent_input['subtask']}\n\n"
            f"Shared context:\n{compact_context}\n\n"
            f"Capability:\n{agent_input['capability_description']}"
        )

    def _fallback_output(self, agent_input: Mapping[str, Any], error: str) -> str | None:
        context = agent_input.get("shared_context")
        if not isinstance(context, Mapping):
            return None
        artifacts = context.get("upstream_artifacts")
        if not artifacts:
            return None
        compact = self._render_fallback_artifacts(artifacts)
        return (
            "The model response was unavailable in time, so this step can only summarize available upstream context.\n\n"
            f"Subtask: {agent_input.get('subtask')}\n\n"
            f"Available context:\n{compact}"
        )

    def _render_fallback_artifacts(self, artifacts: Any) -> str:
        lines: list[str] = []
        if isinstance(artifacts, Mapping):
            for value in artifacts.values():
                self._append_fallback_lines(lines, value)
        else:
            self._append_fallback_lines(lines, artifacts)
        return "\n".join(lines[:12]) if lines else "No task-facing context was available."

    def _append_fallback_lines(self, lines: list[str], value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                self._append_fallback_lines(lines, item)
            return
        if isinstance(value, Mapping):
            output = value.get("output")
            if output is not None and output is not value:
                self._append_fallback_lines(lines, output)
                return
            title = value.get("title")
            snippet = value.get("snippet") or value.get("message")
            url = value.get("url")
            if title or snippet:
                line = f"- {title or snippet}"
                if title and snippet:
                    line += f": {snippet}"
                if url:
                    line += f" ({url})"
                lines.append(line)
                return
            results = value.get("results")
            if isinstance(results, list):
                self._append_fallback_lines(lines, results)
                return
            return
        if value not in (None, ""):
            text = str(value)
            lines.append(f"- {text[:500]}")

    def _compact_value(self, value: Any, max_chars: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[truncated]"

    def _persist(self, invocation: AgentInvocation) -> None:
        if self.store is not None:
            self.store.save_agent_invocation(invocation)

    def _log(self, invocation: AgentInvocation) -> None:
        if self.logger is not None:
            self.logger.log_event(invocation.task_id, "agent_invoked", invocation.to_record())
