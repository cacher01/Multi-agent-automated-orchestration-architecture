from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.agents.schemas import AgentInvocation
from app.models.event import TaskEvent
from app.models.memory import CandidateMemory
from app.models.plan import ExecutionPlan
from app.models.task import Task
from app.tools.base import ToolInvocationResult


def _to_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


class SQLiteStorage:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite:///"):
            database_url = database_url.removeprefix("sqlite:///")
        self.database_path = database_url
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self.database_path == ":memory:":
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(self.database_path)
                self._memory_conn.row_factory = sqlite3.Row
            return self._memory_conn
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    user_input TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_mode TEXT,
                    result TEXT,
                    error TEXT,
                    persist_logs INTEGER NOT NULL,
                    persist_intermediate_results INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_plans (
                    plan_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS agent_invocations (
                    invocation_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    input TEXT,
                    output TEXT,
                    status TEXT NOT NULL,
                    token_usage INTEGER,
                    error TEXT,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS tool_invocations (
                    invocation_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    input TEXT,
                    permission_status TEXT NOT NULL,
                    execution_status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    source_task_id TEXT,
                    content TEXT NOT NULL,
                    reason TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    deleted_at TEXT
                );
                """
            )

    def create_task(self, task: Task) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, user_input, status, execution_mode, result, error,
                    persist_logs, persist_intermediate_results, retry_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.user_input,
                    task.status.value,
                    task.execution_mode,
                    task.result,
                    task.error,
                    int(task.persist_logs),
                    int(task.persist_intermediate_results),
                    task.retry_count,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )

    def get_task(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return Task(
            task_id=row["task_id"],
            user_input=row["user_input"],
            status=row["status"],
            execution_mode=row["execution_mode"],
            result=row["result"],
            error=row["error"],
            persist_logs=bool(row["persist_logs"]),
            persist_intermediate_results=bool(row["persist_intermediate_results"]),
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_task(self, task: Task) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET user_input = ?, status = ?, execution_mode = ?, result = ?, error = ?,
                    persist_logs = ?, persist_intermediate_results = ?, retry_count = ?,
                    created_at = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    task.user_input,
                    task.status.value,
                    task.execution_mode,
                    task.result,
                    task.error,
                    int(task.persist_logs),
                    int(task.persist_intermediate_results),
                    task.retry_count,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    task.task_id,
                ),
            )

    def append_event(self, event: TaskEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_events (event_id, task_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.task_id,
                    event.event_type,
                    _to_json(event.payload),
                    event.created_at.isoformat(),
                ),
            )

    def get_events(self, task_id: str) -> list[TaskEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [
            TaskEvent(
                event_id=row["event_id"],
                task_id=row["task_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_plan(self, plan: ExecutionPlan) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_plans
                    (plan_id, task_id, execution_mode, payload)
                VALUES (?, ?, ?, ?)
                """,
                (plan.plan_id, plan.task_id, plan.execution_mode.value, _to_json(plan)),
            )

    def get_plan(self, task_id: str) -> ExecutionPlan | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM execution_plans WHERE task_id = ? ORDER BY created_at DESC",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return ExecutionPlan.model_validate(json.loads(row["payload"]))

    def save_memory(self, memory: CandidateMemory) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memories (
                    memory_id, source_task_id, content, reason, status,
                    created_at, confirmed_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.memory_id,
                    memory.source_task_id,
                    memory.content,
                    memory.reason,
                    memory.status.value,
                    memory.created_at.isoformat(),
                    memory.confirmed_at.isoformat() if memory.confirmed_at else None,
                    memory.deleted_at.isoformat() if memory.deleted_at else None,
                ),
            )

    def get_memories(self) -> list[CandidateMemory]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM memories ORDER BY created_at ASC").fetchall()
        return [self._memory_from_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> CandidateMemory | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?", (memory_id,)).fetchone()
        return None if row is None else self._memory_from_row(row)

    def update_memory(self, memory: CandidateMemory) -> None:
        self.save_memory(memory)

    def save_tool_invocation(self, invocation: ToolInvocationResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_invocations (
                    invocation_id, task_id, tool_name, requested_by, input,
                    permission_status, execution_status, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invocation.invocation_id,
                    invocation.task_id or "",
                    invocation.tool_name,
                    invocation.requested_by,
                    _to_json(invocation.input),
                    invocation.permission_status,
                    invocation.execution_status,
                    invocation.message,
                    invocation.created_at.isoformat(),
                ),
            )

    def save_agent_invocation(self, invocation: AgentInvocation) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_invocations (
                    invocation_id, task_id, agent_id, capability, input, output,
                    status, token_usage, error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invocation.invocation_id,
                    invocation.task_id,
                    invocation.agent_id,
                    invocation.capability,
                    _to_json(invocation.input),
                    invocation.output,
                    invocation.status,
                    invocation.token_usage,
                    invocation.error,
                    invocation.started_at.isoformat(),
                    invocation.finished_at.isoformat() if invocation.finished_at else None,
                ),
            )

    @staticmethod
    def _memory_from_row(row: sqlite3.Row) -> CandidateMemory:
        return CandidateMemory(
            memory_id=row["memory_id"],
            source_task_id=row["source_task_id"],
            content=row["content"],
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            deleted_at=row["deleted_at"],
        )
