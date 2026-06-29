from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.agents.registry import AgentRegistry
from app.agents.runtime import AgentRuntime
from app.agents.schemas import BUILT_IN_CAPABILITIES, AgentInvocation, AgentInvocationRequest
from app.llm.base import FakeLLMProvider
from app.memory.context import SharedContext


class FakeAgentStore:
    def __init__(self) -> None:
        self.saved: list[AgentInvocation] = []

    def save_agent_invocation(self, invocation: AgentInvocation) -> None:
        self.saved.append(invocation)


class FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, Mapping[str, Any]]] = []

    def log_event(self, task_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        self.events.append((task_id, event_type, payload))


def test_registry_contains_builtin_capabilities() -> None:
    registry = AgentRegistry()

    assert registry.validate_builtin_coverage()
    assert set(registry.list_capabilities()) == set(BUILT_IN_CAPABILITIES)


def test_agent_runtime_invokes_llm_with_only_subtask_and_shared_context() -> None:
    llm = FakeLLMProvider(responses=["agent output"])
    store = FakeAgentStore()
    logger = FakeLogger()
    runtime = AgentRuntime(llm_provider=llm, store=store, logger=logger)
    shared = SharedContext(
        task_summary="summary",
        constraints=["constraint"],
        upstream_artifacts={"allowed": "value"},
    )

    invocation = runtime.invoke(
        AgentInvocationRequest(
            task_id="task-1",
            capability="writer",
            subtask="write final answer",
            shared_context=shared,
        )
    )

    assert invocation.status == "succeeded"
    assert invocation.output == "agent output"
    assert invocation.input == {
        "subtask": "write final answer",
        "shared_context": shared.to_prompt_data(),
        "capability": "writer",
        "capability_description": "You are a writing agent. Produce the requested artifact from upstream context, preserving user intent, constraints, and useful details.",
    }
    assert store.saved == [invocation]
    assert logger.events[0][1] == "agent_invoked"
    assert "private" not in str(llm.calls[0]["messages"]).lower()


def test_agent_runtime_records_failed_invocation() -> None:
    class BrokenProvider(FakeLLMProvider):
        def generate(self, messages: Any, model_options: Any = None) -> Any:
            raise RuntimeError("provider down")

    runtime = AgentRuntime(llm_provider=BrokenProvider())

    invocation = runtime.invoke(
        AgentInvocationRequest(
            task_id="task-1",
            capability="reviewer",
            subtask="review",
            shared_context=SharedContext(task_summary="summary"),
        )
    )

    assert invocation.status == "failed"
    assert invocation.error == "provider down"


def test_agent_runtime_falls_back_when_upstream_context_exists() -> None:
    class BrokenProvider(FakeLLMProvider):
        def generate(self, messages: Any, model_options: Any = None) -> Any:
            raise TimeoutError("slow model")

    runtime = AgentRuntime(llm_provider=BrokenProvider())

    invocation = runtime.invoke(
        AgentInvocationRequest(
            task_id="task-1",
            capability="analyst",
            subtask="analyze",
            shared_context=SharedContext(task_summary="summary", upstream_artifacts={"tool_results": [{"output": "fact"}]}),
        )
    )

    assert invocation.status == "succeeded"
    assert invocation.output is not None
    assert "model response was unavailable" in invocation.output.lower()
    assert "tool_results" not in invocation.output
    assert "invocation_id" not in invocation.output
    assert invocation.error == "slow model"
