from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from app.llm.base import (
    FakeLLMProvider,
    LLMConfigurationError,
    LLMMessage,
    LLMProviderError,
    LLMTimeoutError,
)
from app.llm.deepseek import DeepSeekProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_fake_provider_records_calls() -> None:
    provider = FakeLLMProvider(responses=["hello"])

    response = provider.generate([LLMMessage(role="user", content="Hi")])

    assert response.content == "hello"
    assert provider.calls[0]["messages"] == [{"role": "user", "content": "Hi"}]


def test_deepseek_missing_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    with pytest.raises(LLMConfigurationError, match="DEEPSEEK_API_KEY"):
        DeepSeekProvider()


def test_deepseek_generate_parses_mocked_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
    captured: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> FakeHTTPResponse:
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeHTTPResponse(
            {
                "model": "deepseek-test",
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    provider = DeepSeekProvider(timeout_seconds=7)
    response = provider.generate([{"role": "user", "content": "question"}])

    assert response.content == "answer"
    assert response.total_tokens == 5
    assert response.provider == "deepseek"
    assert captured == {"authorization": "Bearer secret-value", "timeout": 7}


def test_deepseek_timeout_is_structured(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        raise urllib.error.URLError(TimeoutError("slow"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LLMTimeoutError):
        DeepSeekProvider().generate([{"role": "user", "content": "question"}])


def test_deepseek_invalid_shape_is_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-test")
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeHTTPResponse({"choices": []}))

    with pytest.raises(LLMProviderError, match="missing message content"):
        DeepSeekProvider().generate([{"role": "user", "content": "question"}])
