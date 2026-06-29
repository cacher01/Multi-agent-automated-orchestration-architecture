from __future__ import annotations

from app.memory.context import ContextManager
from app.memory.preferences import CandidateMemory, MemoryStatus, UserPreferenceStore


class FakeMemoryStore:
    def __init__(self) -> None:
        self.saved: list[CandidateMemory] = []
        self.updated: list[CandidateMemory] = []

    def save_memory(self, memory: CandidateMemory) -> None:
        self.saved.append(memory)

    def update_memory(self, memory: CandidateMemory) -> None:
        self.updated.append(memory)


def test_context_private_data_isolated_and_shared_context_is_explicit() -> None:
    manager = ContextManager()
    manager.create_task_context("task-1", "original task", ["keep concise"])
    manager.create_private_context("task-1", "agent-a", "private subtask")
    manager.add_intermediate_result("task-1", "artifact-a", {"value": 1}, share=True)
    manager.add_intermediate_result("task-1", "artifact-b", {"value": 2}, share=False)

    private = manager.get_private_context("task-1", "agent-a", "agent-a")
    shared = manager.build_shared_context("task-1", include_result_keys=["artifact-a", "artifact-b"])

    assert private.subtask_input == "private subtask"
    assert shared.to_prompt_data()["upstream_artifacts"] == {"artifact-a": {"value": 1}}
    assert shared.to_prompt_data()["constraints"] == ["keep concise"]


def test_cross_agent_private_context_access_rejected() -> None:
    manager = ContextManager()
    manager.create_task_context("task-1", "original task")
    manager.create_private_context("task-1", "agent-a", "private subtask")

    try:
        manager.get_private_context("task-1", "agent-b", "agent-a")
    except PermissionError as exc:
        assert "isolated" in str(exc)
    else:
        raise AssertionError("cross-agent private context access was allowed")


def test_cleanup_respects_persist_intermediate_results() -> None:
    manager = ContextManager()
    manager.create_task_context("task-1", "original task")
    manager.create_private_context("task-1", "agent-a", "private subtask")
    manager.record_agent_output("task-1", "agent-a", "output", share=True)

    cleaned = manager.cleanup_task_context("task-1", persist_intermediate_results=False)

    assert cleaned.agent_private_contexts == {}
    assert cleaned.shared_results == {}
    assert cleaned.agent_outputs == {}


def test_memory_candidate_requires_explicit_approval_and_can_be_deleted() -> None:
    backend = FakeMemoryStore()
    store = UserPreferenceStore(backend)

    memory = store.create_candidate(content="Use terse output.", reason="User preference", source_task_id="task-1")
    assert memory.status == MemoryStatus.PENDING.value
    assert backend.saved == [memory]

    approved = store.approve(memory.memory_id)
    assert approved.status == MemoryStatus.APPROVED.value
    assert approved.confirmed_at is not None

    deleted = store.delete(memory.memory_id)
    assert deleted.status == MemoryStatus.DELETED.value
    assert store.list_memories() == []
    assert store.list_memories(include_deleted=True) == [memory]
