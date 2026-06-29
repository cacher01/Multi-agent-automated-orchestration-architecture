from contextvars import ContextVar, Token
from typing import Any, Callable

from app.db.repositories import Repository
from app.llm.client import LLMClient, LLMResponse


class TaskAwareLLMClient:
    def __init__(
        self,
        delegate: LLMClient,
        repository: Repository,
        checkpoint: Callable[[str], None],
    ) -> None:
        self.delegate = delegate
        self.repository = repository
        self.checkpoint = checkpoint
        self._task_id: ContextVar[str | None] = ContextVar(
            "llm_task_id", default=None
        )

    def bind_task(self, task_id: str) -> Token:
        return self._task_id.set(task_id)

    def reset_task(self, token: Token) -> None:
        self._task_id.reset(token)

    async def chat(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> LLMResponse:
        task_id = self._task_id.get()
        if task_id is not None:
            self.checkpoint(task_id)
        response = await self.delegate.chat(messages, **kwargs)
        if task_id is not None:
            self.repository.increment_task_tokens(task_id, response.token_estimate)
            self.checkpoint(task_id)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)
