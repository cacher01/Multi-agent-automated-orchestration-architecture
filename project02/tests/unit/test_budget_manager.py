from datetime import datetime, timedelta, timezone

import pytest

from app.budget.manager import BudgetError, BudgetManager
from app.config.settings import Settings


class FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object] | None]] = []

    def log_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.events.append((task_id, event_type, payload))


def make_manager() -> BudgetManager:
    return BudgetManager(
        Settings(
            deepseek_api_key=None,
            deepseek_base_url=None,
            deepseek_model=None,
            task_token_budget=10,
            agent_token_budget=5,
            max_llm_calls_per_task=2,
            max_child_agents_per_task=1,
            task_timeout_seconds=1,
            max_retry_attempts=1,
        )
    )


def test_budget_limits() -> None:
    manager = make_manager()
    manager.check_llm_call("t1", estimated_tokens=4)
    manager.check_llm_call("t1", estimated_tokens=4)
    with pytest.raises(BudgetError, match="Maximum LLM calls"):
        manager.check_llm_call("t1")


def test_agent_token_limit() -> None:
    with pytest.raises(BudgetError, match="Agent token budget"):
        make_manager().check_llm_call("t1", estimated_tokens=6)


def test_child_agent_and_retry_limits() -> None:
    manager = make_manager()
    manager.check_child_agent("t1")
    with pytest.raises(BudgetError, match="Maximum child agents"):
        manager.check_child_agent("t1")
    manager.check_retry("t1")
    with pytest.raises(BudgetError, match="Maximum retry"):
        manager.check_retry("t1")


def test_timeout_limit() -> None:
    manager = make_manager()
    state = manager.get_state("t1")
    state.started_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    with pytest.raises(BudgetError, match="timeout"):
        manager.check_timeout("t1")


def test_budget_checks_are_logged() -> None:
    logger = FakeLogger()
    manager = BudgetManager(
        Settings(deepseek_api_key=None, deepseek_base_url=None, deepseek_model=None),
        logger=logger,
    )
    manager.check_llm_call("t1", estimated_tokens=1)
    assert logger.events[0][1] == "budget_checked"
