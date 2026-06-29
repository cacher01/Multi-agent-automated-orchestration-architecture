from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class LLMResponse:
    content: str
    raw_response: Mapping[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str | None = None
    provider: str | None = None
    error: str | None = None


class LLMProviderError(RuntimeError):
    pass


class LLMConfigurationError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def generate(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        model_options: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        ...


@dataclass
class FakeLLMProvider(LLMProvider):
    responses: list[LLMResponse | str] = field(default_factory=lambda: ["fake response"])
    provider_name: str = "fake"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate(
        self,
        messages: Sequence[LLMMessage | Mapping[str, str]],
        model_options: Mapping[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": [message.to_dict() if isinstance(message, LLMMessage) else dict(message) for message in messages],
                "model_options": dict(model_options or {}),
            }
        )
        response = self.responses.pop(0) if self.responses else "fake response"
        if isinstance(response, LLMResponse):
            return response
        return LLMResponse(content=response, model="fake-model", provider=self.provider_name)
