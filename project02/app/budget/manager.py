from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.config.settings import Settings


class BudgetLogger(Protocol):
    def log_event(self, task_id: str, event_type: str, payload: dict[str, object] | None = None) -> None:
        ...


class BudgetError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class BudgetState:
    task_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    used_tokens: int = 0
    llm_calls: int = 0
    child_agents: int = 0
    retries: int = 0


class BudgetManager:
    def __init__(self, settings: Settings, logger: BudgetLogger | None = None) -> None:
        self.settings = settings
        self.logger = logger
        self._states: dict[str, BudgetState] = {}

    def get_state(self, task_id: str) -> BudgetState:
        if task_id not in self._states:
            self._states[task_id] = BudgetState(task_id=task_id)
        return self._states[task_id]

    def check_llm_call(self, task_id: str, estimated_tokens: int = 0) -> None:
        state = self.get_state(task_id)
        self._check_timeout(state)
        if state.llm_calls + 1 > self.settings.max_llm_calls_per_task:
            raise BudgetError("llm_call_limit", "Maximum LLM calls per task exceeded")
        if estimated_tokens > self.settings.agent_token_budget:
            raise BudgetError("agent_token_budget", "Agent token budget exceeded")
        if state.used_tokens + estimated_tokens > self.settings.task_token_budget:
            raise BudgetError("task_token_budget", "Task token budget exceeded")
        state.llm_calls += 1
        state.used_tokens += estimated_tokens
        self._log(
            task_id,
            {
                "check": "llm_call",
                "estimated_tokens": estimated_tokens,
                "used_tokens": state.used_tokens,
                "llm_calls": state.llm_calls,
            },
        )

    def check_child_agent(self, task_id: str) -> None:
        state = self.get_state(task_id)
        self._check_timeout(state)
        if state.child_agents + 1 > self.settings.max_child_agents_per_task:
            raise BudgetError("child_agent_limit", "Maximum child agents per task exceeded")
        state.child_agents += 1
        self._log(task_id, {"check": "child_agent", "child_agents": state.child_agents})

    def check_retry(self, task_id: str) -> None:
        state = self.get_state(task_id)
        if state.retries + 1 > self.settings.max_retry_attempts:
            raise BudgetError("retry_limit", "Maximum retry attempts exceeded")
        state.retries += 1
        self._log(task_id, {"check": "retry", "retries": state.retries})

    def check_timeout(self, task_id: str) -> None:
        self._check_timeout(self.get_state(task_id))

    def _check_timeout(self, state: BudgetState) -> None:
        elapsed = (datetime.now(timezone.utc) - state.started_at).total_seconds()
        if elapsed > self.settings.task_timeout_seconds:
            raise BudgetError("task_timeout", "Task timeout exceeded")

    def _log(self, task_id: str, payload: dict[str, object]) -> None:
        if self.logger is not None:
            self.logger.log_event(task_id, "budget_checked", payload)
