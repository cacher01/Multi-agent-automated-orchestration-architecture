from app.agents.schemas import AgentInvocation
from app.models.event import TaskEvent
from app.models.memory import CandidateMemory
from app.models.plan import ExecutionMode, ExecutionPlan
from app.models.task import Task, TaskStatus
from app.storage.sqlite import SQLiteStorage
from app.tools.base import ToolInvocationResult


def test_sqlite_storage_crud() -> None:
    storage = SQLiteStorage(":memory:")
    storage.init_db()
    storage.init_db()

    task = Task(task_id="t1", user_input="hello")
    storage.create_task(task)
    loaded = storage.get_task("t1")
    assert loaded is not None
    assert loaded.status == TaskStatus.CREATED

    task.status = TaskStatus.SUCCEEDED
    task.result = "done"
    storage.update_task(task)
    assert storage.get_task("t1").result == "done"  # type: ignore[union-attr]

    event = TaskEvent(event_id="e1", task_id="t1", event_type="task_created", payload={"ok": True})
    storage.append_event(event)
    assert storage.get_events("t1")[0].payload == {"ok": True}

    plan = ExecutionPlan(plan_id="p1", task_id="t1", execution_mode=ExecutionMode.DIRECT)
    storage.save_plan(plan)
    assert storage.get_plan("t1").plan_id == "p1"  # type: ignore[union-attr]

    memory = CandidateMemory(memory_id="m1", source_task_id="t1", content="preference")
    storage.save_memory(memory)
    assert storage.get_memory("m1").content == "preference"  # type: ignore[union-attr]
    assert len(storage.get_memories()) == 1

    storage.save_tool_invocation(
        ToolInvocationResult(
            tool_name="time_lookup",
            requested_by="orchestrator",
            input={"timezone": "UTC"},
            permission_status="allowed",
            execution_status="succeeded",
            message="done",
            task_id="t1",
        )
    )
    storage.save_agent_invocation(
        AgentInvocation(
            task_id="t1",
            agent_id="writer:t1",
            capability="writer",
            input={"subtask": "write"},
            output="done",
            status="succeeded",
        )
    )
