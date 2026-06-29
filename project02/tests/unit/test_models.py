import pytest
from pydantic import ValidationError

from app.models.memory import CandidateMemory, MemoryStatus
from app.models.plan import Complexity, DecisionResult, ExecutionMode, ExecutionPlan, ExecutionStep
from app.models.task import FailureResult, Task, TaskStatus


def test_core_models_serialize() -> None:
    decision = DecisionResult(
        complexity=Complexity.SIMPLE,
        execution_mode=ExecutionMode.DIRECT,
        reason="short direct task",
    )
    plan = ExecutionPlan(
        plan_id="p1",
        task_id="t1",
        execution_mode=ExecutionMode.DIRECT,
        steps=[ExecutionStep(step_id="s1", description="answer")],
    )
    task = Task(task_id="t1", user_input="hello")
    failure = FailureResult(task_id="t1", reason="failed", error_message="error")
    memory = CandidateMemory(memory_id="m1", content="Use concise output")

    assert decision.model_dump()["execution_mode"] == ExecutionMode.DIRECT
    assert plan.steps[0].step_id == "s1"
    assert task.status == TaskStatus.CREATED
    assert failure.retry_count == 0
    assert memory.status == MemoryStatus.PENDING


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Task(task_id="t1", user_input="hello", status="not-a-status")  # type: ignore[arg-type]


def test_invalid_execution_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutionPlan(plan_id="p1", task_id="t1", execution_mode="bad")  # type: ignore[arg-type]
