from __future__ import annotations

from collections.abc import Callable

from app.memory.context import ContextManager
from app.services.task_service import (
    ExecutionMode,
    FailureResult,
    ProcessorPreview,
    ProcessorResult,
    TaskRequest,
    TaskService,
    TaskStatus,
)
from app.storage.sqlite import SQLiteStorage


class FakeProcessor:
    def __init__(self, *, complex_task: bool = False, result: ProcessorResult | None = None) -> None:
        self.complex_task = complex_task
        self.result = result or ProcessorResult(
            status=TaskStatus.SUCCEEDED,
            execution_mode=ExecutionMode.DIRECT.value,
            result="fake answer",
        )
        self.run_calls: list[tuple[str, str]] = []

    def preview(self, user_input: str) -> ProcessorPreview:
        return ProcessorPreview(
            is_complex=self.complex_task,
            execution_mode=ExecutionMode.DAG.value if self.complex_task else ExecutionMode.DIRECT.value,
        )

    def run(self, task_id: str, user_input: str) -> ProcessorResult:
        self.run_calls.append((task_id, user_input))
        return self.result


class ContextAwareProcessor(FakeProcessor):
    def __init__(self, *, complex_task: bool = False, result: ProcessorResult | None = None) -> None:
        super().__init__(complex_task=complex_task, result=result)
        self.context_calls: list[tuple[str, str, str | None]] = []

    def run_with_context(self, task_id: str, user_input: str, session_context: str | None = None) -> ProcessorResult:
        self.context_calls.append((task_id, user_input, session_context))
        return self.result


def test_simple_task_runs_synchronously() -> None:
    processor = FakeProcessor()
    service = TaskService(processor)

    response = service.submit_task(TaskRequest(input="hello"))

    assert response["status"] == "succeeded"
    assert response["result"] == "fake answer"
    assert len(processor.run_calls) == 1
    assert service.get_result(response["task_id"])["result"] == "fake answer"
    assert response["session_id"].startswith("session_")


def test_complex_task_uses_background_callback() -> None:
    processor = FakeProcessor(complex_task=True)
    service = TaskService(processor)
    scheduled: list[tuple[Callable[[str], None], str]] = []

    def schedule(callback: Callable[[str], None], task_id: str) -> None:
        scheduled.append((callback, task_id))

    response = service.submit_task(TaskRequest(input="plan a complex thing"), schedule)

    assert response["status"] == "running"
    assert response["mode"] == "async"
    assert scheduled
    callback, task_id = scheduled[0]
    assert service.get_task(task_id)["status"] == "running"

    callback(task_id)

    assert service.get_task(task_id)["status"] == "succeeded"
    assert service.get_result(task_id)["result"] == "fake answer"


def test_failure_result_is_persisted() -> None:
    service = TaskService(
        FakeProcessor(
            result=ProcessorResult(
                status=TaskStatus.FAILED,
                execution_mode=ExecutionMode.DIRECT.value,
                error="review failed",
                failure=FailureResult(
                    reason="review_failed",
                    error_message="review failed",
                    completed_parts=["draft"],
                    incomplete_parts=["review"],
                    retry_count=3,
                ),
            )
        )
    )

    response = service.submit_task(TaskRequest(input="fail"))
    result = service.get_result(response["task_id"])

    assert response["status"] == "failed"
    assert result["failure"]["retry_count"] == 3
    assert result["failure"]["incomplete_parts"] == ["review"]


def test_candidate_memory_requires_explicit_approval() -> None:
    service = TaskService(
        FakeProcessor(
            result=ProcessorResult(
                status=TaskStatus.SUCCEEDED,
                execution_mode=ExecutionMode.DIRECT.value,
                result="done",
                candidate_memories=[
                    {
                        "memory_id": "mem_test",
                        "source_task_id": "ignored",
                        "content": "Prefer concise answers.",
                        "reason": "User preference",
                        "status": "pending",
                    }
                ],
            )
        )
    )

    service.submit_task(TaskRequest(input="remember this"))

    memories = service.list_memories()["memories"]
    assert memories[0]["status"] == "pending"
    assert service.approve_memory("mem_test")["status"] == "approved"
    assert service.reject_memory("mem_test")["status"] == "rejected"
    assert service.delete_memory("mem_test")["status"] == "deleted"


def test_task_service_persists_task_logs_and_memories_to_sqlite() -> None:
    storage = SQLiteStorage(":memory:")
    service = TaskService(
        FakeProcessor(
            result=ProcessorResult(
                status=TaskStatus.SUCCEEDED,
                execution_mode=ExecutionMode.DIRECT.value,
                result="done",
                candidate_memories=[
                    {
                        "memory_id": "mem_sqlite",
                        "content": "Persist this preference.",
                        "reason": "Test memory",
                    }
                ],
            )
        ),
        storage=storage,
    )

    response = service.submit_task(TaskRequest(input="persist", persist_logs=True))
    task_id = response["task_id"]

    persisted_task = storage.get_task(task_id)
    assert persisted_task is not None
    assert persisted_task.result == "done"
    assert {event.event_type for event in storage.get_events(task_id)} >= {
        "task_created",
        "decision_made",
        "task_succeeded",
    }
    assert storage.get_memory("mem_sqlite") is not None


def test_session_context_is_passed_to_follow_up_task() -> None:
    processor = FakeProcessor()
    service = TaskService(processor)
    first = service.submit_task(TaskRequest(input="summarize company A", session_id="session-test"))

    second = service.submit_task(TaskRequest(input="continue from last task", session_id=first["session_id"]))

    assert second["session_id"] == "session-test"
    assert "Session context from previous tasks" in processor.run_calls[-1][1]
    assert "summarize company A" in processor.run_calls[-1][1]


def test_context_aware_processor_keeps_current_input_clean_and_context_separate() -> None:
    processor = ContextAwareProcessor()
    service = TaskService(processor)
    first = service.submit_task(TaskRequest(input="summarize company A", session_id="session-test"))

    service.submit_task(TaskRequest(input="what about its risks?", session_id=first["session_id"]))

    assert processor.context_calls[-1][1] == "what about its risks?"
    assert processor.context_calls[-1][2] is not None
    assert "summarize company A" in processor.context_calls[-1][2]


def test_simple_direct_task_does_not_record_logs_by_default() -> None:
    storage = SQLiteStorage(":memory:")
    service = TaskService(FakeProcessor(), storage=storage)

    response = service.submit_task(TaskRequest(input="hello"))

    assert service.get_logs(response["task_id"])["events"] == []


def test_task_service_initializes_task_context() -> None:
    context_manager = ContextManager()
    service = TaskService(FakeProcessor(), context_manager=context_manager)

    response = service.submit_task(TaskRequest(input="hello"))
    context = context_manager.get_task_context(response["task_id"])

    assert context.original_input == "hello"
